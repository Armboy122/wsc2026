"""HTTP surface of the Voice agent: health only (voice runs over `WS /ws/live`)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts import HealthResponse, KnowledgeIndexHealth
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
        knowledge_index=_knowledge_index_health(request.app.state),
    )


def _knowledge_index_health(app_state: object) -> KnowledgeIndexHealth:
    """Report index readiness with counts only; never paths, content, or error text."""
    manager = getattr(app_state, "knowledge_index_manager", None)
    if manager is None:
        # No manager means the optional index extra is absent or nothing was configured.
        return KnowledgeIndexHealth(status="error", documents=0, chunks=0)
    snapshot = manager.health()
    return KnowledgeIndexHealth(
        status=snapshot.status.value,
        documents=snapshot.documents,
        chunks=snapshot.chunks,
    )
