"""Deterministic planning seam contributed by enabled operational plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.contracts import ToolAction, ToolName
from app.llm.models import LLMMessage


@dataclass(frozen=True, slots=True)
class DemoToolCall:
    position: int
    name: ToolName
    action: ToolAction
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DemoPlan:
    calls: tuple[DemoToolCall, ...] = ()
    direct_response: str | None = None
    exclusive: bool = False


class DemoBehavior(Protocol):
    """No-I/O plugin behavior used only by the offline demo adapter."""

    def plan_demo(self, message: str, correlation_id: UUID) -> DemoPlan | None: ...

    def after_tools_demo(
        self,
        messages: tuple[LLMMessage, ...],
        results: tuple[dict[str, Any], ...],
        correlation_id: UUID,
    ) -> DemoPlan | None: ...

    def has_demo_intent(self, message: str) -> bool: ...
