"""Generic presentation seams supplied by enabled operational plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.contracts import ToolErrorCode, ToolResult, ToolResultStatus


@dataclass(frozen=True, slots=True)
class ErrorPresentation:
    """Safe error facts a plugin permits the LLM and user to see."""

    code: ToolErrorCode
    explanation: str
    next_step: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.explanation.strip() or len(self.explanation) > 500:
            raise ValueError("error explanation ต้องมีความยาว 1-500 ตัวอักษร")
        if not self.next_step.strip() or len(self.next_step) > 500:
            raise ValueError("error next_step ต้องมีความยาว 1-500 ตัวอักษร")

    def fallback_message(self) -> str:
        return (
            f"{self.explanation.strip()} {self.next_step.strip()}\n"
            f"รหัสข้อผิดพลาด: {self.code.value}"
        )

    def llm_payload(self) -> dict[str, object]:
        return {
            "explanation": self.explanation.strip(),
            "nextStep": self.next_step.strip(),
        }


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

    def error_presentation(self, result: ToolResult) -> ErrorPresentation | None: ...

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

    def error_presentation(self, result: ToolResult) -> ErrorPresentation | None:
        if result.status is not ToolResultStatus.ERROR or result.error is None:
            return None
        for policy in self.policies:
            presentation = policy.error_presentation(result)
            if presentation is not None and presentation.code is result.error.code:
                return presentation
        return None

    def grounds_followup(self, result: ToolResult) -> bool:
        return any(policy.grounds_followup(result) for policy in self.policies)
