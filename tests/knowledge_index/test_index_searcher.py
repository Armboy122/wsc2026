"""Hybrid searcher tests: Q&A lane precedence, budget, dedupe, aliases, safety."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.knowledge.aliases import KnowledgeAliasRule
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_QA,
    MAX_QUERY_CHARS,
    FakeEmbedder,
    InvalidQueryError,
    KnowledgeIndex,
    Searcher,
    SearchResult,
    expand_query,
)

QA_FILE = (
    "# ถาม: การขอใช้ไฟฟ้าใหม่ต้องทำอย่างไร | คำถามใกล้เคียง: ขอไฟใหม่ทำอย่างไร / "
    "ติดตั้งมิเตอร์ใหม่ต้องทำอะไร\n\n"
    "## สถานะหลักฐาน\n\nตรง\n\n"
    "## ตอบ\n\nยื่นคำขอที่สำนักงานการไฟฟ้าในพื้นที่พร้อมเอกสารประกอบ\n\n"
    "## แหล่งอ้างอิงทางการ\n\nhttps://www.pea.co.th/faqs\n"
)


def _doc(title: str, body: str) -> str:
    return f"# {title}\n\n## ส่วนบริการ\n\n{body}\n"


def test_qa_lane_ranks_above_chunks_and_is_never_chunked(
    temp_catalog: Callable[..., KnowledgeCatalog],
) -> None:
    catalog = temp_catalog(
        {
            "PEA_ขอใช้ไฟฟ้าใหม่.md": _doc("การขอใช้ไฟฟ้าใหม่", "การขอใช้ไฟฟ้าใหม่ " * 60),
            "qa/qa_ทดสอบ.md": QA_FILE,
        }
    )
    index = KnowledgeIndex(catalog, embedder=FakeEmbedder())

    result = index.search("การขอใช้ไฟฟ้าใหม่ต้องทำอย่างไร")

    assert result.qa
    assert result.qa[0].source_id == "qa/qa_ทดสอบ.md"
    assert result.qa[0].text == QA_FILE
    assert all(chunk.source_id != "qa/qa_ทดสอบ.md" for chunk in result.chunks)
    assert "qa/qa_ทดสอบ.md" in result.sources


def test_real_qa_units_are_never_document_chunks(real_index: KnowledgeIndex) -> None:
    qa_ids = {unit.source_id for unit in real_index.qa_units}
    assert len(qa_ids) == 11
    assert all(chunk.source_id not in qa_ids for chunk in real_index.chunks)


def test_search_caps_qa_and_chunk_counts(real_index: KnowledgeIndex) -> None:
    result = real_index.search("การขอใช้ไฟฟ้าใหม่")

    assert 0 < len(result.qa) <= DEFAULT_MAX_QA
    assert len(result.chunks) <= DEFAULT_MAX_CHUNKS
    assert (DEFAULT_MAX_QA, DEFAULT_MAX_CHUNKS) == (2, 5)


def test_search_respects_the_total_character_budget(real_catalog: KnowledgeCatalog) -> None:
    index = KnowledgeIndex(
        real_catalog, embedder=FakeEmbedder(), max_total_chars=MAX_QUERY_CHARS
    )

    result = index.search("การขอใช้ไฟฟ้าใหม่")

    assert result.qa, "the first relevant hit must always be returned"
    assert result.total_chars <= MAX_QUERY_CHARS
    assert result.total_chars == sum(len(hit.text) for hit in (*result.qa, *result.chunks))


def test_returned_chunks_never_duplicate_a_returned_qa_source(
    real_index: KnowledgeIndex,
) -> None:
    result = real_index.search("ขอคืนเงินประกันการใช้ไฟฟ้า")

    qa_sources = {hit.source_id for hit in result.qa}
    chunk_sources = {hit.source_id for hit in result.chunks}
    assert not qa_sources & chunk_sources


@pytest.mark.parametrize("query", ["", "   ", "\n\t "])
def test_search_rejects_blank_queries(real_index: KnowledgeIndex, query: str) -> None:
    with pytest.raises(InvalidQueryError):
        real_index.search(query)


@pytest.mark.parametrize("query", [None, 12, b"bytes", ["list"]])
def test_search_rejects_non_string_queries(real_index: KnowledgeIndex, query: object) -> None:
    with pytest.raises(InvalidQueryError):
        real_index.search(query)  # type: ignore[arg-type]


def test_search_rejects_overlong_queries(real_index: KnowledgeIndex) -> None:
    with pytest.raises(InvalidQueryError):
        real_index.search("ก" * (MAX_QUERY_CHARS + 1))


def test_invalid_query_error_is_a_value_error() -> None:
    assert issubclass(InvalidQueryError, ValueError)


def test_searcher_alias_is_the_search_entry_point(real_index: KnowledgeIndex) -> None:
    assert Searcher is KnowledgeIndex
    assert isinstance(real_index, Searcher)


def test_alias_expansion_appends_terms_for_matching_triggers() -> None:
    rules = (KnowledgeAliasRule("r", ("ผ่อนจ่าย", "ผ่อนผันพิเศษ"), ("PEA_x.md",)),)

    assert expand_query("อยากผ่อนจ่ายค่าไฟ", rules) == ("ผ่อนจ่าย", "ผ่อนผันพิเศษ")
    assert expand_query("เรื่องอื่นทั่วไป", rules) == ()
    assert expand_query("", rules) == ()


def test_alias_expansion_changes_retrieval(
    temp_catalog: Callable[..., KnowledgeCatalog], tmp_path: Path
) -> None:
    aliases = {
        "rule.md": (
            "---\nid: test-alias\naliases:\n  - ผ่อนจ่าย\n  - ผ่อนผันพิเศษ\n"
            "sourceIds:\n  - PEA_target.md\n---\n\n# rule\n"
        )
    }
    catalog = temp_catalog(
        {
            "PEA_target.md": _doc("เป้าหมาย", "ผ่อนผันพิเศษได้ที่สำนักงาน " * 40),
            "PEA_other.md": _doc("อื่น", "เรื่องอื่นทั่วไป " * 40),
            "PEA_third.md": _doc("ที่สาม", "บริการอื่นที่ไม่เกี่ยวข้อง " * 40),
        },
        aliases,
    )

    expanded = KnowledgeIndex(catalog, embedder=FakeEmbedder())
    plain = KnowledgeIndex(
        catalog, embedder=FakeEmbedder(), alias_root=tmp_path / "no-aliases"
    )

    with_aliases = expanded.search("ผ่อนจ่าย")
    without_aliases = plain.search("ผ่อนจ่าย")

    assert with_aliases.chunks[0].source_id == "PEA_target.md"
    assert without_aliases.chunks[0].source_id != "PEA_target.md"


def test_sources_are_unique_and_attributed(real_index: KnowledgeIndex) -> None:
    result = real_index.search("ค่าไฟฟ้า")

    assert result.sources
    assert len(set(result.sources)) == len(result.sources)
    assert set(result.sources) == {hit.source_id for hit in result.qa} | {
        hit.source_id for hit in result.chunks
    }
    for hit in result.qa:
        assert hit.uri == f"knowledge://source/{hit.source_id}"


def test_search_is_deterministic(real_index: KnowledgeIndex) -> None:
    first = real_index.search("การขอใช้ไฟฟ้าใหม่")
    second = real_index.search("การขอใช้ไฟฟ้าใหม่")

    assert isinstance(first, SearchResult)
    assert first == second
