"""Deterministic offline planning owned by the enabled OMS plugin."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from app.contracts import ToolAction, ToolName
from app.llm.demo_behavior import DemoPlan, DemoToolCall
from app.llm.models import LLMMessage

_CA_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9-])[0-9]{12}(?![A-Za-z0-9-])")


class OmsDemoBehavior:
    def has_demo_intent(self, message: str) -> bool:
        text = message.casefold()
        return _recognised_ca_number(message) is not None or any(
            term in text
            for term in ("outage", "power failure", "ไฟดับ", "ไฟฟ้าขัดข้อง", "แจ้งเหตุ", "ตรวจสอบ", "สถานะ")
        )

    def plan_demo(self, message: str, correlation_id: UUID) -> DemoPlan | None:
        text = message.casefold()
        outage_requested = any(term in text for term in ("outage", "power failure", "ไฟดับ", "ไฟฟ้าขัดข้อง", "แจ้งเหตุ"))
        if not outage_requested:
            return None

        ca_number = _recognised_ca_number(message)
        description = _labelled_value(message, "description", 2000)
        location = _labelled_value(message, "location", 1000)
        contact_phone = _labelled_value(message, "contactPhone", 32)
        check_requested = any(term in text for term in ("check outage", "outage status", "ตรวจสอบ", "สถานะ"))
        if check_requested:
            if not ca_number:
                return DemoPlan(direct_response="oms_ca_number")
            return DemoPlan(calls=(_call(message, ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": ca_number}),))
        if ca_number and description:
            return DemoPlan(calls=(_call(message, ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": ca_number}),))
        if not ca_number and description and location and contact_phone:
            action = ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE
            return DemoPlan(calls=(_call(message, action, {
                "description": description,
                "location": location,
                "contactPhone": contact_phone,
                "idempotencyKey": _idempotency_key(correlation_id, action, f"{description}:{location}:{contact_phone}"),
            }),))
        if ca_number:
            return DemoPlan(direct_response="oms_with_ca_inputs")
        return DemoPlan(direct_response="oms_outage_start")

    def after_tools_demo(
        self,
        messages: tuple[LLMMessage, ...],
        results: tuple[dict[str, Any], ...],
        correlation_id: UUID,
    ) -> DemoPlan | None:
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
        if not isinstance(outage_check, dict) or outage_check.get("activeEvent") is not None:
            return None
        if outage_check.get("recommendedAction") != "CREATE_METER_EVENT":
            return None
        ca_number = outage_check.get("caNumber")
        description = _labelled_value(messages[0].content, "description", 2000)
        if not isinstance(ca_number, str) or not _recognised_ca_number(ca_number) or not description:
            return DemoPlan(direct_response="oms_with_ca_inputs")
        contact_phone = _labelled_value(messages[0].content, "contactPhone", 32)
        location_note = _labelled_value(messages[0].content, "locationNote", 500)
        action = ToolAction.OMS_PREPARE_OUTAGE_WITH_CA
        return DemoPlan(calls=(_call(messages[0].content, action, {
            "caNumber": ca_number,
            "description": description,
            "contactPhone": contact_phone,
            "locationNote": location_note,
            "idempotencyKey": _idempotency_key(correlation_id, action, f"{ca_number}:{description}"),
        }),))


def _call(message: str, action: ToolAction, input_data: dict[str, Any]) -> DemoToolCall:
    markers = {
        ToolAction.OMS_GET_OUTAGE_BY_CA: ("outage", "ไฟดับ", "ตรวจสอบ", "สถานะ"),
        ToolAction.OMS_PREPARE_OUTAGE_WITH_CA: ("outage", "ไฟดับ", "แจ้งเหตุ"),
        ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE: ("outage", "ไฟดับ", "แจ้งเหตุ"),
    }[action]
    text = message.casefold()
    positions = (text.find(marker.casefold()) for marker in markers)
    position = min((index for index in positions if index >= 0), default=len(text))
    return DemoToolCall(position, ToolName.OMS, action, input_data)


def _recognised_ca_number(message: str) -> str | None:
    match = _CA_NUMBER_PATTERN.search(message)
    return match.group(0) if match else None


def _labelled_value(message: str, label: str, maximum: int) -> str | None:
    thai_labels = {
        "location": "สถานที่",
        "locationNote": "สถานที่เพิ่มเติม",
        "description": "รายละเอียดเหตุ",
        "contactPhone": "เบอร์โทร",
    }
    accepted = (label, thai_labels.get(label, label))
    pattern = "|".join(re.escape(item) for item in accepted)
    match = re.search(
        rf"(?:^|[;\n])\s*(?:{pattern})\s*:\s*(.+?)(?=\s*(?:;|\n|$))",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return value if 0 < len(value) <= maximum else None


def _idempotency_key(correlation_id: UUID, action: ToolAction, value: str) -> str:
    digest = hashlib.sha256(
        f"demo:{correlation_id}:{action.value}:{value.casefold()}".encode()
    ).hexdigest()[:24]
    return f"demo-{action.value}-{digest}"
