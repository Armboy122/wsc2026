"""จุดเข้า webhook ของ Telegram Bot API

route นี้เป็น transport boundary: ตรวจ secret token ด้วย compare_digest,
แยก update payload, ตอบ 200 ทันทีแล้วส่งงานเข้า background tasks
เพื่อไม่ให้ติด timeout ของ Telegram
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.telegram.service import TelegramWebhookService

logger = get_logger(__name__)

router = APIRouter()

_service: TelegramWebhookService | None = None


def configure_telegram_webhook(service: TelegramWebhookService) -> None:
    """ลงทะเบียนบริการ Telegram webhook เมื่อตั้งค่าครบ"""
    global _service
    _service = service


def telegram_webhook_configured() -> bool:
    return _service is not None


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request, background: BackgroundTasks) -> JSONResponse:
    service = _service
    if service is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Telegram webhook ยังไม่ได้เปิดใช้งาน"},
        )

    # กฎ 🔒: ตรวจ secret_token ผ่าน compare_digest ก่อนแตะข้อมูลใด ๆ (fail closed)
    secret_token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(secret_token_header, service.secret):
        logger.warning("ปฏิเสธ Telegram webhook ที่ secret_token ไม่ถูกต้อง")
        return JSONResponse(status_code=403, content={"detail": "secret_token ไม่ถูกต้อง"})

    body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"detail": "เนื้อหาไม่ใช่ JSON ที่ถูกต้อง"})

    if isinstance(payload, dict) and payload:
        background.add_task(service.handle_update, payload)
    return JSONResponse(content={})
