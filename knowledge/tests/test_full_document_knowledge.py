"""Public-interface tests for full-document Gemini knowledge routing."""

from __future__ import annotations

import asyncio
import json
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

from app.backends.full_document_knowledge import (
    FullDocumentKnowledgeBackend,
    _OpenAICompatibleClient,
    _json_response,
)


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
    def __init__(self, responses: list[str], delays: list[float] | None = None) -> None:
        self.responses = iter(responses)
        self.delays = iter(delays or [])
        self.calls: list[dict] = []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        time.sleep(next(self.delays, 0))
        return SimpleNamespace(text=next(self.responses))


def backend(tmp_path: Path, responses: list[str], **kwargs):
    client = FakeClient(responses)
    instance = FullDocumentKnowledgeBackend(
        api_key="test-key", source_root=tmp_path, client_factory=lambda _: client, **kwargs
    )
    return instance, client


def test_gemini_json_response_requests_json_without_unsupported_thinking_override() -> None:
    client = FakeClient(['{"ok":true}'])

    result = _json_response(client, "gemini-3.5-flash-lite", "return json")

    assert result == {"ok": True}
    assert client.calls == [
        {
            "model": "gemini-3.5-flash-lite",
            "contents": "return json",
            "config": {"response_mime_type": "application/json"},
        }
    ]


def test_maxplus_openai_client_posts_chat_completion_and_parses_json() -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size: int = -1) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": '{"sourceIds":["rates.docx"]}'}}]}
            ).encode()

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    client = _OpenAICompatibleClient(
        api_key="ccsk-secret",
        base_url="https://api.maxplus-ai.cc/gpt-lite/v1/",
        timeout_seconds=7,
        urlopen=urlopen,
    )

    result = _json_response(client, "gpt-5.4-mini", "route this")

    assert result == {"sourceIds": ["rates.docx"]}
    assert captured["url"] == "https://api.maxplus-ai.cc/gpt-lite/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer ccsk-secret"
    assert captured["body"] == {
        "model": "gpt-5.4-mini",
        "max_tokens": 4096,
        "temperature": 0,
        "stream": False,
        "messages": [{"role": "user", "content": "route this"}],
    }
    assert captured["timeout"] == 7


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
    assert "at most 200 characters" in completion_prompt


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
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["steps.docx"]}',
            '{"answer":"คำตอบ","citations":[{"sourceId":"steps.docx",'
            '"snippet":"ขั้นตอนที่ 1\\nขั้นตอนที่ 2"}]}',
        ],
    )

    evidence = asyncio.run(service.search("ติดตั้งมิเตอร์อย่างไร", 1))

    assert evidence.answer_context == "คำตอบ"
    assert evidence.citations[0].snippet == "ขั้นตอนที่ 1\nขั้นตอนที่ 2"



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



def test_router_and_answer_each_receive_a_full_timeout_budget(tmp_path: Path) -> None:
    write_docx(tmp_path / "service.docx", "หลักฐาน", title="ขอใช้ไฟฟ้า")
    client = FakeClient(
        [
            '{"sourceIds":["service.docx"]}',
            '{"answer":"คำตอบ","citations":[{"sourceId":"service.docx","snippet":"หลักฐาน"}]}',
        ],
        delays=[0.1, 0.1],
    )
    service = FullDocumentKnowledgeBackend(
        api_key="test-key",
        source_root=tmp_path,
        client_factory=lambda _: client,
        timeout_seconds=0.15,
    )

    evidence = asyncio.run(service.search("ต้องใช้เอกสารอะไร", 1))

    assert evidence.answer_context == "คำตอบ"
    assert evidence.result_count == 1
