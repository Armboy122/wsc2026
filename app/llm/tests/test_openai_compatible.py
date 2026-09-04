"""Tests for the OpenAI-compatible LLM adapter without real network calls."""

from unittest.mock import ANY
from uuid import uuid4

import pytest

from app.llm.models import LLMMessage, LLMRequest
from app.llm.openai_compatible import OpenAICompatibleLLMAdapter


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"message":"","toolCalls":[],"directResponse":null}'
                    }
                }
            ]
        }


_capture: dict[str, object] = {}


class _Client:
    def __init__(self, **kwargs: object) -> None:
        _capture["client_kwargs"] = kwargs

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> _Response:
        _capture.update({"url": url, **kwargs})
        return _Response()


@pytest.mark.asyncio
async def test_openai_compatible_adapter_sends_model_and_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.llm.openai_compatible.httpx.AsyncClient", _Client)
    adapter = OpenAICompatibleLLMAdapter(
        api_key="secret",
        base_url="http://localhost:11434/v1/",
        model="qwen3.8-27b",
        thinking=False,
        effort="high",
    )

    result = await adapter.complete(
        LLMRequest(messages=(LLMMessage("user", "สวัสดี"),), tools=(), correlation_id=uuid4())
    )

    assert _capture["url"] == "http://localhost:11434/v1/chat/completions"
    assert _capture["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret",
    }
    assert _capture["json"] == {
        "model": "qwen3.8-27b",
        "messages": [{"role": "system", "content": ANY}, {"role": "user", "content": "สวัสดี"}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "reasoning_effort": "none",
    }
    assert result.provider_metadata == {
        "provider": "openai-compatible",
        "model": "qwen3.8-27b",
        "thinking": False,
        "effort": "high",
    }


@pytest.mark.asyncio
async def test_openai_compatible_adapter_enables_requested_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.llm.openai_compatible.httpx.AsyncClient", _Client)
    adapter = OpenAICompatibleLLMAdapter(
        api_key=None,
        base_url="https://llm.example/v1",
        model="model-a",
        thinking=True,
        effort="medium",
    )

    await adapter.complete(
        LLMRequest(messages=(LLMMessage("user", "hi"),), tools=(), correlation_id=uuid4())
    )

    assert "Authorization" not in _capture["headers"]
    assert _capture["json"]["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_openai_compatible_adapter_rejects_invalid_endpoint() -> None:
    adapter = OpenAICompatibleLLMAdapter(
        api_key=None, base_url="not-a-url", model="model-a", thinking=False, effort="low"
    )
    assert await adapter.ready() is False
