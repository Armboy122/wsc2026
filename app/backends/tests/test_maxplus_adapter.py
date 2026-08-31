"""ทดสอบ MaxPlus adapter โดยไม่เรียก network จริง"""

from uuid import uuid4

import pytest

from app.llm.maxplus import MaxPlusDeepSeekAdapter
from app.llm.models import LLMMessage, LLMRequest, ToolDefinition
from app.contracts import ToolName


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": '{"message":"","toolCalls":[],"directResponse":null}'}}]}


_request_capture: dict[str, object] = {}


class _Client:
    def __init__(self, **kwargs: object) -> None:
        _request_capture["client_kwargs"] = kwargs

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> _Response:
        _request_capture.update({"url": url, **kwargs})
        return _Response()


@pytest.mark.asyncio
async def test_adapter_calls_configured_deepseek_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.maxplus.httpx.AsyncClient", _Client)
    adapter = MaxPlusDeepSeekAdapter(
        api_key="secret",
        base_url="https://api.maxplus-ai.cc/v1/",
        model="deepseek-v4-flash-0731",
    )
    request = LLMRequest(
        messages=(LLMMessage("user", "สวัสดี"),),
        tools=(ToolDefinition(ToolName.KNOWLEDGE, "ค้นหา", ("search",)),),
        correlation_id=uuid4(),
    )

    result = await adapter.complete(request)

    payload = _request_capture["json"]
    assert _request_capture["url"] == "https://api.maxplus-ai.cc/v1/chat/completions"
    assert _request_capture["headers"] == {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-flash-0731"
    assert "inputSchema" in str(payload["messages"])
    assert result.provider_metadata == {"provider": "maxplus_openai", "model": "deepseek-v4-flash-0731"}
    assert result.text.startswith("{")


@pytest.mark.asyncio
async def test_adapter_prompt_contains_current_voc_intake_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.maxplus.httpx.AsyncClient", _Client)
    adapter = MaxPlusDeepSeekAdapter(
        api_key="secret",
        base_url="https://api.maxplus-ai.cc/v1/",
        model="deepseek-v4-flash-0731",
    )
    request = LLMRequest(
        messages=(
            LLMMessage("user", "ร้องเรียนการบริการหน่อย"),
            LLMMessage("assistant", "กรุณาเล่ารายละเอียดเรื่องร้องเรียน"),
            LLMMessage("user", "ไฟดับบ่อยมากที่บ้านฉัน"),
        ),
        tools=(ToolDefinition(ToolName.VOC, "รับและติดตามเรื่องร้องเรียน", ("prepare_case", "get_case")),),
        correlation_id=uuid4(),
    )

    await adapter.complete(request)

    payload = _request_capture["json"]
    assert isinstance(payload, dict)
    system_prompt = payload["messages"][0]["content"]
    assert "voc_contact_name" in system_prompt
    assert "voc_tracking_inputs" in system_prompt
    assert "ห้ามเรียก `voc_tool.prepare_case` จนกว่าข้อมูลจะครบ" in system_prompt
    assert "คำตอบภาษาธรรมชาติ" in system_prompt


@pytest.mark.asyncio
async def test_adapter_rejects_untrusted_endpoint() -> None:
    adapter = MaxPlusDeepSeekAdapter(api_key="secret", base_url="http://evil.example/v1")
    assert await adapter.ready() is False
