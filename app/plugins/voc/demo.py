"""Deterministic offline planning owned by the enabled VOC plugin."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.contracts import ToolAction, ToolName
from app.llm.demo_behavior import DemoPlan, DemoToolCall
from app.llm.models import LLMMessage

_BARE_VOC_ID_PATTERN = re.compile(r"\bSIM-CASE-\d{4,8}\b", re.IGNORECASE)
_BARE_TRACKING_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{6,64}")


class VocDemoBehavior:
    """Support deterministic VOC reads without inventing intake or consent data."""

    tool_name = ToolName.VOC

    def has_demo_intent(self, message: str) -> bool:
        text = message.casefold()
        return _wants_categories(text) or _tracking_requested(text) or _case_requested(text)

    def plan_demo(self, message: str, correlation_id: UUID) -> DemoPlan | None:
        del correlation_id
        text = message.casefold()
        if _wants_categories(text):
            return DemoPlan(
                calls=(DemoToolCall(0, ToolName.VOC, ToolAction.VOC_LIST_CATEGORIES, {}),),
                exclusive=True,
            )
        if _tracking_requested(text):
            voc_id = _labelled_value(message, "vocId", 64) or _bare_voc_id(message)
            tracking_key = _labelled_value(message, "trackingKey", 64) or _bare_tracking_key(message, voc_id)
            if not voc_id or not tracking_key:
                return DemoPlan(direct_response="voc_tracking_inputs", exclusive=True)
            return DemoPlan(
                calls=(DemoToolCall(0, ToolName.VOC, ToolAction.VOC_GET_CASE, {
                    "vocId": voc_id,
                    "trackingKey": tracking_key,
                }),),
                exclusive=True,
            )
        if _case_requested(text):
            return DemoPlan(direct_response="voc_demo_prepare_unavailable", exclusive=True)
        return None

    def after_tools_demo(
        self,
        messages: tuple[LLMMessage, ...],
        results: tuple[dict[str, Any], ...],
        correlation_id: UUID,
    ) -> DemoPlan | None:
        del messages, results, correlation_id
        return None


def _wants_categories(text: str) -> bool:
    if any(term in text for term in ("complaint category", "complaint categories", "case types", "หมวดร้องเรียน", "ประเภทเรื่องร้องเรียน", "หัวข้อร้องเรียน")):
        return True
    asks = any(term in text for term in ("category", "categories", "หมวด", "ประเภทเรื่อง", "หัวข้ออะไรบ้าง", "หัวจ้ออะไรบ้าง"))
    context = any(term in text for term in ("voc", "complain", "complaint", "ร้องเรียน"))
    return asks and context


def _tracking_requested(text: str) -> bool:
    return bool(_BARE_VOC_ID_PATTERN.search(text)) or any(
        term in text for term in ("track", "tracking", "ติดตาม", "ติดตามเรื่อง", "ตรวจสอบเรื่อง")
    ) or bool(re.search(r"\b(?:vocid|trackingkey)\b", text))


def _case_requested(text: str) -> bool:
    return any(term in text for term in (
        "file a complaint", "submit a complaint", "service complaint", "service report",
        "เรื่องร้องเรียน", "ต้องการร้องเรียน", "อยากร้องเรียน", "ขอร้องเรียน",
        "ร้องเรียนการ", "ร้องเรียนเรื่อง", "แจ้งปัญหาบริการ", "แจ้งปัญหาการบริการ",
    ))


def _labelled_value(message: str, label: str, maximum: int) -> str | None:
    thai = {"vocId": "เลขเรื่อง", "trackingKey": "คีย์ติดตาม"}
    pattern = "|".join(re.escape(item) for item in (label, thai.get(label, label)))
    match = re.search(
        rf"(?:^|[;\n])\s*(?:{pattern})\s*:\s*(.+?)(?=\s*(?:;|\n|$))",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return value if 0 < len(value) <= maximum else None


def _bare_voc_id(message: str) -> str | None:
    match = _BARE_VOC_ID_PATTERN.search(message)
    return match.group(0).upper() if match else None


def _bare_tracking_key(message: str, voc_id: str | None) -> str | None:
    if not voc_id:
        return None
    remainder = message.replace(voc_id, " ").replace(voc_id.lower(), " ")
    candidates = [token for token in re.split(r"[\s;]+", remainder) if _BARE_TRACKING_KEY_PATTERN.fullmatch(token)]
    return candidates[0] if len(candidates) == 1 else None
