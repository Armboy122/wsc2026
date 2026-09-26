"""Human-readable summaries and JSONL output for the evaluation runs.

The summary format mirrors the research harness ``~/rag-eval/summary.txt`` so a ported run can
be compared with the recorded baseline. Every file is written under the gitignored
``evaluation/rag/out/`` directory by the CLI; nothing here writes anywhere else.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Mapping
from pathlib import Path

from evaluation.rag.answer_eval import VALID_VERDICTS, AnswerRecord
from evaluation.rag.retrieval_eval import RetrievalMetrics, RetrievalRecord


def percent(part: int, total: int) -> str:
    return f"{(part / total * 100):.0f}%" if total else "n/a"


def format_retrieval_summary(
    *,
    embedder: str,
    question_kind: str,
    metrics: RetrievalMetrics,
    ks: tuple[int, ...],
) -> str:
    """Reference-style one-block retrieval table."""
    total = metrics.total
    hit_at = " ".join(
        f"hit@{k}={metrics.hit_at.get(k, 0)}/{total}" for k in ks
    )
    chunk_hit_at = " ".join(
        f"chunk_hit@{k}={metrics.chunk_hit_at.get(k, 0)}/{total}" for k in ks
    )
    return "\n".join(
        [
            f"===== retrieval eval — embedder={embedder}, questions={question_kind}",
            (
                f"n={total} | "
                f"qa_hit@1={metrics.qa_hit_at_1}/{total} ({percent(metrics.qa_hit_at_1, total)}) | "
                f"qa_hit@2={metrics.qa_hit_at_2}/{total} ({percent(metrics.qa_hit_at_2, total)}) | "
                f"{hit_at} | {chunk_hit_at} | "
                f"mean={metrics.mean_latency_ms:.2f} ms/search | "
                f"median returned tokens={metrics.median_returned_tokens}"
            ),
        ]
    )


def format_answer_summary(
    *,
    mode: str,
    model: str,
    question_kind: str,
    records: tuple[AnswerRecord, ...],
) -> str:
    """Reference-style one-line-per-model answer summary."""
    counts: dict[str, int] = dict.fromkeys(VALID_VERDICTS, 0)
    for record in records:
        if record.verdict in counts:
            counts[record.verdict] += 1
    total = len(records)
    other = total - sum(counts.values())
    latencies = [record.answer_latency_s + record.judge_latency_s for record in records]
    context_tokens = [record.context_tokens for record in records]
    median_latency = statistics.median(latencies) if latencies else 0.0
    median_tokens = (
        statistics.median_low(context_tokens) if context_tokens else 0
    )
    return "\n".join(
        [
            f"===== answer eval — mode={mode}, model={model}, questions={question_kind}",
            (
                f"{model} n={total} "
                f"CORRECT={counts['CORRECT']} PARTIAL={counts['PARTIAL']} "
                f"WRONG={counts['WRONG']} NO_ANSWER={counts['NO_ANSWER']} other={other} | "
                f"strict={percent(counts['CORRECT'], total)} "
                f"lenient(C+P)={percent(counts['CORRECT'] + counts['PARTIAL'], total)} | "
                f"median sec={median_latency:.1f} | "
                f"median context tokens={median_tokens}"
            ),
        ]
    )


def write_text(path: Path | str, text: str) -> Path:
    """Write ``text`` with a trailing newline, creating parent directories."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return destination


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, object]]) -> Path:
    """Write one JSON object per line, UTF-8, without escaping Thai text."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return destination


def retrieval_rows(records: tuple[RetrievalRecord, ...]) -> list[dict[str, object]]:
    return [
        {
            "question_id": record.question_id,
            "source_id": record.source_id,
            "kind": record.kind,
            "question": record.question,
            "qa_source_ids": list(record.qa_source_ids),
            "chunk_source_ids": list(record.chunk_source_ids),
            "latency_ms": record.latency_ms,
            "returned_chars": record.returned_chars,
            "returned_tokens": record.returned_tokens,
        }
        for record in records
    ]


def answer_rows(records: tuple[AnswerRecord, ...]) -> list[dict[str, object]]:
    return [record.to_dict() for record in records]


def slugify(spec: str) -> str:
    """Filesystem-safe short name for a model spec (``pi:a/b`` -> ``pi-a-b``)."""
    return "".join(char if char.isalnum() or char in "-." else "-" for char in spec)
