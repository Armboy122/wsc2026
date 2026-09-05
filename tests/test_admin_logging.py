"""Regression tests for admin log redaction and response contracts (T8)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.registry import ToolRegistry
from app.api.admin import router as admin_router
from app.contracts import ToolCall, ToolName, ToolResult, ToolResultStatus
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.prompt_admin import PromptAdminService
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database


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


def _settings() -> Settings:
    return Settings.from_env({"APP_ENV": "development", "ADMIN_PASSWORD": "correct-password-xyz"})


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transport: httpx.BaseTransport | None = None,
    with_prompt: bool = False,
) -> TestClient:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    settings = _settings()
    app = create_platform_app(settings)
    app.state.tool_admin = ToolAdminService(
        db,
        settings=settings,
        registry=ToolRegistry([_KnowledgeStub()]),
        transport=transport,
    )
    if with_prompt:
        import asyncio

        from app.db.bootstrap_prompt import seed_system_prompt

        asyncio.run(seed_system_prompt(db))
        app.state.prompt_admin = PromptAdminService(db)
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": settings.admin_password}).status_code == 200
    return client


@contextmanager
def _capture_admin_logs() -> Iterator[list[logging.LogRecord]]:
    """Capture raw records after app startup replaces root handlers."""
    records: list[logging.LogRecord] = []

    class _RecordHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # The production formatter mutates records during root propagation;
            # retain an independent raw copy so extras remain testable.
            records.append(logging.makeLogRecord(record.__dict__.copy()))

    handler = _RecordHandler()
    loggers = tuple(
        logging.getLogger(name)
        for name in ("app.api.admin", "app.core.prompt_admin", "app.core.tool_admin")
    )
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield records
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


def _record_text(record: logging.LogRecord) -> str:
    return repr(record.__dict__)


def test_login_logs_never_contain_failed_or_successful_password(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client(monkeypatch)
    caplog.set_level(logging.INFO)
    wrong = "wrong-secret-abc123"
    correct = "correct-password-xyz"

    with _capture_admin_logs() as records:
        assert client.post("/api/v1/admin/login", json={"password": wrong}).status_code == 401
        assert records
        assert any(record.getMessage() == "admin_login_failed" for record in records)
        assert all(wrong not in _record_text(record) for record in records)

        records.clear()
        assert client.post("/api/v1/admin/login", json={"password": correct}).status_code == 200
        assert records
        assert any(record.getMessage() == "admin_login_succeeded" for record in records)
        assert all(correct not in _record_text(record) for record in records)


def test_prompt_save_log_contains_length_but_not_full_prompt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client(monkeypatch, with_prompt=True)
    caplog.set_level(logging.INFO)
    prompt = "prompt-secret-body-" + ("ข้อความละเอียดที่ไม่ควรเข้า log " * 20)

    with _capture_admin_logs() as records:
        response = client.put("/api/v1/admin/prompt", json={"content": prompt})
        assert response.status_code == 200
        assert records
        saved = next(record for record in records if record.getMessage() == "admin_prompt_saved")
        assert saved.__dict__["content_length"] == len(prompt)
        assert prompt not in _record_text(saved)


def test_external_tool_try_log_contains_no_secret_or_credential_name(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret_name = "ADMIN_LOG_TEST_CREDENTIAL_XYZ"
    secret = "credential-value-secret-abc987"
    monkeypatch.setenv(secret_name, secret)
    client = _client(
        monkeypatch,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
    )
    caplog.set_level(logging.INFO)
    with _capture_admin_logs() as records:
        response = client.post(
            "/api/v1/admin/tools/try",
            json={
                "httpMethod": "GET",
                "urlTemplate": "http://127.0.0.1:9999/check",
                "authEnvVar": secret_name,
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert records
        tried = next(record for record in records if record.getMessage() == "admin_external_tool_try")
        assert tried.__dict__["ok"] is True
        assert secret not in _record_text(tried)
        assert secret_name not in _record_text(tried)


def test_admin_responses_conform_to_tool_and_try_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        monkeypatch,
        transport=httpx.MockTransport(lambda request: httpx.Response(204, text="")),
    )
    definition = {
        "slug": "contract_probe_tool",
        "displayName": "Contract probe",
        "description": "contract test",
        "operations": [
            {
                "action": "probe",
                "policy": "plain_read",
                "exposure": "llm",
                "mode": "read",
                "httpMethod": "GET",
                "urlTemplate": "http://127.0.0.1:9999/probe",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "outputSchema": None,
            }
        ],
    }
    assert client.post("/api/v1/admin/tools", json=definition).status_code == 201
    tool = client.get("/api/v1/admin/tools/contract_probe_tool")
    assert tool.status_code == 200
    tool_body = tool.json()
    assert isinstance(tool_body["hasAuth"], bool)
    assert "authEnvVar" not in tool_body

    tried = client.post(
        "/api/v1/admin/tools/try",
        json={"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:9999/probe"},
    )
    assert tried.status_code == 200
    body = tried.json()
    assert {"method", "url", "query", "body"} <= set(body["request"])
    assert {"statusCode", "elapsedMs", "body", "isJson", "text"} <= set(body["response"])
    assert not any("header" in key.lower() for key in json.dumps(body).split('"'))
