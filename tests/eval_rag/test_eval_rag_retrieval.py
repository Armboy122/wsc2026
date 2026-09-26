"""Retrieval metric math and an offline run against the real corpus."""

from __future__ import annotations

from app.knowledge.index import KnowledgeIndex
from evaluation.rag.dataset import PARAPHRASE, EvalQuestion, select_questions
from evaluation.rag.retrieval_eval import (
    DEFAULT_KS,
    RetrievalRecord,
    estimate_tokens,
    estimate_tokens_from_chars,
    run_retrieval,
    summarize_retrieval,
)


def _record(
    question_id: str,
    source_id: str,
    qa_ids: tuple[str, ...],
    chunk_ids: tuple[str, ...] = (),
    latency_ms: float = 1.0,
    returned_tokens: int = 100,
) -> RetrievalRecord:
    return RetrievalRecord(
        question_id=question_id,
        source_id=source_id,
        kind=PARAPHRASE,
        question="q",
        qa_source_ids=qa_ids,
        chunk_source_ids=chunk_ids,
        latency_ms=latency_ms,
        returned_chars=returned_tokens * 2,
        returned_tokens=returned_tokens,
    )


def test_estimate_tokens_is_the_documented_character_estimate() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("ab") == 1
    assert estimate_tokens("abc") == 2
    assert estimate_tokens_from_chars(0) == 0
    assert estimate_tokens_from_chars(8000) == 4000


def test_metric_math_counts_each_hit_slot() -> None:
    records = (
        # gold Q&A first -> qa_hit@1, qa_hit@2, hit@1
        _record("a", "gold-a", ("gold-a", "other"), latency_ms=2.0),
        # gold Q&A second -> qa_hit@2 (not @1), hit@2 (not @1)
        _record("b", "gold-b", ("other", "gold-b"), latency_ms=4.0),
        # gold Q&A nowhere -> no qa hit; gold chunk at rank 2 -> hit@2 and chunk_hit@2
        _record("c", "gold-c", ("other",), ("chunk-x", "gold-c"), latency_ms=6.0),
        # total miss
        _record("d", "gold-d", ("other",), ("chunk-x",), latency_ms=8.0),
    )
    metrics = summarize_retrieval(records, ks=DEFAULT_KS)

    assert metrics.total == 4
    assert metrics.qa_hit_at_1 == 1
    assert metrics.qa_hit_at_2 == 2
    assert metrics.hit_at[1] == 1
    assert metrics.hit_at[2] == 2
    assert metrics.hit_at[5] == 3
    assert metrics.chunk_hit_at[1] == 0
    assert metrics.chunk_hit_at[2] == 1
    assert metrics.chunk_hit_at[5] == 1
    assert metrics.mean_latency_ms == 5.0
    assert metrics.median_returned_tokens == 100


def test_empty_records_are_safe() -> None:
    metrics = summarize_retrieval(())
    assert metrics.total == 0
    assert metrics.qa_hit_at_1 == 0
    assert metrics.hit_at == {1: 0, 2: 0, 5: 0}
    assert metrics.mean_latency_ms == 0.0
    assert metrics.median_returned_tokens == 0


def test_fake_embedder_retrieval_run_is_consistent(
    dataset: tuple[EvalQuestion, ...], holdout_index: KnowledgeIndex
) -> None:
    questions = select_questions(dataset, PARAPHRASE)
    records, metrics = run_retrieval(holdout_index, questions, ks=DEFAULT_KS)

    assert metrics.total == 35
    assert len(records) == 35
    # Every metric is a count of questions, so it can never exceed the total or its floor.
    assert 0 <= metrics.qa_hit_at_1 <= metrics.qa_hit_at_2 <= metrics.total
    assert metrics.qa_hit_at_1 >= 1
    assert metrics.median_returned_tokens > 0
    assert metrics.mean_latency_ms >= 0.0
    for record in records:
        assert record.qa_source_ids, record.question_id
        assert record.returned_tokens > 0
        assert record.question_id.startswith(record.source_id)
