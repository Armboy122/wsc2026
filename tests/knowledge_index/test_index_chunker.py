"""Heading-aware, lossless chunker tests."""

from __future__ import annotations

from itertools import pairwise

from app.knowledge.index import MAX_CHUNK_CHARS, chunk_markdown


def test_headings_become_the_chunk_context_prefix() -> None:
    # Each section is larger than MIN_CHUNK_CHARS so sections stay separate and keep
    # their own heading path (tiny sections are merged, covered by another test).
    body = "เนื้อหาประโยคยาว " * 45
    text = (
        "# คู่มือบริการ\n\n"
        f"{body}\n\n"
        "## 1. หัวข้อบริการ\n\n"
        f"{body}\n\n"
        "### 1.1 รายละเอียด\n\n"
        f"{body}\n"
    )
    chunks = chunk_markdown("PEA_test.md", "คู่มือบริการ", text)

    assert [chunk.heading_path for chunk in chunks] == [
        ("คู่มือบริการ",),
        ("คู่มือบริการ", "1. หัวข้อบริการ"),
        ("คู่มือบริการ", "1. หัวข้อบริการ", "1.1 รายละเอียด"),
    ]
    for chunk in chunks:
        assert chunk.text == text[chunk.start : chunk.end]
        assert chunk.uri == "knowledge://source/PEA_test.md"
        assert chunk.title == "คู่มือบริการ"
        # heading context is kept separate from the verbatim body
        assert chunk.index_text.startswith("\n".join(chunk.heading_path))


def test_concatenated_chunks_reproduce_the_source_exactly() -> None:
    text = (
        "# Title\n\nintro paragraph\n\n"
        "## A\n\n" + ("paragraph a\n\n" * 20) +
        "## B\n\nshort\n\n"
        "#### deeper heading stays in the body\n\nkept verbatim\n"
    )
    chunks = chunk_markdown("doc.md", "Title", text)
    assert "".join(chunk.text for chunk in chunks) == text


def test_tiny_consecutive_sections_are_merged() -> None:
    text = "# T\n\n## A\n\nเล็ก\n\n## B\n\nน้อย\n\n## C\n\nจิ๋ว\n"
    chunks = chunk_markdown("doc.md", "T", text)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_oversize_section_is_split_on_paragraph_and_line_boundaries() -> None:
    paragraphs = [f"ย่อหน้าที่ {index}\n" + ("รายละเอียด " * 40) for index in range(40)]
    text = "# T\n\n## Big\n\n" + "\n\n".join(paragraphs) + "\n"
    chunks = chunk_markdown("doc.md", "T", text)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == text
    # every chunk after the first is a slice, so no text is dropped at the seams
    for previous, current in pairwise(chunks):
        assert previous.end == current.start


def test_single_paragraph_longer_than_max_is_hard_split_on_lines() -> None:
    body = "\n".join("บรรทัดที่ยาวมาก " + ("ข้อมูล " * 12) for _ in range(200))
    text = "# T\n\n" + body + "\n"
    chunks = chunk_markdown("doc.md", "T", text)
    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == text


def test_thai_text_is_never_altered() -> None:
    text = "# ค่าไฟฟ้า\n\nค่าไฟฟ้าค้างชำระสามารถแบ่งชำระได้ที่สำนักงาน\n"
    chunks = chunk_markdown("doc.md", "ค่าไฟฟ้า", text)
    assert "".join(chunk.text for chunk in chunks) == text
    assert "ค่าไฟฟ้าค้างชำระ" in "".join(chunk.text for chunk in chunks)


def test_headings_inside_fenced_code_are_not_boundaries() -> None:
    text = "# T\n\n```bash\n# not a heading\n## also not\n```\n\nbody\n"
    chunks = chunk_markdown("doc.md", "T", text)
    assert [chunk.heading_path for chunk in chunks] == [("T",)]
    assert chunks[0].text == text


def test_chunk_ids_are_stable_and_unique() -> None:
    text = "# T\n\n## A\n\n" + ("a" * 500) + "\n\n## B\n\n" + ("b" * 500) + "\n"
    first = chunk_markdown("doc.md", "T", text)
    second = chunk_markdown("doc.md", "T", text)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    assert all(chunk.chunk_id for chunk in first)
    other = chunk_markdown("other.md", "T", text)
    assert first[0].chunk_id != other[0].chunk_id


def test_empty_document_yields_no_chunks() -> None:
    assert chunk_markdown("doc.md", "T", "") == ()
