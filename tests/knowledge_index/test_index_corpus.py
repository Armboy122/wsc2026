"""Real-corpus acceptance: lossless chunking, stable IDs, unchanged files, Q&A-first.

These tests exercise the approved corpus under ``knowledge/`` read-only and use the
deterministic ``FakeEmbedder`` so the whole file stays offline and fast.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import FakeEmbedder, KnowledgeIndex, chunk_markdown

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = ROOT / "knowledge"


def _knowledge_hashes() -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in sorted(KNOWLEDGE_ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            relative = path.relative_to(KNOWLEDGE_ROOT).as_posix()
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _document_text(document: object) -> str:
    return Path(document.path).read_text(encoding="utf-8")  # type: ignore[attr-defined]


def test_every_chunk_body_is_an_exact_source_slice(real_catalog: KnowledgeCatalog) -> None:
    checked = 0
    for document in real_catalog.documents:
        if document.source_id.startswith("qa/"):
            continue
        text = _document_text(document)
        for chunk in chunk_markdown(document.source_id, document.title, text):
            checked += 1
            assert chunk.text == text[chunk.start : chunk.end]
            assert chunk.start < chunk.end
            assert chunk.uri == f"knowledge://source/{document.source_id}"
    assert checked > 0


def test_real_corpus_chunking_loses_no_text(real_catalog: KnowledgeCatalog) -> None:
    documents = 0
    for document in real_catalog.documents:
        if document.source_id.startswith("qa/"):
            continue
        documents += 1
        text = _document_text(document)
        chunks = chunk_markdown(document.source_id, document.title, text)
        joined = "".join(chunk.text for chunk in chunks)
        assert joined == text, document.source_id
        # every non-empty source line is covered by the concatenated chunk bodies
        for line in text.splitlines():
            if line.strip():
                assert line in joined, (document.source_id, line)
    assert documents >= 34


def test_chunk_ids_are_identical_across_independent_builds(
    real_catalog: KnowledgeCatalog,
) -> None:
    first = KnowledgeIndex(real_catalog, embedder=FakeEmbedder())
    second = KnowledgeIndex(real_catalog, embedder=FakeEmbedder())

    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]
    assert [unit.source_id for unit in first.qa_units] == [
        unit.source_id for unit in second.qa_units
    ]


def test_building_and_searching_the_index_leaves_knowledge_files_byte_identical(
    real_catalog: KnowledgeCatalog,
) -> None:
    before = _knowledge_hashes()
    assert before, "expected approved knowledge files"

    index = KnowledgeIndex(real_catalog, embedder=FakeEmbedder())
    index.search("การขอใช้ไฟฟ้าใหม่")
    index.search("ค้างชำระค่าไฟแบ่งชำระ")
    index.search("ขอคืนเงินประกันการใช้ไฟฟ้า")

    assert _knowledge_hashes() == before


def test_indexed_source_ids_are_catalog_relative_and_traversal_free(
    real_catalog: KnowledgeCatalog, real_index: KnowledgeIndex
) -> None:
    approved = {document.source_id for document in real_catalog.documents}
    source_ids = [chunk.source_id for chunk in real_index.chunks] + [
        unit.source_id for unit in real_index.qa_units
    ]

    assert source_ids
    for source_id in source_ids:
        assert source_id in approved
        assert not source_id.startswith("/")
        assert "\\" not in source_id
        assert all(part not in {"", ".", ".."} for part in source_id.split("/"))


def test_real_index_has_exactly_eleven_qa_units(real_index: KnowledgeIndex) -> None:
    assert len(real_index.qa_units) == 11


def test_every_main_question_retrieves_its_own_qa_at_rank_one(
    real_index: KnowledgeIndex,
) -> None:
    units = real_index.qa_units
    assert len(units) == 11

    hits = 0
    for unit in units:
        result = real_index.search(unit.question)
        assert result.qa, unit.source_id
        assert result.qa[0].source_id == unit.source_id, unit.source_id
        assert result.qa[0].text == unit.text
        hits += 1
    assert hits == 11
