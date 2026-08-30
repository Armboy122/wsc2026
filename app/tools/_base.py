"""Shared scaffolding for the three simulated operational tools.

Each concrete tool validates its action input and success data against the frozen
``app.contracts`` models before returning a ``ToolResult``. Every result produced
here is operational data and therefore carries ``simulation: true``.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.backends import BackendError
from app.contracts import (
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    validate_tool_input,
    validate_tool_success_data,
)


class SimulatedTool:
    """Base class implementing the narrow ``execute`` seam for simulated tools."""

    name: ToolName
    backend: Any

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        """Validate the call, dispatch to the backend, and return a typed result."""
        if call.name != self.name:
            return self._error(
                call,
                ToolErrorCode.INVALID_INPUT,
                f"Tool {call.name.value} does not handle this call.",
            )
        try:
            input_model = validate_tool_input(call)
        except ValidationError:
            return self._error(
                call,
                ToolErrorCode.INVALID_INPUT,
                f"Invalid input for {call.action.value}.",
            )
        try:
            data = self._run(call.action, input_model)
        except BackendError as exc:
            return self._error(call, exc.code, exc.message)
        except Exception:  # noqa: BLE001 - fail closed on any unexpected backend error
            return self._error(call, ToolErrorCode.INTERNAL, "Unexpected internal error.")
        try:
            output_model = validate_tool_success_data(call.action, data)
        except ValidationError:
            return self._error(call, ToolErrorCode.INTERNAL, "Tool produced invalid output.")
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data=output_model.model_dump(by_alias=True, mode="json"),
            error=None,
            citations=(),
            simulation=True,
        )

    def reset(self) -> None:
        """Reset this tool's backend state (delegates to the backend)."""
        self.backend.reset()

    def _run(self, action: Any, input_model: Any) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _error(call: ToolCall, code: ToolErrorCode, message: str) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            data=None,
            error=ToolError(code=code, message=message),
            citations=(),
            simulation=True,
        )
