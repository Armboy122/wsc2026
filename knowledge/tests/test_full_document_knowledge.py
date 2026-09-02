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
    _extract_docx_text,
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


def test_committed_tou_tariff_document_is_catalogued_with_verifiable_rates() -> None:
    source_root = Path(__file__).resolve().parents[1] / "source"
    backend = FullDocumentKnowledgeBackend(api_key="test-key", source_root=source_root)

    catalog = backend._catalog()
    document = catalog["PEA_อัตราค่าไฟฟ้า_TOU_2569.docx"]
    text = _extract_docx_text(document.path)

    assert document.title == "อัตราค่าไฟฟ้า TOU (Time of Use) ปี 2569"
    assert "Peak 5.1135 บาท/หน่วย" in text
    assert "Off-Peak 2.6037 บาท/หน่วย" in text
    assert "วันแรงงานแห่งชาติ วันพืชมงคล" in text
    assert "https://www.pea.co.th/sites/default/files/documents/tariff/electricity_tariff.pdf" in text


def test_committed_tou_tariff_document_returns_a_grounded_citation() -> None:
    source_root = Path(__file__).resolve().parents[1] / "source"
    snippet = "Peak: วันจันทร์-วันศุกร์ เวลา 09.00-22.00 น."
    service, _ = backend(
        source_root,
        [
            '{"sourceIds":["PEA_อัตราค่าไฟฟ้า_TOU_2569.docx"]}',
            '{"answer":"Peak คือวันจันทร์-วันศุกร์ เวลา 09.00-22.00 น.",'
            '"citations":[{"sourceId":"PEA_อัตราค่าไฟฟ้า_TOU_2569.docx",'
            f'"snippet":"{snippet}"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("อยากรู้อัตรค่าบริการ TOU", 3))

    assert evidence.result_count == 1
    assert evidence.citations[0].source_id == "PEA_อัตราค่าไฟฟ้า_TOU_2569.docx"
    assert evidence.citations[0].snippet == snippet


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


def test_answer_url_verbatim_from_selected_document_is_accepted(tmp_path: Path) -> None:
    url = "https://sabuyservice.pea.co.th/sub-menu/b3c04204-212c-418c-98a2-08dcb8233569"
    write_docx(tmp_path / "service.docx", f"สมัครออนไลน์ได้ที่ {url}", title="ขอใช้ไฟฟ้าใหม่")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["service.docx"]}',
            f'{{"answer":"สมัครออนไลน์ได้\\nดำเนินการออนไลน์: {url}","citations":[{{"sourceId":"service.docx","snippet":"สมัครออนไลน์ได้ที่ {url}"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("สมัครออนไลน์ที่ไหน", 1))

    assert evidence.result_count == 1
    assert url in evidence.answer_context


def test_service_answer_prompt_requests_one_clickable_online_call_to_action(tmp_path: Path) -> None:
    url = "https://sabuyservice.pea.co.th/sub-menu/b3c04204-212c-418c-98a2-08dcb8233569"
    write_docx(tmp_path / "service.docx", f"ยื่นคำขอออนไลน์ได้ที่ {url}", title="ขอใช้ไฟฟ้าใหม่")
    service, client = backend(
        tmp_path,
        [
            '{"sourceIds":["service.docx"]}',
            f'{{"answer":"ยื่นคำขอใช้ไฟฟ้าใหม่ได้ทางออนไลน์\\nดำเนินการออนไลน์: {url}",'
            f'"citations":[{{"sourceId":"service.docx","snippet":"ยื่นคำขอออนไลน์ได้ที่ {url}"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("ขอลิงก์ยื่นขอใช้ไฟฟ้าใหม่", 1))

    assert evidence.answer_context == f"ยื่นคำขอใช้ไฟฟ้าใหม่ได้ทางออนไลน์\nดำเนินการออนไลน์: {url}"
    prompt = client.calls[1]["contents"]
    assert "directly, completely, and concisely" in prompt
    assert "at most three short bullets or sentences" in prompt
    assert "ดำเนินการออนไลน์: <URL>" in prompt
    assert "exactly one primary" in prompt
    assert "no punctuation after the URL" in prompt


def test_non_concise_or_malformed_online_action_answers_fail_closed(tmp_path: Path) -> None:
    url = "https://sabuyservice.pea.co.th/sub-menu/b3c04204-212c-418c-98a2-08dcb8233569"
    source_text = f"ยื่นคำขอออนไลน์ได้ที่ {url}"
    write_docx(tmp_path / "service.docx", source_text, title="ขอใช้ไฟฟ้าใหม่")
    invalid_answers = (
        "หนึ่ง. สอง. สาม. สี่.",
        f"ดำเนินการออนไลน์: {url}\\nดำเนินการออนไลน์: {url}",
        f"ดำเนินการออนไลน์: {url}\\nรายละเอียดเพิ่มเติม",
        f"สมัครออนไลน์ได้ที่ {url}",
        "สมัครออนไลน์ได้\nดำเนินการออนไลน์: เปิดเว็บไซต์",
    )

    for answer in invalid_answers:
        service, _ = backend(
            tmp_path,
            [
                '{"sourceIds":["service.docx"]}',
                json.dumps({"answer": answer, "citations": [{"sourceId": "service.docx", "snippet": source_text}]}),
            ],
        )

        evidence = asyncio.run(service.search("ขอใช้ไฟฟ้าใหม่", 1))

        assert evidence.result_count == 0
        assert evidence.answer_context == ""
        assert evidence.citations == ()


def test_answer_url_with_appended_punctuation_fails_closed(tmp_path: Path) -> None:
    """พรอมต์ห้ามเติมวรรคตอนต่อท้าย URL — คำตอบที่เติมแล้วต้อง fail closed"""
    url = "https://cdp.pea.co.th/"
    write_docx(tmp_path / "deposit.docx", f"ขอคืนเงินประกันได้ที่ {url}", title="คืนเงินประกัน")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["deposit.docx"]}',
            f'{{"answer":"ดูรายละเอียดที่ {url}.","citations":[{{"sourceId":"deposit.docx","snippet":"ขอคืนเงินประกันได้ที่ {url}"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("คืนเงินประกัน", 1))

    assert evidence.result_count == 0
    assert evidence.answer_context == ""
    assert evidence.citations == ()


def test_answer_url_with_modified_token_fails_closed(tmp_path: Path) -> None:
    """URL ที่ถูกดัดแปลง/เติมอักขระใน token (แม้มี prefix ตรง) ต้อง fail closed"""
    url = "https://sabuyservice.pea.co.th/status/login"
    write_docx(tmp_path / "service.docx", f"ติดตามสถานะได้ที่ {url}", title="ติดตามคำขอ")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["service.docx"]}',
            f'{{"answer":"ติดตามสถานะได้ที่ {url}.evil.com","citations":[{{"sourceId":"service.docx","snippet":"ติดตามสถานะได้ที่ {url}"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("ติดตามสถานะ", 1))

    assert evidence.result_count == 0
    assert evidence.answer_context == ""
    assert evidence.citations == ()


def test_answer_with_invented_url_fails_closed(tmp_path: Path) -> None:
    write_docx(tmp_path / "service.docx", "ไม่มีลิงก์ในเอกสารนี้", title="ขอใช้ไฟฟ้า")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["service.docx"]}',
            '{"answer":"ดูรายละเอียดที่ https://evil.example.net/steal","citations":[{"sourceId":"service.docx","snippet":"ไม่มีลิงก์ในเอกสารนี้"}]}',
        ],
    )

    evidence = asyncio.run(service.search("สมัครที่ไหน", 1))

    assert evidence.result_count == 0
    assert evidence.answer_context == ""
    assert evidence.citations == ()


def test_answer_url_from_unselected_document_fails_closed(tmp_path: Path) -> None:
    url = "https://installment.pea.co.th/Register"
    write_docx(tmp_path / "selected.docx", "เอกสารที่เลือก", title="อัตราค่าไฟ")
    write_docx(tmp_path / "unselected.docx", f"ผ่อนชำระได้ที่ {url}", title="ผ่อนชำระ")
    service, _ = backend(
        tmp_path,
        [
            '{"sourceIds":["selected.docx"]}',
            f'{{"answer":"ผ่อนชำระได้ที่ {url}","citations":[{{"sourceId":"selected.docx","snippet":"เอกสารที่เลือก"}}]}}',
        ],
    )

    evidence = asyncio.run(service.search("ผ่อนชำระ", 1))

    assert evidence.result_count == 0
    assert evidence.answer_context == ""
    assert evidence.citations == ()
