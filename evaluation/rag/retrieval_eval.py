"""Offline retrieval evaluation over the production :mod:`app.knowledge.index`.

The evaluation imports the production ``KnowledgeCatalog`` and ``KnowledgeIndex``; it never
copies the chunker or the retriever. With ``--embedder fake`` the whole run is offline and
finishes in seconds; ``--embedder bge-m3`` loads the real self-hosted model and is never used
by pytest.

Metrics per held-out question:

- ``qa_hit@1`` / ``qa_hit@2`` — the gold Q&A source is the first / among the first two
  approved Q&A hits (the production Q&A lane).
- ``hit@k`` — the gold source appears in the combined ranked result (Q&A first, then chunks),
  the faithful port of the research harness ``hit@k`` over all retrieved chunks.
- ``chunk_hit@k`` — the gold source appears in the document-chunk lane. On this Q&A-only
  question set it is expected to be zero because approved Q&A sources are never emitted as
  chunks; it is reported as a diagnostic so a future document-question set can use it.
- ``mean_latency_ms`` — wall-clock ``KnowledgeIndex.search`` time per question.
- ``median_returned_tokens`` — estimate of the returned context size. The index has no
  tokenizer, so tokens are estimated as ``ceil(chars / 2)`` (Thai text averages roughly two
  characters per token in these documents; the production context budget is 8,000 characters
  ≈ 4,000 tokens). This is a documented estimate, not a measured tokenizer count.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import KnowledgeIndex, build_embedder
from evaluation.rag.dataset import DEFAULT_SOURCE_ROOT, EvalQuestion

DEFAULT_KS = (1, 2, 5)
CHARS_PER_TOKEN = 2
SUPPORTED_EMBEDDERS = ("fake", "bge-m3")


def estimate_tokens(text: str) -> int:
    """Documented character-based token estimate (see the module docstring)."""
    return estimate_tokens_from_chars(len(text))


def estimate_tokens_from_chars(chars: int) -> int:
    """Token estimate for a known character count (``ceil(chars / 2)``)."""
    return math.ceil(chars / CHARS_PER_TOKEN) if chars > 0 else 0


@dataclass(frozen=True)
class RetrievalRecord:
    """One question's retrieval outcome."""

    question_id: str
    source_id: str
    kind: str
    question: str
    qa_source_ids: tuple[str, ...]
    chunk_source_ids: tuple[str, ...]
    latency_ms: float
    returned_chars: int
    returned_tokens: int

    @property
    def combined_source_ids(self) -> tuple[str, ...]:
        return self.qa_source_ids + self.chunk_source_ids


@dataclass(frozen=True)
class RetrievalMetrics:
    """Aggregated retrieval metrics for one run."""

    total: int
    qa_hit_at_1: int
    qa_hit_at_2: int
    hit_at: dict[int, int]
    chunk_hit_at: dict[int, int]
    mean_latency_ms: float
    median_returned_tokens: int


def build_index(
    embedder_name: str = "fake",
    *,
    source_root: Path | str | None = None,
    include_qa_paraphrases: bool = False,
) -> KnowledgeIndex:
    """Build the production index with paraphrases held out by default."""
    root = Path(source_root) if source_root is not None else DEFAULT_SOURCE_ROOT
    catalog = KnowledgeCatalog(root)
    return KnowledgeIndex(
        catalog,
        embedder=build_embedder(embedder_name),
        include_qa_paraphrases=include_qa_paraphrases,
    )


def run_retrieval(
    index: KnowledgeIndex,
    questions: tuple[EvalQuestion, ...],
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
) -> tuple[tuple[RetrievalRecord, ...], RetrievalMetrics]:
    """Search every question and summarize the result."""
    records: list[RetrievalRecord] = []
    for question in questions:
        started = time.perf_counter()
        result = index.search(question.question)
        latency_ms = (time.perf_counter() - started) * 1000.0
        returned_chars = sum(len(hit.text) for hit in result.qa) + sum(
            len(hit.text) for hit in result.chunks
        )
        records.append(
            RetrievalRecord(
                question_id=question.id,
                source_id=question.source_id,
                kind=question.kind,
                question=question.question,
                qa_source_ids=tuple(hit.source_id for hit in result.qa),
                chunk_source_ids=tuple(hit.source_id for hit in result.chunks),
                latency_ms=round(latency_ms, 3),
                returned_chars=returned_chars,
                returned_tokens=estimate_tokens_from_chars(returned_chars),
            )
        )
    return tuple(records), summarize_retrieval(tuple(records), ks=ks)


def summarize_retrieval(
    records: tuple[RetrievalRecord, ...], *, ks: tuple[int, ...] = DEFAULT_KS
) -> RetrievalMetrics:
    """Compute hit rates, mean latency and median returned tokens."""
    total = len(records)
    qa_hit_at_1 = sum(1 for r in records if r.qa_source_ids[:1] == (r.source_id,))
    qa_hit_at_2 = sum(1 for r in records if r.source_id in r.qa_source_ids[:2])
    hit_at = {
        k: sum(1 for r in records if r.source_id in r.combined_source_ids[:k]) for k in ks
    }
    chunk_hit_at = {
        k: sum(1 for r in records if r.source_id in r.chunk_source_ids[:k]) for k in ks
    }
    mean_latency_ms = (
        round(sum(r.latency_ms for r in records) / total, 3) if total else 0.0
    )
    median_returned_tokens = (
        statistics.median_low([r.returned_tokens for r in records]) if total else 0
    )
    return RetrievalMetrics(
        total=total,
        qa_hit_at_1=qa_hit_at_1,
        qa_hit_at_2=qa_hit_at_2,
        hit_at=hit_at,
        chunk_hit_at=chunk_hit_at,
        mean_latency_ms=mean_latency_ms,
        median_returned_tokens=median_returned_tokens,
    )
