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


def _new_trace_id() -> uuid.UUID:
    return uuid.uuid4()


@router.post("/api/v1/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    trace_id = _new_trace_id()
    logger.info("chat_received", extra={"trace_id": str(trace_id)})
    return await agent_service.agent.handle_chat(
        conversation_id=body.conversation_id,
        message=body.message,
        request_id=body.request_id,
        trace_id=trace_id,
    )


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
    trace_id = _new_trace_id()
    pending_action, tool_result = await agent_service.agent.confirm_pending_action(
        pending_action_id=pending_action_id,
        confirmation_note=body.confirmation_note,
        trace_id=trace_id,
    )
    return ActionDecisionResponse(
        pending_action=pending_action,
        tool_result=tool_result,
        trace_id=trace_id,
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
    trace_id = _new_trace_id()
    pending_action = await agent_service.agent.reject_pending_action(
        pending_action_id=pending_action_id,
        reason=body.reason,
        trace_id=trace_id,
    )
    return ActionDecisionResponse(
        pending_action=pending_action,
        tool_result=None,
        trace_id=trace_id,
    )


@router.get("/api/v1/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(request: Request, trace_id: uuid.UUID) -> TraceResponse:
    events = await agent_service.agent.get_trace(trace_id=trace_id)
    if not events:
        raise NotFoundException(detail=f"trace {trace_id} not found")
    return TraceResponse(trace_id=trace_id, events=events)


@router.post("/api/v1/reset", response_model=ResetResponse)
async def reset_demo(request: Request) -> ResetResponse:
    await agent_service.agent.reset_demo()
    return ResetResponse(reset=True)


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
