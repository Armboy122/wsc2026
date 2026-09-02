"""Typed and ownership-bound contributions returned by plugin factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agent.response_policy import ResponsePolicy
from app.contracts import ToolAction, ToolName
from app.llm.demo_behavior import DemoBehavior, DemoPlan
from app.llm.models import LLMMessage


@dataclass(frozen=True, slots=True)
class PluginRuntime:
    tool: Any
    response_policy: ResponsePolicy | None = None
    demo_behavior: DemoBehavior | None = None


@dataclass(frozen=True, slots=True)
class BoundDemoBehavior:
    """Fail closed when a plugin proposes another tool or a hidden action."""

    behavior: DemoBehavior
    tool_name: ToolName
    allowed_actions: frozenset[ToolAction]

    def has_demo_intent(self, message: str) -> bool:
        return self.behavior.has_demo_intent(message)

    def plan_demo(self, message: str, correlation_id: UUID) -> DemoPlan | None:
        return self._validate(self.behavior.plan_demo(message, correlation_id))

    def after_tools_demo(
        self,
        messages: tuple[LLMMessage, ...],
        results: tuple[dict[str, Any], ...],
        correlation_id: UUID,
    ) -> DemoPlan | None:
        return self._validate(
            self.behavior.after_tools_demo(messages, results, correlation_id)
        )

    def _validate(self, plan: DemoPlan | None) -> DemoPlan | None:
        if plan is None:
            return None
        if any(
            call.name is not self.tool_name or call.action not in self.allowed_actions
            for call in plan.calls
        ):
            raise ValueError(
                f"demo behavior ของ {self.tool_name.value} เสนอ tool/action นอก manifest"
            )
        return plan
