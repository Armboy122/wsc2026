"""ค่าที่ไม่ขึ้นกับ provider ซึ่งใช้ที่ขอบเขต LLM ของ Main Agent"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from app.contracts import ToolCall, ToolName


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """ข้อความแชตขนาดเล็กโดยเจตนา ซึ่งไม่เก็บกระบวนการคิดที่ซ่อนอยู่"""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """รายการในแค็ตตาล็อกเครื่องมือที่ LLM provider มองเห็น"""

    name: ToolName
    description: str
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    tools: tuple[ToolDefinition, ...]
    correlation_id: UUID


class DirectResponseKind(str, Enum):
    """ชนิดข้อความตรงที่ Main Agent สร้างจากแม่แบบที่เชื่อถือได้"""

    GREETING = "greeting"
    UNSUPPORTED = "unsupported"
    PAYMENT_INPUTS = "payment_inputs"
    ACCOUNT_REF = "account_ref"
    OUTAGE_REPORT_INPUTS = "outage_report_inputs"
    OUTAGE_STATUS_AREA = "outage_status_area"
    VOC_DETAILS = "voc_details"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """คำตอบจาก provider ที่แปลงเป็นการเรียกเครื่องมือภายในและผ่านการตรวจสอบแล้ว"""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    direct_response: DirectResponseKind | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
