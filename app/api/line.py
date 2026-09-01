"""จุดเข้า webhook ของ LINE Messaging API

route นี้เป็นเพียงขอบเขต transport: ตรวจลายเซ็น, แยก events, ตอบ 200
ทันทีแล้วส่งงานไปทำใน background เพราะ agent loop อาจนานเกินกรอบเวลา
ที่ LINE รอคำตอบ webhook นโยบายธุรกิจทั้งหมดอยู่ที่ Main Agent ผ่าน bridge
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.line.service import LineWebhookService
from app.line.signature import verify_webhook_signature

logger = get_logger(__name__)

router = APIRouter()

_service: LineWebhookService | None = None


def configure_line_webhook(service: LineWebhookService) -> None:
    """ลงทะเบียนบริการ webhook ที่ประกอบใน app.main เมื่อตั้งค่าครบ"""
    global _service
    _service = service


def line_webhook_configured() -> bool:
    return _service is not None


@router.post("/webhook/line")
async def line_webhook(request: Request, background: BackgroundTasks) -> JSONResponse:
    service = _service
    if service is None:
        return JSONResponse(status_code=404, content={"detail": "LINE webhook ยังไม่ได้เปิดใช้งาน"})

    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_webhook_signature(service.secret, body, signature):
        # ขอบเขตความปลอดภัย: ปฏิเสธก่อนแตะข้อมูลใด ๆ (fail closed)
        logger.warning("ปฏิเสธ LINE webhook ที่ลายเซ็นไม่ถูกต้อง")
        return JSONResponse(status_code=403, content={"detail": "ลายเซ็นไม่ถูกต้อง"})

    try:
        payload: dict[str, Any] = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"detail": "เนื้อหาไม่ใช่ JSON ที่ถูกต้อง"})

    events = payload.get("events")
    if isinstance(events, list) and events:
        background.add_task(service.handle_events, events)
    return JSONResponse(content={})
