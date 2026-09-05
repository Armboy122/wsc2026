"""ทดสอบ P1 — auth ของ declarative tool เก็บใน DB ได้ทุกแบบ (header name + scheme)

ความเสี่ยงที่เทสนี้กันไว้:

- OMS ต้องการ ``X-API-Key: <key>`` ไม่ใช่ ``Authorization: Bearer`` — ถ้า executor
  ยัง hardcode รูปแบบเดิม แจ้งไฟดับจะได้ 401 ตลอด
- tool เดิมที่ไม่ได้ตั้ง header_name/scheme ต้องยังใช้ Authorization/Bearer เหมือนเดิม
  (migration ใส่ DEFAULT ให้พฤติกรรมไม่เปลี่ยน)
- auth semantics เดิม (omitted = preserve, string = replace, null = remove) ห้ามพัง
  และต้องขยายให้แก้ header/scheme ได้โดยไม่ต้องพิมพ์ชื่อ env var ซ้ำ
- secret_ref (ชื่อ env var) และค่า secret ห้ามรั่วออกทาง response — header/scheme คืนได้
  เพราะไม่ใช่ความลับ (P1 ยืนยันขอบเขตนี้ชัดเจน)
- seed_oms_tool ต้อง seed tool_auth ให้ OMS แบบ idempotent และไม่ทับค่าที่ผู้ใช้แก้เอง
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.declarative_tools import load_declarative_tools
from app.agent.registry import ToolContext, ToolRegistry
from app.api.admin import router as admin_router
from app.contracts import ToolCall, ToolName, ToolResult, ToolResultStatus
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database
from app.db import bootstrap_oms
from app.db.bootstrap_oms import OMS_TOOL_SLUG, seed_oms_tool
from app.tools.declarative_executor import DeclarativeToolAuth, DeclarativeToolExecutor
from app.tools.declarative_request import build_declarative_http_request

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
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        }
    ],
}


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
        transport=transport,
    )
    app = create_platform_app(_settings(app_env))
    app.state.tool_admin = service
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client, registry, db

def _db_exec(db: Database, sql: str, params: tuple = ()) -> int:
    cursor = db._conn.execute(sql, params)  # noqa: SLF001 — เทสเขียนแถวตรง ๆ เพื่อจัดสถานการณ์
    db._conn.commit()
    return cursor.lastrowid or 0


def _db_one(db: Database, sql: str, params: tuple = ()) -> Any:
    return db._conn.execute(sql, params).fetchone()


def _create_tool(client: TestClient, **overrides: Any) -> httpx.Response:
    definition = json.loads(json.dumps(_VALID_DEFINITION))
    definition.update(overrides)
    return client.post("/api/v1/admin/tools", json=definition)


# ชุดคีย์ที่แบบฟอร์มจริง (web/admin-form.js) ส่งขึ้น — GET คืนฟิลด์อ่านอย่างเดียวเพิ่มด้วย
_PUT_OP_KEYS = {
    "action", "policy", "exposure", "mode", "submitAction", "httpMethod",
    "urlTemplate", "inputSchema", "outputSchema", "limits", "clientContext",
}
_PUT_TOOL_KEYS = {
    "slug", "displayName", "description", "enabled", "authEnvVar",
    "authHeaderName", "authScheme", "operations",
}


def _payload_for_put(definition: dict[str, Any]) -> dict[str, Any]:
    """กรอง GET definition ให้เหลือเฉพาะ contract fields — เลียนแบบ buildToolPayload ของฟอร์ม"""
    payload = {k: v for k, v in definition.items() if k in _PUT_TOOL_KEYS}
    payload["operations"] = [
        {k: v for k, v in op.items() if k in _PUT_OP_KEYS}
        for op in definition["operations"]
    ]
    return payload


# --------------------------------------------------------------------------
# 1) migration 003 — คอลัมน์ใหม่มี DEFAULT ที่ทำให้ tool เดิมพฤติกรรมไม่เปลี่ยน
# --------------------------------------------------------------------------


def test_migration_003_defaults_keep_legacy_authorization_bearer(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        tool_id = _db_exec(
            db,
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("legacy_tool", "Legacy", "", "db"),
        )
        _db_exec(
            db,
            "INSERT INTO tool_auth (tool_id, type, secret_ref) VALUES (?, 'api_key', ?)",
            (tool_id, "LEGACY_KEY"),
        )
        row = _db_one(db, "SELECT * FROM tool_auth WHERE tool_id = ?", (tool_id,))
        assert row is not None
        # แถวเดิมสไตล์ (ไม่ระบุ header) ต้องได้ค่าเดิมคือ Authorization / Bearer
        assert row["header_name"] == "Authorization"
        assert row["scheme"] == "Bearer"
    finally:
        db.close()


def test_migration_003_rerun_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        db.migrate()  # รันซ้ำต้องไม่ raise และไม่เพิ่มเวอร์ชัน
        versions = [row[0] for row in db._conn.execute("SELECT version FROM schema_version")]
        assert sorted(versions) == [1, 2, 3]
    finally:
        db.close()


@pytest.mark.parametrize("existing_column", ["header_name", "scheme"])
def test_migration_003_recovers_partial_apply(tmp_path: Path, existing_column: str) -> None:
    db_path = tmp_path / "partial.db"
    db = Database(db_path)
    try:
        db._conn.executescript(
            f"""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO schema_version(version) VALUES (1), (2);
            CREATE TABLE tool (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL
            );
            CREATE TABLE tool_auth (
                id INTEGER PRIMARY KEY,
                tool_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                secret_ref TEXT NOT NULL,
                {existing_column} TEXT NOT NULL DEFAULT
                    '{'Authorization' if existing_column == 'header_name' else 'Bearer'}'
            );
            INSERT INTO tool(id, slug, source) VALUES (1, 'oms_tool', 'db');
            """
        )
        db._conn.commit()
        db.migrate()
        columns = {row[1] for row in db._conn.execute("PRAGMA table_info(tool_auth)")}
        assert columns >= {"header_name", "scheme"}
        assert [row[0] for row in db._conn.execute("SELECT version FROM schema_version")] == [1, 2, 3]
    finally:
        db.close()


def test_migration_003_backfills_legacy_oms_auth_once(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    db = Database(db_path)
    try:
        db._conn.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO schema_version(version) VALUES (1), (2);
            CREATE TABLE tool (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, source TEXT);
            CREATE TABLE tool_auth (
                id INTEGER PRIMARY KEY, tool_id INTEGER, type TEXT, secret_ref TEXT
            );
            INSERT INTO tool(id, slug, source) VALUES (1, 'oms_tool', 'db');
            INSERT INTO tool_auth(id, tool_id, type, secret_ref)
                VALUES (1, 1, 'api_key', 'OLD_OMS_KEY');
            DELETE FROM tool_auth WHERE tool_id = 1;
            """
        )
        db._conn.commit()
        db.migrate()
        row = db._conn.execute("SELECT * FROM tool_auth WHERE tool_id = 1").fetchone()
        assert row is not None
        assert (row[2], row[3], row[4], row[5]) == (
            "api_key", "OMS_API_KEY", "X-API-Key", ""
        )
        db.migrate()
        assert db._conn.execute(
            "SELECT COUNT(*) FROM tool_auth WHERE tool_id = 1"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_migration_003_does_not_overwrite_existing_oms_auth(tmp_path: Path) -> None:
    db = Database(tmp_path / "legacy_with_auth.db")
    try:
        db._conn.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO schema_version(version) VALUES (1), (2);
            CREATE TABLE tool (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, source TEXT);
            CREATE TABLE tool_auth (
                id INTEGER PRIMARY KEY, tool_id INTEGER, type TEXT, secret_ref TEXT
            );
            INSERT INTO tool(id, slug, source) VALUES (1, 'oms_tool', 'db');
            INSERT INTO tool_auth(id, tool_id, type, secret_ref)
                VALUES (1, 1, 'api_key', 'USER_OMS_KEY');
            """
        )
        db._conn.commit()
        db.migrate()
        rows = db._conn.execute(
            "SELECT secret_ref, header_name, scheme FROM tool_auth WHERE tool_id = 1"
        ).fetchall()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            ("USER_OMS_KEY", "Authorization", "Bearer")
        ]
    finally:
        db.close()


# --------------------------------------------------------------------------
# 2) executor — สร้าง header ตาม header_name/scheme จริง
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_sends_x_api_key_without_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOOL_API_KEY", "raw-key-123")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    executor = DeclarativeToolExecutor(
        app_env="development", transport=httpx.MockTransport(handler)
    )
    request = build_declarative_http_request(
        http_method="GET",
        url_template="https://api.example.com/outages/by-ca/112233445566",
        input={},
        auth=DeclarativeToolAuth(env_var="MY_TOOL_API_KEY", header_name="X-API-Key", scheme=""),
    )
    response = await executor.execute(request)
    assert response.status_code == 200
    assert captured[0].headers["x-api-key"] == "raw-key-123"
    assert "authorization" not in captured[0].headers


@pytest.mark.asyncio
async def test_executor_default_is_authorization_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOOL_API_KEY", "raw-key-123")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    executor = DeclarativeToolExecutor(
        app_env="development", transport=httpx.MockTransport(handler)
    )
    request = build_declarative_http_request(
        http_method="GET",
        url_template="https://api.example.com/things",
        input={},
        auth=DeclarativeToolAuth(env_var="MY_TOOL_API_KEY"),
    )
    await executor.execute(request)
    assert captured[0].headers["authorization"] == "Bearer raw-key-123"


# --------------------------------------------------------------------------
# 3) loader — อ่าน header_name/scheme จาก DB ไปสร้าง header จริงตอนยิง
# --------------------------------------------------------------------------


def _seed_tool_with_auth(
    db: Database, *, header_name: Any, scheme: Any
) -> int:
    tool_id = _db_exec(
        db,
        "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
        ("hdr_tool", "Hdr", "", "db"),
    )
    _db_exec(db,
        "INSERT INTO tool_operation "
        "(tool_id, action, policy, input_schema, output_schema, exposure, mode, "
        "submit_action, http_method, url_template) "
        "VALUES (?, 'get_thing', 'plain_read', ?, 'null', 'llm', 'read', NULL, 'GET', ?)",
        (
            tool_id,
            json.dumps(
                {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                }
            ),
            "https://api.example.com/things",
        ),
    )
    _db_exec(
        db,
        "INSERT INTO tool_auth (tool_id, type, secret_ref, header_name, scheme) "
        "VALUES (?, 'api_key', ?, ?, ?)",
        (tool_id, "HDR_TOOL_KEY", header_name, scheme),
    )
    return tool_id


@pytest.mark.asyncio
async def test_loader_reads_header_and_scheme_from_db(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        _seed_tool_with_auth(db, header_name="X-API-Key", scheme="")
        monkeypatch_env = {"HDR_TOOL_KEY": "k-1"}
        bundle = await load_declarative_tools(db, app_env="development", allowlist=())
        assert len(bundle.tools) == 1

        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"ok": True})

        with patch.dict("os.environ", monkeypatch_env):
            with patch(
                "app.tools.declarative_executor.httpx.AsyncClient",
                return_value=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            ):
                result = await bundle.tools[0].execute(
                    ToolCall(
                        call_id=uuid.uuid4(),
                        name="hdr_tool",
                        action="get_thing",
                        input={},
                    ),
                    ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4()),
                )
        assert result.status is ToolResultStatus.SUCCESS
        assert captured[0].headers["x-api-key"] == "k-1"
        assert "authorization" not in captured[0].headers
    finally:
        db.close()


# --------------------------------------------------------------------------
# 4) admin API — auth semantics เดิม + ช่อง header/scheme ใหม่
# --------------------------------------------------------------------------


def test_create_tool_with_x_api_key_auth_persists_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName="X-API-Key", authScheme=""
    )
    assert response.status_code == 201, response.text

    row = _db_one(db, "SELECT * FROM tool_auth")
    assert row is not None
    assert row["secret_ref"] == "CATFACT_API_KEY"
    assert row["header_name"] == "X-API-Key"
    assert row["scheme"] == ""

    body = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    assert body["hasAuth"] is True
    # header/scheme ไม่ใช่ความลับ — คืนได้เพื่อให้ฟอร์มแสดงค่าปัจจุบัน
    assert body["authHeaderName"] == "X-API-Key"
    assert body["authScheme"] == ""
    # secret_ref (ชื่อ env var) ห้ามรั่วออกทาง response เด็ดขาด
    assert "CATFACT_API_KEY" not in response.text
    listing = client.get("/api/v1/admin/tools")
    assert "CATFACT_API_KEY" not in listing.text


def test_create_tool_without_header_fields_defaults_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(client, authEnvVar="CATFACT_API_KEY")
    assert response.status_code == 201, response.text
    row = _db_one(db, "SELECT * FROM tool_auth")
    assert row["header_name"] == "Authorization"
    assert row["scheme"] == "Bearer"


def test_update_header_fields_preserves_secret_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    """แก้ header/scheme โดยไม่พิมพ์ชื่อ env var ซ้ำ — secret_ref ต้องคงเดิม"""
    client, _, db = _make_client(monkeypatch)
    assert _create_tool(client, authEnvVar="CATFACT_API_KEY").status_code == 201

    edited = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    edited["authHeaderName"] = "X-Api-Key-Custom"
    edited["authScheme"] = "Token"
    # ไม่ส่ง authEnvVar — ต้อง preserve
    response = client.put("/api/v1/admin/tools/cat_fact_tool", json=_payload_for_put(edited))
    assert response.status_code == 200, response.text

    row = _db_one(db, "SELECT * FROM tool_auth")
    assert row["secret_ref"] == "CATFACT_API_KEY"  # คงเดิม
    assert row["header_name"] == "X-Api-Key-Custom"
    assert row["scheme"] == "Token"


def test_update_without_auth_fields_preserves_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    assert _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName="X-API-Key", authScheme=""
    ).status_code == 201

    edited = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    edited["description"] = "คำอธิบายใหม่"
    response = client.put("/api/v1/admin/tools/cat_fact_tool", json=_payload_for_put(edited))
    assert response.status_code == 200, response.text

    row = _db_one(db, "SELECT * FROM tool_auth")
    assert row["secret_ref"] == "CATFACT_API_KEY"
    assert row["header_name"] == "X-API-Key"
    assert row["scheme"] == ""


def test_update_null_auth_removes_whole_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    assert _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName="X-API-Key"
    ).status_code == 201

    edited = client.get("/api/v1/admin/tools/cat_fact_tool").json()
    edited["authEnvVar"] = None
    response = client.put("/api/v1/admin/tools/cat_fact_tool", json=_payload_for_put(edited))
    assert response.status_code == 200, response.text
    assert _db_one(db, "SELECT * FROM tool_auth") is None


def test_create_tool_rejects_invalid_header_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName="X API\nKey"
    )
    assert response.status_code == 400
    assert _db_one(db, "SELECT * FROM tool_auth") is None  # ไม่ persist ของพัง


def test_create_tool_rejects_trailing_newline_header(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName="X-API-Key\n"
    )
    assert response.status_code == 400
    assert _db_one(db, "SELECT * FROM tool_auth") is None


def test_create_tool_rejects_empty_header_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authHeaderName=""
    )
    assert response.status_code == 422
    assert _db_one(db, "SELECT * FROM tool_auth") is None


def test_try_rejects_empty_header_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch, app_env="development")
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "TRY_SECRET",
            "authHeaderName": "",
        },
    )
    assert response.status_code == 422


def test_try_rejects_trailing_newline_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRY_SECRET", "raw-try-key")
    client, _, _ = _make_client(monkeypatch, app_env="development")
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "TRY_SECRET",
            "authScheme": "Bearer\n",
        },
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "invalid_input"


def test_create_tool_rejects_invalid_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db = _make_client(monkeypatch)
    response = _create_tool(
        client, authEnvVar="CATFACT_API_KEY", authScheme="Bearer extra"
    )
    assert response.status_code == 400
    assert _db_one(db, "SELECT * FROM tool_auth") is None


# --------------------------------------------------------------------------
# 5) ปุ่ม "ลองยิงดู" — ใช้ header/scheme ที่ส่งมาจริง + redaction ครบ
# --------------------------------------------------------------------------


def _echo_transport(header_name: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        echoed = request.headers.get(header_name, "")
        # แยก prefix กับค่า secret — ค่า secret ต้องถูก redact แต่ prefix ต้องยังอยู่
        prefix, _, value = echoed.partition(" ")
        return httpx.Response(
            200,
            json={"prefix": prefix, "value": value, "nested": {"value": echoed}},
        )

    return httpx.MockTransport(handler)


def test_try_operation_uses_custom_header_and_redacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRY_SECRET", "raw-try-key")
    client, _, _ = _make_client(
        monkeypatch, app_env="development", transport=_echo_transport("x-api-key")
    )
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "TRY_SECRET",
            "authHeaderName": "X-API-Key",
            "authScheme": "",
        },
    )
    body = response.json()
    assert body["ok"] is True, body
    # executor ต้องส่ง secret ตรง ๆ ใน X-API-Key (ไม่มี prefix) และค่าต้องถูก redact —
    # scheme ว่างเปล่า = ทั้ง header value คือค่า secret เอง จึงถูกแทนด้วย [REDACTED]
    assert body["response"]["body"]["prefix"] == "[REDACTED]"
    # partition แล้วด้านหลังว่าง = ไม่มีช่องว่าง = ไม่มี prefix นำหน้าค่า secret
    assert body["response"]["body"]["value"] == ""
    assert body["response"]["body"]["nested"]["value"] == "[REDACTED]"
    assert "raw-try-key" not in response.text


def test_try_operation_rejects_invalid_header_without_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """header ผิดรูปแบบที่ /tools/try ต้องได้ ok:false (ไม่ใช่ 500)"""
    monkeypatch.setenv("TRY_SECRET", "raw-try-key")
    client, _, _ = _make_client(
        monkeypatch, app_env="development", transport=_echo_transport("x-api-key")
    )
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "TRY_SECRET",
            "authHeaderName": "X API\nKey",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["reason"] == "invalid_input"
    assert "raw-try-key" not in response.text


def test_try_operation_default_scheme_is_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRY_SECRET", "raw-try-key")
    client, _, _ = _make_client(
        monkeypatch, app_env="development", transport=_echo_transport("authorization")
    )
    response = client.post(
        "/api/v1/admin/tools/try",
        json={
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/echo",
            "authEnvVar": "TRY_SECRET",
        },
    )
    body = response.json()
    assert body["ok"] is True, body
    # ค่าเริ่มต้นยังเป็น Authorization: Bearer เหมือนเดิม — ค่า secret ถูก redact
    assert body["response"]["body"]["prefix"] == "Bearer"
    assert body["response"]["body"]["value"] == "[REDACTED]"


# --------------------------------------------------------------------------
# 7) หน้าฟอร์ม admin — ช่อง header/scheme และพฤติกรรมส่ง payload ตาม semantics
# --------------------------------------------------------------------------


def test_admin_form_has_auth_header_fields_with_default_values() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "admin.html").read_text()
    assert 'id="tool-auth-header"' in html
    assert 'id="tool-auth-scheme"' in html
    assert "X-API-Key" in html  # ตัวเลือกยอมฮิตใน datalist

    js = (root / "web" / "admin.js").read_text()
    # ฟอร์มสร้างใหม่/tool ที่ไม่มี auth: ค่าเริ่มต้น Authorization/Bearer
    assert 'views.toolAuthHeader.value = "Authorization"' in js
    assert 'views.toolAuthScheme.value = "Bearer"' in js
    # tool ที่มี auth: แสดงค่าปัจจุบันจาก API (header/scheme ไม่ใช่ความลับ)
    assert "tool.authHeaderName" in js
    # ไม่พิมพ์ชื่อ env var ซ้ำ = ส่งเฉพาะ header/scheme เพื่อ preserve secret_ref
    assert "payload.authHeaderName = authHeader;" in js
    # ปุ่มลองยิงดู: ส่ง header/scheme เฉพาะเมื่อกรอก env var
    assert "authHeaderName: authEnv ? authHeader : null," in js
    assert "authScheme: authEnv ? authScheme : null," in js


# --------------------------------------------------------------------------
# 6) seed_oms_tool — seed tool_auth ให้ OMS แบบ idempotent ไม่ทับของผู้ใช้
# --------------------------------------------------------------------------


def test_seed_oms_tool_does_not_restore_removed_auth(tmp_path: Path) -> None:
    db_path = tmp_path / "test_pea.db"
    db = Database(db_path)
    try:
        db.migrate()
        tool_id = asyncio.run(seed_oms_tool(db, oms_base_url="http://oms.test"))
        assert tool_id is not None
        _db_exec(db, "DELETE FROM tool_auth WHERE tool_id = ?", (tool_id,))
        db.close()
        db = Database(db_path)
        db.migrate()  # migration 003 is already recorded; it must not re-backfill auth
        # Simulate the next startup: existing state, including intentional auth removal,
        # must not be changed by the repeatable bootstrap.
        seeded = asyncio.run(seed_oms_tool(db, oms_base_url="http://oms.test"))
        assert seeded is None  # tool มีอยู่แล้ว — ไม่สร้างใหม่
        row = _db_one(db, "SELECT * FROM tool_auth WHERE tool_id = ?", (tool_id,))
        assert row is None
    finally:
        db.close()


def test_seed_oms_tool_never_overwrites_user_auth(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        tool_id = _db_exec(
            db,
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            (OMS_TOOL_SLUG, "OMS", "", "db"),
        )
        _db_exec(
            db,
            "INSERT INTO tool_auth (tool_id, type, secret_ref, header_name, scheme) "
            "VALUES (?, 'api_key', 'USER_KEY', 'X-Custom-Key', 'Token')",
            (tool_id,),
        )
        asyncio.run(seed_oms_tool(db, oms_base_url="http://oms.test"))
        row = _db_one(db, "SELECT * FROM tool_auth WHERE tool_id = ?", (tool_id,))
        # ผู้ใช้แก้เองไว้ — seed ต้องไม่ทับทั้ง secret_ref และ header/scheme
        assert row["secret_ref"] == "USER_KEY"
        assert row["header_name"] == "X-Custom-Key"
        assert row["scheme"] == "Token"
    finally:
        db.close()


def test_seed_oms_tool_fresh_db_includes_auth(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        tool_id = asyncio.run(
            seed_oms_tool(db, oms_base_url="http://oms.test")
        )
        assert tool_id is not None
        row = _db_one(db, "SELECT * FROM tool_auth WHERE tool_id = ?", (tool_id,))
        assert row is not None
        assert row["secret_ref"] == "OMS_API_KEY"
        assert row["header_name"] == "X-API-Key"
        assert row["scheme"] == ""
    finally:
        db.close()


def test_seed_oms_tool_rolls_back_definition_and_auth_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = Database(tmp_path / "atomic.db")
    try:
        db.migrate()
        monkeypatch.setattr(
            bootstrap_oms,
            "OMS_OPERATIONS",
            (bootstrap_oms.OMS_OPERATIONS[0], bootstrap_oms.OMS_OPERATIONS[0]),
        )
        with pytest.raises(sqlite3.IntegrityError):
            asyncio.run(seed_oms_tool(db, oms_base_url="http://oms.test"))
        assert _db_one(db, "SELECT id FROM tool WHERE slug = ?", (OMS_TOOL_SLUG,)) is None
        assert _db_one(db, "SELECT id FROM tool_auth") is None
        assert _db_one(db, "SELECT id FROM tool_operation") is None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_seeded_oms_dispatch_sends_x_api_key(tmp_path: Path) -> None:
    """เส้นทางจริงปลายทางถึงปลายทาง: seed → load → dispatch ต้องส่ง X-API-Key"""
    db = Database(tmp_path / "test_pea.db")
    try:
        db.migrate()
        await seed_oms_tool(db, oms_base_url="https://oms.example.test")
        bundle = await load_declarative_tools(db, app_env="development", allowlist=("oms.example.test",))
        registry = ToolRegistry(
            [_KnowledgeStub(), *bundle.tools],
            catalogue=bundle.catalogue,
            operation_specs=bundle.operation_specs,
        )
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={
                    "caNumber": "112233445566",
                    "customerFound": True,
                    "network": {"meterId": "M-1", "transformerId": "T-1", "feederId": "F-1"},
                    "activeEvent": None,
                    "recommendedAction": "CREATE_METER_EVENT",
                },
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict("os.environ", {"OMS_API_KEY": "oms-secret-value"}):
            with patch(
                "app.tools.declarative_executor.httpx.AsyncClient",
                return_value=mock_client,
            ):
                result = await registry.execute(
                    ToolCall(
                        call_id=uuid.uuid4(),
                        name=OMS_TOOL_SLUG,
                        action="get_outage_by_ca",
                        input={"caNumber": "112233445566"},
                    ),
                    ToolContext(
                        conversation_id=uuid.uuid4(),
                        trace_id=uuid.uuid4(),
                    ),
                )
        await mock_client.aclose()
        assert result.status is ToolResultStatus.SUCCESS
        assert captured[0].headers["x-api-key"] == "oms-secret-value"
        assert "authorization" not in captured[0].headers
    finally:
        db.close()
