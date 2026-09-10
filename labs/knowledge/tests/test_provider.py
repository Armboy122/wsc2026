import json

import httpx
import pytest
from voice_assistant.contracts import DraftAnswer, Evidence, Statement
from voice_assistant.providers import GeminiProvider, validate_evidence

DOC = Evidence(source_id="doc", title="เอกสาร", version="abc", text="เอกสารต้องใช้บัตรประชาชน ดู https://example.org/ok")


@pytest.mark.parametrize("source,quote,text", [
    ("other", "เอกสารต้องใช้บัตรประชาชน", "คำตอบ"),
    ("doc", "ข้อความที่ไม่มีอยู่จริง", "คำตอบ"),
    ("doc", "เอกสารต้องใช้บัตรประชาชน", "ไปที่ https://evil.example/"),
])
def test_reject_forged_source_quote_and_url(source, quote, text):
    draft = DraftAnswer(status="answered", statements=(Statement(text=text, source_id=source, quote=quote),))
    with pytest.raises(ValueError):
        validate_evidence(draft, (DOC,))


async def test_gemini_contract_uses_single_call_and_parses_all_text_parts():
    calls = []
    draft = DraftAnswer(status="answered", statements=(Statement(text="ใช้บัตรประชาชน", source_id="doc", quote="เอกสารต้องใช้บัตรประชาชน"),))
    def handler(request):
        calls.append(request)
        data = json.loads(request.content)
        assert data["generationConfig"]["responseJsonSchema"]
        assert "sources" in data["contents"][0]["parts"][0]["text"]
        raw = draft.model_dump_json()
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "hidden", "thought": True}, {"text": raw[:20]}, {"text": raw[20:]}
        ]}}]})
    provider = GeminiProvider("fake-key", "model-test", transport=httpx.MockTransport(handler))
    result = await provider.answer("คำถาม", [], (DOC,))
    assert result == draft
    assert len(calls) == 1
    await provider.close()


async def test_provider_http_error_does_not_retry():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429)
    provider = GeminiProvider("fake", "model", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.answer("คำถาม", [], (DOC,))
    assert len(calls) == 1
    await provider.close()
