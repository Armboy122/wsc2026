"""ไคลเอนต์ LLM ขนาดเล็กที่ไม่ขึ้นกับ provider ซึ่ง Main Agent ใช้งาน"""

from __future__ import annotations

from app.llm.adapter import LLMAdapter
from app.llm.models import LLMRequest, LLMResponse


class LLMClient:
    """ไคลเอนต์สำหรับแอปพลิเคชันซึ่งตั้งใจไม่เปิดเผยชนิดข้อมูลจาก SDK ของ provider"""

    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._adapter.complete(request)

    @property
    def ready(self) -> bool:
        return True


class JudgeLLMClient(LLMClient):
    """integration seam ที่มีชื่อสำหรับ implementation ของ ``LLMAdapter`` ที่กรรมการจัดเตรียมให้"""
