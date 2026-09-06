"""ไคลเอนต์ HTTP สำหรับ Telegram Bot API โดยไม่ใช้ library ภายนอก

ตาม ARCHITECTURE-V2.md §5.6: ยิง httpx ตรง ไม่เพิ่ม library
และซ่อน bot token ใน log เสมอ
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.telegram.org"


class TokenRedactFilter(logging.Filter):
    """ตัวกรอง log record เพื่อปกปิด bot token ทุกจุด ทั้ง msg, args, traceback, และ exc_info"""

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token.strip() if token else ""

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.token:
            return True

        if isinstance(record.msg, str) and self.token in record.msg:
            record.msg = record.msg.replace(self.token, "[REDACTED]")

        if record.args:
            new_args: list[Any] = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(arg.replace(self.token, "[REDACTED]"))
                elif isinstance(arg, httpx.URL):
                    new_args.append(httpx.URL(str(arg).replace(self.token, "[REDACTED]")))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)

        if record.exc_info:
            try:
                formatted = "".join(traceback.format_exception(*record.exc_info))
                record.exc_text = formatted.replace(self.token, "[REDACTED]")
            except Exception:
                pass

        if record.exc_text and self.token in record.exc_text:
            record.exc_text = record.exc_text.replace(self.token, "[REDACTED]")

        if getattr(record, "stack_info", None) and self.token in str(record.stack_info):
            record.stack_info = str(record.stack_info).replace(self.token, "[REDACTED]")

        return True


def install_token_redactor(token: str) -> TokenRedactFilter:
    """ติดตั้ง TokenRedactFilter ให้กับ logger หลักที่เกี่ยวข้อง (httpx, app.telegram, root)"""
    flt = TokenRedactFilter(token)
    for name in ("httpx", "app.telegram", "app.telegram.api_client", "app.telegram.service", ""):
        log = logging.getLogger(name)
        # ตรวจสอบเพื่อไม่ติดตั้ง filter ซ้ำ
        if not any(isinstance(f, TokenRedactFilter) and f.token == token for f in log.filters):
            log.addFilter(flt)
    return flt


class TelegramApiError(RuntimeError):
    """Telegram Bot API ตอบ HTTP ที่ไม่สำเร็จ หรือเกิดข้อผิดพลาดในการเชื่อมต่อ (ปลอดภัยต่อการแสดงผลและ log)"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Telegram API ตอบ {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class TelegramApiClient:
    """ไคลเอนต์สำหรับ Telegram Bot API รองรับการส่งข้อความ, แก้ markup, และ answerCallbackQuery"""

    def __init__(
        self,
        bot_token: str,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._timeout = timeout_seconds
        self._client = client
        if self._bot_token:
            install_token_redactor(self._bot_token)

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """ส่งข้อความตัวอักษรพร้อมตัวเลือก reply_markup (InlineKeyboardMarkup)"""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", payload)

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """แก้ไขหรือลบ reply_markup ของข้อความเดิม (ส่ง reply_markup=None เพื่อลบปุ่มออก)"""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("editMessageReplyMarkup", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        """ตอบกลับ callback query ทุกครั้งเพื่อหยุดตัวหมุน loading บนปุ่มของผู้ใช้"""
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text[:200]
        return await self._post("answerCallbackQuery", payload)

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = "typing",
    ) -> None:
        """ส่งสถานะ typing ให้ผู้ใช้เห็นว่าระบบกำลังเตรียมคำตอบ (best effort)"""
        try:
            await self._post("sendChatAction", {"chat_id": chat_id, "action": action})
        except Exception:
            logger.warning("ส่ง Telegram chat action typing ไม่สำเร็จ")

    def _redact(self, text: str) -> str:
        if not self._bot_token:
            return text
        return text.replace(self._bot_token, "[REDACTED]")

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{_BASE_URL}/bot{self._bot_token}/{method}"
        redacted_log_url = f"{_BASE_URL}/bot[REDACTED]/{method}"

        try:
            if self._client is not None:
                response = await self._client.post(url, json=payload, timeout=self._timeout)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            safe_err = self._redact(str(exc))
            logger.warning(
                "Telegram API การเชื่อมต่อล้มเหลว",
                extra={"method": method, "url": redacted_log_url, "error": safe_err},
            )
            raise TelegramApiError(0, f"การเชื่อมต่อล้มเหลว: {safe_err}") from None
        except Exception as exc:
            safe_err = self._redact(str(exc))
            logger.warning(
                "Telegram API เกิดข้อผิดพลาดที่ไม่คาดคิด",
                extra={"method": method, "url": redacted_log_url, "error": safe_err},
            )
            raise TelegramApiError(0, f"ข้อผิดพลาด: {safe_err}") from None

        if response.status_code >= 400:
            safe_detail = self._redact(response.text[:200])
            logger.warning(
                "Telegram API ตอบไม่สำเร็จ",
                extra={"method": method, "url": redacted_log_url, "status_code": response.status_code},
            )
            raise TelegramApiError(response.status_code, safe_detail)

        try:
            data: dict[str, Any] = response.json()
        except Exception as exc:
            raise TelegramApiError(response.status_code, "คำตอบไม่ใช่ JSON ที่ถูกต้อง") from None

        if not data.get("ok", False):
            raw_desc = str(data.get("description") or "Telegram error")
            safe_desc = self._redact(raw_desc[:200])
            logger.warning(
                "Telegram API ตอบ ok=false",
                extra={"method": method, "url": redacted_log_url, "description": safe_desc},
            )
            raise TelegramApiError(response.status_code, safe_desc)

        return data
