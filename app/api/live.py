"""Thin WebSocket entry point for the Gemini Live voice session."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.core.config import load_settings
from app.core.di import agent_service

router = APIRouter()


@router.websocket("/ws/live")
async def gemini_live(websocket: WebSocket) -> None:
    """Create a fresh Gemini session, queue, bridge, and conversation per socket."""
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
        agent=agent_service.agent,
    )
    await session.serve(websocket)
