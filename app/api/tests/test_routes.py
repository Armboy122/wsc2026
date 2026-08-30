"""Tests for platform HTTP routes using a scripted Main Agent stub."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import router
from app.contracts import (
    ActionDecisionResponse,
    ChatResponse,
    PendingAction,
    PendingActionStatus,
    ToolAction,
    ToolName,
    TraceEventKind,
    TraceResponse,
)
from app.core.di import agent_service
from app.core.startup import create_platform_app


class ScriptedMainAgent:
    """Minimal in-memory stub satisfying MainAgent protocol for route tests."""

    name = "scripted"

    def __init__(self) -> None:
        self.traces: dict[uuid.UUID, TraceResponse] = {}
        self.pending: dict[uuid.UUID, PendingAction] = {}
        self.conversations: dict[uuid.UUID, list[str]] = {}

    async def handle_chat(self, request: Any) -> ChatResponse:
        convo = getattr(request, "conversation_id", None) or uuid.uuid4()
        trace_id = uuid.uuid4()
        message = getattr(request, "message", "ack")
        self.conversations.setdefault(convo, []).append(message)
        self.traces[trace_id] = TraceResponse(
            trace_id=trace_id,
            events=(
                {
                    "event_id": uuid.uuid4(),
                    "trace_id": trace_id,
                    "sequence": 1,
                    "at": datetime.now(UTC),
                    "kind": TraceEventKind.CHAT_RECEIVED,
                    "data": {"message_redacted": True},
                },
            ),
        )
        return ChatResponse(
            conversation_id=convo,
            trace_id=trace_id,
            message="ack",
        )

    async def confirm_pending_action(
        self,
        pending_action_id: uuid.UUID,
        confirmation_note: str | None = None,
    ) -> ActionDecisionResponse:
        action = self.pending.get(pending_action_id)
        if action is None:
            raise KeyError(pending_action_id)
        from app.contracts import ToolResult, ToolResultStatus

        submission_result = ToolResult(
            call_id=uuid.uuid4(),
            name=action.tool_name,
            action=action.submit_action,
            status=ToolResultStatus.SUCCESS,
            data={"receipt_id": "R-1", "account_ref": "A-1", "amount_thb": "100.00", "status": "accepted"},
            simulation=True,
        )
        confirmed = action.model_copy(
            update={"status": PendingActionStatus.SUBMITTED, "submission_result": submission_result}
        )
        self.pending[pending_action_id] = confirmed
        return ActionDecisionResponse(
            pending_action=confirmed,
            tool_result=submission_result,
            trace_id=uuid.uuid4(),
        )

    async def reject_pending_action(
        self,
        pending_action_id: uuid.UUID,
        reason: str,
    ) -> ActionDecisionResponse:
        action = self.pending.get(pending_action_id)
        if action is None:
            raise KeyError(pending_action_id)
        rejected = action.model_copy(update={"status": PendingActionStatus.REJECTED})
        self.pending[pending_action_id] = rejected
        return ActionDecisionResponse(
            pending_action=rejected,
            tool_result=None,
            trace_id=uuid.uuid4(),
        )

    def get_trace(self, trace_id: uuid.UUID) -> TraceResponse:
        trace = self.traces.get(trace_id)
        if trace is None:
            raise LookupError(trace_id)
        return trace

    def reset_demo(self) -> Any:
        self.traces.clear()
        self.pending.clear()
        self.conversations.clear()
        return {"reset": True}


@pytest.fixture
def app() -> FastAPI:
    test_app = create_platform_app()
    test_app.include_router(router)
    agent = ScriptedMainAgent()
    agent_service.set_agent(agent)
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_chat_creates_conversation(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "ack"
    assert "conversationId" in data
    assert "traceId" in data


@pytest.mark.anyio
async def test_chat_with_conversation_id(client: AsyncClient) -> None:
    convo = str(uuid.uuid4())
    response = await client.post("/api/v1/chat", json={"conversationId": convo, "message": "hi"})
    assert response.status_code == 200
    assert response.json()["conversationId"] == convo


@pytest.mark.anyio
async def test_confirm_pending_action(client: AsyncClient, app: FastAPI) -> None:
    agent = agent_service.agent
    pending_id = uuid.uuid4()
    agent.pending[pending_id] = PendingAction(
        pending_action_id=pending_id,
        conversation_id=uuid.uuid4(),
        tool_name=ToolName.SABUY,
        prepare_action=ToolAction.SABUY_PREPARE_PAYMENT,
        submit_action=ToolAction.SABUY_SUBMIT_PAYMENT,
        prepared_input={},
        summary="Pay 100 THB",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = await client.post(
        f"/api/v1/actions/{pending_id}/confirm",
        json={"confirmationNote": "ok"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pendingAction"]["status"] == "submitted"
    assert data["traceId"]


@pytest.mark.anyio
async def test_reject_pending_action(client: AsyncClient) -> None:
    agent = agent_service.agent
    pending_id = uuid.uuid4()
    agent.pending[pending_id] = PendingAction(
        pending_action_id=pending_id,
        conversation_id=uuid.uuid4(),
        tool_name=ToolName.VOC,
        prepare_action=ToolAction.VOC_PREPARE_CASE,
        submit_action=ToolAction.VOC_SUBMIT_CASE,
        prepared_input={},
        summary="Open VOC case",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-2",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = await client.post(
        f"/api/v1/actions/{pending_id}/reject",
        json={"reason": "changed my mind"},
    )
    assert response.status_code == 200
    assert response.json()["pendingAction"]["status"] == "rejected"


@pytest.mark.anyio
async def test_get_trace_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/traces/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_trace_found(client: AsyncClient) -> None:
    agent = agent_service.agent
    trace_id = uuid.uuid4()
    agent.traces[trace_id] = TraceResponse(
        trace_id=trace_id,
        events=(
            {
                "event_id": uuid.uuid4(),
                "trace_id": trace_id,
                "sequence": 1,
                "at": datetime.now(UTC),
                "kind": TraceEventKind.CHAT_RECEIVED,
                "data": {},
            },
        ),
    )
    response = await client.get(f"/api/v1/traces/{trace_id}")
    assert response.status_code == 200
    assert response.json()["traceId"] == str(trace_id)


@pytest.mark.anyio
async def test_reset(client: AsyncClient) -> None:
    response = await client.post("/api/v1/reset")
    assert response.status_code == 200
    assert response.json()["reset"] is True


@pytest.mark.anyio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["llmAdapter"] == "ready"
    assert data["knowledgeBackend"] == "ready"
    assert data["simulationMode"] is True


@pytest.mark.anyio
async def test_validation_error_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
