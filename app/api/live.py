"""Thin WebSocket entry point for the ADK Gemini Live session."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.core.config import load_settings

router = APIRouter()

_UNAVAILABLE = {"type": "error", "message": "โหมดเสียงไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"}


@router.websocket("/ws/live")
async def gemini_live(websocket: WebSocket) -> None:
    """Create one ADK Live session for each browser connection."""
    settings = load_settings()
    if not settings.gemini_api_key:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "โหมดเสียงยังไม่ได้ตั้งค่า"})
        await websocket.close(code=1011)
        return
    index_manager = getattr(websocket.app.state, "knowledge_index_manager", None)
    try:
        from app.runtime.adk_live import AdkLiveSession
    except ImportError:
        await websocket.accept()
        await websocket.send_json(_UNAVAILABLE)
        await websocket.close(code=1011)
        return
    if index_manager is None:
        await websocket.accept()
        await websocket.send_json(_UNAVAILABLE)
        await websocket.close(code=1011)
        return

    session = AdkLiveSession(
        api_key=settings.gemini_api_key,
        model=settings.live_model,
        voice=settings.live_voice,
        index_manager=index_manager,
    )
    await session.serve(websocket)
