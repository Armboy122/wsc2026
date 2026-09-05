"""registry ของเครื่องมือที่เปิดใช้งาน: Knowledge เป็น built-in ส่วนที่เหลือมาจากปลั๊กอิน"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable
from uuid import UUID

from pydantic import ValidationError

from app.agent.operation_policy import OperationLimits, OperationPolicy, OperationSpec
from app.agent.response_policy import ResponsePolicies, ResponsePolicy
from app.core.logging import get_logger, log_extra
from app.tools.declarative_tool import DeclarativeTool
from app.contracts import (
    INPUT_MODELS,
    OUTPUT_MODELS,
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

logger = get_logger(__name__)

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
BUILT_IN_OPERATION_SPECS: dict[tuple[str, str], OperationSpec] = {
    (ToolName.KNOWLEDGE.value, ToolAction.KNOWLEDGE_SEARCH.value): OperationSpec(
        policy=OperationPolicy.GROUNDED_ANSWER,
        limits=OperationLimits(max_calls_per_turn=_MAX_KNOWLEDGE_SEARCHES_PER_TURN),
        mode="read",
        exposure="llm",
    ),
}


@dataclass(frozen=True, slots=True)
class ToolContext:
    conversation_id: UUID
    trace_id: UUID


@runtime_checkable
class Tool(Protocol):
    # D2.6: str เฉย ๆ ไม่ใช่ ToolName เสมอไปแล้ว — declarative tool จาก DB มี slug นอก enum
    # (ToolName ยังเป็น str subclass จึงยังใช้ตรงนี้ได้เหมือนเดิมสำหรับ 3 tool เดิม)
    name: str

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """ดำเนินการเรียกที่ตรวจสอบแล้วโดยใช้บริบทคำขอที่ได้รับ"""


def _display_name(name: str) -> str:
    """ข้อความ error อ่านง่าย ไม่ว่า ``name`` จะเป็น enum เดิมหรือ slug ของ declarative tool"""
    return getattr(name, "value", name)


class ToolRegistry:
    """registry ของเครื่องมือที่เปิดใช้งานจริง โดย Knowledge ต้องมีเสมอ

    เครื่องมือปฏิบัติการอื่นมาจาก plugin loader หรือ declarative tool จาก DB จึงไม่บังคับ
    ว่าต้องมี OMS ทำให้ปิดปลั๊กอินใน manifest แล้วระบบยังเริ่มทำงานได้
    """

    def __init__(
        self,
        tools: tuple[Tool, ...] | list[Tool],
        *,
        catalogue: tuple[ToolDefinition, ...] | None = None,
        response_policies: tuple[ResponsePolicy, ...] = (),
        operation_specs: Mapping[Any, OperationSpec] | None = None,
        disabled_code_tools: Iterable[str] | frozenset[str] = (),
        code_tool_enabled_provider: Callable[[str], bool] | None = None,
    ) -> None:
        by_name: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in by_name:
                raise ValueError(f"ลงทะเบียนเครื่องมือซ้ำ: {_display_name(tool.name)}")
            by_name[tool.name] = tool
        if ToolName.KNOWLEDGE not in by_name:
            raise ValueError("registry ต้องมีเครื่องมือ Knowledge ที่เป็น built-in เสมอ")
        for name, tool in by_name.items():
            if name is not ToolName.KNOWLEDGE and not callable(getattr(tool, "reset", None)):
                raise ValueError(f"เครื่องมือปฏิบัติการต้องรีเซ็ตได้: {_display_name(name)}")
        self._tools = by_name
        self._code_tool_state_listeners: list[Callable[[str, bool], None]] = []
        self._code_tool_enabled_provider = code_tool_enabled_provider
        # P4: สถานะปิดของ code tool (เก็บเป็น plain string เสมอ กัน hash ของ str-Enum)
        # knowledge ถูกตัดทิ้งเสมอ เพราะ registry บังคับว่า built-in ตัวนี้ต้องใช้งานได้เสมอ
        # (เส้นทางความรู้คือ critical path — ปิดแล้วคำตอบจะไม่ grounded อีก)
        registered_code_tools = frozenset(
            _display_name(name)
            for name, tool in by_name.items()
            if name != ToolName.KNOWLEDGE and not isinstance(tool, DeclarativeTool)
        )
        self._disabled_code_tools: frozenset[str] = frozenset(
            _display_name(name)
            for name in disabled_code_tools
            if _display_name(name) in registered_code_tools
        )
        self._response_policies = ResponsePolicies(response_policies)
        self._catalogue = BUILT_IN_CATALOGUE + tuple(catalogue or ())
        declared = {definition.name for definition in self._catalogue}
        unknown = declared - frozenset(by_name)
        if unknown:
            raise ValueError(
                f"แค็ตตาล็อกอ้างถึงเครื่องมือที่ไม่ได้ลงทะเบียน: {sorted(_display_name(name) for name in unknown)}"
            )
        specs: dict[tuple[str, str], OperationSpec] = dict(BUILT_IN_OPERATION_SPECS)
        if operation_specs:
            for key, spec in operation_specs.items():
                if isinstance(key, tuple):
                    specs[(str(key[0]), str(key[1]))] = spec
                else:
                    action_str = key.value if hasattr(key, "value") else str(key)
                    matched_tool = None
                    for t_name, t_actions in TOOL_ACTIONS.items():
                        t_action_strs = {a.value if hasattr(a, "value") else str(a) for a in t_actions}
                        if action_str in t_action_strs:
                            matched_tool = t_name.value if hasattr(t_name, "value") else str(t_name)
                            break
                    if matched_tool:
                        specs[(matched_tool, action_str)] = spec
                    else:
                        for t_name, tool_obj in by_name.items():
                            t_acts = getattr(tool_obj, "actions", None)
                            if t_acts and action_str in t_acts:
                                matched_tool = t_name.value if hasattr(t_name, "value") else str(t_name)
                                specs[(matched_tool, action_str)] = spec
                                break
                        if not matched_tool:
                            specs[("", action_str)] = spec
        self._operation_specs: dict[tuple[str, str], OperationSpec] = specs

    @property
    def llm_catalogue(self) -> tuple[ToolDefinition, ...]:
        """แค็ตตาล็อกที่ Main Agent ส่งให้ LLM โดยไม่รวม action ที่เป็น internal

        code tool ที่ถูกปิดจากหน้า admin (P4) หายจากแค็ตตาล็อกนี้ด้วย — LLM ไม่เห็น
        จึงไม่มีทางเรียก ส่วนแค็ตตาล็อกเต็มสำหรับหน้า admin อยู่ที่ ``full_catalogue``
        """
        disabled_code_tools = self.disabled_code_tools
        if not disabled_code_tools:
            return self._catalogue
        return tuple(
            definition
            for definition in self._catalogue
            if _display_name(definition.name) not in disabled_code_tools
        )

    @property
    def full_catalogue(self) -> tuple[ToolDefinition, ...]:
        """แค็ตตาล็อกทุกรายการโดยไม่กรอง tool ที่ถูกปิด — ใช้กับหน้า admin/ชั้นที่ต้องเห็นครบ"""
        return self._catalogue

    @property
    def disabled_code_tools(self) -> frozenset[str]:
        """slug ของ code tool ที่ถูกปิดอยู่ (แหล่งเดียวกับที่ catalogue/dispatch ใช้)"""
        if self._code_tool_enabled_provider is not None:
            return frozenset(
                name for name in self.code_tool_names
                if not self._code_tool_enabled_provider(name)
            )
        return self._disabled_code_tools

    def code_tool_enabled(self, slug: str) -> bool:
        """สถานะเปิด/ปิดปัจจุบันของ code tool — ใช้แสดงผลในหน้า admin"""
        if self._code_tool_enabled_provider is not None:
            return self._code_tool_enabled_provider(_display_name(slug))
        return _display_name(slug) not in self._disabled_code_tools

    def set_code_tool_enabled(self, slug: str, enabled: bool) -> None:
        """เปิด/ปิด code tool ใน registry (in-memory) — ผู้เรียกต้อง persist ลง DB เอง

        เป็น guard ข้อเดียวของระบบ: ห้ามปิด knowledge เพราะ registry บังคับว่า
        built-in ตัวนี้ต้องมีและใช้งานได้เสมอ (ปิดแล้วคำตอบความรู้ไม่ grounded)
        ผู้เรียกควร validate ก่อนเขียน DB แล้วเรียกเมธอดนี้หลัง persist สำเร็จ
        """
        name = _display_name(slug)
        self.validate_code_tool_enabled(name, enabled)
        if enabled:
            self._disabled_code_tools = self._disabled_code_tools - {name}
        else:
            self._disabled_code_tools = self._disabled_code_tools | {name}
        for listener in tuple(self._code_tool_state_listeners):
            try:
                listener(name, enabled)
            except Exception as exc:
                # A failed observer must not turn a committed admin toggle into
                # a 500 or prevent other observers from reaching fail-closed state.
                logger.warning(
                    "code_tool_state_listener_failed",
                    extra=log_extra(
                        slug=name, enabled=enabled, error_type=type(exc).__name__
                    ),
                )

    def add_code_tool_state_listener(
        self, listener: Callable[[str, bool], None]
    ) -> None:
        """Subscribe to code-tool transitions without exposing registry internals."""
        self._code_tool_state_listeners.append(listener)

    def validate_code_tool_enabled(self, slug: str, enabled: bool) -> None:
        """ตรวจ guard ของสถานะ code tool โดยไม่เปลี่ยนสถานะใน registry."""
        if _display_name(slug) == ToolName.KNOWLEDGE.value and not enabled:
            raise ValueError(
                "ปิดเครื่องมือความรู้ (knowledge) ไม่ได้ — เป็นเส้นทางหลักที่ระบบต้องใช้เสมอ"
            )

    def replace_declarative_tools(
        self,
        tools: Iterable[Tool],
        catalogue: Iterable[ToolDefinition],
        operation_specs: Mapping[tuple[str, str], OperationSpec],
    ) -> None:
        """แทนที่ declarative tool (source: db) ทั้งชุดแบบ hot-reload — D3.4 "save แล้วมีผลเลย"

        ตัวที่ไม่ใช่ declarative (knowledge, ปลั๊กอิน Python) ไม่ถูกแตะ — ตรวจด้วย
        ``isinstance(DeclarativeTool)`` เท่านั้น ไม่ใช้ ``source`` ตัดสินใจตอน dispatch ตามเดิม
        (``source`` เป็นข้อมูลสำหรับ admin/health) ลำดับเดิมของ ``_operation_specs`` ที่ไม่ใช่
        declarative คงอยู่ครบ
        """
        old_names = {n for n, t in self._tools.items() if isinstance(t, DeclarativeTool)}
        new_tools = tuple(tools)
        new_names = {t.name for t in new_tools}
        retained = set(self._tools) - old_names
        duplicate = retained & new_names
        if duplicate:
            raise ValueError(f"ลงทะเบียนเครื่องมือซ้ำ slug: {sorted(duplicate)}")
        merged = {n: t for n, t in self._tools.items() if n not in old_names}
        merged.update({t.name: t for t in new_tools})
        self._tools = merged
        # A stale code-state row may be reused by a declarative definition after
        # its plugin is removed; the live declarative tool must not inherit it.
        self._disabled_code_tools = self._disabled_code_tools - new_names
        kept_catalogue = tuple(d for d in self._catalogue if d.name not in old_names)
        self._catalogue = kept_catalogue + tuple(catalogue)
        self._operation_specs = {
            key: spec for key, spec in self._operation_specs.items() if key[0] not in old_names
        }
        self._operation_specs.update(
            {(str(key[0]), str(key[1])): spec for key, spec in operation_specs.items()}
        )

    @property
    def operation_specs(self) -> Mapping[tuple[str, str], OperationSpec]:
        """policy ต่อ operation ทั้งหมดที่ประกาศไว้ (built-in + ปลั๊กอิน + declarative tool)"""
        return self._operation_specs

    def operation_spec(self, tool_slug: str | tuple[str, str], action: str | None = None) -> OperationSpec:
        """policy ของ operation นี้ — ไม่ประกาศ = ค่าเริ่มต้น plain_read (fail safe, ARCHITECTURE-V2.md §4.5)"""
        if isinstance(tool_slug, tuple):
            return self._operation_specs.get((str(tool_slug[0]), str(tool_slug[1])), OperationSpec())
        if action is not None:
            return self._operation_specs.get((str(tool_slug), str(action)), OperationSpec())
        action_str = tool_slug.value if hasattr(tool_slug, "value") else str(tool_slug)
        for (t, a), spec in self._operation_specs.items():
            if a == action_str:
                return spec
        return OperationSpec()

    def operation_spec_for_call(self, call: ToolCall) -> OperationSpec:
        tool_name = call.name.value if hasattr(call.name, "value") else str(call.name)
        action_name = call.action.value if hasattr(call.action, "value") else str(call.action)
        return self.operation_spec(tool_name, action_name)

    def operation_spec_for_result(self, result: ToolResult) -> OperationSpec:
        tool_name = result.name.value if hasattr(result.name, "value") else str(result.name)
        action_name = result.action.value if hasattr(result.action, "value") else str(result.action)
        return self.operation_spec(tool_name, action_name)

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
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    @property
    def code_tool_names(self) -> frozenset[str]:
        """ชื่อ (slug) ของ tool ที่มาจากโค้ด — built-in + ปลั๊กอิน Python ไม่รวม declarative จาก DB

        ใช้เพื่อ admin/ส่วนแสดงผลจัดการขอบเขต "tool ที่แก้จากหน้าเว็บไม่ได้" โดยอ่านจาก
        registry จริงเสมอ (แหล่งเดียวกับที่ dispatch ใช้) คืนเป็น plain string เสมอ
        เพื่อไม่ให้ hash ของ str-Enum กลายเป็นบั๊กการเทียบค่า
        """
        return frozenset(
            _display_name(name)
            for name, tool in self._tools.items()
            if not isinstance(tool, DeclarativeTool)
        )

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        # D2.5: action_belongs_to_tool ย้ายมาตรวจตรงนี้แทนที่จะเป็น validator ของ ToolCall
        # เพราะ ToolCall.name/action เป็น string ล้วนแล้ว ไม่รู้ล่วงหน้าว่า tool ไหนมี action อะไร
        # (CONTRACTS-V2 §3.5: "action ไม่ได้อยู่ใน tool ที่ระบุ → ปฏิเสธ ตรวจกับ registry ตอน dispatch")
        # ใช้ .get() แทนการ index ตรง ๆ: tool ที่ยังไม่มีใน TOOL_ACTIONS (declarative tool จาก DB
        # ตาม D2.6) ต้องถูกปฏิเสธแบบ fail-safe ไม่ใช่ KeyError — สำหรับ tool แบบนั้น ถามที่ตัว tool
        # เองแทนว่ามันรู้จัก action อะไรบ้าง (``.actions``) เพราะไม่มี dict กลางที่รู้จักมันล่วงหน้า
        # ข้อยกเว้นเดียวคือ declarative oms_tool ที่ slug ตรงกับ ToolName.OMS เดิม (D2.7) — ยังผูก
        # กับ TOOL_ACTIONS ของ alias เดิมอยู่ จึงยังได้ validation/output behavior ตาม contracts
        legacy_actions = TOOL_ACTIONS.get(call.name)
        if legacy_actions is not None:
            allowed_actions = legacy_actions
        else:
            allowed_actions = getattr(self._tools.get(call.name), "actions", None) or frozenset()
        if call.name not in self._tools or call.action not in allowed_actions:
            return _error_result(call, ToolErrorCode.INVALID_INPUT, "ไม่รู้จักเครื่องมือหรือการกระทำ")
        # P4: code tool ที่ถูกปิดจากหน้า admin ต้องถูกปฏิเสธอย่างชัดเจนที่จุด dispatch เดียว
        # (ครอบทุกช่องทางรวมช่องทางเสียงผ่าน scoped registry) — ไม่พึ่งแค่การหายจากแค็ตตาล็อก
        if not self.code_tool_enabled(_display_name(call.name)):
            return _error_result(
                call,
                ToolErrorCode.UNAVAILABLE,
                "เครื่องมือนี้ถูกปิดใช้งานอยู่ — เปิดใหม่ได้จากหน้า admin",
            )
        # INPUT_MODELS/OUTPUT_MODELS รู้จักเฉพาะ action ของ 3 tool เดิม (voc/knowledge/oms) —
        # จึงบังคับใช้เฉพาะคู่ (tool_slug, action) ที่เป็น legacy จริง (มีใน TOOL_ACTIONS) เท่านั้น
        # ประกอบด้วย action อย่างเดียวไม่พอ เพราะ declarative tool ตัวใหม่เลือกชื่อ action ชนกับ
        # legacy ได้ (เช่น "search") และต้อง validate ด้วย JSON Schema ของตัวเอง ไม่ใช่ Pydantic
        # ของ legacy tool ส่วน declarative tool ตรวจ input/output ของตัวเองด้วย jsonschema อยู่แล้ว
        # ใน .execute() (app/tools/declarative_tool.py, D2.6)
        if legacy_actions is not None and call.action in INPUT_MODELS:
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
        if (
            result.status is ToolResultStatus.SUCCESS
            and legacy_actions is not None
            and call.action in OUTPUT_MODELS
        ):
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
        # เทียบด้วย == ไม่ใช่ is: call.name เป็น str ธรรมดาแล้วตั้งแต่ D2.5
        simulation=call.name != ToolName.KNOWLEDGE,
    )
