"""Deterministic local knowledge index: chunking, hybrid retrieval, Q&A lane.

This package never calls a generative model and never imports torch or
sentence-transformers at import time. The public entry point is :class:`KnowledgeIndex`.
"""

from app.knowledge.index.aliases_expand import expand_query
from app.knowledge.index.bm25 import Bm25Ranker
from app.knowledge.index.chunker import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    chunk_markdown,
    parse_qa_unit,
    qa_index_text,
)
from app.knowledge.index.embedder import BgeM3Embedder, Embedder, FakeEmbedder
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
from app.knowledge.index.searcher import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_QA,
    DEFAULT_MAX_TOTAL_CHARS,
    MAX_QUERY_CHARS,
    KnowledgeIndex,
)
from app.knowledge.index.tokenize import tokenize

# ``Searcher`` is the name used in the Story 4 contract for the search entry point.
Searcher = KnowledgeIndex

__all__ = [
    "DEFAULT_MAX_CHUNKS",
    "DEFAULT_MAX_QA",
    "DEFAULT_MAX_TOTAL_CHARS",
    "MAX_CHUNK_CHARS",
    "MAX_QUERY_CHARS",
    "MIN_CHUNK_CHARS",
    "RRF_K",
    "BgeM3Embedder",
    "Bm25Ranker",
    "Chunk",
    "ChunkHit",
    "Embedder",
    "FakeEmbedder",
    "InvalidQueryError",
    "KnowledgeIndex",
    "QaHit",
    "QaUnit",
    "SearchResult",
    "Searcher",
    "as_python_float",
    "chunk_markdown",
    "expand_query",
    "order_by_score",
    "parse_qa_unit",
    "qa_index_text",
    "ranks_from_scores",
    "rrf",
    "tokenize",
]
