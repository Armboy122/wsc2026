"""Tests for admin try operation using saved tool credentials (A1).

Verifies the 5 requirements:
1. Create new tool without credential -> no auth sent.
2. Edit existing tool without changing credential -> uses server-side saved credential.
3. Edit existing tool with new env var -> uses new env var for try.
4. Edit existing tool with remove credential -> tries without auth.
5. Edit existing tool with modified header/scheme but preserved credential -> uses form's header/scheme with saved credential.

Security and safety guarantees:
- Unknown tool slug returns safe error and does not fallback.
- Non-admin sessions cannot use this endpoint.
- Try operation never mutates DB records.
- Secrets and env var names do not leak in response or logs.
- Upstream echoed secrets are redacted.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.registry import ToolRegistry
from app.api.admin import router as admin_router
from app.contracts import ToolCall, ToolName, ToolResult, ToolResultStatus
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database

_SAVED_SECRET = "synthetic-saved-oms-key-888"
_NEW_SECRET = "synthetic-new-key-999"


class _KnowledgeStub:
    name = ToolName.KNOWLEDGE

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            simulation=False,
        )


def _settings(app_env: str = "development") -> Settings:
    return Settings.from_env({"APP_ENV": app_env, "ADMIN_PASSWORD": "pw"})


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str = "development",
    transport: httpx.BaseTransport | None = None,
) -> tuple[TestClient, Database, ToolAdminService]:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    service = ToolAdminService(
        db,
        settings=_settings(app_env),
        registry=ToolRegistry([_KnowledgeStub()]),
        transport=transport,
    )
    app = create_platform_app(_settings(app_env))
    app.state.tool_admin = service
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client, db, service


def _seed_db_tool(
    db: Database,
    slug: str = "oms_tool",
    *,
    secret_ref: str | None = "OMS_API_KEY",
    header_name: str = "X-API-Key",
    scheme: str = "",
) -> None:
    tool_id = db._conn.execute(  # noqa: SLF001
        "INSERT INTO tool (slug, display_name, description, enabled, source) "
        "VALUES (?, ?, 'OMS test tool', 1, 'db')",
        (slug, f"Tool {slug}"),
    ).lastrowid
    db._conn.execute(  # noqa: SLF001
        "INSERT INTO tool_operation "
        "(tool_id, action, policy, input_schema, output_schema, exposure, mode, "
        "submit_action, limits, client_context, http_method, url_template) "
        "VALUES (?, 'get_outage', 'plain_read', '{}', 'null', 'llm', 'read', NULL, NULL, NULL, 'GET', 'http://127.0.0.1:9999/outage')",
        (tool_id,),
    )
    if secret_ref is not None:
        db._conn.execute(  # noqa: SLF001
            "INSERT INTO tool_auth (tool_id, type, secret_ref, header_name, scheme) "
            "VALUES (?, 'api_key', ?, ?, ?)",
            (tool_id, secret_ref, header_name, scheme),
        )
    db._conn.commit()  # noqa: SLF001


def test_try_saved_auth_preserves_credential_and_sends_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 2: Edit existing tool without changing credential uses server-side saved credential."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"status": "active"})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    # Try operation referencing oms_tool with NO authEnvVar sent
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
            "input": {},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True, data
    assert len(captured) == 1
    assert captured[0].headers.get("x-api-key") == _SAVED_SECRET
    # Ensure secret and secret_ref name do not leak
    assert _SAVED_SECRET not in response.text
    assert "OMS_API_KEY" not in response.text

    # Verify DB was NOT modified
    row = db._conn.execute("SELECT secret_ref, header_name, scheme FROM tool_auth").fetchone()  # noqa: SLF001
    assert row[0] == "OMS_API_KEY"
    assert row[1] == "X-API-Key"
    assert row[2] == ""


def test_try_saved_auth_with_custom_header_and_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 5: Change header/scheme in form but preserve credential -> uses form values with saved secret."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    # Try operation with custom header name and scheme from form
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
            "authHeaderName": "X-Custom-Auth",
            "authScheme": "Token",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True, data
    assert len(captured) == 1
    assert captured[0].headers.get("x-custom-auth") == f"Token {_SAVED_SECRET}"
    assert "x-api-key" not in captured[0].headers

    # Verify DB was NOT modified
    row = db._conn.execute("SELECT header_name, scheme FROM tool_auth").fetchone()  # noqa: SLF001
    assert row[0] == "X-API-Key"
    assert row[1] == ""


def test_try_saved_auth_replace_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 3: Specify new env var -> uses new env var for try."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)
    monkeypatch.setenv("NEW_KEY_VAR", _NEW_SECRET)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    # Send new authEnvVar
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
            "authEnvVar": "NEW_KEY_VAR",
            "authHeaderName": "Authorization",
            "authScheme": "Bearer",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True, data
    assert len(captured) == 1
    assert captured[0].headers.get("authorization") == f"Bearer {_NEW_SECRET}"
    assert "x-api-key" not in captured[0].headers

    # Verify DB was NOT modified
    row = db._conn.execute("SELECT secret_ref FROM tool_auth").fetchone()  # noqa: SLF001
    assert row[0] == "OMS_API_KEY"


def test_try_saved_auth_remove_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 4: Remove credential -> tries without auth."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    # Send authEnvVar: null (explicit removal)
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
            "authEnvVar": None,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True, data
    assert len(captured) == 1
    assert "x-api-key" not in captured[0].headers
    assert "authorization" not in captured[0].headers

    # Verify DB was NOT modified
    row = db._conn.execute("SELECT secret_ref FROM tool_auth").fetchone()  # noqa: SLF001
    assert row is not None
    assert row[0] == "OMS_API_KEY"


def test_try_unknown_tool_slug_returns_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown tool identifier must return a safe error and never fallback."""
    client, _, _ = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True})),
    )
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "non_existent_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/test",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is False
    assert data["reason"] == "not_found"


def test_try_saved_auth_redacts_echoed_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redaction must cover the saved secret when upstream echoes it."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)

    def handler(request: httpx.Request) -> httpx.Response:
        echoed = request.headers.get("x-api-key", "")
        return httpx.Response(200, json={"echoed_key": echoed, "message": f"Hello {echoed}"})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert _SAVED_SECRET not in response.text
    assert data["response"]["body"]["echoed_key"] == "[REDACTED]"
    assert data["response"]["body"]["message"] == "Hello [REDACTED]"


def test_try_saved_auth_redacts_secret_used_as_response_object_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A secret echoed as a JSON property name must be removed by the admin route too."""
    monkeypatch.setenv("OMS_API_KEY", _SAVED_SECRET)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={_SAVED_SECRET: "value", f"prefix-{_SAVED_SECRET}": "embedded-value"},
        )

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True, data
    assert _SAVED_SECRET not in response.text
    assert data["response"]["body"] == {
        "[REDACTED]": "value",
        "prefix-[REDACTED]": "embedded-value",
    }


def test_try_without_admin_session_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-admin session cannot access the try endpoint."""
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    app = create_platform_app(_settings())
    app.include_router(admin_router)
    client = TestClient(app)
    # Do NOT login
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
        },
    )
    assert response.status_code == 401


def test_try_saved_auth_missing_env_var_returns_missing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When configured secret_ref is not present in environment, returns missing_secret."""
    monkeypatch.delenv("OMS_API_KEY", raising=False)
    client, db, _ = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    _seed_db_tool(db, "oms_tool", secret_ref="OMS_API_KEY", header_name="X-API-Key", scheme="")

    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "oms_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/outage",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["reason"] == "missing_secret"


def test_try_tool_without_saved_auth_runs_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool that exists in DB with no auth runs unauthenticated when preserved."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client, db, _ = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    _seed_db_tool(db, "public_tool", secret_ref=None)

    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "toolSlug": "public_tool",
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/public",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(captured) == 1
    assert "x-api-key" not in captured[0].headers
    assert "authorization" not in captured[0].headers
