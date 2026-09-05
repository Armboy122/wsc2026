"""registry ของเครื่องมือที่เปิดใช้งาน: Knowledge เป็น built-in ส่วนที่เหลือมาจากปลั๊กอิน"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID

from pydantic import ValidationError

from app.agent.operation_policy import OperationLimits, OperationPolicy, OperationSpec
from app.agent.response_policy import ResponsePolicies, ResponsePolicy
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
from app.llm.models import ToolDefinition

# Knowledge เป็นความสามารถหลักที่ไม่ผ่านระบบปลั๊กอิน จึงประกาศแค็ตตาล็อกไว้ที่เดียว
BUILT_IN_CATALOGUE: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        ToolName.KNOWLEDGE,
        "ตอบความรู้ PEA จากข้อความฉบับเต็มของไฟล์ที่เลือก",
        ("search",),
    ),
)

# planner มักขยายถ้อยคำค้นหาภาษาไทยเล็กน้อยทุกรอบ ทำให้ guard กัน input ซ้ำตรง ๆ จับไม่ได้
# จึงจำกัดจำนวนค้นหาความรู้ต่อเทิร์น แล้วใช้ผลที่ค้นได้แล้วไปเรียบเรียงคำตอบต่อ
_MAX_KNOWLEDGE_SEARCHES_PER_TURN = 2

# Knowledge ไม่ผ่าน plugin manifest จึงประกาศ policy ของตัวเองไว้ที่เดียวตรงนี้
# (ปลั๊กอินอื่นประกาศผ่าน operations ใน plugin.yaml — ดู app/plugins/manifest.py)
BUILT_IN_OPERATION_SPECS: dict[ToolAction, OperationSpec] = {
    ToolAction.KNOWLEDGE_SEARCH: OperationSpec(
        policy=OperationPolicy.GROUNDED_ANSWER,
        limits=OperationLimits(max_calls_per_turn=_MAX_KNOWLEDGE_SEARCHES_PER_TURN),
    ),
}


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
    """registry ของเครื่องมือที่เปิดใช้งานจริง โดย Knowledge ต้องมีเสมอ

    เครื่องมือปฏิบัติการอื่นมาจาก plugin loader จึงไม่บังคับว่าต้องมี OMS
    ทำให้ปิดปลั๊กอินใน manifest แล้วระบบยังเริ่มทำงานได้
    """

    def __init__(
        self,
        tools: tuple[Tool, ...] | list[Tool],
        *,
        catalogue: tuple[ToolDefinition, ...] | None = None,
        response_policies: tuple[ResponsePolicy, ...] = (),
        operation_specs: Mapping[ToolAction, OperationSpec] | None = None,
    ) -> None:
        by_name: dict[ToolName, Tool] = {}
        for tool in tools:
            if tool.name in by_name:
                raise ValueError(f"ลงทะเบียนเครื่องมือซ้ำ: {tool.name.value}")
            by_name[tool.name] = tool
        if ToolName.KNOWLEDGE not in by_name:
            raise ValueError("registry ต้องมีเครื่องมือ Knowledge ที่เป็น built-in เสมอ")
        for name, tool in by_name.items():
            if name is not ToolName.KNOWLEDGE and not callable(getattr(tool, "reset", None)):
                raise ValueError(f"เครื่องมือปฏิบัติการต้องรีเซ็ตได้: {name.value}")
        self._tools = by_name
        self._response_policies = ResponsePolicies(response_policies)
        self._catalogue = BUILT_IN_CATALOGUE + tuple(catalogue or ())
        declared = {definition.name for definition in self._catalogue}
        unknown = declared - frozenset(by_name)
        if unknown:
            raise ValueError(
                f"แค็ตตาล็อกอ้างถึงเครื่องมือที่ไม่ได้ลงทะเบียน: {sorted(name.value for name in unknown)}"
            )
        self._operation_specs: dict[ToolAction, OperationSpec] = {
            **BUILT_IN_OPERATION_SPECS,
            **(operation_specs or {}),
        }

    @property
    def llm_catalogue(self) -> tuple[ToolDefinition, ...]:
        """แค็ตตาล็อกที่ Main Agent ส่งให้ LLM โดยไม่รวม action ที่เป็น internal"""
        return self._catalogue

    @property
    def operation_specs(self) -> Mapping[ToolAction, OperationSpec]:
        """policy ต่อ operation ทั้งหมดที่ประกาศไว้ (built-in + ปลั๊กอิน)"""
        return self._operation_specs

    def operation_spec(self, action: ToolAction) -> OperationSpec:
        """policy ของ operation นี้ — ไม่ประกาศ = ค่าเริ่มต้น plain_read (fail safe, ARCHITECTURE-V2.md §4.5)"""
        return self._operation_specs.get(action, OperationSpec())

    def operation_spec_for_call(self, call: ToolCall) -> OperationSpec:
        return self.operation_spec(call.action)

    def operation_spec_for_result(self, result: ToolResult) -> OperationSpec:
        return self.operation_spec(result.action)

    @property
    def response_policies(self) -> ResponsePolicies:
        """Presentation policies contributed by the tools that are actually enabled."""
        return self._response_policies

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
