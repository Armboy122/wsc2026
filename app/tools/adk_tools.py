"""Thin ADK adapters over WSC's existing validated domain operations.

No planner here: ADK invokes these tools and sends their results to Gemini.
Pending IDs live in ADK state; WSC remains the authority for write transitions.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import ValidationError

from app.agent.main_agent import MainAgent
from app.contracts import (
    INPUT_MODELS, PREPARE_TO_SUBMIT, ChatRequest, PendingActionStatus,
    ToolAction, ToolCall, ToolName, ToolResultStatus,
)
from app.core.logging import get_logger
from app.live.bridge import VoiceBridge

logger = get_logger(__name__)
_ALLOWED = frozenset({ToolName.KNOWLEDGE, ToolName.OMS, ToolName.VOC})
_PENDING = "wsc_pending_action_id"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


class WscTools:
    """One socket's domain adapter, serialized even if ADK dispatches in parallel."""

    def __init__(self, agent: MainAgent, conversation_id: UUID, *, has_display: bool) -> None:
        self.agent = agent
        self.conversation_id = conversation_id
        self._lock = asyncio.Lock()
        self._presentation = VoiceBridge(agent, has_display=has_display)
        self._allowed = {
            (definition.name, ToolAction(action))
            for definition in agent.tool_catalogue if definition.name in _ALLOWED
            for action in definition.actions
            if ToolAction(action) not in PREPARE_TO_SUBMIT.values()
            and ToolAction(action) is not ToolAction.VOC_PREPARE_CASE
        }

    def definitions(self) -> list[BaseTool]:
        definitions: list[BaseTool] = []
        for definition in self.agent.tool_catalogue:
            for action_name in definition.actions:
                action = ToolAction(action_name)
                if (definition.name, action) not in self._allowed:
                    continue
                schema = INPUT_MODELS[action].model_json_schema(by_alias=True)
                # Internal write keys and client coordinates never come from the model.
                for field in ("idempotencyKey", "lat", "lon"):
                    schema.get("properties", {}).pop(field, None)
                    if field in schema.get("required", []):
                        schema["required"].remove(field)
                definitions.append(WscTool(
                    self, f"{definition.name.value}_{action.value}",
                    definition.description, schema, definition.name, action,
                ))
        if any(d.name is ToolName.VOC for d in self.agent.tool_catalogue):
            definitions.append(WscTool(self, "voc_intake", "เริ่มหรือเดินขั้นตอนร้องเรียน VOC ด้วยคำพูดผู้ใช้ตามเดิม", {
                "type": "object", "properties": {"message": {"type": "string", "maxLength": 4000}},
                "required": ["message"], "additionalProperties": False,
            }))
        for name, field, description in (
            ("pea_confirm_pending_action", "confirmationNote", "ยืนยันเฉพาะรายการปัจจุบันหลังผู้ใช้ตกลงชัดเจน"),
            ("pea_reject_pending_action", "reason", "ยกเลิกเฉพาะรายการปัจจุบันเมื่อผู้ใช้ปฏิเสธ"),
        ):
            definitions.append(WscTool(self, name, description, {
                "type": "object", "properties": {field: {"type": "string", "minLength": 1, "maxLength": 500}},
                "required": [field], "additionalProperties": False,
            }))
        return definitions

    async def call(self, tool: WscTool, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        async with self._lock:
            try:
                # Validate before dispatch, including custom tools. Never echo invalid payloads.
                from jsonschema import validate
                from jsonschema.exceptions import ValidationError as SchemaError
                try:
                    validate(args, tool.schema)
                except SchemaError:
                    result = _error("invalid_input", "ข้อมูลยังไม่ครบหรือรูปแบบไม่ถูกต้อง กรุณาระบุเฉพาะข้อมูลที่ขาดครับ")
                    result["missingFields"] = sorted(set(tool.schema.get("required", [])) - args.keys())
                    return result
                state = context.state
                pending_id = state.get(_PENDING)
                if pending_id and not self.agent.domain_action_is_open(UUID(pending_id)):
                    state[_PENDING] = None
                if tool.name in {"pea_confirm_pending_action", "pea_reject_pending_action"}:
                    pending_id = state.get(_PENDING)
                    if not pending_id:
                        return _error("no_pending_action", "ยังไม่มีรายการที่รอการยืนยันในเซสชันนี้ครับ")
                    if tool.name == "pea_confirm_pending_action":
                        user_turn = _latest_user_turn(context)
                        if not user_turn or user_turn == state.get("wsc_prepared_user_turn"):
                            return _error("confirmation_required", "กรุณาฟังสรุปรายการแล้วตอบยืนยันอีกครั้งครับ")
                        decision = await self.agent.confirm_pending_action(UUID(pending_id), args["confirmationNote"])
                    else:
                        decision = await self.agent.reject_pending_action(UUID(pending_id), args["reason"])
                    if decision.pending_action.status in {
                        PendingActionStatus.SUBMITTED, PendingActionStatus.REJECTED, PendingActionStatus.FAILED,
                    }:
                        state[_PENDING] = None
                    return decision.model_dump(mode="json", by_alias=True)

                if tool.name == "voc_intake":
                    if state.get(_PENDING):
                        return _error("action_conflict", "กรุณายืนยันหรือยกเลิกรายการเดิมก่อนครับ")
                    response = await self.agent.advance_domain_intake(ChatRequest(
                        conversation_id=self.conversation_id, message=args["message"],
                    ))
                    if response is None:
                        return _error("invalid_input", "กรุณาระบุเรื่องร้องเรียนที่ต้องการแจ้งครับ")
                else:
                    if (tool.tool_name, tool.action) not in self._allowed:
                        return _error("unknown_function", "คำสั่งนี้ไม่รองรับครับ")
                    if tool.action in PREPARE_TO_SUBMIT and state.get(_PENDING):
                        return _error("action_conflict", "กรุณายืนยันหรือยกเลิกรายการเดิมก่อนครับ")
                    if tool.action is ToolAction.OMS_PREPARE_OUTAGE_WITH_CA:
                        lookup = state.get("wsc_oms_lookup", {})
                        if (lookup.get("caNumber") != args.get("caNumber")
                            or lookup.get("activeEvent") is not None
                            or lookup.get("recommendedAction") != "CREATE_METER_EVENT"):
                            return _error("action_conflict", "กรุณาตรวจเหตุจากหมายเลขผู้ใช้ไฟก่อน และห้ามสร้างเหตุซ้ำครับ")
                    payload = dict(args)
                    if tool.action in PREPARE_TO_SUBMIT:
                        payload["idempotencyKey"] = str(uuid4())
                    response = await self.agent.execute_domain_tool(ToolCall(
                        call_id=uuid4(), name=tool.tool_name, action=tool.action, input=payload,
                    ), self.conversation_id, user_message=str(args.get("query", "")))
                    if tool.action is ToolAction.OMS_GET_OUTAGE_BY_CA:
                        result = response.tool_results[0]
                        state["wsc_oms_lookup"] = (
                            {**(result.data or {}), "caNumber": args["caNumber"]}
                            if result.status is ToolResultStatus.SUCCESS else {}
                        )
                if response.pending_action:
                    state[_PENDING] = str(response.pending_action.pending_action_id)
                    state["wsc_prepared_user_turn"] = _latest_user_turn(context)
                payload = response.model_dump(mode="json", by_alias=True)
                payload["voiceGuidance"] = self._presentation._voice_guidance(response)
                return payload
            except ValidationError:
                return _error("invalid_input", "ข้อมูลคำขอไม่ถูกต้อง กรุณาตรวจสอบข้อมูลครับ")
            except LookupError:
                context.state[_PENDING] = None
                return _error("no_pending_action", "ไม่พบรายการที่รอการยืนยันครับ")
            except RuntimeError:
                return _error("action_conflict", "รายการนี้ไม่สามารถดำเนินการได้ในสถานะปัจจุบันครับ")
            except Exception:
                logger.error("adk_domain_tool_failed", extra={"function_name": tool.name})
                return _error("unavailable", "ไม่สามารถดำเนินการได้ในขณะนี้ครับ")


def _latest_user_turn(context: ToolContext) -> str | None:
    """Require an actual later user event, never a model-supplied confirmation ID."""
    return next((event.id for event in reversed(context.session.events)
                 if event.author == "user" and (event.input_transcription or event.content)), None)


class WscTool(BaseTool):
    def __init__(self, owner: WscTools, name: str, description: str, schema: dict[str, Any],
                 tool_name: ToolName | None = None, action: ToolAction | None = None) -> None:
        super().__init__(name=name, description=description)
        self.owner, self.schema = owner, schema
        self.tool_name, self.action = tool_name, action

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(name=self.name, description=self.description, parameters_json_schema=self.schema)

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> dict[str, Any]:
        return await self.owner.call(self, args, tool_context)
