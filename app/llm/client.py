"""Small provider-agnostic LLM clients used by the Main Agent."""

from __future__ import annotations

from app.llm.adapter import LLMAdapter
from app.llm.models import LLMRequest, LLMResponse


class LLMClient:
    """Application-facing client which deliberately exposes no provider SDK types."""

    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._adapter.complete(request)

    @property
    def ready(self) -> bool:
        return True


class JudgeLLMClient(LLMClient):
    """Named integration seam for a judge-provided ``LLMAdapter`` implementation."""
