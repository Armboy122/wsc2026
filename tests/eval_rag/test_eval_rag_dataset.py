"""Dataset loading and paraphrase holdout on the real approved Q&A files."""

from __future__ import annotations

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import KnowledgeIndex, qa_index_text
from evaluation.rag.dataset import (
    DEFAULT_SOURCE_ROOT,
    MAIN,
    PARAPHRASE,
    longctx_corpus,
    select_questions,
)


def test_dataset_has_eleven_main_and_thirtyfive_paraphrases(
    dataset: tuple,
) -> None:
    mains = [question for question in dataset if question.kind == MAIN]
    paraphrases = [question for question in dataset if question.kind == PARAPHRASE]
    assert len(mains) == 11
    assert len(paraphrases) == 35
    assert len(dataset) == 46


def test_question_ids_are_unique_and_traceable(dataset: tuple) -> None:
    ids = [question.id for question in dataset]
    assert len(set(ids)) == len(ids)
    for question in dataset:
        assert question.source_id.startswith("qa/qa_")
        assert question.id == f"{question.source_id}#main" or question.id.startswith(
            f"{question.source_id}#p"
        )
        assert question.question.strip()
        assert question.gold_answer.strip()


def test_every_paraphrase_is_attributed_to_its_source(dataset: tuple) -> None:
    by_source: dict[str, set[str]] = {}
    for question in dataset:
        by_source.setdefault(question.source_id, set()).add(question.kind)
    assert len(by_source) == 11
    for source_id, kinds in by_source.items():
        assert kinds == {MAIN, PARAPHRASE}, source_id


def test_select_questions_filters(dataset: tuple) -> None:
    assert len(select_questions(dataset, MAIN)) == 11
    assert len(select_questions(dataset, PARAPHRASE)) == 35
    assert len(select_questions(dataset, "all")) == 46


def test_gold_answer_is_the_answer_section_not_the_question(dataset: tuple) -> None:
    expected = "สามารถแบ่งชำระบางเดือนได้"
    gold = next(
        question.gold_answer
        for question in dataset
        if question.source_id == "qa/qa_ค้างชำระค่าไฟ_แบ่งชำระ.md"
    )
    assert expected in gold
    assert "##" not in gold
    assert "สถานะหลักฐาน" not in gold


def test_holdout_removes_every_paraphrase_from_the_indexed_qa_text(
    dataset: tuple, holdout_index: KnowledgeIndex
) -> None:
    paraphrases = [q for q in dataset if q.kind == PARAPHRASE]
    assert len(holdout_index.qa_units) == 11
    units = {unit.source_id: unit for unit in holdout_index.qa_units}
    for question in paraphrases:
        unit = units[question.source_id]
        scored = qa_index_text(unit, include_paraphrases=False)
        assert question.question not in scored, question.id
        # The holdout only affects scoring text; the approved Q&A body stays verbatim.
        assert len(unit.text) > 0
    with_paraphrases = qa_index_text(units[paraphrases[0].source_id], include_paraphrases=True)
    assert paraphrases[0].question in with_paraphrases


def test_longctx_corpus_is_qa_first_and_free_of_held_out_paraphrases(
    dataset: tuple,
) -> None:
    corpus = longctx_corpus(KnowledgeCatalog(DEFAULT_SOURCE_ROOT))
    assert corpus
    first_document = next(
        index for index, (source_id, _) in enumerate(corpus) if not source_id.startswith("qa/")
    )
    assert all(source_id.startswith("qa/") for source_id, _ in corpus[:first_document])
    assert any(source_id.startswith("qa/") for source_id, _ in corpus)
    assert any(not source_id.startswith("qa/") for source_id, _ in corpus)
    for _, text in corpus:
        assert "| คำถามใกล้เคียง:" not in text
    # The gold answers are still present after stripping the heading.
    held_out = select_questions(dataset, PARAPHRASE)
    qa_text = "\n".join(text for source_id, text in corpus if source_id.startswith("qa/"))
    assert held_out[0].gold_answer in qa_text
