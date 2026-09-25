"""Thin WebSocket entry point for the ADK Gemini Live session."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.core.config import load_settings
from app.core.di import get_knowledge_tool

router = APIRouter()


@router.websocket("/ws/live")
async def gemini_live(websocket: WebSocket) -> None:
    """Create one ADK Live session for each browser connection."""
    settings = load_settings()
    if not settings.gemini_api_key:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "โหมดเสียงยังไม่ได้ตั้งค่า"})
        await websocket.close(code=1011)
        return
    try:
        from app.runtime.adk_live import AdkLiveSession
    except ImportError:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "โหมดเสียงไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"})
        await websocket.close(code=1011)
        return

    session = AdkLiveSession(
        api_key=settings.gemini_api_key,
        model=settings.live_model,
        voice=settings.live_voice,
        knowledge_tool=get_knowledge_tool(),
    )
    await session.serve(websocket)
