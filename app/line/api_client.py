"""ไคลเอนต์บาง ๆ สำหรับ LINE Messaging API ที่ webhook ใช้

ครอบเพียงสาม endpoint ที่จำเป็นสำหรับเดโม ได้แก่ reply, push และ
loading indicator ตามเอกสารทางการ:
https://developers.line.biz/en/reference/messaging-api/
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"


class LineApiError(RuntimeError):
    """LINE API ตอบ HTTP ที่ไม่สำเร็จ พร้อมรหัสสถานะเพื่อบันทึก/ตัดสินใจต่อ"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"LINE API ตอบ {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class LineApiClient:
    """ไคลเอนต์แบบไม่มีสถานะค้าง สร้าง connection ต่อการเรียก (เพียงพอสำหรับเดโม)"""

    def __init__(self, access_token: str, timeout_seconds: float = 10.0) -> None:
        self._access_token = access_token
        self._timeout = timeout_seconds

    async def reply_message(self, reply_token: str, messages: list[dict]) -> None:
        """ตอบกลับด้วย reply token ของ event (ใช้ได้ครั้งเดียว อายุประมาณ 1 นาที)"""
        await self._post(_REPLY_URL, {"replyToken": reply_token, "messages": messages})

    async def push_message(self, user_id: str, messages: list[dict]) -> None:
        """ส่งข้อความถึงผู้ใช้โดยตรง (ใช้เป็น fallback เมื่อ reply token หมดอายุ)"""
        await self._post(_PUSH_URL, {"to": user_id, "messages": messages})

    async def show_loading_indicator(self, chat_id: str, seconds: int = 30) -> None:
        """แสดงอนิเมชัน "..." ให้ผู้ใช้เห็นว่าระบบกำลังทำงาน (แชท 1-on-1 เท่านั้น)"""
        await self._post(_LOADING_URL, {"chatId": chat_id, "loadingSeconds": seconds})

    async def _post(self, url: str, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            # ไม่บันทึก body ทั้งหมดเพื่อกันข้อมูลลับ/เนื้อหายาวรั่วเข้า log
            logger.warning(
                "LINE API ตอบไม่สำเร็จ",
                extra={"url": url, "status_code": response.status_code},
            )
            raise LineApiError(response.status_code, response.text[:200])
        return response
