"""เส้นทาง HTTP ตามสัญญาของแพลตฟอร์ม PEA One Agent

ตัวจัดการทั้งหมดมอบหมายงานให้ interface ของ Main Agent โดยไม่มีการให้เหตุผล
และไม่เรียกเครื่องมือโดยตรง
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.agent.stores import trace_channel
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
from app.core.admin_auth import require_admin
from app.core.di import agent_service
from app.core.errors import NotFoundException, PublicApiException
from app.core.logging import get_logger
from app.core.public_api import (
    WEB_SESSION_COOKIE,
    ApiKeyRecord,
    ApiKeyStore,
    ConversationOwnership,
    InMemoryRateLimiter,
    WebSession,
    WebSessionStore,
)

logger = get_logger(__name__)

router = APIRouter()


async def require_public_api_key(request: Request) -> ApiKeyRecord:
    """Authenticate every request on the external API boundary."""
    store: ApiKeyStore | None = getattr(request.app.state, "api_key_store", None)
    if store is None:
        raise RuntimeError("public API authentication is not configured")
    value = request.headers.get("x-api-key")
    if not value:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            value = authorization[7:].strip()
    record = await store.authenticate(value)
    if record is None:
        raise PublicApiException(
            status.HTTP_401_UNAUTHORIZED,
            "unauthorized",
            "ไม่สามารถยืนยันตัวตนได้",
        )
    limiter = getattr(request.app.state, "public_api_rate_limiter", None)
    if limiter is None:
        settings = getattr(request.app.state, "settings", None)
        limiter = InMemoryRateLimiter(
            getattr(settings, "public_api_rate_limit_per_minute", 60)
        )
        request.app.state.public_api_rate_limiter = limiter
    if not limiter.allow(record.id):
        raise PublicApiException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "เกินจำนวนคำขอที่อนุญาต",
        )
    request.state.public_api_key_id = record.id
    return record


def _web_sessions(request: Request) -> WebSessionStore:
    store: WebSessionStore | None = getattr(
        request.app.state,
        "web_session_store",
        None,
    )
    if store is None:
        raise RuntimeError("web session authentication is not configured")
    return store


async def require_web_session(request: Request) -> WebSession:
    session = _web_sessions(request).authenticate(
        request.cookies.get(WEB_SESSION_COOKIE)
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ต้องเริ่มเซสชันหน้าเว็บก่อน",
        )
    return session


def _ownership(request: Request) -> ConversationOwnership:
    ownership = getattr(request.app.state, "conversation_ownership", None)
    if ownership is None:
        raise RuntimeError("public API ownership is not configured")
    return ownership


def _check_conversation_owner(
    request: Request,
    key: ApiKeyRecord,
    conversation_id: uuid.UUID,
) -> None:
    ownership = _ownership(request)
    if ownership.owner_of(conversation_id) != key.id:
        raise PublicApiException(status.HTTP_404_NOT_FOUND, "not_found", "ไม่พบทรัพยากร")


def _check_pending_owner(
    request: Request,
    key: ApiKeyRecord,
    pending_action_id: uuid.UUID,
) -> None:
    ownership = _ownership(request)
    if ownership.pending_owner_of(pending_action_id) != key.id:
        raise PublicApiException(status.HTTP_404_NOT_FOUND, "not_found", "ไม่พบทรัพยากร")


@router.post("/api/v1/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    request: Request,
    body: ChatRequest,
    key: Annotated[ApiKeyRecord, Depends(require_public_api_key)],
) -> ChatResponse:
    if body.conversation_id is not None:
        _check_conversation_owner(request, key, body.conversation_id)
    with trace_channel("api"):
        response = await agent_service.agent.handle_chat(body)
    ownership = _ownership(request)
    if not ownership.claim(response.conversation_id, key.id):
        raise PublicApiException(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "ไม่พบทรัพยากร",
        )
    if response.pending_action is not None:
        if not await ownership.claim_pending(
            response.pending_action.pending_action_id,
            key.id,
        ):
            raise PublicApiException(
                status.HTTP_404_NOT_FOUND,
                "not_found",
                "ไม่พบทรัพยากร",
            )
    return response


@router.post(
    "/api/v1/actions/{pending_action_id}/confirm",
    response_model=ActionDecisionResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_pending_action(
    request: Request,
    pending_action_id: uuid.UUID,
    body: ConfirmActionRequest,
    key: Annotated[ApiKeyRecord, Depends(require_public_api_key)],
) -> ActionDecisionResponse:
    _check_pending_owner(request, key, pending_action_id)
    with trace_channel("api"):
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
    key: Annotated[ApiKeyRecord, Depends(require_public_api_key)],
) -> ActionDecisionResponse:
    _check_pending_owner(request, key, pending_action_id)
    with trace_channel("api"):
        return await agent_service.agent.reject_pending_action(
            pending_action_id,
            reason=body.reason,
        )


@router.get("/api/v1/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(
    request: Request,
    trace_id: uuid.UUID,
    _: Annotated[None, Depends(require_admin)],
) -> TraceResponse:
    return _get_trace(trace_id)


@router.post("/api/v1/reset", response_model=ResetResponse)
async def reset_demo(
    request: Request,
    _: Annotated[None, Depends(require_admin)],
) -> ResetResponse:
    return await _reset_demo(request)


@router.post("/api/v1/web/session")
async def create_web_session(request: Request) -> JSONResponse:
    store: WebSessionStore = request.app.state.web_session_store
    token = store.create()
    response = JSONResponse({"authenticated": True})
    settings = request.app.state.settings
    response.set_cookie(
        WEB_SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/api/v1/web",
        max_age=8 * 60 * 60,
    )
    return response


@router.post("/api/v1/web/chat", response_model=ChatResponse)
async def web_chat(
    request: Request,
    body: ChatRequest,
    session: Annotated[WebSession, Depends(require_web_session)],
) -> ChatResponse:
    sessions = _web_sessions(request)
    if (
        body.conversation_id is not None
        and not sessions.owns_conversation(session, body.conversation_id)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบทรัพยากร")
    with trace_channel("web"):
        response = await agent_service.agent.handle_chat(body)
    if not sessions.claim_conversation(session, response.conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบทรัพยากร")
    if response.pending_action is not None and not sessions.claim_pending(
        session,
        response.pending_action.pending_action_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบทรัพยากร")
    return response


@router.post(
    "/api/v1/web/actions/{pending_action_id}/confirm",
    response_model=ActionDecisionResponse,
)
async def web_confirm_pending_action(
    request: Request,
    pending_action_id: uuid.UUID,
    body: ConfirmActionRequest,
    session: Annotated[WebSession, Depends(require_web_session)],
) -> ActionDecisionResponse:
    if not _web_sessions(request).owns_pending(session, pending_action_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบทรัพยากร")
    with trace_channel("web"):
        return await agent_service.agent.confirm_pending_action(
            pending_action_id,
            confirmation_note=body.confirmation_note,
        )


@router.post(
    "/api/v1/web/actions/{pending_action_id}/reject",
    response_model=ActionDecisionResponse,
)
async def web_reject_pending_action(
    request: Request,
    pending_action_id: uuid.UUID,
    body: RejectActionRequest,
    session: Annotated[WebSession, Depends(require_web_session)],
) -> ActionDecisionResponse:
    if not _web_sessions(request).owns_pending(session, pending_action_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบทรัพยากร")
    with trace_channel("web"):
        return await agent_service.agent.reject_pending_action(
            pending_action_id,
            reason=body.reason,
        )


def _get_trace(trace_id: uuid.UUID) -> TraceResponse:
    try:
        return agent_service.agent.get_trace(trace_id)
    except LookupError as exc:
        raise NotFoundException(detail="ไม่พบ trace") from exc


async def _reset_demo(request: Request) -> ResetResponse:
    response = await agent_service.agent.reset_demo()
    ownership: ConversationOwnership | None = getattr(
        request.app.state,
        "conversation_ownership",
        None,
    )
    if ownership is not None:
        ownership.clear()
    limiter = getattr(request.app.state, "public_api_rate_limiter", None)
    if limiter is not None:
        limiter.clear()
    return response


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    from app.core.di import adapter_service

    llm_ready = adapter_service.llm is None or await adapter_service.llm.ready()
    knowledge_ready = (
        adapter_service.knowledge is None
        or await adapter_service.knowledge.ready()
    )
    return HealthResponse(
        status="ok" if (llm_ready and knowledge_ready) else "degraded",
    )
