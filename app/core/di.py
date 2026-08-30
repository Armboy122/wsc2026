"""Dependency-injection service protocol for the FastAPI platform.

HTTP handlers delegate to the Main Agent interface; they contain no business
policy and never invoke tools directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.contracts import (
    ChatResponse,
    PendingAction,
    ToolCall,
    ToolResult,
)


@runtime_checkable
class MainAgent(Protocol):
    """The sole orchestrator called by platform routes."""

    async def handle_chat(
        self,
        *,
        conversation_id: UUID | None,
        message: str,
        request_id: UUID | None,
        trace_id: UUID,
    ) -> ChatResponse:
        """Handle a chat message and return a frozen contract response."""
        ...

    async def confirm_pending_action(
        self,
        *,
        pending_action_id: UUID,
        confirmation_note: str | None,
        trace_id: UUID,
    ) -> tuple[PendingAction, ToolResult | None]:
        """Submit a pending action once; idempotent on repeat calls."""
        ...

    async def reject_pending_action(
        self,
        *,
        pending_action_id: UUID,
        reason: str,
        trace_id: UUID,
    ) -> PendingAction:
        """Reject a pending action; terminal and idempotent."""
        ...

    async def get_trace(self, *, trace_id: UUID) -> list[dict[str, Any]]:
        """Return ordered, redacted trace events for a trace id."""
        ...

    async def reset_demo(self) -> None:
        """Clear all in-process demo state."""
        ...


class AgentService:
    """Concrete container for the Main Agent and platform adapters.

    The lead worker wires this in app.main via set_agent; platform code never
    constructs a Main Agent implementation.
    """

    def __init__(self) -> None:
        self._agent: MainAgent | None = None

    def set_agent(self, agent: MainAgent) -> None:
        self._agent = agent

    @property
    def agent(self) -> MainAgent:
        if self._agent is None:
            raise RuntimeError("Main Agent has not been wired to AgentService")
        return self._agent


agent_service = AgentService()


@runtime_checkable
class Tool(Protocol):
    """Narrow runtime seam for a callable tool module."""

    name: str

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a validated tool call and return a frozen ToolResult."""
        ...


@runtime_checkable
class LLMAdapter(Protocol):
    """Provider-agnostic LLM seam referenced by the platform for health checks."""

    async def ready(self) -> bool:
        """Return True when the adapter can serve requests."""
        ...


@runtime_checkable
class KnowledgeBackend(Protocol):
    """Readiness seam for the knowledge backend."""

    async def ready(self) -> bool:
        """Return True when the backend can serve retrieval requests."""
        ...


class AdapterService:
    """Container for optional platform adapters used by /health."""

    def __init__(self) -> None:
        self.llm: LLMAdapter | None = None
        self.knowledge: KnowledgeBackend | None = None

    def set_llm(self, adapter: LLMAdapter) -> None:
        self.llm = adapter

    def set_knowledge(self, backend: KnowledgeBackend) -> None:
        self.knowledge = backend


adapter_service = AdapterService()
