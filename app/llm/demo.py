"""ตัววางแผนแบบกำหนดผลลัพธ์ได้และทำงานออฟไลน์สำหรับเดโม PEA ที่มีการจัดการ

อะแดปเตอร์อ่านเฉพาะข้อความ ``user`` และ ``tool`` ที่มองเห็นได้ ไม่เคยรับ เก็บรักษา
หรืออนุมานกระบวนการคิดที่ซ่อนอยู่ การเรียกใช้งานปฏิบัติการต้องใช้ตัวระบุเดโมที่รู้จัก
และข้อมูลสำหรับเขียนที่ครบถ้วนและระบุอย่างชัดเจน
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.contracts import ContactChannel, ToolAction, ToolCall, ToolName, VocCategory
from app.llm.models import (
    KnowledgeConversationContext,
    LLMMessage,
    LLMRequest,
    LLMResponse,
)

_CA_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9-])[0-9]{12}(?![A-Za-z0-9-])")
# ผู้ใช้มักคัดลอกเลขเรื่องและคีย์ติดตามมาวางตรง ๆ โดยไม่ใส่ label
_BARE_VOC_ID_PATTERN = re.compile(r"\bSIM-CASE-\d{4,8}\b", re.IGNORECASE)
_BARE_TRACKING_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{6,64}")


class DemoLLMAdapter:
    """วางแผนการกระทำเดโมตามสัญญาอย่างปลอดภัยโดยไม่เข้าถึงเครือข่ายหรือ provider"""

    async def ready(self) -> bool:
        """อะแดปเตอร์แบบกำหนดผลลัพธ์ได้พร้อมใช้งานแบบออฟไลน์เสมอ"""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """ส่งคืนการวางแผนแบบกำหนดผลลัพธ์ได้หรือคำตอบที่อ้างอิงผลลัพธ์เครื่องมือ"""
        user_index = _latest_user_index(request.messages)
        if user_index is None:
            return _direct_response("greeting")
        current_messages = request.messages[user_index:]
        tool_messages = tuple(message for message in current_messages if message.role == "tool")
        if tool_messages:
            return self._after_tools(current_messages, tool_messages, request.correlation_id)
        return self._plan(
            _planning_message(request.messages, user_index, request.knowledge_context),
            request.correlation_id,
        )

    def _plan(self, message: str, correlation_id: UUID) -> LLMResponse:
        text = message.casefold()
        ca_number = _recognised_ca_number(message)
        location = _labelled_value(message, "location", 500)
        outage_location = _labelled_value(message, "location", 1000)
        location_note = _labelled_value(message, "locationNote", 500)
        description = _labelled_value(message, "description", 2000)
        subject = _labelled_value(message, "subject", 140)
        detail = _labelled_value(message, "detail", 2000)
        contact_name = _labelled_value(message, "contactName", 100)
        contact_phone = _labelled_value(message, "contactPhone", 32)
        voc_id = _labelled_value(message, "vocId", 64) or _bare_voc_id(message)
        tracking_key = _labelled_value(message, "trackingKey", 64) or _bare_tracking_key(message, voc_id)
        planned: list[tuple[int, ToolName, ToolAction, dict[str, Any]]] = []

        if _is_greeting(text):
            return _direct_response("greeting")
        if _is_thanks(text):
            return _direct_response("thanks")
        if _is_unsafe_or_unknown_request(text):
            return _direct_response("unsupported")

        wants_categories = _wants_categories(text)
        case_requested = _case_requested(text, wants_categories=wants_categories, has_details=bool(subject and detail))
        tracking_requested = _tracking_requested(text, wants_categories=wants_categories, has_details=bool(subject and detail))
        outage_requested = any(term in text for term in ("outage", "power failure", "ไฟดับ", "ไฟฟ้าขัดข้อง", "แจ้งเหตุ"))
        check_requested = any(term in text for term in ("check outage", "outage status", "ตรวจสอบ", "สถานะ"))
        knowledge_requested = any(term in text for term in ("knowledge", "policy", "tariff", "rate", "search", "guidance", "ค้นหา", "ข้อมูล")) or ("safety" in text and not case_requested)

        if outage_requested and not case_requested:
            if check_requested:
                if ca_number:
                    _append_plan(planned, message, ("outage", "ไฟดับ", "ตรวจสอบ", "สถานะ"), ToolName.OMS, ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": ca_number})
                else:
                    return _direct_response("oms_ca_number")
            elif ca_number and description:
                # OMS ต้องตรวจเหตุที่มีอยู่ก่อนเสมอ เพื่อป้องกันการสร้างเหตุซ้ำ
                _append_plan(planned, message, ("outage", "ไฟดับ", "แจ้งเหตุ"), ToolName.OMS, ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": ca_number})
            elif not ca_number and description and outage_location and contact_phone:
                action = ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE
                _append_plan(planned, message, ("outage", "ไฟดับ", "แจ้งเหตุ"), ToolName.OMS, action, {"description": description, "location": outage_location, "contactPhone": contact_phone, "idempotencyKey": _idempotency_key(correlation_id, action, f"{description}:{outage_location}:{contact_phone}")})
            elif ca_number:
                return _direct_response("oms_with_ca_inputs")
            else:
                # ยังไม่รู้ว่าผู้ใช้มี CA หรือไม่ ถาม CA ก่อนเสมอ
                return _direct_response("oms_outage_start")

        if knowledge_requested:
            _append_plan(planned, message, ("knowledge", "policy", "tariff", "rate", "guidance", "safety", "payment channels", "ค้นหา", "นโยบาย", "อัตราค่าไฟ"), ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3})

        if planned:
            return _planned_response(correlation_id, [item[1:] for item in sorted(planned, key=lambda item: item[0])])
        if _is_pea_knowledge_request(text):
            return _planned_response(correlation_id, [(ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3})])
        return _direct_response("unsupported")

    def _after_tools(self, messages: tuple[LLMMessage, ...], tool_messages: tuple[LLMMessage, ...], correlation_id: UUID) -> LLMResponse:
        """ใช้ผลตรวจเหตุจาก OMS เป็นเงื่อนไขก่อนเตรียมสร้างเหตุที่รู้ CA"""
        results = tuple(_tool_payload(message.content) for message in tool_messages)
        outage_check = next(
            (
                result["data"]
                for result in results
                if result.get("status") == "success"
                and isinstance(result.get("data"), dict)
                and "activeEvent" in result["data"]
            ),
            None,
        )
        if isinstance(outage_check, dict):
            if outage_check.get("activeEvent") is not None:
                return LLMResponse(text=_grounded_message(results))
            if outage_check.get("recommendedAction") == "CREATE_METER_EVENT":
                return _prepare_outage_with_ca(messages[0].content, correlation_id, outage_check)
        return LLMResponse(text=_grounded_message(results))


def _prepare_outage_with_ca(message: str, correlation_id: UUID, outage_check: dict[str, Any]) -> LLMResponse:
    """เตรียมสร้างเหตุเมื่อ OMS ยืนยันว่า CA ไม่มี active event เท่านั้น"""
    ca_number = outage_check.get("caNumber")
    description = _labelled_value(message, "description", 2000)
    if not isinstance(ca_number, str) or not _recognised_ca_number(ca_number) or not description:
        return _direct_response("oms_with_ca_inputs")
    contact_phone = _labelled_value(message, "contactPhone", 32)
    location_note = _labelled_value(message, "locationNote", 500)
    action = ToolAction.OMS_PREPARE_OUTAGE_WITH_CA
    return _planned_response(correlation_id, [(ToolName.OMS, action, {
        "caNumber": ca_number,
        "description": description,
        "contactPhone": contact_phone,
        "locationNote": location_note,
        "idempotencyKey": _idempotency_key(correlation_id, action, f"{ca_number}:{description}"),
    })])


def _latest_user_index(messages: tuple[LLMMessage, ...]) -> int | None:
    return next((index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"), None)


_CLARIFICATION_MARKERS = ("กรุณาระบุ", "กรุณาแจ้ง")


def _planning_message(
    messages: tuple[LLMMessage, ...],
    user_index: int,
    knowledge_context: KnowledgeConversationContext | None,
) -> str:
    """รวม clarification chain หรือบริบท Knowledge ที่ตรวจสอบแล้วกับคำถามปัจจุบัน"""
    current_message = messages[user_index].content
    user_messages = [current_message]
    cursor = user_index - 1
    while cursor >= 1:
        assistant = messages[cursor]
        # ข้อความขอให้ผู้ใช้เก็บข้อมูลเพิ่มอาจถูกเรียบเรียงใหม่ได้ จึงไม่ผูกกับวลีใดวลีเดียว
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

    if knowledge_context and _can_reuse_knowledge_context(current_message):
        current_context = " ".join(current_message.split())[:450]
        source_context = "; ".join(knowledge_context.sources)[:300]
        previous_context = " ".join(knowledge_context.previous_question.split())[:120]
        return (
            f"คำถามปัจจุบันที่ต้องตอบ: {current_context}\n"
            f"บริบทเอกสารจากรอบก่อน: {source_context}\n"
            f"คำถามก่อนหน้าเพื่อระบุหัวข้อเท่านั้น: {previous_context}"
        )
    return current_message



def _can_reuse_knowledge_context(message: str) -> bool:
    """รับเฉพาะคำถามต่อเนื่องหรือคำถาม PEA โดยไม่ใช้ deny-list แบบเปิดกว้าง"""
    text = " ".join(message.casefold().split())
    if (
        not text
        or _is_greeting(text)
        or _is_unsafe_or_unknown_request(text)
        or _has_explicit_operational_intent(message)
    ):
        return False
    if _is_pea_knowledge_request(text):
        return True
    if any(
        reference in text
        for reference in (
            "กรณีนี้",
            "อันนี้",
            "ดังกล่าว",
            "เรื่องนี้",
            "บริการนี้",
            "เอกสารนี้",
            "ผู้ขอ",
            "เจ้าของบ้าน",
            "ผู้ยื่น",
            "it",
            "this",
            "that",
            "the applicant",
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


def _wants_categories(text: str) -> bool:
    if any(term in text for term in (
        "complaint category",
        "complaint categories",
        "case types",
        "หมวดร้องเรียน",
        "ประเภทเรื่องร้องเรียน",
        "หัวข้อร้องเรียน",
    )):
        return True
    asks_for_topics = any(term in text for term in (
        "category",
        "categories",
        "หมวด",
        "ประเภทเรื่อง",
        "หัวข้ออะไรบ้าง",
        "หัวจ้ออะไรบ้าง",
    ))
    has_voc_context = any(term in text for term in (
        "voc",
        "complain",
        "complaint",
        "ร้องเรียน",
    ))
    return asks_for_topics and has_voc_context


def _case_requested(
    text: str, *, wants_categories: bool, has_details: bool
) -> bool:
    return not wants_categories and (
        bool(re.search(r"\bcomplain\b", text))
        or "service report" in text
        or "เรื่องร้องเรียน" in text
        or "ต้องการร้องเรียน" in text
        or "อยากร้องเรียน" in text
        or "ขอร้องเรียน" in text
        or "ร้องเรียนการ" in text
        or "ร้องเรียนเรื่อง" in text
        or "แจ้งปัญหาบริการ" in text
        or "แจ้งปัญหาการบริการ" in text
        or bool(re.search(r"(?:^|\n)ร้องเรียน(?:$|\n|;)", text))
        or bool(re.search(r"\bprepare\b[^;\n]{0,40}\b(?:complaint|case)\b", text))
        or (has_details and any(term in text for term in ("complaint", "case", "ร้องเรียน")))
    )


def _tracking_requested(text: str, *, wants_categories: bool, has_details: bool) -> bool:
    """แยกเจตนาติดตามเรื่องร้องเรียน (voc_tool.get_case) ออกจากเจตนาแจ้งเรื่องใหม่

    เครื่องหมายติดตาม (ติดตาม/track/vocId/trackingKey) มีความเฉพาะเจาะจงและ
    ถูกตรวจสอบก่อน case_requested จึงมีสิทธิ์ชนะแม้ข้อความจะมีคำว่า "ร้องเรียน"
    """
    if wants_categories:
        return False
    # การวางเลขเรื่องมาตรง ๆ เป็นเจตนาติดตามอยู่แล้ว แม้ไม่มีคำว่า "ติดตาม"
    if _BARE_VOC_ID_PATTERN.search(text):
        return True
    return any(term in text for term in (
        "track", "tracking", "ติดตาม", "ติดตามเรื่อง", "ตรวจสอบเรื่อง",
    )) or bool(re.search(r"\b(?:vocid|trackingkey)\b", text))


def _has_explicit_operational_intent(message: str) -> bool:
    """ใช้ predicate ชุดเดียวกับ planner เพื่อกัน intent ใหม่ออกจาก Knowledge context"""
    text = message.casefold()
    wants_categories = _wants_categories(text)
    has_case_details = bool(
        _labelled_value(message, "subject", 140)
        and _labelled_value(message, "detail", 2000)
    )
    return (
        _recognised_ca_number(message) is not None
        or any(term in text for term in ("outage", "power failure", "ไฟดับ", "ไฟฟ้าขัดข้อง", "แจ้งเหตุ", "ตรวจสอบ", "สถานะ"))
        or _case_requested(text, wants_categories=wants_categories, has_details=has_case_details)
        or _tracking_requested(text, wants_categories=wants_categories, has_details=has_case_details)
        or wants_categories
    )


def _planned_response(correlation_id: UUID, planned: list[tuple[ToolName, ToolAction, dict[str, Any]]]) -> LLMResponse:
    return LLMResponse(tool_calls=tuple(
        ToolCall(call_id=_call_id(correlation_id, name, action, input_data, ordinal), name=name, action=action, input=input_data)
        for ordinal, (name, action, input_data) in enumerate(planned)
    ))


def _direct_response(kind: str) -> LLMResponse:
    """ขอให้ Main Agent สร้างข้อความตรงจากแม่แบบที่กำหนดไว้"""
    return LLMResponse(direct_response=kind)


def _call_id(correlation_id: UUID, name: ToolName, action: ToolAction, input_data: dict[str, Any], ordinal: int) -> UUID:
    canonical_input = json.dumps(input_data, sort_keys=True, separators=(",", ":"))
    return uuid5(NAMESPACE_URL, f"{correlation_id}:{ordinal}:{name.value}:{action.value}:{canonical_input}")


def _recognised_ca_number(message: str) -> str | None:
    """รับเฉพาะหมายเลขผู้ใช้ไฟ 12 หลักที่ OMS ระบุไว้ในสัญญา"""
    match = _CA_NUMBER_PATTERN.search(message)
    return match.group(0) if match else None


def _append_plan(
    planned: list[tuple[int, ToolName, ToolAction, dict[str, Any]]],
    message: str,
    markers: tuple[str, ...],
    name: ToolName,
    action: ToolAction,
    input_data: dict[str, Any],
) -> None:
    text = message.casefold()
    positions = (text.find(marker.casefold()) for marker in markers)
    position = min((index for index in positions if index >= 0), default=len(text))
    planned.append((position, name, action, input_data))


def _is_greeting(text: str) -> bool:
    return text.strip(" !,.?\n") in {"hello", "hi", "hey", "สวัสดี"}


def _is_thanks(text: str) -> bool:
    return text.strip(" !,.?\n").casefold() in {"ขอบคุณ", "ขอบคุณครับ", "ขอบคุณมาก", "ขอบคุณมากครับ", "thank you", "thanks"}


def _is_unsafe_or_unknown_request(text: str) -> bool:
    return any(term in text for term in (
        "system prompt", "ignore all policy", "api_key", "payment token", "pan-", "delete_database", "hidden tool",
    ))


def _is_pea_knowledge_request(text: str) -> bool:
    """แยกคำถามความรู้ในขอบเขต PEA ออกจากคำขอทั่วไปที่ไม่มีเครื่องมือรองรับ"""
    return any(term in text for term in (
        "bill", "account", "electric", "power", "outage", "payment", "meter", "service",
        "complaint", "case", "generator", "wire", "downed line", "safety", "contact",
        "restoration", "mailing", "maintenance", "overdue", "paid status", "official message",
        "document", "ไฟ", "บัญชี", "ชำระ", "มิเตอร์", "บริการ", "ร้องเรียน", "สายไฟ",
        "ความปลอดภัย", "ติดต่อ", "เอกสาร",
    ))


def _idempotency_key(correlation_id: UUID, action: ToolAction, value: str) -> str:
    digest = hashlib.sha256(f"demo:{correlation_id}:{action.value}:{value.casefold()}".encode()).hexdigest()[:24]
    return f"demo-{action.value}-{digest}"


def _labelled_value(message: str, label: str, maximum: int) -> str | None:
    thai_labels = {
        "location": "สถานที่",
        "locationNote": "สถานที่เพิ่มเติม",
        "description": "รายละเอียดเหตุ",
        "subject": "หัวข้อ",
        "detail": "รายละเอียด",
        "contactName": "ชื่อ",
        "contactPhone": "เบอร์โทร",
        "vocId": "เลขเรื่อง",
        "trackingKey": "คีย์ติดตาม",
    }
    accepted_labels = (label, thai_labels.get(label, label))
    labels_pattern = "|".join(re.escape(item) for item in accepted_labels)
    match = re.search(rf"(?:^|[;\n])\s*(?:{labels_pattern})\s*:\s*(.+?)(?=\s*(?:;|\n|$))", message, re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return value if 0 < len(value) <= maximum else None


def _bare_voc_id(message: str) -> str | None:
    """รับเลขเรื่องที่ผู้ใช้วางมาโดยไม่มี label เพราะรูปแบบ ``SIM-CASE-000001`` ชัดเจนพอ"""
    match = _BARE_VOC_ID_PATTERN.search(message)
    return match.group(0).upper() if match else None


def _bare_tracking_key(message: str, voc_id: str | None) -> str | None:
    """รับคีย์ติดตามที่วางมาโดยไม่มี label เมื่อพบเลขเรื่องคู่กันในข้อความเดียว

    ยอมรับเฉพาะโทเคนที่หน้าตาเหมือนคีย์จาก ``secrets.token_urlsafe`` เท่านั้น
    เพื่อไม่ให้คำภาษาไทยหรือคำสั่งทั่วไปถูกตีความเป็นคีย์โดยไม่ตั้งใจ
    """
    if not voc_id:
        return None
    remainder = message.replace(voc_id, " ").replace(voc_id.lower(), " ")
    candidates = [
        token
        for token in re.split(r"[\s;]+", remainder)
        if _BARE_TRACKING_KEY_PATTERN.fullmatch(token)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _case_category(message: str) -> VocCategory:
    if any(term in message for term in (
        "stakeholder",
        "feedback",
        "ผู้มีส่วนได้ส่วนเสีย",
        "เสนอแนะ",
        "ข้อคิดเห็น",
    )):
        return VocCategory.STAKEHOLDER_FEEDBACK
    if any(term in message for term in ("compliment", "praise", "ชื่นชม")):
        return VocCategory.COMPLIMENT
    if any(term in message for term in ("safety", "danger", "hazard", "อันตราย", "เบาะแส")):
        return VocCategory.TIP_OFF
    if any(term in message for term in ("partner", "vendor", "operation", "คู่ค้า", "ดำเนินงาน")):
        return VocCategory.OPERATIONS
    if any(term in message for term in (
        "outage",
        "voltage",
        "คุณภาพไฟฟ้า",
        "ไฟดับ",
        "ไฟตก",
        "แรงดัน",
    )):
        return VocCategory.POWER_QUALITY
    return VocCategory.SERVICE


def _safe_query(message: str) -> str:
    return " ".join(message.split())[:1000] or "ข้อมูลเดโม PEA"


def _tool_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {"status": "error", "error": "ผลลัพธ์เครื่องมือไม่พร้อมใช้งาน"}
    return payload if isinstance(payload, dict) else {"status": "error", "error": "ผลลัพธ์เครื่องมือไม่ถูกต้อง"}


def _grounded_message(results: tuple[dict[str, Any], ...]) -> str:
    messages: list[str] = []
    for result in results:
        if result.get("status") != "success":
            messages.append(str(result.get("error", "บริการที่ร้องขอไม่พร้อมใช้งาน")))
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        if "vocId" in data and "status" in data:
            messages.append(f"เรื่องร้องเรียน {data['vocId']} มีสถานะ {data['status']} (หมวดหมู่ {data['category']})")
        elif "activeEvent" in data:
            messages.append(str(data.get("activeEvent", {}).get("message", "ไม่พบเหตุไฟฟ้าขัดข้องที่เกี่ยวข้อง")) if data.get("activeEvent") else "ไม่พบเหตุไฟฟ้าขัดข้องที่เกี่ยวข้อง")
        elif "summary" in data:
            messages.append(str(data["summary"]))
        elif "categories" in data:
            messages.append("หมวดหมู่ที่มี: " + ", ".join(str(item["label"]) for item in data["categories"]))
        elif "answerContext" in data:
            citation_count = len(result.get("citations", []))
            messages.append(f"{data['answerContext']} (อ้างอิง {citation_count} แหล่ง)")
    return " ".join(messages) or "การค้นหาที่ร้องขอไม่พบข้อมูลที่ใช้งานได้"
