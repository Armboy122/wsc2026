"""Evaluation dataset over the approved Q&A files under ``knowledge/source/qa/``.

Each ``qa_*.md`` file contributes one main question plus its ``คำถามใกล้เคียง`` paraphrases;
the gold answer is the ``## ตอบ`` section. Parsing reuses the production
:func:`app.knowledge.index.parse_qa_unit`, so the evaluation and the runtime agree on what a
Q&A document says.

The paraphrases are the held-out set. They are removed from the *indexed* Q&A text by building
the production index with ``include_qa_paraphrases=False``, and :func:`holdout_qa_text` removes
them from any Q&A body placed in an answer context, exactly like the research harness
(``~/rag-eval/common.py``) stripped the heading before building its corpus. Without the holdout
the paraphrase question would appear verbatim in the retrieved context and the evaluation would
only measure string matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.knowledge.catalog import KnowledgeCatalog, KnowledgeDocument
from app.knowledge.index import parse_qa_unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "knowledge" / "source"

QA_PREFIX = "qa/"
QA_PARAPHRASE_SEPARATOR = "| คำถามใกล้เคียง:"

MAIN = "main"
PARAPHRASE = "paraphrase"
QUESTION_KINDS = (MAIN, PARAPHRASE, "all")


@dataclass(frozen=True)
class EvalQuestion:
    """One evaluation question with its gold answer and source provenance."""

    id: str
    source_id: str
    question: str
    kind: str
    gold_answer: str


def load_dataset(source_root: Path | str | None = None) -> tuple[EvalQuestion, ...]:
    """Load every main question and paraphrase from the approved Q&A files."""
    catalog = KnowledgeCatalog(_source_root(source_root))
    questions: list[EvalQuestion] = []
    for document in catalog.documents:
        if not document.source_id.startswith(QA_PREFIX):
            continue
        unit = parse_qa_unit(document.source_id, document.title, read_document(document))
        questions.append(
            EvalQuestion(
                id=f"{unit.source_id}#main",
                source_id=unit.source_id,
                question=unit.question,
                kind=MAIN,
                gold_answer=unit.answer,
            )
        )
        for position, paraphrase in enumerate(unit.paraphrases, start=1):
            questions.append(
                EvalQuestion(
                    id=f"{unit.source_id}#p{position}",
                    source_id=unit.source_id,
                    question=paraphrase,
                    kind=PARAPHRASE,
                    gold_answer=unit.answer,
                )
            )
    return tuple(questions)


def select_questions(
    questions: tuple[EvalQuestion, ...], kind: str = PARAPHRASE
) -> tuple[EvalQuestion, ...]:
    """Filter by ``main``, ``paraphrase`` or ``all`` (default: held-out paraphrases)."""
    if kind == "all":
        return questions
    if kind not in (MAIN, PARAPHRASE):
        raise ValueError(f"unsupported question kind {kind!r}: expected main, paraphrase or all")
    return tuple(question for question in questions if question.kind == kind)


def read_document(document: KnowledgeDocument) -> str:
    return document.path.read_text(encoding="utf-8")


def holdout_qa_text(text: str) -> str:
    """Return a Q&A body with the ``คำถามใกล้เคียง`` paraphrase list removed from the heading.

    Only the first line changes; the ``## ตอบ`` answer and every other section stay verbatim.
    """
    head, separator, rest = text.partition("\n")
    head = head.split(QA_PARAPHRASE_SEPARATOR)[0]
    return head + (separator + rest if separator else "")


def longctx_corpus(
    catalog: KnowledgeCatalog,
) -> tuple[tuple[str, str], ...]:
    """Approved documents as ``(source_id, text)`` pairs with approved Q&A first.

    Q&A headings are stripped of paraphrases (:func:`holdout_qa_text`), matching the research
    harness long-context corpus. Only ``knowledge/source/**`` is included (decision D7).
    """
    qa: list[tuple[str, str]] = []
    documents: list[tuple[str, str]] = []
    for document in catalog.documents:
        text = read_document(document)
        if document.source_id.startswith(QA_PREFIX):
            qa.append((document.source_id, holdout_qa_text(text)))
        else:
            documents.append((document.source_id, text))
    return tuple(qa + documents)


def _source_root(source_root: Path | str | None) -> Path:
    return Path(source_root) if source_root is not None else DEFAULT_SOURCE_ROOT
