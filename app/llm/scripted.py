"""อะแดปเตอร์แบบกำหนดผลลัพธ์ได้สำหรับเดโมและการทดสอบ"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.llm.adapter import LLMUnavailableError
from app.llm.models import LLMRequest, LLMResponse


class ScriptedLLMAdapter:
    """ส่งคืนคำตอบตามลำดับโดยไม่ตรวจข้อมูลหรือติดต่อ provider"""

    def __init__(self, responses: Iterable[LLMResponse] = ()) -> None:
        self._responses: deque[LLMResponse] = deque(responses)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMUnavailableError("ไม่มีคำตอบ LLM แบบ scripted ที่พร้อมใช้งาน")
        return self._responses.popleft()

    def append(self, response: LLMResponse) -> None:
        self._responses.append(response)
