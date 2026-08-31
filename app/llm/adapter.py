"""สัญญาของ provider adapter โดย provider ทำหน้าที่แปลงข้อมูลและไม่เก็บนโยบาย PEA"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.models import LLMRequest, LLMResponse


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """ดำเนินการคำขอที่ไม่ขึ้นกับ provider หนึ่งรายการให้เสร็จ"""


class LLMUnavailableError(RuntimeError):
    """provider ไม่สามารถส่งคำตอบที่ปลอดภัยและใช้งานได้"""
