"""Deterministic hybrid knowledge search over approved Markdown.

Build one :class:`KnowledgeIndex` from a :class:`~app.knowledge.catalog.KnowledgeCatalog`
(the catalog is the only allowlist) and call :meth:`KnowledgeIndex.search`. Approved Q&A
files form a separate lane that always ranks above document chunks; document chunks are
scored with BM25 + dense cosine fused by RRF.
"""

from __future__ import annotations

import posixpath
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from app.knowledge.aliases import KnowledgeAliasRule, load_alias_rules
from app.knowledge.catalog import KnowledgeCatalog, KnowledgeDocument
from app.knowledge.index.aliases_expand import expand_query
from app.knowledge.index.bm25 import Bm25Ranker
from app.knowledge.index.chunker import chunk_markdown, parse_qa_unit, qa_index_text
from app.knowledge.index.embedder import Embedder, FakeEmbedder
from app.knowledge.index.fusion import (
    RRF_K,
    as_python_float,
    order_by_score,
    ranks_from_scores,
    rrf,
)
from app.knowledge.index.models import (
    Chunk,
    ChunkHit,
    InvalidQueryError,
    QaHit,
    QaUnit,
    SearchResult,
)
from app.knowledge.index.tokenize import tokenize

DEFAULT_MAX_QA = 2
DEFAULT_MAX_CHUNKS = 5
# ~4K tokens of Thai context in a Live session, expressed as a fixed character budget.
DEFAULT_MAX_TOTAL_CHARS = 8_000
MAX_QUERY_CHARS = 1_000
QA_DIRNAME = "qa"
QA_FILE_PREFIX = "qa_"


class KnowledgeIndex:
    """Immutable in-memory index over one approved source root."""

    def __init__(
        self,
        catalog: KnowledgeCatalog,
        *,
        embedder: Embedder | None = None,
        alias_root: Path | str | None = None,
        include_qa_paraphrases: bool = True,
        max_qa: int = DEFAULT_MAX_QA,
        max_chunks: int = DEFAULT_MAX_CHUNKS,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        rrf_k: int = RRF_K,
    ) -> None:
        if max_qa < 0 or max_chunks < 0:
            raise ValueError("max_qa and max_chunks must not be negative")
        if max_total_chars < 1:
            raise ValueError("max_total_chars must be at least 1")

        self._catalog = catalog
        self._embedder: Embedder = embedder if embedder is not None else FakeEmbedder()
        self._max_qa = max_qa
        self._max_chunks = max_chunks
        self._max_total_chars = max_total_chars
        self._rrf_k = rrf_k
        self._include_qa_paraphrases = include_qa_paraphrases
        self._alias_rules: tuple[KnowledgeAliasRule, ...] = load_alias_rules(
            _alias_root(catalog, alias_root),
            {document.source_id for document in catalog.documents},
        )

        chunks, qa_units = _load_corpus(catalog)
        self._chunks: tuple[Chunk, ...] = tuple(chunks)
        self._qa_units: tuple[QaUnit, ...] = tuple(qa_units)

        chunk_texts = [chunk.index_text for chunk in self._chunks]
        qa_texts = [
            qa_index_text(unit, include_paraphrases=include_qa_paraphrases)
            for unit in self._qa_units
        ]
        self._chunk_bm25 = Bm25Ranker([tokenize(text) for text in chunk_texts])
        self._qa_bm25 = Bm25Ranker([tokenize(text) for text in qa_texts])
        self._chunk_vectors = self._embedder.embed_documents(chunk_texts)
        self._qa_vectors = self._embedder.embed_documents(qa_texts)

    @property
    def catalog(self) -> KnowledgeCatalog:
        return self._catalog

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    @property
    def qa_units(self) -> tuple[QaUnit, ...]:
        return self._qa_units

    def search(self, query: str) -> SearchResult:
        """Return top approved Q&A (≤ ``max_qa``) then chunks (≤ ``max_chunks``)."""
        validated = self._validate_query(query)
        expansion = expand_query(validated, self._alias_rules)
        scoring_text = " ".join((validated, *expansion)) if expansion else validated
        query_tokens = tokenize(scoring_text)
        query_vector = self._embedder.embed_query(scoring_text)

        qa_fused = self._fuse(self._qa_bm25, self._qa_vectors, query_tokens, query_vector)
        chunk_fused = self._fuse(
            self._chunk_bm25, self._chunk_vectors, query_tokens, query_vector
        )

        selected_qa: list[QaHit] = []
        selected_chunks: list[ChunkHit] = []
        total_chars = 0

        for index in order_by_score(qa_fused)[: self._max_qa]:
            unit = self._qa_units[index]
            if (
                selected_qa or selected_chunks
            ) and total_chars + len(unit.text) > self._max_total_chars:
                continue
            selected_qa.append(
                QaHit(
                    source_id=unit.source_id,
                    title=unit.title,
                    uri=unit.uri,
                    question=unit.question,
                    text=unit.text,
                    score=as_python_float(qa_fused[index]),
                )
            )
            total_chars += len(unit.text)

        answered_sources = {hit.source_id for hit in selected_qa}
        for index in order_by_score(chunk_fused)[: self._max_chunks]:
            chunk = self._chunks[index]
            if chunk.source_id in answered_sources:
                continue
            if (
                selected_qa or selected_chunks
            ) and total_chars + len(chunk.text) > self._max_total_chars:
                continue
            selected_chunks.append(
                ChunkHit(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    title=chunk.title,
                    uri=chunk.uri,
                    heading_path=chunk.heading_path,
                    text=chunk.text,
                    start=chunk.start,
                    end=chunk.end,
                    score=as_python_float(chunk_fused[index]),
                )
            )
            total_chars += len(chunk.text)

        sources = tuple(
            dict.fromkeys(
                [hit.source_id for hit in selected_qa]
                + [hit.source_id for hit in selected_chunks]
            )
        )
        return SearchResult(
            query=validated,
            qa=tuple(selected_qa),
            chunks=tuple(selected_chunks),
            sources=sources,
            total_chars=total_chars,
        )

    def _fuse(
        self,
        bm25: Bm25Ranker,
        vectors: np.ndarray,
        query_tokens: Sequence[str],
        query_vector: np.ndarray,
    ) -> np.ndarray:
        if len(bm25) == 0:
            return np.empty(0, dtype=np.float64)
        dense_scores = vectors @ query_vector if vectors.size else np.zeros(len(bm25))
        return rrf([bm25.ranks(query_tokens), ranks_from_scores(dense_scores)], k=self._rrf_k)

    def _validate_query(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise InvalidQueryError("query must be a non-empty string")
        validated = query.strip()
        if len(validated) > MAX_QUERY_CHARS:
            raise InvalidQueryError(f"query must be at most {MAX_QUERY_CHARS} characters")
        return validated


def _alias_root(catalog: KnowledgeCatalog, alias_root: Path | str | None) -> Path:
    if alias_root is not None:
        return Path(alias_root)
    return catalog.source_root.parent / "aliases"


def _is_qa_source(source_id: str) -> bool:
    directory, filename = posixpath.split(source_id)
    return directory == QA_DIRNAME and filename.startswith(QA_FILE_PREFIX) and filename.endswith(".md")


def _load_corpus(catalog: KnowledgeCatalog) -> tuple[list[Chunk], list[QaUnit]]:
    chunks: list[Chunk] = []
    qa_units: list[QaUnit] = []
    for document in catalog.documents:
        text = _read_document(document)
        if _is_qa_source(document.source_id):
            qa_units.append(parse_qa_unit(document.source_id, document.title, text))
        else:
            chunks.extend(chunk_markdown(document.source_id, document.title, text))
    return chunks, qa_units


def _read_document(document: KnowledgeDocument) -> str:
    try:
        return document.path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read approved knowledge document: {document.source_id}") from exc
