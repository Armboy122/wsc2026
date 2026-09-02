"""Deterministic offline adapter that composes behavior from enabled plugins.

The adapter owns only generic conversation and Knowledge behavior. Operational
intent, calls, and follow-up chaining are contributed by plugin-owned
``DemoBehavior`` implementations injected when the adapter is constructed.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.contracts import ToolAction, ToolCall, ToolName
from app.llm.demo_behavior import DemoBehavior, DemoPlan, DemoToolCall
from app.llm.models import (
    KnowledgeConversationContext,
    LLMMessage,
    LLMRequest,
    LLMResponse,
)


class DemoLLMAdapter:
    """Plan deterministic demo turns from explicitly enabled plugin behaviors."""

    def __init__(self, behaviors: tuple[DemoBehavior, ...] = ()) -> None:
        self._behaviors = behaviors

    async def ready(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        user_index = _latest_user_index(request.messages)
        if user_index is None:
            return _direct_response("greeting")
        current_messages = request.messages[user_index:]
        tool_messages = tuple(message for message in current_messages if message.role == "tool")
        if tool_messages:
            return self._after_tools(
                current_messages,
                tool_messages,
                request.correlation_id,
                self._behaviors,
            )
        message = _planning_message(
            request.messages,
            user_index,
            request.knowledge_context,
            self._behaviors,
        )
        return self._plan(message, request.correlation_id, self._behaviors)

    def _plan(
        self,
        message: str,
        correlation_id: UUID,
        planners: tuple[DemoBehavior, ...],
    ) -> LLMResponse:
        text = message.casefold()
        if _is_greeting(text):
            return _direct_response("greeting")
        if _is_thanks(text):
            return _direct_response("thanks")
        if _is_unsafe_or_unknown_request(text):
            return _direct_response("unsupported")

        contributions = tuple(
            contribution
            for planner in planners
            if (contribution := planner.plan_demo(message, correlation_id)) is not None
        )
        selected = _select_contributions(contributions)
        if direct := _direct_from(selected):
            return _direct_response(direct)

        calls = [call for contribution in selected for call in contribution.calls]
        if _knowledge_requested(text):
            calls.append(
                DemoToolCall(
                    _first_marker_position(
                        message,
                        ("knowledge", "policy", "tariff", "rate", "guidance", "safety", "payment channels", "ค้นหา", "นโยบาย", "อัตราค่าไฟ"),
                    ),
                    ToolName.KNOWLEDGE,
                    ToolAction.KNOWLEDGE_SEARCH,
                    {"query": _safe_query(message), "maxResults": 3},
                )
            )
        if calls:
            return _planned_response(correlation_id, calls)

        has_operational_intent = any(planner.has_demo_intent(message) for planner in planners)
        if _is_pea_knowledge_request(text) and not has_operational_intent:
            return _planned_response(
                correlation_id,
                [DemoToolCall(0, ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3})],
            )
        return _direct_response("unsupported")

    def _after_tools(
        self,
        messages: tuple[LLMMessage, ...],
        tool_messages: tuple[LLMMessage, ...],
        correlation_id: UUID,
        planners: tuple[DemoBehavior, ...],
    ) -> LLMResponse:
        results = tuple(_tool_payload(message.content) for message in tool_messages)
        contributions = tuple(
            contribution
            for planner in planners
            if (contribution := planner.after_tools_demo(messages, results, correlation_id)) is not None
        )
        selected = _select_contributions(contributions)
        if direct := _direct_from(selected):
            return _direct_response(direct)
        calls = [call for contribution in selected for call in contribution.calls]
        if calls:
            return _planned_response(correlation_id, calls)
        return LLMResponse(text=_generic_grounded_message(results))


def _select_contributions(contributions: tuple[DemoPlan, ...]) -> tuple[DemoPlan, ...]:
    exclusive = tuple(
        contribution for contribution in contributions if contribution.exclusive_among_plugins
    )
    return exclusive or contributions


def _direct_from(contributions: tuple[DemoPlan, ...]) -> str | None:
    labels = tuple(dict.fromkeys(
        contribution.direct_response
        for contribution in contributions
        if contribution.direct_response is not None
    ))
    return labels[0] if len(labels) == 1 else ("unsupported" if labels else None)


def _latest_user_index(messages: tuple[LLMMessage, ...]) -> int | None:
    return next((index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"), None)


_CLARIFICATION_MARKERS = ("กรุณาระบุ", "กรุณาแจ้ง")


def _planning_message(
    messages: tuple[LLMMessage, ...],
    user_index: int,
    knowledge_context: KnowledgeConversationContext | None,
    planners: tuple[DemoBehavior, ...],
) -> str:
    current_message = messages[user_index].content
    user_messages = [current_message]
    cursor = user_index - 1
    while cursor >= 1:
        assistant = messages[cursor]
        if assistant.role != "assistant" or not any(marker in assistant.content for marker in _CLARIFICATION_MARKERS):
            break
        previous_user_index = next(
            (index for index in range(cursor - 1, -1, -1) if messages[index].role == "user"),
            None,
        )
        if previous_user_index is None:
            break
        user_messages.append(messages[previous_user_index].content)
        cursor = previous_user_index - 1
    if len(user_messages) > 1:
        return "\n".join(reversed(user_messages))

    if knowledge_context and _can_reuse_knowledge_context(current_message, planners):
        current_context = " ".join(current_message.split())[:450]
        source_context = "; ".join(knowledge_context.sources)[:300]
        previous_context = " ".join(knowledge_context.previous_question.split())[:120]
        return (
            f"คำถามปัจจุบันที่ต้องตอบ: {current_context}\n"
            f"บริบทเอกสารจากรอบก่อน: {source_context}\n"
            f"คำถามก่อนหน้าเพื่อระบุหัวข้อเท่านั้น: {previous_context}"
        )
    return current_message


def _can_reuse_knowledge_context(message: str, planners: tuple[DemoBehavior, ...]) -> bool:
    text = " ".join(message.casefold().split())
    if (
        not text
        or _is_greeting(text)
        or _is_unsafe_or_unknown_request(text)
        or any(planner.has_demo_intent(message) for planner in planners)
    ):
        return False
    if _is_pea_knowledge_request(text):
        return True
    if any(
        reference in text
        for reference in (
            "กรณีนี้", "อันนี้", "ดังกล่าว", "เรื่องนี้", "บริการนี้", "เอกสารนี้",
            "ผู้ขอ", "เจ้าของบ้าน", "ผู้ยื่น", "it", "this", "that", "the applicant",
        )
    ):
        return True
    return bool(
        re.search(
            r"^(?:แล้ว\s*)?(?:ต้อง)?(?:ยื่น|เตรียม|ติดต่อ|ดำเนินการ|สมัคร)"
            r"|^(?:แล้ว\s*)?(?:มี)?(?:ค่าใช้จ่าย|ค่าธรรมเนียม|ระยะเวลา)"
            r"|^(?:แล้ว\s*)?ต้องทำอะไร(?:ต่อ|เพิ่ม)?"
            r"|^(?:ถ้า|กรณี)"
            r"|^(?:where|when|what else|how much)\b",
            text,
            re.IGNORECASE,
        )
    )


def _planned_response(correlation_id: UUID, planned: list[DemoToolCall]) -> LLMResponse:
    ordered = sorted(planned, key=lambda item: item.position)
    return LLMResponse(tool_calls=tuple(
        ToolCall(
            call_id=_call_id(correlation_id, call.name, call.action, call.input, ordinal),
            name=call.name,
            action=call.action,
            input=call.input,
        )
        for ordinal, call in enumerate(ordered)
    ))


def _direct_response(kind: str) -> LLMResponse:
    return LLMResponse(direct_response=kind)


def _call_id(
    correlation_id: UUID,
    name: ToolName,
    action: ToolAction,
    input_data: dict[str, Any],
    ordinal: int,
) -> UUID:
    canonical_input = json.dumps(input_data, sort_keys=True, separators=(",", ":"))
    return uuid5(NAMESPACE_URL, f"{correlation_id}:{ordinal}:{name.value}:{action.value}:{canonical_input}")


def _first_marker_position(message: str, markers: tuple[str, ...]) -> int:
    text = message.casefold()
    positions = (text.find(marker.casefold()) for marker in markers)
    return min((index for index in positions if index >= 0), default=len(text))


def _is_greeting(text: str) -> bool:
    return text.strip(" !,.?\n") in {"hello", "hi", "hey", "สวัสดี"}


def _is_thanks(text: str) -> bool:
    return text.strip(" !,.?\n").casefold() in {
        "ขอบคุณ", "ขอบคุณครับ", "ขอบคุณมาก", "ขอบคุณมากครับ", "thank you", "thanks",
    }


def _is_unsafe_or_unknown_request(text: str) -> bool:
    return any(term in text for term in (
        "system prompt", "ignore all policy", "api_key", "payment token", "pan-", "delete_database", "hidden tool",
    ))


def _knowledge_requested(text: str) -> bool:
    return any(term in text for term in (
        "knowledge", "policy", "tariff", "rate", "search", "guidance", "ค้นหา", "ข้อมูล", "safety",
    ))


def _is_pea_knowledge_request(text: str) -> bool:
    return any(term in text for term in (
        "bill", "account", "electric", "power", "outage", "payment", "meter", "service",
        "complaint", "case", "generator", "wire", "downed line", "safety", "contact",
        "restoration", "mailing", "maintenance", "overdue", "paid status", "official message",
        "document", "ไฟ", "บัญชี", "ชำระ", "มิเตอร์", "บริการ", "ร้องเรียน", "สายไฟ",
        "ความปลอดภัย", "ติดต่อ", "เอกสาร",
    ))


def _safe_query(message: str) -> str:
    return " ".join(message.split())[:1000] or "ข้อมูลเดโม PEA"


def _tool_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {"status": "error", "error": "ผลลัพธ์เครื่องมือไม่พร้อมใช้งาน"}
    return payload if isinstance(payload, dict) else {"status": "error", "error": "ผลลัพธ์เครื่องมือไม่ถูกต้อง"}


def _generic_grounded_message(results: tuple[dict[str, Any], ...]) -> str:
    messages: list[str] = []
    for result in results:
        if result.get("status") != "success":
            presentation = result.get("errorPresentation")
            if isinstance(presentation, dict):
                explanation = presentation.get("explanation")
                next_step = presentation.get("nextStep")
                if isinstance(explanation, str) and isinstance(next_step, str):
                    messages.append(f"{explanation} {next_step}")
                    continue
            messages.append("บริการที่ร้องขอไม่พร้อมใช้งาน กรุณาลองใหม่ภายหลังครับ")
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("summary"), str):
            messages.append(data["summary"])
        elif isinstance(data.get("answerContext"), str):
            citation_count = len(result.get("citations", []))
            messages.append(f"{data['answerContext']} (อ้างอิง {citation_count} แหล่ง)")
    return " ".join(messages)
