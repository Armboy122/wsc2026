"""registry แบบคงที่และผ่านการตรวจสอบสำหรับเครื่องมือระดับบนสุดสี่ตัวที่อนุญาต"""

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
        """ดำเนินการเรียกที่ตรวจสอบแล้วโดยใช้บริบทคำขอที่ได้รับ"""


class ToolRegistry:
    """registry ที่เก็บเครื่องมือตามสัญญาได้สี่ตัวพอดี ตัวละหนึ่งรายการ"""

    _required_names = frozenset(ToolName)

    def __init__(self, tools: tuple[Tool, ...] | list[Tool]) -> None:
        by_name: dict[ToolName, Tool] = {}
        for tool in tools:
            if tool.name in by_name:
                raise ValueError(f"ลงทะเบียนเครื่องมือซ้ำ: {tool.name.value}")
            by_name[tool.name] = tool
        if frozenset(by_name) != self._required_names:
            missing = self._required_names - frozenset(by_name)
            extra = frozenset(by_name) - self._required_names
            raise ValueError(f"registry ต้องมีเครื่องมือคงที่สี่ตัวพอดี; ขาด={missing}, เกิน={extra}")
        for name, tool in by_name.items():
            if name is not ToolName.KNOWLEDGE and not callable(getattr(tool, "reset", None)):
                raise ValueError(f"เครื่องมือปฏิบัติการต้องรีเซ็ตได้: {name.value}")
        self._tools = by_name

    def reset(self) -> None:
        """รีเซ็ตเครื่องมือปฏิบัติการทุกตัวเพียงหนึ่งครั้งสำหรับการรันเดโมใหม่"""
        for name, tool in self._tools.items():
            if name is not ToolName.KNOWLEDGE:
                tool.reset()  # type: ignore[attr-defined]  # ตรวจสอบแล้วขณะลงทะเบียน

    @property
    def names(self) -> frozenset[ToolName]:
        return frozenset(self._tools)

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        if call.name not in self._tools or call.action not in TOOL_ACTIONS[call.name]:
            return _error_result(call, ToolErrorCode.INVALID_INPUT, "ไม่รู้จักเครื่องมือหรือการกระทำ")
        try:
            validate_tool_input(call)
        except ValidationError:
            return _error_result(call, ToolErrorCode.INVALID_INPUT, "ข้อมูลนำเข้าของเครื่องมือไม่ตรงกับสัญญาของการกระทำ")

        try:
            result = await self._tools[call.name].execute(call, context)
        except Exception:
            return _error_result(call, ToolErrorCode.UNAVAILABLE, "บริการที่ร้องขอไม่พร้อมใช้งานชั่วคราว")

        if result.call_id != call.call_id or result.name != call.name or result.action != call.action:
            return _error_result(call, ToolErrorCode.INTERNAL, "บริการส่งผลลัพธ์ที่ไม่ถูกต้อง")
        if result.status is ToolResultStatus.SUCCESS:
            try:
                validate_tool_success_data(call.action, result.data or {})
            except ValidationError:
                return _error_result(call, ToolErrorCode.INTERNAL, "บริการส่งข้อมูลที่ไม่ถูกต้อง")
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
