"""The stub answer + judge pipeline writes JSONL and a summary, fully offline."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.rag.answer_eval import (
    JUDGE_ERR,
    VALID_VERDICTS,
    AnswerRecord,
    build_judge_user_prompt,
    parse_verdict,
    run_answer_eval,
)
from evaluation.rag.dataset import PARAPHRASE, EvalQuestion, select_questions
from evaluation.rag.models import StubModel
from evaluation.rag.report import (
    answer_rows,
    format_answer_summary,
    write_jsonl,
    write_text,
)


def _questions(dataset: tuple[EvalQuestion, ...], limit: int = 3) -> tuple[EvalQuestion, ...]:
    return select_questions(dataset, PARAPHRASE)[:limit]


def test_parse_verdict_accepts_json_and_falls_back_to_error() -> None:
    assert parse_verdict('{"verdict":"PARTIAL","reason":"ok"}').verdict == "PARTIAL"
    assert parse_verdict('prefix {"verdict": "wrong"} suffix').verdict == "WRONG"
    assert parse_verdict("no json here").verdict == JUDGE_ERR
    assert parse_verdict('{"verdict":"MAYBE"}').verdict == JUDGE_ERR
    assert parse_verdict('{"verdict":"CORRECT"}').reason == ""


def test_judge_prompt_contains_question_gold_and_answer() -> None:
    prompt = build_judge_user_prompt("ถาม", "ทอง", "ตอบ")
    assert "ถาม" in prompt
    assert "ทอง" in prompt
    assert "ตอบ" in prompt
    assert "verdict" in prompt


def test_stub_pipeline_writes_jsonl_and_summary(
    dataset: tuple[EvalQuestion, ...], tmp_path: Path, holdout_index
) -> None:
    questions = _questions(dataset)
    records = run_answer_eval(
        questions,
        mode="hybrid_qafirst",
        answer_model=StubModel(),
        judge_model=StubModel(),
        index=holdout_index,
    )

    assert len(records) == 3
    for record in records:
        assert record.verdict in VALID_VERDICTS
        assert record.verdict == "CORRECT"
        assert record.retrieved_ids, "hybrid mode must record the returned source ids"
        assert record.context_tokens > 0
        assert record.answer.strip()

    jsonl_path = write_jsonl(tmp_path / "answers.jsonl", answer_rows(records))
    summary = format_answer_summary(
        mode="hybrid_qafirst", model="stub", question_kind=PARAPHRASE, records=records
    )
    summary_path = write_text(tmp_path / "answers.txt", summary)

    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    payload = json.loads(lines[0])
    assert payload["question_id"] == records[0].question_id
    assert payload["mode"] == "hybrid_qafirst"
    assert payload["model"] == "stub"
    assert payload["verdict"] == "CORRECT"
    assert payload["retrieved_ids"]
    assert "answer" in payload
    assert "answer_latency_s" in payload

    assert "n=3" in summary
    assert "CORRECT=3" in summary
    assert summary_path.read_text(encoding="utf-8").strip() == summary


def test_stub_verdict_is_configurable_and_other_is_counted(
    dataset: tuple[EvalQuestion, ...], holdout_index
) -> None:
    records = run_answer_eval(
        _questions(dataset, 2),
        mode="hybrid_qafirst",
        answer_model=StubModel(),
        judge_model=StubModel(verdict="WRONG", reason="nope"),
        index=holdout_index,
    )
    assert all(record.verdict == "WRONG" for record in records)
    summary = format_answer_summary(
        mode="hybrid_qafirst", model="stub", question_kind=PARAPHRASE, records=records
    )
    assert "WRONG=2" in summary


def test_longctx_mode_records_the_whole_corpus(
    dataset: tuple[EvalQuestion, ...]
) -> None:
    records = run_answer_eval(
        _questions(dataset, 1),
        mode="longctx_qafirst",
        answer_model=StubModel(),
        judge_model=StubModel(),
    )
    record: AnswerRecord = records[0]
    assert record.retrieved_ids
    assert any(source_id.startswith("qa/") for source_id in record.retrieved_ids)
    assert any(
        not source_id.startswith("qa/") for source_id in record.retrieved_ids
    )
    assert record.context_tokens > 10_000
