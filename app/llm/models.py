"""Provider-neutral values used at the Main Agent LLM boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.contracts import ToolCall, ToolName


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """A deliberately small chat message; it never carries hidden reasoning."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A tool catalogue item visible to an LLM provider."""

    name: ToolName
    description: str
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    tools: tuple[ToolDefinition, ...]
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A provider response translated into local, validated tool calls."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    provider_metadata: dict[str, Any] = field(default_factory=dict)
