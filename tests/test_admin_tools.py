"""ทดสอบหน้า admin ฝั่ง tool — D3.3/D3.4/D3.5 (TASKS-3DAYS.md)

ความเสี่ยงที่เทสนี้กันไว้:

- D3.4: ฟอร์ม save อะไรก็ได้ = ระบบพังตอนเดโม → validation ต้องก่อน persist เสมอ
- D3.4: save แล้วต้องมีผลเลย → registry ต้องเห็น tool ใหม่/ที่ปิดทันที (hot reload)
- D3.5: ปุ่ม "ลองยิงดู" เป็นทางลัดข้าม SSRF policy → ต้องถูกบล็อกเหมือน executor จริง
- D3.3: tool ที่ปิดตัวเอง (definition ผิด) ต้องแสดงพร้อมเหตุผล กัน "หายเงียบ"
- D3.1: ทุก endpoint ใหม่ fail closed เมื่อไม่ผ่าน admin auth
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.registry import ToolRegistry
from app.agent.tool_shape import ToolOperationShape, ToolShape
from app.api.admin import router as admin_router
from app.contracts import ToolCall, ToolName, ToolResult, ToolResultStatus
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database

_VALID_DEFINITION: dict[str, Any] = {
    "slug": "cat_fact_tool",
    "displayName": "สุ่มข้อเท็จจริงเกี่ยวกับแมว",
    "description": "ดึงข้อเท็จจริงเกี่ยวกับแมวจากบริการสาธารณะ",
    "enabled": True,
    "operations": [
        {
            "action": "get_random_fact",
            "policy": "plain_read",
            "exposure": "llm",
            "mode": "read",
            "httpMethod": "GET",
            "urlTemplate": "https://catfact.ninja/fact",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "max_length": {"type": "integer", "description": "ความยาวสูงสุด"}
                },
                "required": [],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
                "additionalProperties": False,
            },
        }
    ],
}


class _KnowledgeStub:
    """registry บังคับว่าต้องมี Knowledge เสมอ — ตัวปลอมที่เบาที่สุดสำหรับเทส"""

    name = ToolName.KNOWLEDGE

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            simulation=False,
        )


def _code_shape_stub() -> ToolShape:
    """ปลั๊กอิน Python ปลอมสำหรับเช็คว่าอยู่รายการเดียวกับ declarative tool แต่แก้ไม่ได้"""
    return ToolShape(
        slug="code_only_tool",
        display_name="Tool จากโค้ด",
        description="",
        operations=(
            ToolOperationShape(
                action="do_something",
                description="",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema=None,
                exposure="llm",
                mode="read",
                submit_action=None,
                policy="plain_read",
                limits=None,
                client_context=None,
            ),
        ),
        executor=None,
        source="code",
    )


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"fact": "แมวนอนวันละ 16 ชั่วโมง", "length": 20})

    return httpx.MockTransport(handler)


def _settings(app_env: str) -> Settings:
    return Settings.from_env({"APP_ENV": app_env, "ADMIN_PASSWORD": "pw"})


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str = "development",
    transport: httpx.BaseTransport | None = None,
) -> tuple[TestClient, ToolRegistry, Database]:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    registry = ToolRegistry([_KnowledgeStub()])
    service = ToolAdminService(
        db,
        settings=_settings(app_env),
        registry=registry,
        extra_code_shapes=(_code_shape_stub(),),
        transport=transport,
    )
    app = create_platform_app(_settings(app_env))
    app.state.tool_admin = service
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client, registry, db


def _db_write(db: Database, sql: str, params: tuple = ()) -> None:
    db._conn.execute(sql, params)  # noqa: SLF001 — เทสเขียนแถวที่ผิดตรง ๆ โดยตั้งใจ
    db._conn.commit()


# --------------------------------------------------------------------- D3.1 auth --


def test_tool_endpoints_fail_closed_without_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    app = create_platform_app(_settings("development"))
    app.state.tool_admin = ToolAdminService(
        db=Database(":memory:"),
        settings=_settings("development"),
        registry=ToolRegistry([_KnowledgeStub()]),
    )
    app.include_router(admin_router)
    client = TestClient(app)

    for method, url, body in (
        ("get", "/api/v1/admin/tools", None),
        ("post", "/api/v1/admin/tools", _VALID_DEFINITION),
        ("patch", "/api/v1/admin/tools/x/enabled", {"enabled": False}),
        ("post", "/api/v1/admin/tools/try", {"httpMethod": "GET", "urlTemplate": "https://x.test/"}),
    ):
        if method == "get":
            response = client.get(url)
        else:
            response = getattr(client, method)(url, json=body)
        assert response.status_code == 401, (method, url, response.status_code)


# ------------------------------------------------------------------- D3.3 list --


def test_list_tools_shows_db_and_code_tools_with_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201

    body = client.get("/api/v1/admin/tools").json()
    by_slug = {tool["slug"]: tool for tool in body["tools"]}
    assert body["appEnv"] == "development"
    tool = by_slug["cat_fact_tool"]
    assert tool["editable"] is True
    assert tool["operations"][0]["policy"] == "plain_read"
    assert tool["operations"][0]["mode"] == "read"
    # tool จากโค้ดอยู่รายการเดียวกัน แต่ช่องแก้ถูก disable (D3.3)
    assert by_slug["code_only_tool"]["editable"] is False


def test_list_tools_shows_self_disabled_tool_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tool ที่ definition ผิด fail closed ต้องปรากฏในรายการพร้อมเหตุผล กันหายเงียบ"""
    client, registry, db = _make_client(monkeypatch)
    _db_write(
        db,
        "INSERT INTO tool (slug, display_name, description, source) "
        "VALUES ('broken_tool', 'เสีย', '', 'db')",
    )
    _db_write(
        db,
        "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, "
        "exposure, mode, http_method, url_template) "
        "SELECT id, 'do', 'plain_read', ?, 'null', 'llm', 'read', 'GET', 'https://ok.test/x' "
        "FROM tool WHERE slug = 'broken_tool'",
        (
            json.dumps(
                {"type": "object", "oneOf": [{"type": "object"}], "additionalProperties": False}
            ),
        ),
    )
    # reload เหมือนที่ service ทำตอน startup/save — tool เสียต้องไม่ dispatch ได้
    asyncio.run(client.app.state.tool_admin.reload())
    assert "broken_tool" not in registry.names

    body = client.get("/api/v1/admin/tools").json()
    broken = next(tool for tool in body["tools"] if tool["slug"] == "broken_tool")
    assert broken["enabled"] is True  # DB บอกเปิด แต่...
    assert broken["selfDisabledReason"]  # ...มีเหตุผลที่แสดงให้ admin เห็น
    assert "oneOf" in broken["selfDisabledReason"]


# -------------------------------------------------------------- D3.4 save form --


def test_create_tool_saves_and_hot_reloads_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    client, registry, _ = _make_client(monkeypatch)
    response = client.post("/api/v1/admin/tools", json=_VALID_DEFINITION)
    assert response.status_code == 201
    assert response.json()["slug"] == "cat_fact_tool"

    # save แล้วมีผลเลย: registry dispatch ได้ และ LLM เห็นในแค็ตตาล็อก (เทิร์นถัดไป)
    assert "cat_fact_tool" in registry.names
    catalogue_names = {definition.name for definition in registry.llm_catalogue}
    assert "cat_fact_tool" in catalogue_names


def test_update_tool_replaces_operations_and_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201

    edited = copy.deepcopy(_VALID_DEFINITION)
    edited["operations"][0]["action"] = "renamed_action"
    response = client.put("/api/v1/admin/tools/cat_fact_tool", json=edited)
    assert response.status_code == 200
    assert response.json()["operations"][0]["action"] == "renamed_action"

    refreshed = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    assert [op["action"] for op in refreshed["operations"]] == ["renamed_action"]


def test_create_rejects_invalid_schema_and_persists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, registry, _ = _make_client(monkeypatch)
    bad = copy.deepcopy(_VALID_DEFINITION)
    bad["operations"][0]["inputSchema"] = {
        "type": "object",
        "oneOf": [{"type": "object"}],  # ไม่อยู่ใน allowlist §2.1
        "additionalProperties": False,
    }
    response = client.post("/api/v1/admin/tools", json=bad)
    assert response.status_code == 400
    assert "oneOf" in response.json()["detail"]
    assert "cat_fact_tool" not in registry.names


def test_create_rejects_dangerous_url_at_save_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """production: save URL metadata IP ต้อง fail ตั้งแต่ปุ่ม save ไม่ต้องรอลองยิง"""
    client, registry, _ = _make_client(monkeypatch, app_env="production")
    bad = copy.deepcopy(_VALID_DEFINITION)
    bad["operations"][0]["urlTemplate"] = "http://169.254.169.254/latest/meta-data"
    response = client.post("/api/v1/admin/tools", json=bad)
    assert response.status_code == 400
    assert "cat_fact_tool" not in registry.names


def test_create_duplicate_slug_is_409(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 409


def test_disable_tool_removes_it_from_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    client, registry, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201
    assert (
        client.patch(
            "/api/v1/admin/tools/cat_fact_tool/enabled", json={"enabled": False}
        ).status_code
        == 200
    )
    assert "cat_fact_tool" not in registry.names

    # เปิดกลับได้
    assert (
        client.patch(
            "/api/v1/admin/tools/cat_fact_tool/enabled", json={"enabled": True}
        ).status_code
        == 200
    )
    assert "cat_fact_tool" in registry.names


def test_get_tool_does_not_leak_auth_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONTRACTS-V2 §10.2: secret_ref ห้ามปรากฏใน response — เขียนได้อย่างเดียว"""
    client, _, _ = _make_client(monkeypatch)
    definition = copy.deepcopy(_VALID_DEFINITION)
    definition["authEnvVar"] = "CATFACT_API_KEY"
    assert client.post("/api/v1/admin/tools", json=definition).status_code == 201
    body = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    assert "authEnvVar" not in body
    assert "CATFACT_API_KEY" not in json.dumps(body)
    assert body["hasAuth"] is True


def _auth_definition(auth_env_var: str | None = "OLD_API_KEY") -> dict[str, Any]:
    definition = copy.deepcopy(_VALID_DEFINITION)
    if auth_env_var is not None:
        definition["authEnvVar"] = auth_env_var
    return definition


def test_update_without_auth_field_preserves_credential_in_db(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_auth_definition()).status_code == 201
    edited = _auth_definition()
    edited.pop("authEnvVar")
    assert client.put("/api/v1/admin/tools/cat_fact_tool", json=edited).status_code == 200
    row = db._conn.execute(
        "SELECT secret_ref FROM tool_auth JOIN tool ON tool.id = tool_auth.tool_id "
        "WHERE tool.slug = 'cat_fact_tool'"
    ).fetchone()
    assert row["secret_ref"] == "OLD_API_KEY"


def test_update_auth_field_replaces_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_auth_definition()).status_code == 201
    edited = _auth_definition("NEW_API_KEY")
    assert client.put("/api/v1/admin/tools/cat_fact_tool", json=edited).status_code == 200
    row = db._conn.execute(
        "SELECT secret_ref FROM tool_auth JOIN tool ON tool.id = tool_auth.tool_id "
        "WHERE tool.slug = 'cat_fact_tool'"
    ).fetchone()
    assert row["secret_ref"] == "NEW_API_KEY"


def test_update_null_auth_field_removes_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_auth_definition()).status_code == 201
    edited = _auth_definition()
    edited["authEnvVar"] = None
    assert client.put(
        "/api/v1/admin/tools/cat_fact_tool", json=edited
    ).status_code == 200
    count = db._conn.execute(
        "SELECT COUNT(*) AS count FROM tool_auth JOIN tool ON tool.id = tool_auth.tool_id "
        "WHERE tool.slug = 'cat_fact_tool'"
    ).fetchone()["count"]
    assert count == 0
    assert client.get("/api/v1/admin/tools/cat_fact_tool").json()["hasAuth"] is False


def test_list_tools_exposes_has_auth_without_secret_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_auth_definition()).status_code == 201
    body = client.get("/api/v1/admin/tools").json()
    tool = next(item for item in body["tools"] if item["slug"] == "cat_fact_tool")
    assert tool["hasAuth"] is True
    assert "OLD_API_KEY" not in json.dumps(body)


# --------------------------------------------------------------------- D3.5 try --


def test_try_block_metadata_ip_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3.5: ปุ่มลองยิงต้องผ่าน SSRF policy — 169.254.169.254 บน production ต้องถูกบล็อก"""
    client, _, _ = _make_client(monkeypatch, app_env="production", transport=_mock_transport())
    response = client.post(
        "/api/v1/admin/tools/try",
        json={"httpMethod": "GET", "urlTemplate": "https://169.254.169.254/latest/meta-data"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["reason"] == "internal_ip"
    assert "169.254.169.254" in body["error"]


def test_try_block_localhost_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """เทสที่ TASKS-3DAYS.md กำหนดไว้ตรงตัว: 127.0.0.1 บน production ยิงไม่ได้"""
    client, _, _ = _make_client(monkeypatch, app_env="production", transport=_mock_transport())
    response = client.post(
        "/api/v1/admin/tools/try",
        json={"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:8080/secret"},
    )
    body = response.json()
    assert body["ok"] is False
    assert body["reason"] in {"not_https", "domain_not_in_allowlist", "internal_ip"}


def test_try_success_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch, app_env="development", transport=_mock_transport())
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/fact",
            "inputSchema": _VALID_DEFINITION["operations"][0]["inputSchema"],
            "input": {},
        },
    )
    body = response.json()
    assert body["ok"] is True, body
    assert body["response"]["statusCode"] == 200
    assert body["response"]["body"] == {"fact": "แมวนอนวันละ 16 ชั่วโมง", "length": 20}
    assert "elapsedMs" in body["response"]


def test_try_rejects_input_not_matching_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch, app_env="development", transport=_mock_transport())
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/fact",
            "inputSchema": _VALID_DEFINITION["operations"][0]["inputSchema"],
            "input": {"max_length": "ไม่ใช่ตัวเลข"},
        },
    )
    body = response.json()
    assert body["ok"] is False
    assert body["reason"] == "invalid_input"


# ------------------------------------------------------- D3.5 secret redaction --


_SECRET = "super-secret-token-9f2a"


def _echo_auth_transport() -> httpx.MockTransport:
    """ปลายทางจอมกวน: echo Authorization header กลับมาทุกรูปแบบที่ฝังได้"""

    def handler(request: httpx.Request) -> httpx.Response:
        echoed = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={
                "echo": echoed,
                "nested": {"token": echoed, "deep": {"value": echoed}},
                "list": [echoed, {"inside": echoed}, "ข้อมูลปกติ"],
            },
        )

    return httpx.MockTransport(handler)


def test_try_redacts_echoed_secret_from_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3.5 (hardening): ปลายทาง echo Authorization กลับมา — ค่า secret ต้องไม่ปรากฏใน response

    ครอบคลุมทั้งระดับบนสุด object/list ซ้อนกันและ string ที่ฝังอยู่"""
    monkeypatch.setenv("ADMIN_TRY_SECRET", _SECRET)
    client, _, _ = _make_client(
        monkeypatch, app_env="development", transport=_echo_auth_transport()
    )
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "ADMIN_TRY_SECRET",
        },
    )
    body = response.json()
    assert body["ok"] is True, body
    # ค่าจริงห้ามปรากฏที่ไหนใน response แม้แต่ตัวเดียว (เทียบ raw text ทั้งก้อน)
    assert _SECRET not in response.text
    # ทุกตำแหน่งที่เคยมี secret กลายเป็น [REDACTED] — รวม object/list ซ้อนกัน
    response_body = body["response"]["body"]
    assert response_body["echo"] == "[REDACTED]"
    assert response_body["nested"] == {
        "token": "[REDACTED]",
        "deep": {"value": "[REDACTED]"},
    }
    assert response_body["list"] == ["[REDACTED]", {"inside": "[REDACTED]"}, "ข้อมูลปกติ"]


def test_try_error_does_not_leak_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3.5 (hardening): error (เช่น missing_secret) ต้องไม่มีค่าจริงของ secret ปรากฏ"""
    monkeypatch.setenv("ADMIN_TRY_SECRET", _SECRET)
    client, _, _ = _make_client(monkeypatch, app_env="development", transport=_mock_transport())
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/fact",
            "authEnvVar": "ADMIN_TRY_SECRET_NOT_SET",
        },
    )
    body = response.json()
    assert body["ok"] is False
    assert body["reason"] == "missing_secret"
    assert _SECRET not in response.text
    assert "ADMIN_TRY_SECRET_NOT_SET" not in response.text
