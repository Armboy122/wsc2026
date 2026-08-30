"""Provider adapter contracts. Providers translate; they do not hold PEA policy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.models import LLMRequest, LLMResponse


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete one provider-neutral request."""


class LLMUnavailableError(RuntimeError):
    """A provider could not return a safe, usable completion."""
