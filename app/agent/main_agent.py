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
from app.agent.voc_intake import (
    VocIntakeCoordinator,
    VocIntakeState,
    VocWorkflowStore,
    category_choices,
)
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
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    VocCategoryItem,
    TraceEventKind,
    TraceResponse,
    validate_tool_input,
)
from app.llm import (
    DirectResponseKind,
    KnowledgeConversationContext,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ToolDefinition,
)

# Keep the loop bounded while allowing a short clarification/tool chain.
_MAX_TOOL_STEPS = 12
_SUBMIT_ACTIONS = frozenset({
    ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
    ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE,
})
# ค่า legacy เหล่านี้คงไว้เป็น denylist เท่านั้น เพื่อให้ provider ที่ส่ง VOC มาถูกปฏิเสธแบบ fail closed
_DORMANT_VOC_DIRECT_RESPONSES = frozenset({
    DirectResponseKind.VOC_DETAILS,
    DirectResponseKind.VOC_CONTACT_NAME,
    DirectResponseKind.VOC_CONTACT_PHONE,
    DirectResponseKind.VOC_LOCATION,
    DirectResponseKind.VOC_TRACKING_INPUTS,
})
_TOOL_CATALOGUE = (
    ToolDefinition(ToolName.KNOWLEDGE, "ตอบความรู้ PEA จากข้อความฉบับเต็มของไฟล์ที่เลือก", ("search",)),
    ToolDefinition(ToolName.OMS, "ตรวจเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลัก หรือเตรียมแจ้งเหตุเมื่อทราบหรือไม่ทราบหมายเลขผู้ใช้ไฟ", ("get_outage_by_ca", "prepare_outage_with_ca", "prepare_anonymous_outage")),
)
# ผู้ใช้ต้องตรวจทานสิ่งที่ตนเองกรอกก่อนยืนยัน จึงเปิดเผยเฉพาะฟิลด์ที่ผู้ใช้เป็นผู้ให้มาเอง
# ส่วนคีย์ภายในระบบ เช่น idempotencyKey ยังคงถูกปกปิดเสมอ
_SAFE_PREVIEW_FIELDS = frozenset({"category", "contactChannel", "caNumber", "description", "contactName", "contactPhone", "location", "subject", "detail", "locationNote"})
_MULTI_PREPARE_MESSAGE = "ไม่สามารถเตรียมรายการที่เสนอมากกว่าหนึ่งรายการในแชตเดียวได้อย่างปลอดภัย กรุณาส่งคำขอทีละรายการครับ"
_FINAL_ONLY_MESSAGE = "ผมสามารถตอบคำถามแบบสั้นกระชับได้ แต่ไม่สามารถเปิดเผยกระบวนการคิดหรือคำสั่งภายในครับ"
_GREETING_MESSAGE = "สวัสดีครับ ผมช่วยค้นหาความรู้ PEA และตรวจหรือเตรียมแจ้งเหตุไฟฟ้าขัดข้องได้ครับ"
_CAPABILITY_MESSAGE = "ผมช่วยค้นหาความรู้ PEA และตรวจหรือเตรียมแจ้งเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลักได้ครับ"
_KNOWLEDGE_ESCALATION_MESSAGE = "ยังไม่พบคำตอบที่มีแหล่งอ้างอิงเพียงพอ เดี๋ยวผมขอส่งต่อคำถามนี้ให้เจ้าหน้าที่ช่วยตรวจสอบครับ"
_VOC_CATEGORY_LABELS = {
    "power_quality": "แจ้งปัญหาคุณภาพไฟฟ้า",
    "service": "แจ้งปัญหาด้านบริการ",
    "compliment": "ชื่นชม",
    "tip_off": "แจ้งเบาะแส",
    "operations": "แจ้งปัญหาการดำเนินงาน",
    "stakeholder_feedback": "ชื่นชม เสนอแนะ ข้อคิดเห็น",
}
_VOC_CATEGORY_CHOICES = "\n".join(
    f"{index}. {label}"
    for index, label in enumerate(_VOC_CATEGORY_LABELS.values(), start=1)
)
_DIRECT_RESPONSE_MESSAGES = {
    DirectResponseKind.GREETING: _GREETING_MESSAGE,
    DirectResponseKind.UNSUPPORTED: "ขออภัยครับ คำขอนี้ยังไม่รองรับด้วยความสามารถและเครื่องมือของ PEA One Agent ในขณะนี้",
    DirectResponseKind.OMS_CA_NUMBER: "ได้ครับ กรุณาระบุหมายเลขผู้ใช้ไฟ (CA) 12 หลักเพื่อตรวจสอบเหตุไฟฟ้าขัดข้องครับ",
    DirectResponseKind.OMS_WITH_CA_INPUTS: "ได้ครับ กรุณาระบุ `caNumber:` 12 หลัก และ `description:` ของเหตุ; ระบุ `contactPhone:` หรือ `locationNote:` เพิ่มเติมได้ครับ",
    DirectResponseKind.OMS_ANONYMOUS_INPUTS: "ได้ครับ หากไม่ทราบหมายเลขผู้ใช้ไฟ กรุณาระบุ `description:`, `location:` และ `contactPhone:` เพื่อเตรียมแจ้งเหตุครับ",
}
_EXACT_GREETINGS = frozenset({"hi", "hello", "hey"})
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
        voc_workflows: VocWorkflowStore | None = None,
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        self._conversations = conversations or ConversationStore()
        self._pending_actions = pending_actions or PendingActionStore()
        self._traces = traces or TraceStore()
        self._call_inputs: dict[UUID, dict[str, Any]] = {}
        self._confirmation_tasks: dict[UUID, asyncio.Task[ActionDecisionResponse]] = {}
        self._knowledge_contexts: dict[UUID, KnowledgeConversationContext] = {}
        self._voc_workflows = voc_workflows or VocWorkflowStore()
        self._voc_intake = VocIntakeCoordinator()
        self._voc_categories: tuple[VocCategoryItem, ...] | None = None
        # ข้อมูลที่กรอกไว้ของรายการที่ยังไม่สิ้นสุด ใช้คืนให้ผู้ใช้แก้ต่อเมื่อปฏิเสธ
        self._rejectable_voc_states: dict[UUID, VocIntakeState] = {}
        self._reset_generation = 0

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4()
        trace_id = uuid4()
        self._traces.append(trace_id, TraceEventKind.CHAT_RECEIVED, {"message": "[redacted]", "requestId": str(request.request_id) if request.request_id else None})
        history = self._conversations.messages_for(conversation_id) + (LLMMessage("user", request.message),)
        all_results: list[ToolResult] = []
        final_text = ""
        direct_completion_text: str | None = None
        direct_response_kind: DirectResponseKind | None = None
        seen_knowledge_calls: set[tuple[str, str]] = set()
        duplicate_knowledge_call = False

        for _ in range(_MAX_TOOL_STEPS):
            self._traces.append(trace_id, TraceEventKind.LLM_REQUESTED, {"messageCount": len(history), "toolCount": len(_TOOL_CATALOGUE)})
            try:
                response = await self._llm.complete(
                    LLMRequest(
                        history,
                        _TOOL_CATALOGUE,
                        trace_id,
                        self._knowledge_contexts.get(conversation_id),
                    )
                )
            except Exception as error:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "llm", "type": type(error).__name__})
                final_text = "ขณะนี้ไม่สามารถดำเนินการตามคำขอได้ เนื่องจากบริการผู้ช่วยไม่พร้อมใช้งานครับ"
                break

            calls, planner_text, parsed_direct_response = _calls_from_response(response)
            self._traces.append(trace_id, TraceEventKind.LLM_RESPONDED, {"toolCallCount": len(calls), "hasText": bool(response.text or planner_text)})
            final_text = planner_text or response.text or final_text
            if not calls:
                direct_completion_text = final_text
                direct_response_kind = response.direct_response or parsed_direct_response
                if direct_response_kind in _DORMANT_VOC_DIRECT_RESPONSES:
                    direct_response_kind = DirectResponseKind.UNSUPPORTED
                    final_text = _DIRECT_RESPONSE_MESSAGES[DirectResponseKind.UNSUPPORTED]
                    direct_completion_text = final_text
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
                history += (LLMMessage("tool", _result_message(result)),)
                if result.status is ToolResultStatus.SUCCESS and result.action in PREPARE_TO_SUBMIT:
                    prepared = True
                    break
            if prepared or duplicate_knowledge_call:
                break
        else:  # pragma: no cover - มีเงื่อนไขป้องกันไว้ด้านบน เพื่อระบุขีดจำกัดตายตัวให้ชัดเจน
            final_text = "ไม่สามารถดำเนินการตามคำขอได้ภายในขีดจำกัดขั้นตอนเครื่องมือครับ"

        pending = self._create_pending_from_results(conversation_id, trace_id, all_results)
        citations = tuple(citation for result in all_results if result.status is ToolResultStatus.SUCCESS for citation in result.citations)
        if not all_results and direct_completion_text is not None:
            final_text = _safe_direct_message(request.message, direct_completion_text, direct_response=direct_response_kind)
            if final_text == _FINAL_ONLY_MESSAGE:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "output_policy", "policy": "final_only"})
        message = _authoritative_message(final_text, all_results, pending, user_message=request.message)
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
        self._conversations.append(conversation_id, LLMMessage("assistant", message))
        return ChatResponse(conversation_id=conversation_id, trace_id=trace_id, message=message, citations=citations, pending_action=pending, tool_results=tuple(all_results))

    async def _load_voc_categories(
        self,
        conversation_id: UUID,
        trace_id: UUID,
    ) -> tuple[VocCategoryItem, ...]:
        if self._voc_categories is not None:
            return self._voc_categories
        call = ToolCall(call_id=uuid4(), name=ToolName.VOC, action=ToolAction.VOC_LIST_CATEGORIES, input={})
        result = await self._execute_chat_call(call, conversation_id, trace_id)
        if result.status is not ToolResultStatus.SUCCESS:
            return ()
        raw_categories = (result.data or {}).get("categories")
        if not isinstance(raw_categories, list):
            return ()
        try:
            categories = tuple(VocCategoryItem.model_validate(item) for item in raw_categories)
        except ValidationError:
            return ()
        self._voc_categories = categories
        return categories

    async def _continue_voc_intake(
        self,
        conversation_id: UUID,
        trace_id: UUID,
        message: str,
        state: VocIntakeState,
    ) -> ChatResponse:
        normalized = " ".join(message.casefold().split())
        if normalized in {"ยกเลิก", "ไม่ร้องเรียนแล้ว", "cancel", "stop"}:
            self._voc_workflows.pop(conversation_id)
            return self._finish_voc_turn(conversation_id, trace_id, message, "ยกเลิกการเตรียมเรื่องร้องเรียนแล้วครับ")

        categories = await self._load_voc_categories(conversation_id, trace_id)
        if not categories:
            return self._finish_voc_turn(conversation_id, trace_id, message, "ขณะนี้ไม่สามารถโหลดประเภทเรื่องร้องเรียนได้ กรุณาลองใหม่อีกครั้งครับ")
        decision = (
            self._voc_intake.advance(state, "", categories)
            if normalized in {"ดำเนินต่อ", "ทำต่อ", "continue"}
            else self._voc_intake.advance(state, message, categories)
        )
        self._voc_workflows.put(conversation_id, decision.state)
        if not decision.state.ready:
            response_text = category_choices(categories) if decision.needs_categories else decision.prompt or "กรุณาระบุข้อมูลเรื่องร้องเรียนเพิ่มเติมครับ"
            return self._finish_voc_turn(conversation_id, trace_id, message, response_text)

        call = ToolCall(
            call_id=uuid4(),
            name=ToolName.VOC,
            action=ToolAction.VOC_PREPARE_CASE,
            input=decision.state.prepare_input(f"voc-{uuid4()}"),
        )
        result = await self._execute_chat_call(call, conversation_id, trace_id)
        results = [result]
        pending = self._create_pending_from_results(conversation_id, trace_id, results)
        if result.status is ToolResultStatus.SUCCESS and pending is not None:
            # เก็บข้อมูลที่กรอกไว้จนกว่าจะส่งเรื่องจริง ผู้ใช้ที่ปฏิเสธเพราะพิมพ์ผิด
            # จะได้แก้เฉพาะฟิลด์ที่ผิดต่อได้ โดยไม่ต้องกรอกใหม่ทั้งหมด
            self._rejectable_voc_states[pending.pending_action_id] = decision.state
            self._voc_workflows.pop(conversation_id)
        response_text = _authoritative_message("", results, pending)
        self._conversations.append(conversation_id, LLMMessage("user", message))
        self._conversations.append(conversation_id, LLMMessage("assistant", response_text))
        return ChatResponse(
            conversation_id=conversation_id,
            trace_id=trace_id,
            message=response_text,
            citations=(),
            pending_action=pending,
            tool_results=tuple(results),
        )

    def _finish_voc_turn(
        self,
        conversation_id: UUID,
        trace_id: UUID,
        user_message: str,
        response_text: str,
    ) -> ChatResponse:
        self._conversations.append(conversation_id, LLMMessage("user", user_message))
        self._conversations.append(conversation_id, LLMMessage("assistant", response_text))
        return ChatResponse(
            conversation_id=conversation_id,
            trace_id=trace_id,
            message=response_text,
            citations=(),
            pending_action=None,
            tool_results=(),
        )

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
        # ส่งเรื่องแล้วไม่ต้องคืนฟอร์มให้แก้อีก
        self._rejectable_voc_states.pop(pending_action_id, None)
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
        # ผู้ใช้มักปฏิเสธเพราะกรอกผิดบางฟิลด์ จึงคืนข้อมูลที่กรอกไว้ให้แก้ต่อได้
        # แทนการทิ้งบทสนทนาจนต้องเริ่มกรอกใหม่ทั้งหมด
        resumable = self._rejectable_voc_states.pop(pending_action_id, None)
        if resumable is not None:
            self._voc_workflows.put(pending.conversation_id, resumable.reopen())
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
        self._voc_workflows.clear()
        self._rejectable_voc_states.clear()
        self._voc_categories = None
        return ResetResponse()

    async def _execute_chat_call(self, call: ToolCall, conversation_id: UUID, trace_id: UUID) -> ToolResult:
        if call.action in _SUBMIT_ACTIONS:
            self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "chat_policy", "action": call.action.value})
            return _error_result(call, ToolErrorCode.CONFLICT, "การส่งรายการต้องได้รับการยืนยันอย่างชัดเจน")
        return await self._execute_internal(call, conversation_id, trace_id)

    async def _execute_internal(self, call: ToolCall, conversation_id: UUID, trace_id: UUID) -> ToolResult:
        self._call_inputs[call.call_id] = dict(call.input)
        self._traces.append(trace_id, TraceEventKind.TOOL_CALLED, {"name": call.name.value, "action": call.action.value, "callId": str(call.call_id)})
        result = await self._tools.execute(call, ToolContext(conversation_id, trace_id))
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
) -> tuple[tuple[ToolCall, ...], str, DirectResponseKind | None]:
    if response.tool_calls:
        return response.tool_calls, "", None
    try:
        payload = json.loads(response.text)
        allowed_keys = {"message", "toolCalls", "directResponse"}
        if (
            not isinstance(payload, dict)
            or set(payload) != allowed_keys
            or not isinstance(payload["message"], str)
            or not isinstance(payload["toolCalls"], list)
        ):
            return (), response.text, None
        direct_response = DirectResponseKind(payload["directResponse"]) if payload["directResponse"] is not None else None
        calls = tuple(ToolCall(call_id=uuid4(), name=item["name"], action=item["action"], input=item["input"]) for item in payload["toolCalls"] if isinstance(item, dict) and set(item) == {"name", "action", "input"})
        if len(calls) != len(payload["toolCalls"]):
            return (), "ไม่สามารถตีความการดำเนินการของเครื่องมือที่ร้องขอได้อย่างปลอดภัยครับ", None
        if calls and direct_response is not None:
            return (), "ไม่สามารถใช้ข้อความตรงร่วมกับการเรียกเครื่องมือได้ครับ", None
        return calls, payload["message"], direct_response
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
        return (), response.text, None


def _requires_final_only_output(text: str) -> bool:
    """ตรวจจับการเปิดเผยกระบวนการคิดหรือคำสั่งภายในอย่างชัดเจนในข้อความตรงจากโมเดล"""
    return any(pattern.search(text) for pattern in _OUTPUT_POLICY_PATTERNS)


def _safe_direct_message(
    user_message: str,
    completion_text: str,
    *,
    direct_response: DirectResponseKind | None = None,
) -> str:
    """สร้างข้อความตรงจากชนิดที่กำหนดไว้ โดยไม่เชื่อถือข้อความอิสระจากโมเดล"""
    if _requires_final_only_output(completion_text):
        return _FINAL_ONLY_MESSAGE
    if user_message.strip().casefold() in _EXACT_GREETINGS:
        return _GREETING_MESSAGE
    if isinstance(direct_response, DirectResponseKind):
        return _DIRECT_RESPONSE_MESSAGES[direct_response]
    return _CAPABILITY_MESSAGE


def _redact_prepared_input(data: dict[str, Any]) -> dict[str, Any]:
    """เปิดเผยเฉพาะฟิลด์ตัวอย่างการยืนยันตามสัญญา และปกปิดคีย์อื่นทั้งหมด"""
    return {key: value if key in _SAFE_PREVIEW_FIELDS else "[redacted]" for key, value in data.items()}


def _result_message(result: ToolResult) -> str:
    if result.status is ToolResultStatus.ERROR:
        return json.dumps({"status": "error", "error": result.error.message if result.error else "ข้อผิดพลาดที่ไม่ทราบสาเหตุ"})
    return json.dumps({"status": "success", "data": result.data, "citations": [citation.model_dump(by_alias=True) for citation in result.citations]}, default=str)


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
) -> str:
    if not results:
        return text or _default_message(results)

    safety = next((str((result.data or {}).get("safetyMessage")) for result in results if result.name is ToolName.OMS and result.status is ToolResultStatus.SUCCESS and (result.data or {}).get("safetyMessage")), None)
    facts = _result_facts(results, user_message=user_message)
    if pending:
        facts.append("กรุณายืนยันรายการที่เสนอนี้อย่างชัดเจนเพื่อส่งรายการครับ")
    message = "\n\n".join(facts) or _default_message(results)
    return f"{safety}\n\n{message}".strip() if safety and not message.startswith(safety) else message


def _operational_error_fact(result: ToolResult) -> str:
    """อธิบายสาเหตุที่ผู้ใช้แก้ไขเองได้ แทนการเหมารวมว่าบริการไม่พร้อมใช้งาน

    ``not_found`` ของการติดตามเรื่องเกิดจาก ``vocId``/``trackingKey`` ไม่ตรงกัน
    ซึ่งผู้ใช้แก้ไขเองได้ จึงต้องไม่สื่อสารเหมือนระบบขัดข้อง
    """
    code = result.error.code if result.error else None
    if result.action is ToolAction.VOC_GET_CASE and code is ToolErrorCode.NOT_FOUND:
        return (
            "ไม่พบเรื่องร้องเรียนที่ตรงกับเลขเรื่องและคีย์ติดตามที่ระบุครับ "
            "กรุณาตรวจสอบว่าทั้งสองค่าตรงกับที่ได้รับตอนส่งเรื่อง "
            "โดยคีย์ติดตามมีการแยกตัวพิมพ์เล็ก-ใหญ่ครับ"
        )
    if result.name is ToolName.OMS and result.action is ToolAction.OMS_GET_OUTAGE_BY_CA and code is ToolErrorCode.NOT_FOUND:
        return "ไม่พบหมายเลขผู้ใช้ไฟใน OMS ครับ หากไม่ทราบหมายเลขผู้ใช้ไฟ สามารถแจ้งเหตุโดยระบุ description, location และ contactPhone ได้ครับ"
    if result.name is ToolName.OMS and code is ToolErrorCode.CONFLICT:
        return "OMS พบเหตุการณ์ที่เกี่ยวข้องอยู่แล้ว จึงไม่สามารถสร้างเหตุซ้ำได้ครับ"
    if code is ToolErrorCode.NOT_FOUND:
        return "ไม่พบข้อมูลที่ตรงกับที่ระบุครับ กรุณาตรวจสอบข้อมูลอีกครั้ง"
    if code is ToolErrorCode.INVALID_INPUT:
        return "ข้อมูลที่ระบุยังไม่ครบถ้วนหรือไม่ถูกต้องครับ กรุณาตรวจสอบแล้วลองใหม่อีกครั้ง"
    return "ไม่สามารถดำเนินการบางส่วนของคำขอได้ เนื่องจากบริการที่จำเป็นไม่พร้อมใช้งานครับ"


def _result_facts(results: list[ToolResult], *, user_message: str = "") -> list[str]:
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
                else _operational_error_fact(result)
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
        elif result.name is ToolName.VOC:
            facts.append(_voc_result_fact(result.action, data))
        elif result.name is ToolName.OMS:
            facts.append(_oms_result_fact(result.action, data))
        elif isinstance(data.get("summary"), str):
            facts.append(data["summary"])
        else:
            facts.append(json.dumps(data, default=str, sort_keys=True))
    return facts


def _knowledge_fact(answer_context: str, user_message: str) -> str:
    """Ask one useful follow-up when grounded evidence spans distinct applicant types."""
    question = user_message.casefold()
    spans_applicant_types = "บุคคลธรรมดา" in answer_context and "นิติบุคคล" in answer_context
    user_selected_type = any(term in question for term in ("บุคคลธรรมดา", "นิติบุคคล", "บริษัท", "ธุรกิจ"))
    if spans_applicant_types and not user_selected_type:
        return (
            "เอกสารที่ต้องเตรียมแตกต่างกันตามประเภทผู้ขอครับ "
            "ขอทราบว่าเป็นการขอในนามบุคคลธรรมดาหรือนิติบุคคลครับ?"
        )
    return answer_context


def _oms_result_fact(action: ToolAction, data: dict[str, Any]) -> str:
    """สรุป OMS โดยไม่เปิดเผยหมายเลขผู้ใช้ไฟหรือโครงข่ายภายใน"""
    if action is ToolAction.OMS_GET_OUTAGE_BY_CA:
        active_event = data.get("activeEvent")
        if isinstance(active_event, dict) and isinstance(active_event.get("message"), str):
            status = active_event.get("status")
            return f"สถานะ {status}: {active_event['message']}" if isinstance(status, str) else active_event["message"]
        return "ไม่พบเหตุไฟฟ้าขัดข้องที่เกี่ยวข้องในขณะนี้ครับ"
    if action in {ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE}:
        summary = data.get("summary")
        return summary if isinstance(summary, str) else "เตรียมแจ้งเหตุไฟฟ้าขัดข้องแล้วครับ"
    if action in {ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE}:
        message = data.get("message")
        status = data.get("status")
        reference = data.get("eventId") or data.get("reportId")
        prefix = f"สถานะ {status}: " if isinstance(status, str) else ""
        if isinstance(message, str) and isinstance(reference, str):
            return f"{prefix}{message} (เลขอ้างอิง {reference})"
        if isinstance(message, str):
            return f"{prefix}{message}"
    return "ดำเนินการกับ OMS เรียบร้อยแล้วครับ"


def _voc_result_fact(action: ToolAction, data: dict[str, Any]) -> str:
    """แปลงผล VOC ที่เชื่อถือได้เป็นภาษาผู้ใช้ โดยไม่เปิดเผย payload ภายใน"""
    if action is ToolAction.VOC_LIST_CATEGORIES:
        categories = data.get("categories")
        if isinstance(categories, list):
            labels = [
                item.get("label")
                for item in categories
                if isinstance(item, dict) and isinstance(item.get("label"), str)
            ]
            if labels:
                choices = "\n".join(
                    f"{index}. {label}" for index, label in enumerate(labels, start=1)
                )
                return (
                    "ประเภทเรื่องที่เลือกได้มีดังนี้:\n"
                    f"{choices}\n\n"
                    "พิมพ์ชื่อประเภทเรื่องที่ต้องการได้เลยครับ"
                )
    if action is ToolAction.VOC_GET_CASE:
        voc_id = data.get("vocId")
        status = data.get("status")
        category = _VOC_CATEGORY_LABELS.get(str(data.get("category")), "ไม่ระบุประเภท")
        if isinstance(voc_id, str) and isinstance(status, str):
            status_label = "ส่งเรื่องแล้ว" if status == "submitted" else status
            return f"เรื่องร้องเรียนเลขที่ {voc_id} มีสถานะ {status_label} ประเภท {category} ครับ"
    if isinstance(data.get("summary"), str):
        return data["summary"]
    return "ดำเนินการเรื่องร้องเรียนเรียบร้อยแล้วครับ"


def _looks_like_knowledge_question(message: str) -> bool:
    """Allow an explicit information question to temporarily interrupt VOC intake."""
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
