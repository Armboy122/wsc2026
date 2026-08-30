"""Fixed, validated registry for the four permitted top-level tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import ValidationError

from app.contracts import (
    TOOL_ACTIONS,
    ToolAction,
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    validate_tool_input,
    validate_tool_success_data,
)


@dataclass(frozen=True, slots=True)
class ToolContext:
    conversation_id: UUID
    trace_id: UUID


@runtime_checkable
class Tool(Protocol):
    name: ToolName

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Execute a prevalidated call using the supplied request context."""


class ToolRegistry:
    """Registry that can contain exactly the frozen four tools, once each."""

    _required_names = frozenset(ToolName)

    def __init__(self, tools: tuple[Tool, ...] | list[Tool]) -> None:
        by_name: dict[ToolName, Tool] = {}
        for tool in tools:
            if tool.name in by_name:
                raise ValueError(f"duplicate tool registration: {tool.name.value}")
            by_name[tool.name] = tool
        if frozenset(by_name) != self._required_names:
            missing = self._required_names - frozenset(by_name)
            extra = frozenset(by_name) - self._required_names
            raise ValueError(f"registry must contain exactly four frozen tools; missing={missing}, extra={extra}")
        for name, tool in by_name.items():
            if name is not ToolName.KNOWLEDGE and not callable(getattr(tool, "reset", None)):
                raise ValueError(f"operational tool must be resettable: {name.value}")
        self._tools = by_name

    def reset(self) -> None:
        """Reset every operational tool exactly once for a fresh demo run."""
        for name, tool in self._tools.items():
            if name is not ToolName.KNOWLEDGE:
                tool.reset()  # type: ignore[attr-defined]  # Validated at registration.

    @property
    def names(self) -> frozenset[ToolName]:
        return frozenset(self._tools)

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        if call.name not in self._tools or call.action not in TOOL_ACTIONS[call.name]:
            return _error_result(call, ToolErrorCode.INVALID_INPUT, "Unknown tool or action")
        try:
            validate_tool_input(call)
        except ValidationError:
            return _error_result(call, ToolErrorCode.INVALID_INPUT, "Tool input does not match the action contract")

        try:
            result = await self._tools[call.name].execute(call, context)
        except Exception:
            return _error_result(call, ToolErrorCode.UNAVAILABLE, "The requested service is temporarily unavailable")

        if result.call_id != call.call_id or result.name != call.name or result.action != call.action:
            return _error_result(call, ToolErrorCode.INTERNAL, "The service returned an invalid result")
        if result.status is ToolResultStatus.SUCCESS:
            try:
                validate_tool_success_data(call.action, result.data or {})
            except ValidationError:
                return _error_result(call, ToolErrorCode.INTERNAL, "The service returned invalid data")
        return result


def _error_result(call: ToolCall, code: ToolErrorCode, message: str) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        name=call.name,
        action=call.action,
        status=ToolResultStatus.ERROR,
        error=ToolError(code=code, message=message),
        simulation=call.name is not ToolName.KNOWLEDGE,
    )
