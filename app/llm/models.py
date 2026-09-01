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
class KnowledgeConversationContext:
    """หัวข้อ Knowledge turn ล่าสุดที่มีหลักฐานและใช้ได้กับคำถามถัดไปหนึ่งรอบ"""

    previous_question: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    tools: tuple[ToolDefinition, ...]
    correlation_id: UUID
    knowledge_context: KnowledgeConversationContext | None = None


class DirectResponseKind(str, Enum):
    """ชนิดข้อความตรงที่ Main Agent สร้างจากแม่แบบที่เชื่อถือได้"""

    GREETING = "greeting"
    THANKS = "thanks"
    UNSUPPORTED = "unsupported"
    OMS_CA_NUMBER = "oms_ca_number"
    OMS_OUTAGE_START = "oms_outage_start"
    OMS_WITH_CA_INPUTS = "oms_with_ca_inputs"
    OMS_ANONYMOUS_INPUTS = "oms_anonymous_inputs"
    VOC_DETAILS = "voc_details"
    VOC_CONTACT_NAME = "voc_contact_name"
    VOC_CONTACT_PHONE = "voc_contact_phone"
    VOC_LOCATION = "voc_location"
    VOC_TRACKING_INPUTS = "voc_tracking_inputs"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """คำตอบจาก provider ที่แปลงเป็นการเรียกเครื่องมือภายในและผ่านการตรวจสอบแล้ว"""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    direct_response: DirectResponseKind | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
