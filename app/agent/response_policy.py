"""Generic presentation seams supplied by enabled operational plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.contracts import ToolResult


class ResponsePolicy(Protocol):
    """Present a plugin's trusted tool outcomes without coupling MainAgent to it."""

    planner_instructions: str

    def direct_message(
        self,
        kind: str,
        followup_text: str,
        allow_grounded_followup: bool,
    ) -> str | None: ...

    def result_fact(self, result: ToolResult) -> str | None: ...

    def error_message(self, result: ToolResult) -> str | None: ...

    def grounds_followup(self, result: ToolResult) -> bool: ...


@dataclass(frozen=True, slots=True)
class ResponsePolicies:
    """Dispatch presentation to enabled plugins in deterministic registry order."""

    policies: tuple[ResponsePolicy, ...] = ()

    @property
    def planner_instructions(self) -> tuple[str, ...]:
        return tuple(policy.planner_instructions for policy in self.policies)

    def direct_message(self, kind: str, followup_text: str, allow_grounded_followup: bool) -> str | None:
        return next(
            (
                message
                for policy in self.policies
                if (message := policy.direct_message(kind, followup_text, allow_grounded_followup)) is not None
            ),
            None,
        )

    def result_fact(self, result: ToolResult) -> str | None:
        for policy in self.policies:
            if (fact := policy.result_fact(result)) is not None:
                return fact
        return None

    def error_message(self, result: ToolResult) -> str | None:
        for policy in self.policies:
            if (message := policy.error_message(result)) is not None:
                return message
        return None

    def grounds_followup(self, result: ToolResult) -> bool:
        return any(policy.grounds_followup(result) for policy in self.policies)
