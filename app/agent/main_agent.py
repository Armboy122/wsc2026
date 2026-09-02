"""ตัวประสานงานที่ขับเคลื่อนด้วยโมเดลเพียงตัวเดียวสำหรับสัญญาเดโม PEA แบบคงที่"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.agent.registry import ToolContext, ToolRegistry, _error_result
from app.agent.stores import ConversationStore, PendingActionStore, TraceStore
from app.agent.response_policy import ErrorPresentation, ResponsePolicies
from app.contracts import (
    PREPARE_TO_SUBMIT,
    ActionDecisionResponse,
    ChatRequest,
    ChatResponse,
    PendingAction,
    PendingActionStatus,
    ResetResponse,
    SubmitPreparedActionInput,
    ToolAction,
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    TraceEventKind,
    TraceResponse,
    validate_tool_input,
)
from app.llm import (
    KnowledgeConversationContext,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ToolDefinition,
)

# Keep the loop bounded while allowing a short clarification/tool chain.
_MAX_TOOL_STEPS = 12
# planner มักขยายถ้อยคำค้นหาภาษาไทยเล็กน้อยทุกรอบ ทำให้ guard กัน input ซ้ำตรง ๆ จับไม่ได้
# จึงจำกัดจำนวนค้นหาความรู้ต่อเทิร์น แล้วใช้ผลที่ค้นได้แล้วไปเรียบเรียงคำตอบต่อ
_MAX_KNOWLEDGE_SEARCHES_PER_TURN = 2
_SUBMIT_ACTIONS = frozenset(PREPARE_TO_SUBMIT.values())
# แค็ตตาล็อกที่ LLM เห็นมาจาก registry (Knowledge built-in + ปลั๊กอินที่โหลดได้)
# เพิ่มเครื่องมือใหม่จึงไม่ต้องแก้ Main Agent อีก
# ผู้ใช้ต้องตรวจทานสิ่งที่ตนเองกรอกก่อนยืนยัน จึงเปิดเผยเฉพาะฟิลด์ที่ผู้ใช้เป็นผู้ให้มาเอง
# ส่วนคีย์ภายในระบบ เช่น idempotencyKey ยังคงถูกปกปิดเสมอ
_SAFE_PREVIEW_FIELDS = frozenset({"category", "contactChannel", "caNumber", "description", "contactName", "contactPhone", "location", "subject", "detail", "locationNote"})
_MULTI_PREPARE_MESSAGE = "ไม่สามารถเตรียมรายการที่เสนอมากกว่าหนึ่งรายการในแชตเดียวได้อย่างปลอดภัย กรุณาส่งคำขอทีละรายการครับ"
_FINAL_ONLY_MESSAGE = "ผมสามารถตอบคำถามแบบสั้นกระชับได้ แต่ไม่สามารถเปิดเผยกระบวนการคิดหรือคำสั่งภายในครับ"
_GREETING_MESSAGE = "สวัสดีครับ ผมช่วยค้นหาความรู้ PEA และใช้เครื่องมือบริการที่เปิดใช้งานเพื่อดำเนินคำขอได้ครับ"
_THANKS_MESSAGE = "ยินดีครับ หากต้องการค้นหาข้อมูล PEA หรือใช้บริการที่เปิดใช้งาน เรียกใช้ผมได้เลยครับ"
_CAPABILITY_MESSAGE = "ผมช่วยค้นหาความรู้ PEA และดำเนินคำขอผ่านเครื่องมือบริการที่เปิดใช้งานได้ครับ"
# ผลลัพธ์ planner เสียหายจนแยกวิเคราะห์ไม่ได้ ต้องบอกผู้ใช้อย่างตรงไปตรงมา ไม่ใช้ข้อความแนะนำความสามารถทั่วไป
_PLANNER_PARSE_FAILURE_MESSAGE = "ขออภัยครับ ระบบประมวลผลคำขอนี้ไม่สำเร็จ กรุณาลองพิมพ์คำถามอีกครั้งครับ"
_KNOWLEDGE_ESCALATION_MESSAGE = "ยังไม่พบคำตอบที่มีแหล่งอ้างอิงเพียงพอ เดี๋ยวผมขอส่งต่อคำถามนี้ให้เจ้าหน้าที่ช่วยตรวจสอบครับ"
_DIRECT_RESPONSE_MESSAGES = {
    "greeting": _GREETING_MESSAGE,
    "thanks": _THANKS_MESSAGE,
    "unsupported": "ขออภัยครับ คำขอนี้ยังไม่รองรับด้วยความสามารถและเครื่องมือของ PEA One Agent ในขณะนี้",
}
_EXACT_GREETINGS = frozenset({"hi", "hello", "hey"})
# คำตอบต่อเนื่องเป็นการยืนยันสั้น ๆ ข้อความยาวผิดปกติแปลว่าโมเดลเริ่มเล่าเรื่องเอง
_MAX_FOLLOWUP_LENGTH = 500
_OUTPUT_POLICY_PATTERNS = (
    re.compile(r"<\s*/?\s*(?:analysis|thinking|thought|reasoning|scratchpad|system)\b|<\|(?:analysis|thinking|reasoning|system)\|>", re.IGNORECASE),
    re.compile(r"\b(?:chain[- ]of[- ]thought|cot|scratchpad|system\s+prompt|developer\s+(?:message|instructions)|internal\s+(?:reasoning|instructions|prompt)|hidden\s+(?:reasoning|instructions))\b", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:analysis|reasoning|thinking|thoughts?|thought\s+process|scratchpad|system)\s*:", re.IGNORECASE),
    re.compile(r"\b(?:let(?:'s| us)\s+think\s+step\s+by\s+step|i(?:'m| am)\s+(?:thinking|reasoning)|my\s+(?:reasoning|thought process))\b", re.IGNORECASE),
)


class NotFoundError(LookupError):
    """ไม่มีทรัพยากรภายใน process ที่ร้องขอ"""


class InvalidActionStateError(RuntimeError):
    """ไม่อนุญาตให้เปลี่ยนสถานะการยืนยันหรือปฏิเสธนี้"""


class MainAgent:
    """ดูแลการประสานงาน นโยบายการยืนยัน และสถานะภายใน process ที่ตรวจสอบย้อนหลังได้"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        *,
        conversations: ConversationStore | None = None,
        pending_actions: PendingActionStore | None = None,
        traces: TraceStore | None = None,
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        # แค็ตตาล็อกมาจาก registry เสมอ เพิ่มปลั๊กอินใหม่จึงไม่ต้องแก้ Main Agent
        self._tool_catalogue = tool_registry.llm_catalogue
        self._response_policies = tool_registry.response_policies
        self._conversations = conversations or ConversationStore()
        self._pending_actions = pending_actions or PendingActionStore()
        self._traces = traces or TraceStore()
        self._call_inputs: dict[UUID, dict[str, Any]] = {}
        self._confirmation_tasks: dict[UUID, asyncio.Task[ActionDecisionResponse]] = {}
        self._knowledge_contexts: dict[UUID, KnowledgeConversationContext] = {}
        self._grounded_conversations: set[UUID] = set()
        self._reset_generation = 0

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4()
        trace_id = uuid4()
        self._traces.append(trace_id, TraceEventKind.CHAT_RECEIVED, {"message": "[redacted]", "requestId": str(request.request_id) if request.request_id else None})
        history = self._conversations.messages_for(conversation_id) + (LLMMessage("user", request.message),)
        all_results: list[ToolResult] = []
        final_text = ""
        direct_completion_text: str | None = None
        direct_response_kind: str | None = None
        seen_knowledge_calls: set[tuple[str, str]] = set()
        duplicate_knowledge_call = False
        knowledge_searches = 0
        knowledge_search_limit_reached = False
        planner_retried = False

        for _ in range(_MAX_TOOL_STEPS):
            self._traces.append(trace_id, TraceEventKind.LLM_REQUESTED, {"messageCount": len(history), "toolCount": len(self._tool_catalogue)})
            try:
                response = await self._llm.complete(
                    LLMRequest(
                        history,
                        self._tool_catalogue,
                        trace_id,
                        self._knowledge_contexts.get(conversation_id),
                        self._response_policies.planner_instructions,
                    )
                )
            except Exception as error:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "llm", "type": type(error).__name__})
                final_text = "ขณะนี้ไม่สามารถดำเนินการตามคำขอได้ เนื่องจากบริการผู้ช่วยไม่พร้อมใช้งานครับ"
                break

            calls, planner_text, parsed_direct_response, planner_malformed = _calls_from_response(response)
            self._traces.append(trace_id, TraceEventKind.LLM_RESPONDED, {"toolCallCount": len(calls), "hasText": bool(response.text or planner_text)})
            if planner_malformed:
                # ผลลัพธ์ planner เสียหาย ไม่ใช่การตอบตรงโดยตั้งใจ — บันทึก trace แล้วลองใหม่ครั้งเดียว
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "planner_parse"})
                if planner_retried:
                    final_text = _PLANNER_PARSE_FAILURE_MESSAGE
                    break
                planner_retried = True
                continue
            final_text = planner_text or response.text or final_text
            if not calls:
                direct_completion_text = final_text
                direct_response_kind = response.direct_response or parsed_direct_response
                break
            if len(all_results) + len(calls) > _MAX_TOOL_STEPS:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "tool_limit", "maximum": _MAX_TOOL_STEPS})
                final_text = "ไม่สามารถดำเนินการตามคำขอได้ เนื่องจากต้องใช้ขั้นตอนเครื่องมือมากเกินไปครับ"
                break
            if sum(call.action in PREPARE_TO_SUBMIT for call in calls) > 1:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "multi_prepare_policy"})
                final_text = _MULTI_PREPARE_MESSAGE
                break

            prepared = False
            ordered_calls = tuple(call for call in calls if call.action not in PREPARE_TO_SUBMIT) + tuple(
                call for call in calls if call.action in PREPARE_TO_SUBMIT
            )
            for call in ordered_calls:
                # planner ขยายถ้อยคำค้นหาใหม่ทุกรอบ ทำให้ guard กัน input ซ้ำจับไม่ได้
                # จึงตัดการค้นหาที่เกินโควตาต่อเทิร์น แล้วใช้ผลที่ค้นได้แล้วไปตอบแทน
                if call.name is ToolName.KNOWLEDGE:
                    if knowledge_searches >= _MAX_KNOWLEDGE_SEARCHES_PER_TURN:
                        self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "knowledge_search_limit", "maximum": _MAX_KNOWLEDGE_SEARCHES_PER_TURN})
                        knowledge_search_limit_reached = True
                        break
                    knowledge_searches += 1
                # การเรียกอ่านข้อมูลด้วย input ชุดเดิมซ้ำย่อมให้ผลเหมือนเดิม
                # จึงหยุดทันที เพื่อไม่ให้ผู้ใช้เห็นข้อความล้มเหลวซ้ำหลายรอบ
                if call.name is ToolName.KNOWLEDGE or call.action not in PREPARE_TO_SUBMIT:
                    key = (call.name.value, call.action.value, json.dumps(call.input, sort_keys=True, default=str))
                    if key in seen_knowledge_calls:
                        self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "duplicate_read_call", "action": call.action.value})
                        duplicate_knowledge_call = True
                        break
                    seen_knowledge_calls.add(key)
                result = await self._execute_chat_call(call, conversation_id, trace_id)
                all_results.append(result)
                history += (LLMMessage("tool", _result_message(result, self._response_policies)),)
                if result.status is ToolResultStatus.SUCCESS and result.action in PREPARE_TO_SUBMIT:
                    prepared = True
                    break
            if prepared or duplicate_knowledge_call or knowledge_search_limit_reached:
                break
        else:  # pragma: no cover - มีเงื่อนไขป้องกันไว้ด้านบน เพื่อระบุขีดจำกัดตายตัวให้ชัดเจน
            final_text = "ไม่สามารถดำเนินการตามคำขอได้ภายในขีดจำกัดขั้นตอนเครื่องมือครับ"

        pending = self._create_pending_from_results(conversation_id, trace_id, all_results)
        citations = tuple(citation for result in all_results if result.status is ToolResultStatus.SUCCESS for citation in result.citations)
        if not all_results and direct_completion_text is not None:
            final_text = _safe_direct_message(
                request.message,
                direct_completion_text,
                direct_response=direct_response_kind,
                allow_grounded_followup=conversation_id in self._grounded_conversations,
                response_policies=self._response_policies,
            )
            if final_text == _FINAL_ONLY_MESSAGE:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "output_policy", "policy": "final_only"})
        message = _authoritative_message(
            final_text,
            all_results,
            pending,
            user_message=request.message,
            response_policies=self._response_policies,
        )
        self._conversations.append(conversation_id, LLMMessage("user", request.message))
        knowledge_context = next(
            (
                context
                for result in reversed(all_results)
                if (context := _knowledge_context_from_result(request.message, result))
                is not None
            ),
            None,
        )
        if knowledge_context is None:
            self._knowledge_contexts.pop(conversation_id, None)
        else:
            self._knowledge_contexts[conversation_id] = knowledge_context
        if any(self._response_policies.grounds_followup(result) for result in all_results):
            self._grounded_conversations.add(conversation_id)
        self._conversations.append(conversation_id, LLMMessage("assistant", message))
        return ChatResponse(conversation_id=conversation_id, trace_id=trace_id, message=message, citations=citations, pending_action=pending, tool_results=tuple(all_results))

    async def confirm_pending_action(self, pending_action_id: UUID, confirmation_note: str | None = None) -> ActionDecisionResponse:
        task = self._confirmation_tasks.get(pending_action_id)
        if task is not None:
            return await asyncio.shield(task)

        pending = self._require_pending(pending_action_id)
        trace_id = self._require_pending_trace(pending_action_id)
        if pending.status in {PendingActionStatus.SUBMITTED, PendingActionStatus.FAILED}:
            return ActionDecisionResponse(pending_action=pending, tool_result=pending.submission_result, trace_id=trace_id)
        if pending.status is PendingActionStatus.REJECTED:
            raise InvalidActionStateError("ไม่สามารถยืนยันรายการที่ถูกปฏิเสธแล้วได้")
        if pending.status is not PendingActionStatus.PENDING_CONFIRMATION:
            raise InvalidActionStateError("ไม่สามารถยืนยันรายการในสถานะปัจจุบันได้")

        confirmed = pending.model_copy(update={"status": PendingActionStatus.CONFIRMED, "updated_at": _now()})
        self._pending_actions.update(confirmed)
        self._traces.append(trace_id, TraceEventKind.ACTION_CONFIRMED, {"pendingActionId": str(pending_action_id), "hasNote": bool(confirmation_note)})
        generation = self._reset_generation
        task = asyncio.create_task(self._submit_confirmed_action(pending_action_id, confirmed, trace_id, generation))
        self._confirmation_tasks[pending_action_id] = task
        return await asyncio.shield(task)

    async def _submit_confirmed_action(self, pending_action_id: UUID, confirmed: PendingAction, trace_id: UUID, generation: int) -> ActionDecisionResponse:
        if generation != self._reset_generation:
            raise asyncio.CancelledError
        call = ToolCall(
            call_id=uuid4(),
            name=confirmed.tool_name,
            action=confirmed.submit_action,
            input=SubmitPreparedActionInput(
                pending_action_id=pending_action_id,
                idempotency_key=confirmed.idempotency_key,
            ).model_dump(by_alias=True),
        )
        self._traces.append(trace_id, TraceEventKind.ACTION_SUBMITTED, {"pendingActionId": str(pending_action_id), "action": call.action.value})
        result = await self._execute_internal(call, confirmed.conversation_id, trace_id)
        if generation != self._reset_generation:
            raise asyncio.CancelledError
        status = PendingActionStatus.SUBMITTED if result.status is ToolResultStatus.SUCCESS else PendingActionStatus.FAILED
        terminal = confirmed.model_copy(update={"status": status, "updated_at": _now(), "submission_result": result})
        self._pending_actions.update(terminal)
        return ActionDecisionResponse(pending_action=terminal, tool_result=result, trace_id=trace_id)

    async def reject_pending_action(self, pending_action_id: UUID, reason: str) -> ActionDecisionResponse:
        pending = self._require_pending(pending_action_id)
        trace_id = self._require_pending_trace(pending_action_id)
        if pending.status is PendingActionStatus.REJECTED:
            return ActionDecisionResponse(pending_action=pending, tool_result=None, trace_id=trace_id)
        if pending.status is not PendingActionStatus.PENDING_CONFIRMATION:
            raise InvalidActionStateError("ไม่สามารถปฏิเสธรายการในสถานะปัจจุบันได้")
        rejected = pending.model_copy(update={"status": PendingActionStatus.REJECTED, "updated_at": _now()})
        self._pending_actions.update(rejected)
        self._traces.append(trace_id, TraceEventKind.ACTION_REJECTED, {"pendingActionId": str(pending_action_id), "reason": "[redacted]"})
        return ActionDecisionResponse(pending_action=rejected, tool_result=None, trace_id=trace_id)

    def get_trace(self, trace_id: UUID) -> TraceResponse:
        trace = self._traces.get(trace_id)
        if trace is None:
            raise NotFoundError("ไม่พบ trace")
        return trace

    def reset_demo(self) -> ResetResponse:
        self._reset_generation += 1
        for task in self._confirmation_tasks.values():
            if not task.done():
                task.cancel()
        self._confirmation_tasks.clear()
        self._tools.reset()
        self._conversations.clear()
        self._pending_actions.clear()
        self._traces.clear()
        self._call_inputs.clear()
        self._knowledge_contexts.clear()
        self._grounded_conversations.clear()
        return ResetResponse()

    async def _execute_chat_call(self, call: ToolCall, conversation_id: UUID, trace_id: UUID) -> ToolResult:
        if call.action in _SUBMIT_ACTIONS:
            self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "chat_policy", "action": call.action.value})
            result = _error_result(
                call,
                ToolErrorCode.CONFIRMATION_REQUIRED,
                "การส่งรายการต้องได้รับการยืนยันอย่างชัดเจน",
            )
            return _sanitize_error_result(result, self._response_policies)
        return await self._execute_internal(call, conversation_id, trace_id)

    async def _execute_internal(self, call: ToolCall, conversation_id: UUID, trace_id: UUID) -> ToolResult:
        self._call_inputs[call.call_id] = dict(call.input)
        self._traces.append(trace_id, TraceEventKind.TOOL_CALLED, {"name": call.name.value, "action": call.action.value, "callId": str(call.call_id)})
        result = await self._tools.execute(call, ToolContext(conversation_id, trace_id))
        result = _sanitize_error_result(result, self._response_policies)
        self._traces.append(trace_id, TraceEventKind.TOOL_RESULT, {"name": result.name.value, "action": result.action.value, "status": result.status.value, "errorCode": result.error.code.value if result.error else None})
        return result

    def _create_pending_from_results(self, conversation_id: UUID, trace_id: UUID, results: list[ToolResult]) -> PendingAction | None:
        prepared = [result for result in results if result.status is ToolResultStatus.SUCCESS and result.action in PREPARE_TO_SUBMIT]
        if len(prepared) > 1:
            self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "multi_prepare_policy"})
            return None
        if not prepared:
            return None
        result = prepared[0]
        raw_input = self._call_inputs.get(result.call_id, {})
        try:
            prepared_input = validate_tool_input(ToolCall(
                call_id=result.call_id,
                name=result.name,
                action=result.action,
                input=raw_input,
            )).model_dump(by_alias=True)
        except ValidationError:  # pragma: no cover - ผลลัพธ์สำเร็จจาก registry ผ่านการตรวจสอบแล้ว
            return None
        idempotency_key = prepared_input["idempotencyKey"]
        now = _now()
        pending = PendingAction(
            pending_action_id=uuid4(), conversation_id=conversation_id, tool_name=result.name,
            prepare_action=result.action, submit_action=PREPARE_TO_SUBMIT[result.action],
            prepared_input=_redact_prepared_input(prepared_input), summary=str((result.data or {}).get("summary", "รายการที่จัดเตรียมไว้")),
            status=PendingActionStatus.PENDING_CONFIRMATION, idempotency_key=idempotency_key,
            created_at=now, updated_at=now,
        )
        self._pending_actions.put(pending, trace_id)
        self._traces.append(trace_id, TraceEventKind.ACTION_PREPARED, {"pendingActionId": str(pending.pending_action_id), "action": result.action.value})
        return pending

    def _require_pending(self, pending_action_id: UUID) -> PendingAction:
        pending = self._pending_actions.get(pending_action_id)
        if pending is None:
            raise NotFoundError("ไม่พบรายการที่รอดำเนินการ")
        return pending

    def _require_pending_trace(self, pending_action_id: UUID) -> UUID:
        trace_id = self._pending_actions.trace_id_for(pending_action_id)
        if trace_id is None:
            raise NotFoundError("ไม่พบ trace ของรายการที่รอดำเนินการ")
        return trace_id


def _calls_from_response(
    response: LLMResponse,
) -> tuple[tuple[ToolCall, ...], str, str | None, bool]:
    """Parse the strict planner envelope while leaving plugin labels opaque."""
    if response.tool_calls:
        return response.tool_calls, "", None, False
    try:
        payload = json.loads(response.text)
        allowed_keys = {"message", "toolCalls", "directResponse"}
        if (
            not isinstance(payload, dict)
            or set(payload) != allowed_keys
            or not isinstance(payload["message"], str)
            or not isinstance(payload["toolCalls"], list)
            or payload["directResponse"] is not None and not isinstance(payload["directResponse"], str)
        ):
            return (), response.text, None, _looks_like_planner_json(response.text)
        direct_response = payload["directResponse"]
        calls = tuple(ToolCall(call_id=uuid4(), name=item["name"], action=item["action"], input=item["input"]) for item in payload["toolCalls"] if isinstance(item, dict) and set(item) == {"name", "action", "input"})
        if len(calls) != len(payload["toolCalls"]):
            return (), "ไม่สามารถตีความการดำเนินการของเครื่องมือที่ร้องขอได้อย่างปลอดภัยครับ", None, False
        if calls and direct_response is not None:
            return (), "ไม่สามารถใช้ข้อความตรงร่วมกับการเรียกเครื่องมือได้ครับ", None, False
        return calls, payload["message"], direct_response, False
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
        return (), response.text, None, _looks_like_planner_json(response.text)


def _looks_like_planner_json(text: str) -> bool:
    """แยก JSON ของ planner ที่พยายามสร้างแต่เสียหาย ออกจากข้อความตรงธรรมดา"""
    return text.lstrip().startswith("{")


def _requires_final_only_output(text: str) -> bool:
    """ตรวจจับการเปิดเผยกระบวนการคิดหรือคำสั่งภายในอย่างชัดเจนในข้อความตรงจากโมเดล"""
    return any(pattern.search(text) for pattern in _OUTPUT_POLICY_PATTERNS)


def _safe_direct_message(
    user_message: str,
    completion_text: str,
    *,
    direct_response: str | None = None,
    allow_grounded_followup: bool = False,
    response_policies: ResponsePolicies,
) -> str:
    """Render generic labels locally and delegate opaque plugin labels safely."""
    if _requires_final_only_output(completion_text):
        return _FINAL_ONLY_MESSAGE
    if user_message.strip().casefold() in _EXACT_GREETINGS:
        return _GREETING_MESSAGE
    followup = " ".join(completion_text.split())
    if isinstance(direct_response, str):
        if direct_response in _DIRECT_RESPONSE_MESSAGES:
            return _DIRECT_RESPONSE_MESSAGES[direct_response]
        if (message := response_policies.direct_message(direct_response, followup, allow_grounded_followup)) is not None:
            return message
        return _CAPABILITY_MESSAGE
    if allow_grounded_followup and 0 < len(followup) <= _MAX_FOLLOWUP_LENGTH:
        return followup
    return _CAPABILITY_MESSAGE


def _redact_prepared_input(data: dict[str, Any]) -> dict[str, Any]:
    """เปิดเผยเฉพาะฟิลด์ตัวอย่างการยืนยันตามสัญญา และปกปิดคีย์อื่นทั้งหมด"""
    return {key: value if key in _SAFE_PREVIEW_FIELDS else "[redacted]" for key, value in data.items()}


def _result_message(result: ToolResult, response_policies: ResponsePolicies) -> str:
    identity = {"name": result.name.value, "action": result.action.value}
    if result.status is ToolResultStatus.ERROR:
        presentation = _error_presentation(result, response_policies)
        return json.dumps(
            {**identity, "status": "error", "errorPresentation": presentation.llm_payload()},
            ensure_ascii=False,
        )
    return json.dumps({**identity, "status": "success", "data": result.data, "citations": [citation.model_dump(by_alias=True) for citation in result.citations]}, default=str)


def _knowledge_context_from_result(
    question: str, result: ToolResult
) -> KnowledgeConversationContext | None:
    """สร้าง context ต่อเนื่องเฉพาะ Knowledge ที่สำเร็จและมี citation จริง"""
    data = result.data or {}
    if (
        result.name is not ToolName.KNOWLEDGE
        or result.status is not ToolResultStatus.SUCCESS
        or not isinstance(data.get("answerContext"), str)
        or not data["answerContext"].strip()
        or not result.citations
    ):
        return None
    sources = tuple(
        dict.fromkeys(
            f"{citation.source_id} ({citation.title})"
            for citation in result.citations
        )
    )
    return KnowledgeConversationContext(
        previous_question=" ".join(question.split())[:500],
        sources=sources,
    )


def _default_message(results: list[ToolResult]) -> str:
    if any(result.status is ToolResultStatus.ERROR for result in results):
        return "ไม่สามารถดำเนินการบางส่วนของคำขอได้ เนื่องจากบริการที่จำเป็นไม่พร้อมใช้งานครับ"
    return "ดำเนินการค้นหาที่ร้องขอเรียบร้อยแล้วครับ"


def _authoritative_message(
    text: str,
    results: list[ToolResult],
    pending: PendingAction | None,
    *,
    user_message: str = "",
    response_policies: ResponsePolicies,
) -> str:
    if not results:
        return text or _default_message(results)

    if (
        not pending
        and all(result.status is ToolResultStatus.ERROR for result in results)
        and all(result.name is not ToolName.KNOWLEDGE for result in results)
    ):
        presentations = tuple(_error_presentation(result, response_policies) for result in results)
        if _safe_llm_error_wording(text, presentations):
            codes = ", ".join(dict.fromkeys(item.code.value for item in presentations))
            return f"{text.strip()}\n\nรหัสข้อผิดพลาด: {codes}"

    facts = _result_facts(results, user_message=user_message, response_policies=response_policies)
    if pending:
        facts.append("กรุณายืนยันรายการที่เสนอนี้อย่างชัดเจนเพื่อส่งรายการครับ")
    return "\n\n".join(facts) or _default_message(results)


def _safe_llm_error_wording(text: str, presentations: tuple[ErrorPresentation, ...]) -> bool:
    """Accept LLM wording only when every authoritative error fact remains verbatim."""
    candidate = text.strip()
    if not candidate or len(candidate) > 2000 or _requires_final_only_output(candidate):
        return False
    remainder = candidate
    for item in presentations:
        explanation = item.explanation.strip()
        next_step = item.next_step.strip()
        if explanation not in remainder or next_step not in remainder:
            return False
        remainder = remainder.replace(explanation, "", 1).replace(next_step, "", 1)
    for allowed_phrase in ("ขออภัยครับ", "ขออภัยค่ะ", "โปรดทราบว่า", "ดังนั้น", "และ"):
        remainder = remainder.replace(allowed_phrase, "")
    return re.fullmatch(r"[\s,.:;!?()\-–—]*", remainder) is not None


def _error_presentation(
    result: ToolResult,
    response_policies: ResponsePolicies | None = None,
) -> ErrorPresentation:
    if response_policies is not None:
        presentation = response_policies.error_presentation(result)
        if presentation is not None:
            return presentation
    code = result.error.code if result.error else ToolErrorCode.INTERNAL
    defaults = {
        ToolErrorCode.NOT_FOUND: (
            "ไม่พบข้อมูลที่ตรงกับที่ระบุครับ",
            "กรุณาตรวจสอบข้อมูลแล้วลองใหม่อีกครั้งครับ",
            True,
        ),
        ToolErrorCode.INVALID_INPUT: (
            "ข้อมูลที่ระบุยังไม่ครบถ้วนหรือไม่ถูกต้องครับ",
            "กรุณาตรวจสอบข้อมูลแล้วลองใหม่อีกครั้งครับ",
            True,
        ),
        ToolErrorCode.CONFLICT: (
            "ไม่สามารถดำเนินรายการได้เนื่องจากสถานะข้อมูลขัดแย้งกันครับ",
            "กรุณาตรวจสอบสถานะล่าสุดก่อนลองใหม่ครับ",
            False,
        ),
        ToolErrorCode.UNAVAILABLE: (
            "บริการที่จำเป็นยังไม่พร้อมใช้งานครับ",
            "กรุณาลองใหม่อีกครั้งภายหลังครับ",
            True,
        ),
        ToolErrorCode.CONFIRMATION_REQUIRED: (
            "รายการนี้ยังไม่ได้รับการยืนยันจากผู้ใช้ครับ",
            "กรุณาตรวจทานรายการและกดยืนยันผ่านขั้นตอนที่กำหนดก่อนส่งครับ",
            False,
        ),
        ToolErrorCode.INTERNAL: (
            "ระบบไม่สามารถดำเนินคำขอนี้ได้ครับ",
            "กรุณาลองใหม่ภายหลังหรือติดต่อเจ้าหน้าที่หากปัญหายังคงเกิดขึ้นครับ",
            False,
        ),
    }
    explanation, next_step, retryable = defaults[code]
    return ErrorPresentation(code, explanation, next_step, retryable)


def _sanitize_error_result(
    result: ToolResult,
    response_policies: ResponsePolicies,
) -> ToolResult:
    """Replace raw tool error text before it reaches LLM history, API output, or state."""
    if result.status is not ToolResultStatus.ERROR or result.error is None:
        return result
    presentation = _error_presentation(result, response_policies)
    message = presentation.fallback_message()
    if len(message) > 500:
        message = f"{message[:497]}..."
    return result.model_copy(
        update={"error": ToolError(code=result.error.code, message=message)}
    )


def _operational_error_fact(result: ToolResult, response_policies: ResponsePolicies | None = None) -> str:
    """Render a safe deterministic fallback from typed plugin-owned error facts."""
    return _error_presentation(result, response_policies).fallback_message()


def _result_facts(
    results: list[ToolResult], *, user_message: str = "", response_policies: ResponsePolicies
) -> list[str]:
    """จัดรูปแบบเฉพาะข้อมูลผลลัพธ์ที่ผ่านการตรวจสอบ โดยไม่ใช้ข้อความของ planner หลังเรียกเครื่องมือ"""
    facts: list[str] = []
    knowledge_has_grounded = any(
        result.name is ToolName.KNOWLEDGE
        and result.status is ToolResultStatus.SUCCESS
        and result.citations
        and isinstance((result.data or {}).get("answerContext"), str)
        for result in results
    )
    seen_knowledge_facts: set[str] = set()
    for result in results:
        if result.name is ToolName.KNOWLEDGE and knowledge_has_grounded and not result.citations:
            continue
        if result.status is ToolResultStatus.ERROR:
            fact = (
                _KNOWLEDGE_ESCALATION_MESSAGE
                if result.name is ToolName.KNOWLEDGE
                else _operational_error_fact(result, response_policies)
            )
            # การลองซ้ำของโมเดลต้องไม่ทำให้ผู้ใช้เห็นข้อความเดิมซ้ำหลายรอบ
            if fact not in facts:
                facts.append(fact)
            continue
        data = result.data or {}
        if result.name is ToolName.KNOWLEDGE and isinstance(data.get("answerContext"), str):
            fact = (
                _knowledge_fact(data["answerContext"], user_message)
                if result.citations
                else _KNOWLEDGE_ESCALATION_MESSAGE
            )
            if fact not in seen_knowledge_facts:
                facts.append(fact)
                seen_knowledge_facts.add(fact)
        elif (fact := response_policies.result_fact(result)) is not None:
            facts.append(fact)
        elif isinstance(data.get("summary"), str):
            facts.append(data["summary"])
        else:
            facts.append(json.dumps(data, default=str, sort_keys=True))
    return facts


def _knowledge_fact(answer_context: str, user_message: str) -> str:
    """ตอบด้วยหลักฐานที่ยืนยันแล้วเสมอ และเติมคำถามต่อเนื่องเมื่อเป็นเอกสารที่ขึ้นกับประเภทผู้ขอ"""
    question = user_message.casefold()
    # คำถามเรื่องช่องทาง/ลิงก์/สถานที่ต้องการคำตอบที่มี URL อยู่ในหลักฐาน ไม่ใช่คำถามขอเอกสาร
    channel_terms = ("ที่ไหน", "ช่องทาง", "ออนไลน์", "เว็บ", "ลิงก์", "link", "สมัครที่ไหน")
    asks_about_channel = any(term in question for term in channel_terms)
    spans_applicant_types = "บุคคลธรรมดา" in answer_context and "นิติบุคคล" in answer_context
    user_selected_type = any(term in question for term in ("บุคคลธรรมดา", "นิติบุคคล", "บริษัท", "ธุรกิจ"))
    asks_about_documents = any(term in question for term in ("เอกสาร", "หลักฐาน", "เตรียม", "แนบ"))
    if spans_applicant_types and not user_selected_type and not asks_about_channel and asks_about_documents:
        # ห้ามทิ้งคำตอบที่มี citation เดิม — เติมคำถามต่อเนื่องท้ายคำตอบแทนการแทนที่
        return answer_context + (
            " และเอกสารที่ต้องเตรียมแตกต่างกันตามประเภทผู้ขอครับ "
            "ขอทราบว่าเป็นการขอในนามบุคคลธรรมดาหรือนิติบุคคลครับ?"
        )
    return answer_context


def _looks_like_knowledge_question(message: str) -> bool:
    """ตรวจว่าข้อความเป็นคำถามข้อมูลทั่วไปที่ควรส่งให้โมเดลตอบ"""
    text = " ".join(message.casefold().split())
    if re.match(r"^[1-6](?:\s*[.)-])?(?:\s|$)", text):
        return False
    if any(marker in text for marker in ("subject:", "detail:", "contactname:", "contactphone:", "location:")):
        return False
    return any(
        marker in text
        for marker in (
            "เกิดจากอะไร",
            "คืออะไร",
            "ทำไม",
            "อย่างไร",
            "ต้องใช้เอกสาร",
            "ขอข้อมูล",
            "สอบถาม",
            "มีเงื่อนไข",
            "ได้ไหม",
            "หรือไม่",
        )
    )


def _now() -> datetime:
    return datetime.now(UTC)
