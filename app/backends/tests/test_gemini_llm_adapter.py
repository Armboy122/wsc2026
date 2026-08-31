"""ทดสอบ Gemini Main-Agent adapter โดยไม่เรียกเครือข่ายจริง"""

from uuid import uuid4

import pytest

from app.contracts import ToolName
from app.llm.factory import LLMProviderConfig, create_llm_adapter
from app.llm.gemini import GeminiLLMAdapter
from app.llm.models import LLMMessage, LLMRequest, ToolDefinition


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"message":"","toolCalls":[],"directResponse":null}'
                            }
                        ]
                    }
                }
            ]
        }


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
async def test_gemini_adapter_calls_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gemini.httpx.AsyncClient", _Client)
    adapter = GeminiLLMAdapter(api_key="secret", model="gemini-2.5-flash")
    request = LLMRequest(
        messages=(LLMMessage("user", "สวัสดี"),),
        tools=(ToolDefinition(ToolName.KNOWLEDGE, "ค้นหา", ("search",)),),
        correlation_id=uuid4(),
    )

    result = await adapter.complete(request)

    assert _request_capture["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.5-flash:generateContent"
    )
    assert _request_capture["headers"] == {
        "Content-Type": "application/json",
        "x-goog-api-key": "secret",
    }
    payload = _request_capture["json"]
    assert isinstance(payload, dict)
    assert payload["generationConfig"] == {
        "temperature": 0,
        "responseMimeType": "application/json",
    }
    assert "inputSchema" in str(payload["systemInstruction"])
    assert result.provider_metadata == {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
    }
    assert result.text.startswith("{")


@pytest.mark.asyncio
async def test_factory_forwards_trusted_gemini_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gemini.httpx.AsyncClient", _Client)
    adapter = create_llm_adapter(
        LLMProviderConfig(
            provider="gemini",
            api_key="secret",
            model="gemini-2.5-flash",
            base_url="https://generativelanguage.googleapis.com/v1",
        )
    )
    request = LLMRequest(
        messages=(LLMMessage("user", "สวัสดี"),),
        tools=(),
        correlation_id=uuid4(),
    )

    await adapter.complete(request)

    assert _request_capture["url"] == (
        "https://generativelanguage.googleapis.com/v1/"
        "models/gemini-2.5-flash:generateContent"
    )


@pytest.mark.asyncio
async def test_gemini_adapter_requires_key_model_and_trusted_endpoint() -> None:
    assert await GeminiLLMAdapter(api_key=None, model="gemini-2.5-flash").ready() is False
    assert await GeminiLLMAdapter(api_key="secret", model="").ready() is False
    adapter = GeminiLLMAdapter(
        api_key="secret",
        model="gemini-2.5-flash",
        base_url="https://evil.example/v1beta",
    )
    assert await adapter.ready() is False
