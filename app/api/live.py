"""Thin WebSocket entry point for the Gemini Live voice session."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.core.config import load_settings
from app.core.di import agent_service
from app.live.scoped_agent import scoped_voice_agent

router = APIRouter()


@router.websocket("/ws/live")
async def gemini_live(websocket: WebSocket, channel: str = "web") -> None:
    """Create a fresh Gemini session, queue, bridge, and conversation per socket.

    ``channel=phone`` คือสายเสียงล้วนแบบ 1129 ที่ไม่มีหน้าจอ ค่าอื่นทั้งหมด
    ถือว่าเป็นเว็บที่มีจอ เพื่อให้ค่าเริ่มต้นปลอดภัยเมื่อไคลเอนต์ไม่ระบุ
    """
    settings = load_settings()
    if not settings.gemini_api_key:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "โหมดเสียงยังไม่ได้ตั้งค่า"})
        await websocket.close(code=1011)
        return
    try:
        # google-genai is optional: text mode must start without voice extras.
        from app.live.gemini_live import GeminiLiveSession
    except ImportError:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "โหมดเสียงไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"})
        await websocket.close(code=1011)
        return
    session = GeminiLiveSession(
        api_key=settings.gemini_api_key,
        model=settings.live_model,
        voice=settings.live_voice,
        # ช่องทางเสียงเห็นเฉพาะ Knowledge กับ OMS ส่วนเว็บและ LINE ยังครบทุกเครื่องมือ
        agent=scoped_voice_agent(agent_service.agent),
        has_display=channel != "phone",
    )
    await session.serve(websocket)
