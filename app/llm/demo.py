"""ตัววางแผนแบบกำหนดผลลัพธ์ได้และทำงานออฟไลน์สำหรับเดโม PEA ที่มีการจัดการ

อะแดปเตอร์อ่านเฉพาะข้อความ ``user`` และ ``tool`` ที่มองเห็นได้ ไม่เคยรับ เก็บรักษา
หรืออนุมานกระบวนการคิดที่ซ่อนอยู่ การเรียกใช้งานปฏิบัติการต้องใช้ตัวระบุเดโมที่รู้จัก
และข้อมูลสำหรับเขียนที่ครบถ้วนและระบุอย่างชัดเจน
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.contracts import ContactChannel, PaymentMethod, ToolAction, ToolCall, ToolName, VocCategory
from app.llm.models import (
    DirectResponseKind,
    KnowledgeConversationContext,
    LLMMessage,
    LLMRequest,
    LLMResponse,
)

_ACCOUNT_REF_PATTERN = re.compile(r"\bPEA-\d{4}\b", re.IGNORECASE)
_AREA_CODE_PATTERN = re.compile(r"\b[A-Z]{3}-\d{2}\b", re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(r"(?:฿|thb\s*)(\d+(?:\.\d{1,2})?)\b|\b(\d+(?:\.\d{1,2})?)\s*(?:baht|thb|บาท)\b", re.IGNORECASE)
_DEMO_ACCOUNT_REFS = frozenset({"PEA-1001", "PEA-1002", "PEA-1003"})
_DEMO_AREA_CODES = frozenset({"BKK-01", "CNX-02", "HKT-03"})


class DemoLLMAdapter:
    """วางแผนการกระทำเดโมตามสัญญาอย่างปลอดภัยโดยไม่เข้าถึงเครือข่ายหรือ provider"""

    async def ready(self) -> bool:
        """อะแดปเตอร์แบบกำหนดผลลัพธ์ได้พร้อมใช้งานแบบออฟไลน์เสมอ"""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """ส่งคืนการวางแผนแบบกำหนดผลลัพธ์ได้หรือคำตอบที่อ้างอิงผลลัพธ์เครื่องมือ"""
        user_index = _latest_user_index(request.messages)
        if user_index is None:
            return _direct_response(DirectResponseKind.GREETING)
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
        account_ref = _recognised_account_ref(message)
        area_code = _recognised_area_code(message)
        location = _labelled_value(message, "location", 500)
        symptoms = _labelled_value(message, "symptoms", 1000)
        subject = _labelled_value(message, "subject", 140)
        detail = _labelled_value(message, "detail", 2000)
        amount = _requested_amount(message)
        payment_method = _payment_method(message)
        planned: list[tuple[int, ToolName, ToolAction, dict[str, Any]]] = []

        if _is_greeting(text):
            return _direct_response(DirectResponseKind.GREETING)
        if _is_unsafe_or_unknown_request(text):
            return _direct_response(DirectResponseKind.UNSUPPORTED)

        wants_categories = _wants_categories(text)
        payment_requested = _payment_requested(text, payment_method)
        report_requested = _outage_report_requested(
            text, has_details=bool(location or symptoms)
        )
        case_requested = _case_requested(
            text,
            wants_categories=wants_categories,
            has_details=bool(subject and detail),
        )
        status_marked = any(term in text for term in (
            "status", "check outage", "planned outage", "power normal", "outage near",
            "สถานะ", "ตรวจสอบ", "ไฟฟ้าดับ", "ไฟดับ", "ปกติ",
        )) or "outage" in text
        status_requested = bool(area_code) and status_marked and (
            not report_requested or any(term in text for term in ("status", "สถานะ", "ตรวจสอบ"))
        )
        status_needs_area = not area_code and any(term in text for term in (
            "outage status", "check outage", "power status", "สถานะไฟ", "ตรวจสอบไฟ",
        ))
        account_marked = (
            any(term in text for term in ("balance", "due", "overdue", "summary", "ยอด"))
            or bool(re.search(r"\b(?:show|check)\s+account\b", text))
            or bool(not payment_requested and account_ref and f"account {account_ref.casefold()}" in text)
        )
        account_requested = bool(account_ref) and account_marked
        account_needs_ref = not account_ref and (
            any(term in text for term in ("account balance", "account summary", "ยอดคงเหลือ", "ยอดบัญชี"))
            or bool(re.search(r"\b(?:show|check)\s+account\b", text))
        )
        knowledge_requested = any(term in text for term in (
            "knowledge", "policy", "tariff", "rate", "search", "guidance", "payment channels", "ค้นหา", "ข้อมูล",
        )) or ("safety" in text and not case_requested)

        if payment_requested:
            if account_ref and amount and payment_method:
                action = ToolAction.SABUY_PREPARE_PAYMENT
                _append_plan(planned, message, ("prepare payment", "prepare a", "paymentmethod", "pay account", "demo payment"), ToolName.SABUY, action, {
                    "accountRef": account_ref,
                    "amountThb": amount,
                    "paymentMethod": payment_method.value,
                    "idempotencyKey": _idempotency_key(correlation_id, action, f"{account_ref}:{amount}:{payment_method.value}"),
                })
            else:
                return _direct_response(DirectResponseKind.PAYMENT_INPUTS)

        if account_requested:
            _append_plan(planned, message, ("account", "balance", "due", "overdue", "summary", "ยอด"), ToolName.SABUY, ToolAction.SABUY_ACCOUNT_SUMMARY, {"accountRef": account_ref})
        elif account_needs_ref:
            return _direct_response(DirectResponseKind.ACCOUNT_REF)

        if report_requested:
            if area_code and location and symptoms:
                action = ToolAction.OMS_PREPARE_OUTAGE_REPORT
                _append_plan(planned, message, ("report", "fallen wire", "downed line", "sparks", "แจ้งไฟ", "แจ้งเหตุ"), ToolName.OMS, action, {
                    "areaCode": area_code,
                    "locationNote": location,
                    "symptoms": symptoms,
                    "idempotencyKey": _idempotency_key(correlation_id, action, f"{area_code}:{location}:{symptoms}"),
                })
            elif not planned:
                return _direct_response(DirectResponseKind.OUTAGE_REPORT_INPUTS)

        if status_requested:
            _append_plan(planned, message, ("status", "check outage", "planned outage", "power normal", "outage", "สถานะ", "ตรวจสอบ"), ToolName.OMS, ToolAction.OMS_OUTAGE_STATUS, {"areaCode": area_code})
        elif status_needs_area and not planned:
            return _direct_response(DirectResponseKind.OUTAGE_STATUS_AREA)

        # คำขอหมวดหมู่ที่ระบุชัดเจนเป็นการอ่านเสมอ ไม่ใช่การเขียนเรื่องร้องเรียนที่ข้อมูลไม่ครบ
        if wants_categories:
            _append_plan(planned, message, ("category", "categories", "case types", "หมวด"), ToolName.VOC, ToolAction.VOC_LIST_CATEGORIES, {})
        elif case_requested:
            if subject and detail:
                category = _case_category(text)
                action = ToolAction.VOC_PREPARE_CASE
                _append_plan(planned, message, ("complaint", "complain", "case", "service report", "ร้องเรียน"), ToolName.VOC, action, {
                    "category": category.value,
                    "subject": subject,
                    "detail": detail,
                    "contactChannel": ContactChannel.NONE.value,
                    "idempotencyKey": _idempotency_key(correlation_id, action, f"{category.value}:{subject}:{detail}"),
                })
            elif not planned:
                return _direct_response(DirectResponseKind.VOC_DETAILS)

        if knowledge_requested:
            _append_plan(planned, message, ("knowledge", "policy", "tariff", "rate", "guidance", "safety", "payment channels", "ค้นหา", "นโยบาย", "อัตราค่าไฟ"), ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3})

        if planned:
            return _planned_response(correlation_id, [item[1:] for item in sorted(planned, key=lambda item: item[0])])
        if _is_pea_knowledge_request(text):
            return _planned_response(correlation_id, [(ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3})])
        return _direct_response(DirectResponseKind.UNSUPPORTED)

    def _after_tools(self, messages: tuple[LLMMessage, ...], tool_messages: tuple[LLMMessage, ...], correlation_id: UUID) -> LLMResponse:
        results = tuple(_tool_payload(message.content) for message in tool_messages)
        user_text = messages[0].content.casefold()
        account = next((result.get("data") for result in results if isinstance(result.get("data"), dict) and "outstandingBalanceThb" in result["data"]), None)
        payment_prepared = any(isinstance(result.get("data"), dict) and "paymentMethod" in result["data"] for result in results)
        amount = _requested_amount(user_text)
        payment_method = _payment_method(messages[0].content)
        requested_account = _recognised_account_ref(messages[0].content)
        if account and not payment_prepared and amount and payment_method and requested_account == account.get("accountRef"):
            action = ToolAction.SABUY_PREPARE_PAYMENT
            return _planned_response(correlation_id, [(ToolName.SABUY, action, {
                "accountRef": account["accountRef"],
                "amountThb": amount,
                "paymentMethod": payment_method.value,
                "idempotencyKey": _idempotency_key(correlation_id, action, f"{account['accountRef']}:{amount}:{payment_method.value}"),
            })])
        return LLMResponse(text=_grounded_message(results))


def _latest_user_index(messages: tuple[LLMMessage, ...]) -> int | None:
    return next((index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"), None)


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
        if assistant.role != "assistant" or "กรุณาระบุ" not in assistant.content:
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
    return any(term in text for term in ("category", "categories", "case types", "หมวด"))


def _payment_requested(text: str, payment_method: PaymentMethod | None) -> bool:
    return payment_method is not None or bool(
        re.search(
            r"\bprepare\b[^;\n]{0,30}\bpayment\b"
            r"|\bpay\b[^;\n]{0,40}\baccount\b"
            r"|\b(?:want to (?:make )?|make (?:a )?)payment\b"
            r"|(?:ต้องการ|ขอ)?(?:ชำระ|จ่าย)(?:ค่าไฟ|เงิน)?",
            text,
        )
    )


def _outage_report_requested(text: str, *, has_details: bool) -> bool:
    detail_markers = (
        "report",
        "file an outage",
        "fallen wire",
        "downed line",
        "sparks",
        "แจ้งไฟ",
        "แจ้งเหตุ",
        "รายงาน",
        "ไฟฟ้าดับ",
        "ไฟดับ",
    )
    direct_markers = (
        "file an outage",
        "report an outage",
        "ต้องการแจ้งไฟ",
        "ขอแจ้งไฟ",
        "ต้องการแจ้งเหตุ",
        "ขอแจ้งปัญหาไฟฟ้า",
        "แจ้งปัญหาไฟฟ้า",
        "ไฟฟ้ามีปัญหา",
    )
    return (has_details and any(term in text for term in detail_markers)) or any(
        term in text for term in direct_markers
    )


def _case_requested(
    text: str, *, wants_categories: bool, has_details: bool
) -> bool:
    return not wants_categories and (
        bool(re.search(r"\bcomplain\b", text))
        or "service report" in text
        or "เรื่องร้องเรียน" in text
        or "ต้องการร้องเรียน" in text
        or "ขอร้องเรียน" in text
        or "แจ้งปัญหาบริการ" in text
        or "แจ้งปัญหาการบริการ" in text
        or bool(re.search(r"(?:^|\n)ร้องเรียน(?:$|\n|;)", text))
        or bool(re.search(r"\bprepare\b[^;\n]{0,40}\b(?:complaint|case)\b", text))
        or (has_details and any(term in text for term in ("complaint", "case", "ร้องเรียน")))
    )


def _has_explicit_operational_intent(message: str) -> bool:
    """ใช้ predicate ชุดเดียวกับ planner เพื่อกัน intent ใหม่ออกจาก Knowledge context"""
    text = message.casefold()
    wants_categories = _wants_categories(text)
    has_case_details = bool(
        _labelled_value(message, "subject", 140)
        and _labelled_value(message, "detail", 2000)
    )
    return (
        _recognised_account_ref(message) is not None
        or _recognised_area_code(message) is not None
        or _payment_requested(text, _payment_method(message))
        or _outage_report_requested(
            text,
            has_details=bool(
                _labelled_value(message, "location", 500)
                or _labelled_value(message, "symptoms", 1000)
            ),
        )
        or _case_requested(
            text,
            wants_categories=wants_categories,
            has_details=has_case_details,
        )
        or wants_categories
        or any(
            term in text
            for term in (
                "outage status",
                "check outage",
                "power status",
                "สถานะไฟ",
                "ตรวจสอบไฟ",
                "account balance",
                "account summary",
                "ยอดคงเหลือ",
                "ยอดบัญชี",
            )
        )
    )


def _planned_response(correlation_id: UUID, planned: list[tuple[ToolName, ToolAction, dict[str, Any]]]) -> LLMResponse:
    return LLMResponse(tool_calls=tuple(
        ToolCall(call_id=_call_id(correlation_id, name, action, input_data, ordinal), name=name, action=action, input=input_data)
        for ordinal, (name, action, input_data) in enumerate(planned)
    ))


def _direct_response(kind: DirectResponseKind) -> LLMResponse:
    """ขอให้ Main Agent สร้างข้อความตรงจากแม่แบบที่กำหนดไว้"""
    return LLMResponse(direct_response=kind)


def _call_id(correlation_id: UUID, name: ToolName, action: ToolAction, input_data: dict[str, Any], ordinal: int) -> UUID:
    canonical_input = json.dumps(input_data, sort_keys=True, separators=(",", ":"))
    return uuid5(NAMESPACE_URL, f"{correlation_id}:{ordinal}:{name.value}:{action.value}:{canonical_input}")


def _recognised_account_ref(message: str) -> str | None:
    match = _ACCOUNT_REF_PATTERN.search(message)
    value = match.group(0).upper() if match else ""
    return value if value in _DEMO_ACCOUNT_REFS else None


def _recognised_area_code(message: str) -> str | None:
    match = _AREA_CODE_PATTERN.search(message)
    value = match.group(0).upper() if match else ""
    return value if value in _DEMO_AREA_CODES else None


def _payment_method(message: str) -> PaymentMethod | None:
    match = re.search(r"\bpaymentmethod\s*:\s*(demo_card|demo_bank)\b", message, re.IGNORECASE)
    if match:
        return PaymentMethod(match.group(1).casefold())
    if re.search(r"\b(?:credit|debit)?\s*card\b|บัตร", message, re.IGNORECASE):
        return PaymentMethod.DEMO_CARD
    if re.search(r"\b(?:bank(?:\s+transfer)?|wire\s+transfer)\b|ธนาคาร|โอน(?:เงิน)?", message, re.IGNORECASE):
        return PaymentMethod.DEMO_BANK
    return None


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
        "symptoms": "อาการ",
        "subject": "หัวข้อ",
        "detail": "รายละเอียด",
    }
    accepted_labels = (label, thai_labels.get(label, label))
    labels_pattern = "|".join(re.escape(item) for item in accepted_labels)
    match = re.search(rf"(?:^|[;\n])\s*(?:{labels_pattern})\s*:\s*(.+?)(?=\s*(?:;|\n|$))", message, re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return value if 0 < len(value) <= maximum else None


def _requested_amount(message: str) -> str | None:
    match = _AMOUNT_PATTERN.search(message)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1) or match.group(2))
    except (InvalidOperation, TypeError):
        return None
    return format(amount.quantize(Decimal("0.01")), "f") if amount > 0 else None


def _case_category(message: str) -> VocCategory:
    if any(term in message for term in ("compliment", "praise", "ชื่นชม")):
        return VocCategory.COMPLIMENT
    if any(term in message for term in ("safety", "danger", "hazard", "อันตราย", "เบาะแส")):
        return VocCategory.TIP_OFF
    if any(term in message for term in ("partner", "vendor", "operation", "คู่ค้า", "ดำเนินงาน")):
        return VocCategory.OPERATIONS
    if any(term in message for term in ("stakeholder", "feedback", "ผู้มีส่วนได้ส่วนเสีย", "ข้อคิดเห็น")):
        return VocCategory.STAKEHOLDER_FEEDBACK
    if any(term in message for term in ("outage", "voltage", "ไฟดับ", "ไฟตก", "แรงดัน")):
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
        if "outstandingBalanceThb" in data:
            messages.append(f"บัญชี {data['accountRef']} มียอดคงค้าง THB {data['outstandingBalanceThb']} (สถานะ {data['paymentStatus']})")
        elif "safetyMessage" in data and "status" in data:
            messages.append(f"พื้นที่ {data['areaCode']} มีสถานะ {data['status']} {data['safetyMessage']}")
        elif "summary" in data:
            messages.append(str(data["summary"]))
        elif "categories" in data:
            messages.append("หมวดหมู่ที่มี: " + ", ".join(str(item["label"]) for item in data["categories"]))
        elif "answerContext" in data:
            citation_count = len(result.get("citations", []))
            messages.append(f"{data['answerContext']} (อ้างอิง {citation_count} แหล่ง)")
    return " ".join(messages) or "การค้นหาที่ร้องขอไม่พบข้อมูลที่ใช้งานได้"
