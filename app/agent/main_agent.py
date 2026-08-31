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
    TraceEventKind,
    TraceResponse,
    validate_tool_input,
)
from app.llm import DirectResponseKind, LLMClient, LLMMessage, LLMRequest, LLMResponse, ToolDefinition

_MAX_TOOL_STEPS = 6
_SUBMIT_ACTIONS = frozenset({
    ToolAction.SABUY_SUBMIT_PAYMENT,
    ToolAction.VOC_SUBMIT_CASE,
    ToolAction.OMS_SUBMIT_OUTAGE_REPORT,
})
_TOOL_CATALOGUE = (
    ToolDefinition(ToolName.KNOWLEDGE, "ค้นหาความรู้ PEA จากบริการโฮสต์", ("search",)),
    ToolDefinition(ToolName.SABUY, "อ่านข้อมูลบัญชีหรือเตรียมการชำระเงิน", ("get_account_summary", "prepare_payment")),
    ToolDefinition(ToolName.VOC, "แสดง 6 หมวด VOC ของ PEA: ปัญหาคุณภาพไฟฟ้า บริการ ชื่นชม เบาะแส ปัญหาการดำเนินงาน และข้อคิดเห็นผู้มีส่วนได้ส่วนเสีย หรือเตรียมเคส", ("list_categories", "prepare_case")),
    ToolDefinition(ToolName.OMS, "อ่านสถานะไฟฟ้าขัดข้องหรือเตรียมรายงานไฟฟ้าขัดข้อง", ("get_outage_status", "prepare_outage_report")),
)
_SAFE_PREVIEW_FIELDS = frozenset({"accountRef", "amountThb", "paymentMethod", "category", "contactChannel", "areaCode"})
_MULTI_PREPARE_MESSAGE = "ไม่สามารถเตรียมรายการที่เสนอมากกว่าหนึ่งรายการในแชตเดียวได้อย่างปลอดภัย กรุณาส่งคำขอทีละรายการครับ"
_FINAL_ONLY_MESSAGE = "ผมสามารถตอบคำถามแบบสั้นกระชับได้ แต่ไม่สามารถเปิดเผยกระบวนการคิดหรือคำสั่งภายในครับ"
_GREETING_MESSAGE = "สวัสดีครับ ผมช่วยค้นหาความรู้ PEA และใช้เครื่องมือจำลองสำหรับบัญชี ไฟฟ้าขัดข้อง เรื่องร้องเรียน และการชำระเงินได้ครับ"
_CAPABILITY_MESSAGE = "ผมช่วยค้นหาความรู้ PEA และใช้เครื่องมือจำลองสำหรับบัญชี ไฟฟ้าขัดข้อง เรื่องร้องเรียน และการชำระเงินได้ครับ กรุณาบอกสิ่งที่ต้องการ พร้อมข้อมูลบัญชี พื้นที่ รายละเอียดเรื่อง หรือจำนวนเงินที่เกี่ยวข้องครับ"
_DIRECT_RESPONSE_MESSAGES = {
    DirectResponseKind.GREETING: _GREETING_MESSAGE,
    DirectResponseKind.UNSUPPORTED: "ขออภัยครับ คำขอนี้ยังไม่รองรับด้วยความสามารถและเครื่องมือของ PEA One Agent ในขณะนี้",
    DirectResponseKind.PAYMENT_INPUTS: "ได้ครับ กรุณาระบุบัญชีเดโม จำนวนเงินที่มากกว่าศูนย์ และ `paymentMethod: demo_card` หรือ `paymentMethod: demo_bank` เพื่อเตรียมการชำระเงินครับ",
    DirectResponseKind.ACCOUNT_REF: "ได้ครับ กรุณาระบุหมายเลขบัญชีเดโม เช่น `PEA-1001` เพื่อตรวจสอบข้อมูลบัญชีครับ",
    DirectResponseKind.OUTAGE_REPORT_INPUTS: "ได้ครับ กรุณาระบุพื้นที่ที่รู้จัก พร้อมรายละเอียด `location:` และ `symptoms:` เพื่อเตรียมแจ้งเหตุไฟฟ้าขัดข้องครับ",
    DirectResponseKind.OUTAGE_STATUS_AREA: "ได้ครับ กรุณาระบุรหัสพื้นที่เดโม เช่น `BKK-01` เพื่อตรวจสอบสถานะไฟฟ้าขัดข้องครับ",
    DirectResponseKind.VOC_DETAILS: "ได้ครับ ต้องการร้องเรียนด้านบริการเรื่องใด กรุณาระบุหัวข้อ (`subject:`) และรายละเอียด (`detail:`) เพื่อให้ผมเตรียมเรื่องร้องเรียนให้ครับ",
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
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        self._conversations = conversations or ConversationStore()
        self._pending_actions = pending_actions or PendingActionStore()
        self._traces = traces or TraceStore()
        self._call_inputs: dict[UUID, dict[str, Any]] = {}
        self._confirmation_tasks: dict[UUID, asyncio.Task[ActionDecisionResponse]] = {}
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

        for _ in range(_MAX_TOOL_STEPS + 1):
            self._traces.append(trace_id, TraceEventKind.LLM_REQUESTED, {"messageCount": len(history), "toolCount": 4})
            try:
                response = await self._llm.complete(LLMRequest(history, _TOOL_CATALOGUE, trace_id))
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
                result = await self._execute_chat_call(call, conversation_id, trace_id)
                all_results.append(result)
                history += (LLMMessage("tool", _result_message(result)),)
                if result.status is ToolResultStatus.SUCCESS and result.action in PREPARE_TO_SUBMIT:
                    prepared = True
                    break
            if prepared:
                break
        else:  # pragma: no cover - มีเงื่อนไขป้องกันไว้ด้านบน เพื่อระบุขีดจำกัดตายตัวให้ชัดเจน
            final_text = "ไม่สามารถดำเนินการตามคำขอได้ภายในขีดจำกัดขั้นตอนเครื่องมือครับ"

        pending = self._create_pending_from_results(conversation_id, trace_id, all_results)
        citations = tuple(citation for result in all_results if result.status is ToolResultStatus.SUCCESS for citation in result.citations)
        if not all_results and direct_completion_text is not None:
            final_text = _safe_direct_message(request.message, direct_completion_text, direct_response=direct_response_kind)
            if final_text == _FINAL_ONLY_MESSAGE:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "output_policy", "policy": "final_only"})
        message = _authoritative_message(final_text, all_results, pending)
        self._conversations.append(conversation_id, LLMMessage("user", request.message))
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


def _default_message(results: list[ToolResult]) -> str:
    if any(result.status is ToolResultStatus.ERROR for result in results):
        return "ไม่สามารถดำเนินการบางส่วนของคำขอได้ เนื่องจากบริการที่จำเป็นไม่พร้อมใช้งานครับ"
    return "ดำเนินการค้นหาที่ร้องขอเรียบร้อยแล้วครับ"


def _authoritative_message(text: str, results: list[ToolResult], pending: PendingAction | None) -> str:
    if not results:
        return text or _default_message(results)

    safety = next((str((result.data or {}).get("safetyMessage")) for result in results if result.name is ToolName.OMS and result.status is ToolResultStatus.SUCCESS and (result.data or {}).get("safetyMessage")), None)
    facts = _result_facts(results)
    if pending:
        facts.append("กรุณายืนยันรายการที่เสนอนี้อย่างชัดเจนเพื่อส่งรายการครับ")
    message = "\n\n".join(facts) or _default_message(results)
    return f"{safety}\n\n{message}".strip() if safety and not message.startswith(safety) else message


def _result_facts(results: list[ToolResult]) -> list[str]:
    """จัดรูปแบบเฉพาะข้อมูลผลลัพธ์ที่ผ่านการตรวจสอบ โดยไม่ใช้ข้อความของ planner หลังเรียกเครื่องมือ"""
    facts: list[str] = []
    for result in results:
        if result.status is ToolResultStatus.ERROR:
            facts.append("ไม่สามารถดำเนินการบางส่วนของคำขอได้ เนื่องจากบริการที่จำเป็นไม่พร้อมใช้งานครับ")
            continue
        data = result.data or {}
        if result.name is ToolName.KNOWLEDGE and isinstance(data.get("answerContext"), str):
            facts.append(data["answerContext"] if result.citations else "ไม่สามารถให้คำตอบที่มีแหล่งอ้างอิงสำหรับคำขอนี้ได้ครับ")
        elif isinstance(data.get("summary"), str):
            facts.append(data["summary"])
        else:
            facts.append(json.dumps(data, default=str, sort_keys=True))
    return facts


def _now() -> datetime:
    return datetime.now(UTC)
