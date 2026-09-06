"""P8 public API security and contract checks."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.agent.stores import PendingActionStore
from app.api.admin import router as admin_router
from app.api.routes import router
from app.api.tests.test_routes import ScriptedMainAgent
from app.contracts import PendingAction, PendingActionStatus, ToolAction, ToolName
from app.core import admin_auth
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.di import agent_service
from app.core.public_api import (
    ApiKeyStore,
    ConversationOwnership,
    InMemoryRateLimiter,
    WebSessionStore,
    hash_api_key,
)
from app.core.startup import create_platform_app
from app.db import Database


@pytest.fixture
async def public_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_key = Fernet.generate_key().decode("ascii")
    db = Database(tmp_path / "pea.db", state_key=state_key)
    db.migrate()
    app = create_platform_app(
        Settings(
            db_path=tmp_path / "pea.db",
            state_key=state_key,
            admin_password="admin-test-password",
        )
    )
    app.state.api_key_store = ApiKeyStore(db)
    app.state.conversation_ownership = ConversationOwnership()
    app.state.public_api_rate_limiter = InMemoryRateLimiter(60)
    app.include_router(router)
    app.include_router(admin_router)
    monkeypatch.setattr(admin_auth, "admin_session_store", AdminSessionStore())
    previous_agent = agent_service._agent  # noqa: SLF001 - restore global DI after fixture
    agent = ScriptedMainAgent()
    agent_service.set_agent(agent)
    try:
        yield app, app.state.api_key_store, db, agent
    finally:
        agent_service._agent = previous_agent  # noqa: SLF001
        db.close()


async def _client(app):
    # Exercise the installed catch-all handler as a real ASGI server would.
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.mark.anyio
async def test_missing_and_revoked_api_key_are_unauthorized(public_api) -> None:
    app, keys, _, _ = public_api
    async with await _client(app) as client:
        assert (await client.post("/api/v1/chat", json={"message": "hi"})).status_code == 401
        created = await keys.create("test")
        assert (await client.post("/api/v1/chat", headers={"X-API-Key": created.value}, json={"message": "hi"})).status_code == 200
        await keys.revoke(created.record.id)
        assert not await keys.revoke(uuid4())
        response = await client.post("/api/v1/chat", headers={"X-API-Key": created.value}, json={"message": "hi"})
        assert response.status_code == 401


@pytest.mark.anyio
async def test_bundled_web_uses_a_separate_opaque_session(public_api) -> None:
    app, keys, _, agent = public_api
    async with await _client(app) as client_a, await _client(app) as client_b:
        assert (
            await client_a.post("/api/v1/web/chat", json={"message": "hi"})
        ).status_code == 401
        session_a = await client_a.post("/api/v1/web/session")
        session_b = await client_b.post("/api/v1/web/session")
        assert session_a.status_code == session_b.status_code == 200
        assert "httponly" in session_a.headers["set-cookie"].lower()
        assert "samesite=strict" in session_a.headers["set-cookie"].lower()

        first = await client_a.post("/api/v1/web/chat", json={"message": "hi"})
        assert first.status_code == 200
        conversation_id = first.json()["conversationId"]
        cross_session = await client_b.post(
            "/api/v1/web/chat",
            json={"conversationId": conversation_id, "message": "intrude"},
        )
        assert cross_session.status_code == 404
        assert len(agent.conversations[UUID(conversation_id)]) == 1

        public_key = await keys.create("public client")
        public_chat = await client_a.post(
            "/api/v1/chat",
            headers={"X-API-Key": public_key.value},
            json={"message": "public"},
        )
        public_conversation_id = public_chat.json()["conversationId"]
        assert (
            await client_a.post(
                "/api/v1/web/chat",
                json={"conversationId": public_conversation_id, "message": "intrude"},
            )
        ).status_code == 404
        assert (
            await client_a.post(
                "/api/v1/chat",
                headers={"X-API-Key": public_key.value},
                json={"conversationId": conversation_id, "message": "intrude"},
            )
        ).status_code == 404
        assert (
            await client_a.post("/api/v1/chat", json={"message": "hi"})
        ).status_code == 401


def test_bundled_web_client_has_no_privileged_web_aliases() -> None:
    source = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "session: '/api/v1/web/session'" in source
    assert "chat: '/api/v1/web/chat'" in source
    assert "trace: (id) => `/api/v1/traces/" in source
    assert "/api/v1/web/traces" not in source
    assert "/api/v1/web/reset" not in source
    assert "credentials: 'same-origin'" in source


def test_web_session_store_has_a_hard_memory_bound() -> None:
    sessions = WebSessionStore(max_sessions=2)
    first = sessions.create()
    second = sessions.create()
    with pytest.raises(RuntimeError, match="capacity"):
        sessions.create()
    assert sessions.authenticate(first) is not None
    assert sessions.authenticate(second) is not None


@pytest.mark.anyio
async def test_factory_assembled_public_api_fails_closed_without_key_store() -> None:
    app = create_platform_app(Settings(app_env="production"))
    app.include_router(router)
    previous_agent = agent_service._agent  # noqa: SLF001
    agent_service.set_agent(ScriptedMainAgent())
    try:
        async with await _client(app) as client:
            response = await client.post("/api/v1/chat", json={"message": "hi"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal"
    finally:
        agent_service._agent = previous_agent  # noqa: SLF001


@pytest.mark.anyio
async def test_conversation_is_owned_by_the_key_and_cross_key_is_404(public_api) -> None:
    app, keys, _, agent = public_api
    key_a = await keys.create("a")
    key_b = await keys.create("b")
    async with await _client(app) as client:
        first = await client.post("/api/v1/chat", headers={"X-API-Key": key_a.value}, json={"message": "hi"})
        conversation_id = first.json()["conversationId"]
        cross = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": key_b.value},
            json={"conversationId": conversation_id, "message": "hi"},
        )
        assert cross.status_code == 404
        assert cross.json()["error"]["code"] == "not_found"
        assert len(agent.conversations[UUID(conversation_id)]) == 1


@pytest.mark.anyio
async def test_pending_action_is_owned_by_the_key_that_created_it(public_api) -> None:
    app, keys, _, _ = public_api

    class PendingAgent(ScriptedMainAgent):
        async def handle_chat(self, request):
            response = await super().handle_chat(request)
            now = datetime.now(UTC)
            pending = PendingAction(
                pending_action_id=uuid4(),
                conversation_id=response.conversation_id,
                tool_name=ToolName.OMS,
                prepare_action=ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
                submit_action=ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
                prepared_input={},
                summary="แจ้งไฟดับ CA 123456789012",
                status=PendingActionStatus.PENDING_CONFIRMATION,
                idempotency_key="p8-pending-owner",
                created_at=now,
                updated_at=now,
            )
            self.pending[pending.pending_action_id] = pending
            return response.model_copy(update={"pending_action": pending})

    agent_service.set_agent(PendingAgent())
    key_a = await keys.create("pending owner")
    key_b = await keys.create("other")
    async with await _client(app) as client:
        chat = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": key_a.value},
            json={"message": "แจ้งไฟดับ"},
        )
        pending_id = chat.json()["pendingAction"]["pendingActionId"]
        cross = await client.post(
            f"/api/v1/actions/{pending_id}/confirm",
            headers={"X-API-Key": key_b.value},
            json={},
        )
        owner = await client.post(
            f"/api/v1/actions/{pending_id}/confirm",
            headers={"X-API-Key": key_a.value},
            json={},
        )

    assert cross.status_code == 404
    assert cross.json()["error"]["code"] == "not_found"
    assert owner.status_code == 200


@pytest.mark.anyio
async def test_web_pending_action_is_isolated_from_other_channels(public_api) -> None:
    app, keys, _, _ = public_api

    class PendingAgent(ScriptedMainAgent):
        async def handle_chat(self, request):
            response = await super().handle_chat(request)
            now = datetime.now(UTC)
            pending = PendingAction(
                pending_action_id=uuid4(),
                conversation_id=response.conversation_id,
                tool_name=ToolName.OMS,
                prepare_action=ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
                submit_action=ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
                prepared_input={},
                summary="แจ้งไฟดับ CA 123456789012",
                status=PendingActionStatus.PENDING_CONFIRMATION,
                idempotency_key="p8-web-pending-owner",
                created_at=now,
                updated_at=now,
            )
            self.pending[pending.pending_action_id] = pending
            return response.model_copy(update={"pending_action": pending})

    pending_agent = PendingAgent()
    agent_service.set_agent(pending_agent)
    public_key = await keys.create("public client")
    async with await _client(app) as owner, await _client(app) as other:
        assert (await owner.post("/api/v1/web/session")).status_code == 200
        assert (await other.post("/api/v1/web/session")).status_code == 200
        chat = await owner.post("/api/v1/web/chat", json={"message": "แจ้งไฟดับ"})
        pending_id = chat.json()["pendingAction"]["pendingActionId"]

        cross_session = await other.post(
            f"/api/v1/web/actions/{pending_id}/confirm",
            json={},
        )
        cross_channel = await owner.post(
            f"/api/v1/actions/{pending_id}/confirm",
            headers={"X-API-Key": public_key.value},
            json={},
        )
        assert cross_session.status_code == 404
        assert cross_channel.status_code == 404
        assert pending_agent.pending[UUID(pending_id)].status == PendingActionStatus.PENDING_CONFIRMATION

        accepted = await owner.post(
            f"/api/v1/web/actions/{pending_id}/confirm",
            json={},
        )
        assert accepted.status_code == 200


@pytest.mark.anyio
async def test_pending_action_ownership_survives_process_restart(tmp_path: Path) -> None:
    state_key = Fernet.generate_key().decode("ascii")
    db_path = tmp_path / "restart.db"
    first_db = Database(db_path, state_key=state_key)
    first_db.migrate()
    key_store = ApiKeyStore(first_db)
    owner_key = await key_store.create("owner")
    other_key = await key_store.create("other")
    now = datetime.now(UTC)
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_name=ToolName.OMS,
        prepare_action=ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
        submit_action=ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
        prepared_input={},
        summary="แจ้งไฟดับ CA 123456789012",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="p8-restart-owner",
        created_at=now,
        updated_at=now,
    )
    await PendingActionStore(first_db).put(pending, uuid4())
    first_ownership = ConversationOwnership(first_db)
    assert await first_ownership.claim_pending(
        pending.pending_action_id,
        owner_key.record.id,
    )
    first_db.close()

    reopened_db = Database(db_path, state_key=state_key)
    reopened_db.migrate()
    restored = PendingActionStore(reopened_db).get(pending.pending_action_id)
    assert restored is not None
    app = create_platform_app(Settings(db_path=db_path, state_key=state_key))
    app.state.api_key_store = ApiKeyStore(reopened_db)
    app.state.conversation_ownership = ConversationOwnership(reopened_db)
    app.state.public_api_rate_limiter = InMemoryRateLimiter(60)
    app.include_router(router)
    previous_agent = agent_service._agent  # noqa: SLF001
    restarted_agent = ScriptedMainAgent()
    restarted_agent.pending[pending.pending_action_id] = restored
    agent_service.set_agent(restarted_agent)
    try:
        async with await _client(app) as client:
            cross = await client.post(
                f"/api/v1/actions/{pending.pending_action_id}/confirm",
                headers={"X-API-Key": other_key.value},
                json={},
            )
            owner = await client.post(
                f"/api/v1/actions/{pending.pending_action_id}/confirm",
                headers={"X-API-Key": owner_key.value},
                json={},
            )
        assert cross.status_code == 404
        assert owner.status_code == 200
    finally:
        agent_service._agent = previous_agent  # noqa: SLF001
        reopened_db.close()


@pytest.mark.anyio
async def test_public_error_is_closed_and_does_not_leak_internals(
    public_api,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, keys, _, _ = public_api
    created = await keys.create("error")

    class ExplodingAgent(ScriptedMainAgent):
        async def handle_chat(self, request):
            del request
            raise RuntimeError("oms_tool failed at http://internal.example with X-Secret")

    agent_service.set_agent(ExplodingAgent())
    with caplog.at_level(logging.ERROR):
        async with await _client(app) as client:
            response = await client.post(
                "/api/v1/chat",
                headers={"X-API-Key": created.value},
                json={"message": "hi"},
            )
    body = response.json()
    assert response.status_code == 500
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "traceId"}
    UUID(body["error"]["traceId"])
    assert body["error"]["code"] == "internal"
    assert not any(
        secret in response.text.lower()
        for secret in ("traceback", "tool", "http://", "internal.example", "x-secret")
    )
    assert "internal.example" not in caplog.text
    assert "x-secret" not in caplog.text.lower()


@pytest.mark.anyio
async def test_web_error_does_not_log_provider_details(
    public_api,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, _, _, _ = public_api

    class ExplodingAgent(ScriptedMainAgent):
        async def handle_chat(self, request):
            del request
            raise RuntimeError(
                "provider failed at https://secret.example?api_key=LEAKME"
            )

    agent_service.set_agent(ExplodingAgent())
    async with await _client(app) as client:
        assert (await client.post("/api/v1/web/session")).status_code == 200
        with caplog.at_level(logging.ERROR):
            response = await client.post(
                "/api/v1/web/chat",
                json={"message": "hi"},
            )

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "secret.example" not in response.text
    assert "LEAKME" not in response.text
    assert "secret.example" not in caplog.text
    assert "LEAKME" not in caplog.text


@pytest.mark.anyio
async def test_public_routing_error_uses_the_closed_error_contract(public_api) -> None:
    app, _, _, _ = public_api
    async with await _client(app) as client:
        response = await client.get("/api/v1/chat")
    assert response.status_code == 405
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "invalid_input"
    assert set(response.json()["error"]) == {"code", "message", "traceId"}


@pytest.mark.anyio
async def test_rate_limit_is_per_key_and_returns_429(public_api) -> None:
    app, keys, _, _ = public_api
    app.state.public_api_rate_limiter = InMemoryRateLimiter(1)
    created = await keys.create("rate")
    other = await keys.create("other")
    async with await _client(app) as client:
        headers = {"X-API-Key": created.value}
        assert (await client.post("/api/v1/chat", headers=headers, json={"message": "one"})).status_code == 200
        response = await client.post("/api/v1/chat", headers=headers, json={"message": "two"})
        other_response = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": other.value},
            json={"message": "independent"},
        )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert other_response.status_code == 200


@pytest.mark.anyio
async def test_api_key_hash_is_one_way_and_plaintext_is_not_stored(public_api) -> None:
    _, keys, db, _ = public_api
    created = await keys.create("hash")
    row = await db.fetch_one("SELECT key_hash FROM api_key WHERE id = ?", (str(created.record.id),))
    assert row is not None
    assert row["key_hash"] == hash_api_key(created.value)
    assert created.value not in row["key_hash"]
    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO api_key (id, name, key_hash, tenant_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), "other tenant", "hash", "other", "2026-01-01T00:00:00+00:00"),
        )


@pytest.mark.anyio
async def test_admin_returns_plaintext_once_without_persisting_or_logging_it(
    public_api,
) -> None:
    app, _, db, _ = public_api
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logging.getLogger().addHandler(handler)
    try:
        async with await _client(app) as client:
            login = await client.post(
                "/api/v1/admin/login", json={"password": "admin-test-password"}
            )
            assert login.status_code == 200
            created = await client.post(
                "/api/v1/admin/api-keys", json={"name": "billing client"}
            )
            assert created.status_code == 201
            plaintext = created.json()["apiKey"]

            listed = await client.get("/api/v1/admin/api-keys")
            assert listed.status_code == 200
            assert all("apiKey" not in item for item in listed.json()["apiKeys"])
            assert plaintext not in listed.text

            key_id = created.json()["id"]
            revoked = await client.post(f"/api/v1/admin/api-keys/{key_id}/revoke")
            assert revoked.status_code == 200
            assert (
                await client.post(f"/api/v1/admin/api-keys/{key_id}/revoke")
            ).status_code == 404
    finally:
        logging.getLogger().removeHandler(handler)

    row = await db.fetch_one("SELECT * FROM api_key WHERE id = ?", (key_id,))
    assert row is not None
    assert plaintext not in repr(tuple(row))
    assert records, "capture must observe active application logging"
    assert plaintext not in "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in records
    )


@pytest.mark.anyio
async def test_public_api_fails_closed_when_auth_store_is_missing(public_api) -> None:
    app, _, _, _ = public_api
    del app.state.api_key_store
    async with await _client(app) as client:
        response = await client.post("/api/v1/chat", json={"message": "hi"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal"


@pytest.mark.anyio
async def test_trace_and_reset_require_admin_not_an_api_key(public_api) -> None:
    app, keys, _, _ = public_api
    created = await keys.create("trace owner")
    async with await _client(app) as client:
        chat = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": created.value},
            json={"message": "hi"},
        )
        assert chat.status_code == 200
        trace_id = chat.json()["traceId"]

        assert (await client.get(f"/api/v1/traces/{trace_id}")).status_code == 401
        assert (await client.post("/api/v1/reset")).status_code == 401
        assert (await client.post("/api/v1/web/session")).status_code == 200
        assert (await client.get(f"/api/v1/web/traces/{trace_id}")).status_code == 404
        assert (await client.post("/api/v1/web/reset")).status_code == 404

        login = await client.post(
            "/api/v1/admin/login", json={"password": "admin-test-password"}
        )
        assert login.status_code == 200
        assert (await client.get(f"/api/v1/traces/{trace_id}")).status_code == 200
        assert (await client.post("/api/v1/reset")).status_code == 200
