"""ค่าที่ไม่ขึ้นกับ provider ซึ่งใช้ที่ขอบเขต LLM ของ Main Agent"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import UUID

from app.contracts import ToolCall


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """ข้อความแชตขนาดเล็กโดยเจตนา ซึ่งไม่เก็บกระบวนการคิดที่ซ่อนอยู่"""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """รายการในแค็ตตาล็อกเครื่องมือที่ LLM provider มองเห็น

    ``name`` เป็น ``str`` เฉย ๆ (ไม่ใช่ ``ToolName`` enum อีกต่อไป) เพราะ declarative tool
    จาก DB มี slug นอก enum เดิม (D2.6, ARCHITECTURE-V2.md §3.5)
    """

    name: str
    description: str
    actions: tuple[str, ...]
    # D2.6: declarative tool ประกาศ inputSchema เป็นข้อมูลจริงต่อ action (ไม่ใช่ชื่อคลาส
    # Pydantic) — None = ปล่อยให้ ``tool_catalogue`` derive จาก ``INPUT_MODELS`` เหมือนเดิม
    # (3 tool เดิม); ให้ค่านี้เมื่อไม่มี Pydantic model ให้ derive จาก (tool ใหม่ทุกตัว)
    input_schemas: Mapping[str, dict[str, Any]] | None = None


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
    planner_instructions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """คำตอบจาก provider ที่แปลงเป็นการเรียกเครื่องมือภายในและผ่านการตรวจสอบแล้ว"""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    direct_response: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
