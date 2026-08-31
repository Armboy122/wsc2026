"""โปรโตคอลบริการ dependency injection สำหรับแพลตฟอร์ม FastAPI

ตัวจัดการ HTTP มอบหมายงานให้ interface ของ Main Agent โดยไม่มีนโยบายธุรกิจ
และไม่เรียกเครื่องมือโดยตรง
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.contracts import (
    ActionDecisionResponse,
    ChatRequest,
    ChatResponse,
    ResetResponse,
    ToolCall,
    ToolResult,
    TraceResponse,
)


@runtime_checkable
class MainAgent(Protocol):
    """ตัวประสานงานเพียงตัวเดียวที่เส้นทางแพลตฟอร์มเรียกใช้"""

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """จัดการข้อความแชตและส่งคืนคำตอบตามสัญญาแบบคงที่"""
        ...

    async def confirm_pending_action(
        self,
        pending_action_id: UUID,
        confirmation_note: str | None = None,
    ) -> ActionDecisionResponse:
        """ส่งรายการที่รอดำเนินการหนึ่งครั้ง โดยการเรียกซ้ำให้ผลเหมือนเดิม"""
        ...

    async def reject_pending_action(
        self,
        pending_action_id: UUID,
        reason: str,
    ) -> ActionDecisionResponse:
        """ปฏิเสธรายการที่รอดำเนินการ โดยเป็นสถานะสิ้นสุดและการเรียกซ้ำให้ผลเหมือนเดิม"""
        ...

    def get_trace(self, trace_id: UUID) -> TraceResponse:
        """ส่งคืนเหตุการณ์ trace ตามลำดับและผ่านการปกปิดข้อมูลสำหรับ trace id"""
        ...

    def reset_demo(self) -> ResetResponse:
        """ล้างสถานะเดโมทั้งหมดภายใน process"""
        ...


class AgentService:
    """คอนเทนเนอร์แบบรูปธรรมสำหรับ Main Agent และอะแดปเตอร์ของแพลตฟอร์ม

    ผู้ดูแลหลักเชื่อมต่อส่วนนี้ใน app.main ผ่าน set_agent โดยโค้ดแพลตฟอร์ม
    จะไม่สร้าง implementation ของ Main Agent เอง
    """

    def __init__(self) -> None:
        self._agent: MainAgent | None = None

    def set_agent(self, agent: MainAgent) -> None:
        self._agent = agent

    @property
    def agent(self) -> MainAgent:
        if self._agent is None:
            raise RuntimeError("ยังไม่ได้เชื่อมต่อ Main Agent เข้ากับ AgentService")
        return self._agent


agent_service = AgentService()


@runtime_checkable
class Tool(Protocol):
    """จุดเชื่อมต่อ runtime แบบแคบสำหรับโมดูลเครื่องมือที่เรียกใช้ได้"""

    name: str

    async def execute(self, call: ToolCall) -> ToolResult:
        """ดำเนินการเรียกเครื่องมือที่ผ่านการตรวจสอบแล้วและส่งคืน ToolResult แบบคงที่"""
        ...


@runtime_checkable
class LLMAdapter(Protocol):
    """จุดเชื่อมต่อ LLM ที่ไม่ขึ้นกับ provider ซึ่งแพลตฟอร์มใช้อ้างอิงเพื่อตรวจสอบสถานะ"""

    async def ready(self) -> bool:
        """ส่งคืน True เมื่ออะแดปเตอร์พร้อมให้บริการคำขอ"""
        ...


@runtime_checkable
class KnowledgeBackend(Protocol):
    """จุดเชื่อมต่อสำหรับตรวจสอบความพร้อมของ backend ความรู้"""

    async def ready(self) -> bool:
        """ส่งคืน True เมื่อ backend พร้อมให้บริการคำขอค้นคืนข้อมูล"""
        ...


class AdapterService:
    """คอนเทนเนอร์สำหรับอะแดปเตอร์เสริมของแพลตฟอร์มที่ /health ใช้งาน"""

    def __init__(self) -> None:
        self.llm: LLMAdapter | None = None
        self.knowledge: KnowledgeBackend | None = None

    def set_llm(self, adapter: LLMAdapter) -> None:
        self.llm = adapter

    def set_knowledge(self, backend: KnowledgeBackend) -> None:
        self.knowledge = backend


adapter_service = AdapterService()
