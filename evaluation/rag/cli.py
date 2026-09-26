"""Command-line entry points for the offline RAG regression evaluation.

``scripts/eval_rag`` is a thin wrapper around ``python -m evaluation.rag``; the two commands are
``retrieval`` (production index, offline with the fake embedder) and ``answer`` (retrieve,
answer, judge, and write JSONL + a summary). Every output goes to the gitignored
``evaluation/rag/out/`` unless ``--out`` says otherwise.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.rag.answer_eval import (
    HYBRID_QAFIRST,
    LONGCTX_QAFIRST,
    run_answer_eval,
)
from evaluation.rag.dataset import QUESTION_KINDS, load_dataset, select_questions
from evaluation.rag.models import ResponseCache, build_model
from evaluation.rag.report import (
    answer_rows,
    format_answer_summary,
    format_retrieval_summary,
    retrieval_rows,
    slugify,
    write_jsonl,
    write_text,
)
from evaluation.rag.retrieval_eval import (
    DEFAULT_KS,
    SUPPORTED_EMBEDDERS,
    build_index,
    run_retrieval,
)

DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "out"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval_rag",
        description=(
            "Offline regression evaluation for Knowledge search. Real-model runs are an owner "
            "action; the defaults are fully offline."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    retrieval = subparsers.add_parser(
        "retrieval", help="measure Q&A-lane and chunk retrieval against the production index"
    )
    _add_common_retrieval_args(retrieval)

    answer = subparsers.add_parser(
        "answer", help="retrieve, answer and judge every question"
    )
    answer.add_argument(
        "--model",
        default="stub",
        help="answer model spec: stub | pi:<provider/model> | gemini:<name> (default: stub)",
    )
    answer.add_argument(
        "--judge",
        default=None,
        help=(
            "judge model spec: stub | pi:<provider/model> | gemini:<name> "
            "(default: same as --model)"
        ),
    )
    answer.add_argument(
        "--mode",
        choices=(HYBRID_QAFIRST, LONGCTX_QAFIRST),
        default=HYBRID_QAFIRST,
        help="context assembly mode (default: hybrid_qafirst)",
    )
    answer.add_argument(
        "--embedder",
        choices=SUPPORTED_EMBEDDERS,
        default="fake",
        help="index embedder for hybrid mode (default: fake, offline)",
    )
    answer.add_argument(
        "--limit", type=int, default=None, help="only evaluate the first N questions"
    )
    _add_common_question_args(answer)
    answer.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="override KNOWLEDGE source root (default: <repo>/knowledge/source)",
    )
    answer.add_argument(
        "--no-cache", action="store_true", help="do not read or write the response cache"
    )
    answer.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory (default: {DEFAULT_OUT_DIR})",
    )
    return parser


def _add_common_retrieval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--embedder",
        choices=SUPPORTED_EMBEDDERS,
        default="fake",
        help="index embedder (default: fake, offline)",
    )
    _add_common_question_args(parser)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="override KNOWLEDGE source root (default: <repo>/knowledge/source)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory (default: {DEFAULT_OUT_DIR})",
    )


def _add_common_question_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--questions",
        choices=QUESTION_KINDS,
        default="paraphrase",
        help="which questions to run: main, paraphrase or all (default: paraphrase)",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "retrieval":
        return _run_retrieval(args)
    return _run_answer(args)


def _run_retrieval(args: argparse.Namespace) -> int:
    questions = select_questions(load_dataset(args.source_root), args.questions)
    index = build_index(
        args.embedder,
        source_root=args.source_root,
        include_qa_paraphrases=False,
    )
    records, metrics = run_retrieval(index, questions, ks=DEFAULT_KS)
    summary = format_retrieval_summary(
        embedder=args.embedder,
        question_kind=args.questions,
        metrics=metrics,
        ks=DEFAULT_KS,
    )
    print(summary)
    stem = f"retrieval-{args.embedder}-{args.questions}"
    write_text(args.out / f"{stem}.txt", summary)
    write_jsonl(args.out / f"{stem}.jsonl", retrieval_rows(records))
    return 0


def _run_answer(args: argparse.Namespace) -> int:
    questions = select_questions(load_dataset(args.source_root), args.questions)
    cache = None if args.no_cache else ResponseCache(args.out / "cache")
    judge_spec = args.judge or args.model
    answer_model = build_model(args.model, cache=cache, mode=args.mode)
    judge_model = build_model(judge_spec, cache=cache, mode=args.mode)
    index = None
    if args.mode == HYBRID_QAFIRST:
        index = build_index(
            args.embedder,
            source_root=args.source_root,
            include_qa_paraphrases=False,
        )
    records = run_answer_eval(
        questions,
        mode=args.mode,
        answer_model=answer_model,
        judge_model=judge_model,
        index=index,
        embedder=args.embedder,
        source_root=args.source_root,
        limit=args.limit,
    )
    summary = format_answer_summary(
        mode=args.mode,
        model=answer_model.spec,
        question_kind=args.questions,
        records=records,
    )
    print(summary)
    stem = f"answers-{args.mode}-{slugify(answer_model.spec)}-{args.questions}"
    write_text(args.out / f"{stem}.txt", summary)
    write_jsonl(args.out / f"{stem}.jsonl", answer_rows(records))
    return 0
