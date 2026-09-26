"""CLI parsing, model-spec resolution and the offline end-to-end commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.rag.cli import build_parser, main
from evaluation.rag.models import GeminiModel, PiCliModel, StubModel, build_model


def test_parser_accepts_model_specs_without_constructing_them() -> None:
    args = build_parser().parse_args(
        ["answer", "--model", "gemini:gemini-3.6-flash", "--judge", "pi:maxplus/glm-5.3"]
    )
    assert args.command == "answer"
    assert args.model == "gemini:gemini-3.6-flash"
    assert args.judge == "pi:maxplus/glm-5.3"
    assert args.mode == "hybrid_qafirst"


def test_judge_defaults_to_the_answer_model() -> None:
    args = build_parser().parse_args(["answer", "--model", "gemini:gemini-3.6-flash"])
    assert args.judge is None
    assert (args.judge or args.model) == "gemini:gemini-3.6-flash"


def test_parser_retrieval_defaults_to_offline_fake_embedder() -> None:
    args = build_parser().parse_args(["retrieval"])
    assert args.embedder == "fake"
    assert args.questions == "paraphrase"


def test_build_model_resolves_the_right_adapter_class() -> None:
    assert isinstance(build_model("stub"), StubModel)
    assert isinstance(build_model("pi:maxplus/deepseek-v4.1-flash"), PiCliModel)
    assert isinstance(build_model("gemini:gemini-3.6-flash"), GeminiModel)


def test_unknown_model_spec_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_model("openai:gpt-4")
    with pytest.raises(ValueError):
        build_model("pi:")
    with pytest.raises(ValueError):
        build_model("")


def test_answer_cli_writes_jsonl_and_summary_offline(tmp_path: Path) -> None:
    exit_code = main(
        ["answer", "--model", "stub", "--limit", "2", "--out", str(tmp_path)]
    )

    assert exit_code == 0
    jsonl = tmp_path / "answers-hybrid_qafirst-stub-paraphrase.jsonl"
    summary = tmp_path / "answers-hybrid_qafirst-stub-paraphrase.txt"
    assert jsonl.is_file()
    assert summary.is_file()
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["verdict"] == "CORRECT"
    assert "CORRECT=2" in summary.read_text(encoding="utf-8")
    # The response cache is written under the requested output directory.
    assert (tmp_path / "cache").is_dir()


def test_retrieval_cli_writes_jsonl_and_summary_offline(tmp_path: Path) -> None:
    exit_code = main(
        [
            "retrieval",
            "--embedder",
            "fake",
            "--questions",
            "main",
            "--out",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    summary = tmp_path / "retrieval-fake-main.txt"
    jsonl = tmp_path / "retrieval-fake-main.jsonl"
    assert summary.is_file()
    assert jsonl.is_file()
    text = summary.read_text(encoding="utf-8")
    assert "qa_hit@1=" in text
    assert "chunk_hit@5=" in text
    assert len(jsonl.read_text(encoding="utf-8").strip().splitlines()) == 11
