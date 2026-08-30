"""Deterministic adapter for demos and tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.llm.adapter import LLMUnavailableError
from app.llm.models import LLMRequest, LLMResponse


class ScriptedLLMAdapter:
    """Return responses in order without inspecting data or contacting a provider."""

    def __init__(self, responses: Iterable[LLMResponse] = ()) -> None:
        self._responses: deque[LLMResponse] = deque(responses)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMUnavailableError("No scripted LLM response is available")
        return self._responses.popleft()

    def append(self, response: LLMResponse) -> None:
        self._responses.append(response)
