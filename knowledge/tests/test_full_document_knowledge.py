"""Public-interface tests for full-document Gemini knowledge routing."""

from __future__ import annotations

import asyncio
import shutil
import zipfile
from pathlib import Path

from app.backends.full_document_knowledge import (
    USER_SAFE_CHAT_KNOWLEDGE_REMOVED,
    FullDocumentKnowledgeBackend,
    KnowledgeBackendError,
    _extract_document_text,
    _extract_docx_text,
)
from app.contracts import ToolErrorCode


def write_docx(
    path: Path,
    *paragraphs: str,
    title: str | None = None,
    header: str | None = None,
) -> None:
    document = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{document}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
        if title is not None:
            archive.writestr(
                "docProps/core.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                f"<dc:title>{title}</dc:title></cp:coreProperties>",
            )
        if header is not None:
            archive.writestr(
                "word/header1.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:p><w:r><w:t>{header}</w:t></w:r></w:p></w:hdr>",
            )


def test_bill_evidence_loads_exact_allowlisted_source_without_provider_call() -> None:
    source_root = Path(__file__).resolve().parents[1] / "source"
    service = FullDocumentKnowledgeBackend(source_root=source_root)

    evidence = asyncio.run(service.bill_evidence(1))

    assert evidence.result_count == 1
    assert evidence.citations
    assert all(citation.uri.startswith("knowledge://source/") for citation in evidence.citations)
    snippets = {citation.snippet for citation in evidence.citations}
    assert "ประเภทที่ 1 บ้านอยู่อาศัย สำหรับการใช้ไฟฟ้ากับบ้านที่อยู่อาศัย" in snippets
    assert "1.1.2 ใช้พลังงานไฟฟ้าเกิน 150 หน่วยต่อเดือน 24.62" in snippets
    assert "200 หน่วยแรก (หน่วยที่ 0 – 200) 3.0000\n200 หน่วยต่อไป (หน่วยที่ 201 – 400) 4.1584\nเกิน 400 หน่วยขึ้นไป (หน่วยที่ 401 เป็นต้นไป) 4.3583" in snippets
    assert "ค่า Ft\nหน่วยละ\n0.1623 บาท\nหรือ 16.23 สตางค์ (ยังไม่รวมภาษีมูลค่าเพิ่ม)" in snippets
    assert any("อัตราร้อยละหกจุดสาม" in snippet and "๓๐ กันยายน พ.ศ. ๒๕๖๙" in snippet for snippet in snippets)
    assert "ลดอัตราภาษีมูลค่าเพิ่มเป็นการชั่วคราวจากร้อยละ 10 เหลือร้อยละ 6.3 เมื่อรวมกับภาษีท้องถิ่นอีกร้อยละ 0.7 จะเท่ากับร้อยละ 7" in snippets
    assert all(len(citation.snippet) <= 1000 for citation in evidence.citations)


def test_tampered_bill_source_fails_closed(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = Path(__file__).resolve().parents[1] / "source" / "PEA_residential_normal_1_1_2_SEP_DEC_2569.md"
    target = source_root / source.name
    shutil.copyfile(source, target)
    target.write_text(target.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    service = FullDocumentKnowledgeBackend(source_root=source_root)

    evidence = asyncio.run(service.bill_evidence(1))

    assert evidence.answer_context == ""
    assert evidence.citations == ()


def test_committed_tou_tariff_document_is_catalogued_with_verifiable_rates() -> None:
    source_root = Path(__file__).resolve().parents[1] / "source"
    backend = FullDocumentKnowledgeBackend(source_root=source_root)

    catalog = backend._catalog()
    document = catalog["PEA_อัตราค่าไฟฟ้า_TOU_2569.md"]
    text = _extract_document_text(document.path)

    assert document.title == "อัตราค่าไฟฟ้า TOU (Time of Use) ปี 2569"
    assert "Peak 5.1135 บาท/หน่วย" in text
    assert "Off-Peak 2.6037 บาท/หน่วย" in text
    assert "วันแรงงานแห่งชาติ วันพืชมงคล" in text
    assert "https://www.pea.co.th/sites/default/files/documents/tariff/electricity_tariff.pdf" in text


def test_docx_line_breaks_are_preserved_for_verbatim_citations(tmp_path: Path) -> None:
    path = tmp_path / "steps.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>ขั้นตอนที่ 1</w:t><w:br/>'
            '<w:t>ขั้นตอนที่ 2</w:t></w:r></w:p></w:body></w:document>',
        )

    assert "ขั้นตอนที่ 1\nขั้นตอนที่ 2" in _extract_docx_text(path)


def test_legacy_chat_search_fails_closed_without_any_model_call(tmp_path: Path) -> None:
    """Story 2 Ticket 002 removed the Knowledge router/answer model calls."""
    write_docx(tmp_path / "approved.docx", "หลักฐาน", title="เอกสารที่อนุมัติ")
    service = FullDocumentKnowledgeBackend(source_root=tmp_path)

    try:
        asyncio.run(service.search("คำถามใด ๆ", 3))
    except KnowledgeBackendError as exc:
        assert exc.code is ToolErrorCode.UNAVAILABLE
        assert exc.message == USER_SAFE_CHAT_KNOWLEDGE_REMOVED
    else:
        raise AssertionError("legacy Chat Knowledge search must fail closed")


def test_legacy_backend_has_no_generative_provider_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "app" / "backends" / "full_document_knowledge.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("google.genai", "from google import genai", "generate_content", "openai", "api_key"):
        assert forbidden not in source
