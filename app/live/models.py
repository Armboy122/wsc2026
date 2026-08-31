"""สัญญาของ voice bridge: พื้นผิว MainAgent ขั้นต่ำและรูปผลลัพธ์ JSON ที่ปลอดภัย

โมดูลนี้ประกาศเฉพาะส่วนที่ voice layer ใช้จาก Main Agent เดิมเท่านั้น ได้แก่
``handle_chat``, ``confirm_pending_action`` และ ``reject_pending_action``
เพื่อให้ bridge เรียกได้แค่สามเมทอดนี้โดยถูกจำกัดที่ระดับชนิดข้อมูล
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable
from uuid import UUID

from app.contracts import ActionDecisionResponse, ChatRequest, ChatResponse


@runtime_checkable
class MainAgentGateway(Protocol):
    """พื้นผิว MainAgent ขั้นต่ำที่ voice bridge เรียกได้เท่านั้น

    ``app.agent.main_agent.MainAgent`` จริงมีเมทอดทั้งสามนี้และเป็นไปตาม
    โปรโตคอลนี้ ข้อกำหนดด้านความปลอดภัย: voice layer ต้องไม่เรียกเมทอดอื่น
    ของ Main Agent (เช่น ``get_trace`` หรือ ``reset_demo``)
    """

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """จัดการข้อความแชตหนึ่งรอบและส่งคืนคำตอบตามสัญญาแบบคงที่"""
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
        """ปฏิเสธรายการที่รอดำเนินการ โดยเป็นสถานะสิ้นสุดและเรียกซ้ำได้"""
        ...


class ChatTurnResult(TypedDict):
    """ผลลัพธ์แชตแบบ JSON (camelCase) ที่ voice backend ส่งต่อได้ทันที

    ตรงกับ ``ChatResponse.model_dump(mode="json", by_alias=True)``
    """

    conversationId: str
    traceId: str
    message: str
    citations: list[dict[str, object]]
    pendingAction: dict[str, object] | None
    toolResults: list[dict[str, object]]


class ActionDecisionResult(TypedDict):
    """ผลลัพธ์ยืนยัน/ปฏิเสธแบบ JSON (camelCase)

    ตรงกับ ``ActionDecisionResponse.model_dump(mode="json", by_alias=True)``
    """

    pendingAction: dict[str, object]
    toolResult: dict[str, object] | None
    traceId: str
