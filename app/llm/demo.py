"""Deterministic, offline planner for the managed PEA demo.

The adapter reads only visible ``user`` and ``tool`` messages. It never receives,
retains, or infers hidden reasoning. Demo identifiers are restricted to known
fixture values; absent or unrecognised identifiers use ``PEA-1001`` and
``BKK-01``.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.contracts import ContactChannel, PaymentMethod, ToolAction, ToolCall, ToolName, VocCategory
from app.llm.models import LLMMessage, LLMRequest, LLMResponse

_DEFAULT_ACCOUNT_REF = "PEA-1001"
_DEFAULT_AREA_CODE = "BKK-01"
_ACCOUNT_REF_PATTERN = re.compile(r"\bPEA-\d{4}\b", re.IGNORECASE)
_AREA_CODE_PATTERN = re.compile(r"\b[A-Z]{3}-\d{2}\b", re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(r"(?:฿|thb\s*)(\d+(?:\.\d{1,2})?)\b|\b(\d+(?:\.\d{1,2})?)\s*(?:baht|thb)\b", re.IGNORECASE)
_DEMO_ACCOUNT_REFS = frozenset({"PEA-1001", "PEA-1002", "PEA-1003"})
_DEMO_AREA_CODES = frozenset({"BKK-01", "CNX-02", "HKT-03"})


class DemoLLMAdapter:
    """Plan safe frozen demo actions without network or provider access."""

    async def ready(self) -> bool:
        """The deterministic adapter is always available offline."""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic planning or tool-grounded response."""
        visible = tuple(message for message in request.messages if message.role in {"user", "tool"})
        user_index = _latest_user_index(visible)
        if user_index is None:
            return LLMResponse(text="How can I help with the PEA demo?")
        current_messages = visible[user_index:]
        tool_messages = tuple(message for message in current_messages if message.role == "tool")
        if tool_messages:
            return self._after_tools(current_messages, tool_messages, request.correlation_id)
        return self._plan(current_messages[0].content, request.correlation_id)

    def _plan(self, message: str, correlation_id: UUID) -> LLMResponse:
        text = message.casefold()
        account_ref = _account_ref(message)
        area_code = _area_code(message)
        planned: list[tuple[ToolName, ToolAction, dict[str, Any]]] = []
        wants_payment = any(term in text for term in ("pay", "payment", "ชำระ", "จ่ายบิล"))
        wants_account = wants_payment or any(term in text for term in ("account", "balance", "bill", "ยอด", "ค่าไฟ"))
        wants_report = any(term in text for term in ("report outage", "report a power", "แจ้งไฟ", "แจ้งเหตุ"))
        wants_outage = wants_report or any(term in text for term in ("outage", "power status", "ไฟดับ", "ไฟฟ้า"))
        wants_case = any(term in text for term in ("complaint", "complain", "case", "ร้องเรียน"))
        wants_categories = any(term in text for term in ("category", "categories", "หมวด"))
        wants_knowledge = any(term in text for term in ("knowledge", "policy", "tariff", "rate", "search", "ข้อมูล"))

        # Independent account and outage reads exercise a genuine multi-tool flow.
        if wants_account:
            planned.append((ToolName.SABUY, ToolAction.SABUY_ACCOUNT_SUMMARY, {"accountRef": account_ref}))
        if wants_outage and not wants_report:
            planned.append((ToolName.OMS, ToolAction.OMS_OUTAGE_STATUS, {"areaCode": area_code}))
        if wants_report:
            location = _labelled_value(message, "location", 500)
            symptoms = _labelled_value(message, "symptoms", 1000)
            if location and symptoms:
                action = ToolAction.OMS_PREPARE_OUTAGE_REPORT
                planned.append((ToolName.OMS, action, {
                    "areaCode": area_code,
                    "locationNote": location,
                    "symptoms": symptoms,
                    "idempotencyKey": _idempotency_key(correlation_id, action, f"{area_code}:{location}:{symptoms}"),
                }))
            elif not planned:
                return LLMResponse(text="To prepare an outage report, provide `location:` and `symptoms:` details.")
        if wants_case:
            subject = _labelled_value(message, "subject", 140)
            detail = _labelled_value(message, "detail", 2000)
            if subject and detail:
                category = _case_category(text)
                action = ToolAction.VOC_PREPARE_CASE
                planned.append((ToolName.VOC, action, {
                    "category": category.value,
                    "subject": subject,
                    "detail": detail,
                    "contactChannel": ContactChannel.NONE.value,
                    "idempotencyKey": _idempotency_key(correlation_id, action, f"{category.value}:{subject}:{detail}"),
                }))
            elif not planned:
                return LLMResponse(text="To prepare a case, provide `subject:` and `detail:`.")
        elif wants_categories:
            planned.append((ToolName.VOC, ToolAction.VOC_LIST_CATEGORIES, {}))
        if wants_knowledge and not planned:
            planned.append((ToolName.KNOWLEDGE, ToolAction.KNOWLEDGE_SEARCH, {"query": _safe_query(message), "maxResults": 3}))
        if planned:
            return _planned_response(correlation_id, planned)
        return LLMResponse(text="Hello. I can check a demo account or outage, search PEA knowledge, or prepare an action for your explicit confirmation.")

    def _after_tools(self, messages: tuple[LLMMessage, ...], tool_messages: tuple[LLMMessage, ...], correlation_id: UUID) -> LLMResponse:
        results = tuple(_tool_payload(message.content) for message in tool_messages)
        user_text = messages[0].content.casefold()
        account = next((result.get("data") for result in results if isinstance(result.get("data"), dict) and "outstandingBalanceThb" in result["data"]), None)
        payment_prepared = any(isinstance(result.get("data"), dict) and "paymentMethod" in result["data"] for result in results)
        if account and not payment_prepared and any(term in user_text for term in ("pay", "payment", "ชำระ", "จ่ายบิล")):
            amount = _requested_amount(user_text) or account["outstandingBalanceThb"]
            action = ToolAction.SABUY_PREPARE_PAYMENT
            return _planned_response(correlation_id, [(ToolName.SABUY, action, {
                "accountRef": account["accountRef"],
                "amountThb": amount,
                "paymentMethod": PaymentMethod.DEMO_CARD.value,
                "idempotencyKey": _idempotency_key(correlation_id, action, f"{account['accountRef']}:{amount}"),
            })])
        return LLMResponse(text=_grounded_message(results))


def _latest_user_index(messages: tuple[LLMMessage, ...]) -> int | None:
    return next((index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"), None)


def _planned_response(correlation_id: UUID, planned: list[tuple[ToolName, ToolAction, dict[str, Any]]]) -> LLMResponse:
    return LLMResponse(tool_calls=tuple(
        ToolCall(call_id=_call_id(correlation_id, name, action, input_data, ordinal), name=name, action=action, input=input_data)
        for ordinal, (name, action, input_data) in enumerate(planned)
    ))


def _call_id(correlation_id: UUID, name: ToolName, action: ToolAction, input_data: dict[str, Any], ordinal: int) -> UUID:
    canonical_input = json.dumps(input_data, sort_keys=True, separators=(",", ":"))
    return uuid5(NAMESPACE_URL, f"{correlation_id}:{ordinal}:{name.value}:{action.value}:{canonical_input}")


def _account_ref(message: str) -> str:
    match = _ACCOUNT_REF_PATTERN.search(message)
    value = match.group(0).upper() if match else ""
    return value if value in _DEMO_ACCOUNT_REFS else _DEFAULT_ACCOUNT_REF


def _area_code(message: str) -> str:
    match = _AREA_CODE_PATTERN.search(message)
    value = match.group(0).upper() if match else ""
    return value if value in _DEMO_AREA_CODES else _DEFAULT_AREA_CODE


def _idempotency_key(correlation_id: UUID, action: ToolAction, value: str) -> str:
    digest = hashlib.sha256(f"demo:{correlation_id}:{action.value}:{value.casefold()}".encode()).hexdigest()[:24]
    return f"demo-{action.value}-{digest}"


def _labelled_value(message: str, label: str, maximum: int) -> str | None:
    match = re.search(rf"(?:^|[;\n])\s*{re.escape(label)}\s*:\s*(.+?)(?=\s*(?:;|\n|$))", message, re.IGNORECASE)
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
    if any(term in message for term in ("safety", "danger", "hazard", "อันตราย")):
        return VocCategory.SAFETY
    if any(term in message for term in ("bill", "billing", "payment", "ค่าไฟ")):
        return VocCategory.BILLING
    if any(term in message for term in ("service", "meter", "บริการ")):
        return VocCategory.SERVICE
    return VocCategory.OTHER


def _safe_query(message: str) -> str:
    return " ".join(message.split())[:1000] or "PEA demo information"


def _tool_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {"status": "error", "error": "Tool result was unavailable."}
    return payload if isinstance(payload, dict) else {"status": "error", "error": "Tool result was invalid."}


def _grounded_message(results: tuple[dict[str, Any], ...]) -> str:
    messages: list[str] = []
    for result in results:
        if result.get("status") != "success":
            messages.append(str(result.get("error", "A requested service was unavailable.")))
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        if "outstandingBalanceThb" in data:
            messages.append(f"Account {data['accountRef']} has a balance of THB {data['outstandingBalanceThb']} ({data['paymentStatus']}).")
        elif "safetyMessage" in data and "status" in data:
            messages.append(f"Area {data['areaCode']} is {data['status']}. {data['safetyMessage']}")
        elif "summary" in data:
            messages.append(str(data["summary"]))
        elif "categories" in data:
            messages.append("Available categories: " + ", ".join(str(item["label"]) for item in data["categories"]))
        elif "answerContext" in data:
            citation_count = len(result.get("citations", []))
            messages.append(f"{data['answerContext']} ({citation_count} cited source{'s' if citation_count != 1 else ''})")
    return " ".join(messages) or "The requested lookup returned no usable data."
