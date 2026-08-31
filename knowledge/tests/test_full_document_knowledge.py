"""Public-interface tests for full-document Gemini knowledge routing."""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

from app.backends.full_document_knowledge import FullDocumentKnowledgeBackend


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


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict] = []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=next(self.responses))


def backend(tmp_path: Path, responses: list[str], **kwargs):
    client = FakeClient(responses)
    instance = FullDocumentKnowledgeBackend(
        api_key="test-key", source_root=tmp_path, client_factory=lambda _: client, **kwargs
    )
    return instance, client


def test_search_sends_only_selected_complete_file_and_safe_citation(tmp_path: Path) -> None:
    write_docx(
        tmp_path / "rates.docx",
        "rate heading",
        "TAIL-OF-RATES",
        title="อัตราค่าไฟ",
    )
    write_docx(
        tmp_path / "unrelated.docx",
        "SECRET-UNRELATED",
        title="บริการอื่น",
    )
    service, client = backend(
        tmp_path,
        [
            '{"sourceIds":["rates.docx"]}',
            '{"answer":"คำตอบครบถ้วน","citations":[{"sourceId":"rates.docx","snippet":"TAIL-OF-RATES"}]}',
        ],
    )

    evidence = asyncio.run(service.search("ค่าไฟเท่าไร", 2))

    assert evidence.result_count == 1
    assert evidence.answer_context == "คำตอบครบถ้วน"
    assert evidence.citations[0].source_id == "rates.docx"
    assert evidence.citations[0].uri == "knowledge://source/rates.docx"
    assert unquote(evidence.citations[0].uri.split("knowledge://source/", 1)[1]) == "rates.docx"
    router_prompt = client.calls[0]["contents"]
    completion_prompt = client.calls[1]["contents"]
    assert "TAIL-OF-RATES" not in router_prompt
    assert "SECRET-UNRELATED" not in router_prompt
    assert "TAIL-OF-RATES" in completion_prompt
    assert "SECRET-UNRELATED" not in completion_prompt


def test_router_uses_document_title_and_completion_includes_header_text(tmp_path: Path) -> None:
    write_docx(
        tmp_path / "opaque.docx",
        "เนื้อหาหลัก",
        title="บริการตรวจสอบระบบไฟฟ้า",
        header="ข้อความสำคัญในส่วนหัว",
    )
    service, client = backend(
        tmp_path,
        [
            '{"sourceIds":["opaque.docx"]}',
            '{"answer":"คำตอบ","citations":[{"sourceId":"opaque.docx","snippet":"ข้อความสำคัญในส่วนหัว"}]}',
        ],
    )

    evidence = asyncio.run(service.search("ตรวจสอบระบบไฟฟ้า", 1))

    assert evidence.result_count == 1
    assert "บริการตรวจสอบระบบไฟฟ้า" in client.calls[0]["contents"]
    assert "เนื้อหาหลัก" not in client.calls[0]["contents"]
    assert "ข้อความสำคัญในส่วนหัว" not in client.calls[0]["contents"]
    assert "เนื้อหาหลัก" in client.calls[1]["contents"]
    assert "ข้อความสำคัญในส่วนหัว" in client.calls[1]["contents"]



def test_unknown_or_malformed_router_selection_fails_closed(tmp_path: Path) -> None:
    write_docx(tmp_path / "rates.docx", "rate")
    for response in ('{"sourceIds":["unknown.docx"]}', "not json"):
        service, client = backend(tmp_path, [response])
        evidence = asyncio.run(service.search("q", 1))
        assert evidence.result_count == 0
        assert evidence.citations == ()
        assert len(client.calls) == 1


def test_invalid_citation_snippet_fails_closed(tmp_path: Path) -> None:
    write_docx(tmp_path / "rates.docx", "actual source text")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["rates.docx"]}',
            '{"answer":"คำตอบ","citations":[{"sourceId":"rates.docx","snippet":"invented"}]}',
        ],
    )

    assert asyncio.run(service.search("q", 1)).result_count == 0


def test_context_budget_overflow_fails_closed_without_completion_call(tmp_path: Path) -> None:
    write_docx(tmp_path / "rates.docx", "x" * 100)
    service, client = backend(
        tmp_path, ['{"sourceIds":["rates.docx"]}'], hard_context_chars=50
    )

    assert asyncio.run(service.search("q", 1)).result_count == 0
    assert len(client.calls) == 1
