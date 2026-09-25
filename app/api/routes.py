"""HTTP surface of the Voice agent: health only (voice runs over `WS /ws/live`)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts import HealthResponse
from app.core.di import get_knowledge_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    try:
        knowledge_ready = len(get_knowledge_service().catalog) > 0
    except RuntimeError:
        knowledge_ready = False
    live_configured = bool(request.app.state.settings.gemini_api_key)
    return HealthResponse(
        status="ok" if (knowledge_ready and live_configured) else "degraded",
        knowledge_backend="ready" if knowledge_ready else "unavailable",
        live_voice="configured" if live_configured else "not_configured",
    )
