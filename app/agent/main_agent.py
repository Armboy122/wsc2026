"""The single model-driven orchestrator for frozen PEA demo contracts."""

from __future__ import annotations

import asyncio
import json
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
from app.llm import LLMClient, LLMMessage, LLMRequest, LLMResponse, ToolDefinition

_MAX_TOOL_STEPS = 6
_SUBMIT_ACTIONS = frozenset({
    ToolAction.SABUY_SUBMIT_PAYMENT,
    ToolAction.VOC_SUBMIT_CASE,
    ToolAction.OMS_SUBMIT_OUTAGE_REPORT,
})
_TOOL_CATALOGUE = (
    ToolDefinition(ToolName.KNOWLEDGE, "Search hosted PEA knowledge", ("search",)),
    ToolDefinition(ToolName.SABUY, "Read account data or prepare a payment", ("get_account_summary", "prepare_payment")),
    ToolDefinition(ToolName.VOC, "List complaint categories or prepare a case", ("list_categories", "prepare_case")),
    ToolDefinition(ToolName.OMS, "Read outage status or prepare an outage report", ("get_outage_status", "prepare_outage_report")),
)
_SAFE_PREVIEW_FIELDS = frozenset({"accountRef", "amountThb", "paymentMethod", "category", "contactChannel", "areaCode"})
_MULTI_PREPARE_MESSAGE = "I couldn’t safely prepare more than one proposed action in a single chat. Please make one request at a time."


class NotFoundError(LookupError):
    """The requested process-local resource does not exist."""


class InvalidActionStateError(RuntimeError):
    """A confirmation/rejection transition is not allowed."""


class MainAgent:
    """Owns orchestration, confirmation policy, and auditable process-local state."""

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

        for _ in range(_MAX_TOOL_STEPS + 1):
            self._traces.append(trace_id, TraceEventKind.LLM_REQUESTED, {"messageCount": len(history), "toolCount": 4})
            try:
                response = await self._llm.complete(LLMRequest(history, _TOOL_CATALOGUE, trace_id))
            except Exception as error:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "llm", "type": type(error).__name__})
                final_text = "I’m unable to complete that request right now because the assistant service is unavailable."
                break

            calls, planner_text = _calls_from_response(response)
            self._traces.append(trace_id, TraceEventKind.LLM_RESPONDED, {"toolCallCount": len(calls), "hasText": bool(response.text or planner_text)})
            final_text = planner_text or response.text or final_text
            if not calls:
                break
            if len(all_results) + len(calls) > _MAX_TOOL_STEPS:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "tool_limit", "maximum": _MAX_TOOL_STEPS})
                final_text = "I couldn’t complete that request because it required too many tool steps."
                break
            if sum(call.action in PREPARE_TO_SUBMIT for call in calls) > 1:
                self._traces.append(trace_id, TraceEventKind.ERROR, {"stage": "multi_prepare_policy"})
                final_text = _MULTI_PREPARE_MESSAGE
                break

            prepared = False
            for call in calls:
                result = await self._execute_chat_call(call, conversation_id, trace_id)
                all_results.append(result)
                history += (LLMMessage("tool", _result_message(result)),)
                if result.status is ToolResultStatus.SUCCESS and result.action in PREPARE_TO_SUBMIT:
                    prepared = True
                    break
            if prepared:
                break
        else:  # pragma: no cover - guarded above; keeps the hard limit explicit
            final_text = "I couldn’t complete that request within the tool-step limit."

        pending = self._create_pending_from_results(conversation_id, trace_id, all_results)
        citations = tuple(citation for result in all_results if result.status is ToolResultStatus.SUCCESS for citation in result.citations)
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
            raise InvalidActionStateError("A rejected action cannot be confirmed")
        if pending.status is not PendingActionStatus.PENDING_CONFIRMATION:
            raise InvalidActionStateError("Action cannot be confirmed in its current state")

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
            raise InvalidActionStateError("Action cannot be rejected in its current state")
        rejected = pending.model_copy(update={"status": PendingActionStatus.REJECTED, "updated_at": _now()})
        self._pending_actions.update(rejected)
        self._traces.append(trace_id, TraceEventKind.ACTION_REJECTED, {"pendingActionId": str(pending_action_id), "reason": "[redacted]"})
        return ActionDecisionResponse(pending_action=rejected, tool_result=None, trace_id=trace_id)

    def get_trace(self, trace_id: UUID) -> TraceResponse:
        trace = self._traces.get(trace_id)
        if trace is None:
            raise NotFoundError("Trace not found")
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
            return _error_result(call, ToolErrorCode.CONFLICT, "Submit actions require explicit confirmation")
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
        except ValidationError:  # pragma: no cover - a successful registry result is already validated
            return None
        idempotency_key = prepared_input["idempotencyKey"]
        now = _now()
        pending = PendingAction(
            pending_action_id=uuid4(), conversation_id=conversation_id, tool_name=result.name,
            prepare_action=result.action, submit_action=PREPARE_TO_SUBMIT[result.action],
            prepared_input=_redact_prepared_input(prepared_input), summary=str((result.data or {}).get("summary", "Prepared action")),
            status=PendingActionStatus.PENDING_CONFIRMATION, idempotency_key=idempotency_key,
            created_at=now, updated_at=now,
        )
        self._pending_actions.put(pending, trace_id)
        self._traces.append(trace_id, TraceEventKind.ACTION_PREPARED, {"pendingActionId": str(pending.pending_action_id), "action": result.action.value})
        return pending

    def _require_pending(self, pending_action_id: UUID) -> PendingAction:
        pending = self._pending_actions.get(pending_action_id)
        if pending is None:
            raise NotFoundError("Pending action not found")
        return pending

    def _require_pending_trace(self, pending_action_id: UUID) -> UUID:
        trace_id = self._pending_actions.trace_id_for(pending_action_id)
        if trace_id is None:
            raise NotFoundError("Pending action trace not found")
        return trace_id


def _calls_from_response(response: LLMResponse) -> tuple[tuple[ToolCall, ...], str]:
    if response.tool_calls:
        return response.tool_calls, ""
    try:
        payload = json.loads(response.text)
        if not isinstance(payload, dict) or set(payload) != {"message", "toolCalls"} or not isinstance(payload["message"], str) or not isinstance(payload["toolCalls"], list):
            return (), response.text
        calls = tuple(ToolCall(call_id=uuid4(), name=item["name"], action=item["action"], input=item["input"]) for item in payload["toolCalls"] if isinstance(item, dict) and set(item) == {"name", "action", "input"})
        if len(calls) != len(payload["toolCalls"]):
            return (), "I couldn’t safely interpret the requested tool operation."
        return calls, payload["message"]
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
        return (), response.text


def _redact_prepared_input(data: dict[str, Any]) -> dict[str, Any]:
    """Expose only the fixed confirmation-preview fields; keep every other key redacted."""
    return {key: value if key in _SAFE_PREVIEW_FIELDS else "[redacted]" for key, value in data.items()}


def _result_message(result: ToolResult) -> str:
    if result.status is ToolResultStatus.ERROR:
        return json.dumps({"status": "error", "error": result.error.message if result.error else "Unknown error"})
    return json.dumps({"status": "success", "data": result.data, "citations": [citation.model_dump(by_alias=True) for citation in result.citations]}, default=str)


def _default_message(results: list[ToolResult]) -> str:
    if any(result.status is ToolResultStatus.ERROR for result in results):
        return "I couldn’t complete part of that request because a required service was unavailable."
    return "I completed the requested lookup."


def _authoritative_message(text: str, results: list[ToolResult], pending: PendingAction | None) -> str:
    if not results:
        return text or _default_message(results)

    safety = next((str((result.data or {}).get("safetyMessage")) for result in results if result.name is ToolName.OMS and result.status is ToolResultStatus.SUCCESS and (result.data or {}).get("safetyMessage")), None)
    facts = _result_facts(results)
    if pending:
        facts.append("Please explicitly confirm this proposed action to submit it.")
    message = "\n\n".join(facts) or _default_message(results)
    return f"{safety}\n\n{message}".strip() if safety and not message.startswith(safety) else message


def _result_facts(results: list[ToolResult]) -> list[str]:
    """Format only validated result data; planner prose is never used after a tool call."""
    facts: list[str] = []
    for result in results:
        if result.status is ToolResultStatus.ERROR:
            facts.append("I couldn’t complete part of that request because a required service was unavailable.")
            continue
        data = result.data or {}
        if result.name is ToolName.KNOWLEDGE and isinstance(data.get("answerContext"), str):
            facts.append(data["answerContext"] if result.citations else "I couldn’t provide a sourced answer for that request.")
        elif isinstance(data.get("summary"), str):
            facts.append(data["summary"])
        else:
            facts.append(json.dumps(data, default=str, sort_keys=True))
    return facts


def _now() -> datetime:
    return datetime.now(UTC)
