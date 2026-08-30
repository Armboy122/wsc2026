"""Frozen HTTP routes for the PEA One Agent platform.

All handlers delegate to the Main Agent interface; they contain no reasoning
and never invoke tools directly.
"""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Request, status

from app.contracts import (
    ActionDecisionResponse,
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    HealthResponse,
    RejectActionRequest,
    ResetResponse,
    TraceResponse,
)
from app.core.di import agent_service
from app.core.errors import NotFoundException
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/api/v1/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    return await agent_service.agent.handle_chat(body)


@router.post(
    "/api/v1/actions/{pending_action_id}/confirm",
    response_model=ActionDecisionResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_pending_action(
    request: Request,
    pending_action_id: uuid.UUID,
    body: ConfirmActionRequest,
) -> ActionDecisionResponse:
    return await agent_service.agent.confirm_pending_action(
        pending_action_id,
        confirmation_note=body.confirmation_note,
    )


@router.post(
    "/api/v1/actions/{pending_action_id}/reject",
    response_model=ActionDecisionResponse,
    status_code=status.HTTP_200_OK,
)
async def reject_pending_action(
    request: Request,
    pending_action_id: uuid.UUID,
    body: RejectActionRequest,
) -> ActionDecisionResponse:
    return await agent_service.agent.reject_pending_action(
        pending_action_id,
        reason=body.reason,
    )


@router.get("/api/v1/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(request: Request, trace_id: uuid.UUID) -> TraceResponse:
    try:
        return agent_service.agent.get_trace(trace_id)
    except LookupError as exc:
        raise NotFoundException(detail="trace not found") from exc


@router.post("/api/v1/reset", response_model=ResetResponse)
async def reset_demo(request: Request) -> ResetResponse:
    return agent_service.agent.reset_demo()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    from app.core.di import adapter_service

    llm_ready = adapter_service.llm is None or await adapter_service.llm.ready()
    knowledge_ready = adapter_service.knowledge is None or await adapter_service.knowledge.ready()
    return HealthResponse(
        status="ok" if (llm_ready and knowledge_ready) else "degraded",
        llm_adapter="ready" if llm_ready else "unavailable",
        knowledge_backend="ready" if knowledge_ready else "unavailable",
        simulation_mode=True,
    )
