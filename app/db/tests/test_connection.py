"""D2.1: SQLite 5 ตาราง + migration + WAL + connection เดียวผ่าน asyncio.to_thread

ทดสอบเฉพาะจุดที่ความล้มเหลวมีราคาแพง: migration ต้องสร้างตารางครบและรันซ้ำได้ปลอดภัย
constraint ที่ป้องกันข้อมูลผิดต้องยังทำงาน (ไม่ใช่แค่ "ตารางมีอยู่")
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import Database

_EXPECTED_TABLES = {
    "tool",
    "tool_operation",
    "tool_auth",
    "prompt",
    "domain_allowlist",
    "schema_version",
}


def _open(tmp_path: Path) -> Database:
    db = Database(tmp_path / "pea.db")
    db.migrate()
    return db


def test_migrate_creates_exactly_the_five_tables_plus_schema_version(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        rows = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert {row[0] for row in rows} == _EXPECTED_TABLES
    finally:
        db.close()


def test_migrate_is_idempotent_and_records_schema_version_once(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        db.migrate()
        db.migrate()
        versions = db._conn.execute("SELECT version FROM schema_version").fetchall()
        assert [row[0] for row in versions] == [1, 2, 3]
    finally:
        db.close()


def test_migration_rolls_back_prior_statements_when_a_later_statement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_broken.sql").write_text(
        "CREATE TABLE first (id INTEGER);\nCREATE TABLE first (id INTEGER);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.db.connection._MIGRATIONS_DIR", migrations_dir)
    db = Database(tmp_path / "rollback.db")
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.migrate()
        assert db._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'first'"
        ).fetchone() is None
        assert db._conn.execute("SELECT version FROM schema_version").fetchall() == []
    finally:
        db.close()


def test_wal_mode_is_enabled(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        db.close()


async def test_insert_and_fetch_tool_row_roundtrip(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("billing_tool", "Billing", "จ่ายบิล", "db"),
        )
        row = await db.fetch_one("SELECT * FROM tool WHERE id = ?", (tool_id,))
        assert row is not None
        assert row["slug"] == "billing_tool"
        assert row["enabled"] == 1
        assert row["source"] == "db"
    finally:
        db.close()


async def test_tool_slug_must_be_unique(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("billing_tool", "Billing", "db"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
                ("billing_tool", "Billing 2", "db"),
            )
    finally:
        db.close()


async def test_tool_operation_action_is_unique_per_tool(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("billing_tool", "Billing", "db"),
        )
        operation_sql = (
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        await db.execute(
            operation_sql,
            (tool_id, "get_balance", "plain_read", "{}", "{}", "llm", "read"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                operation_sql,
                (tool_id, "get_balance", "plain_read", "{}", "{}", "llm", "read"),
            )
    finally:
        db.close()


async def test_tool_operation_rejects_unknown_policy(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("billing_tool", "Billing", "db"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO tool_operation "
                "(tool_id, action, policy, input_schema, output_schema, exposure, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tool_id, "get_balance", "not_a_real_policy", "{}", "{}", "llm", "read"),
            )
    finally:
        db.close()


async def test_domain_allowlist_domain_is_unique(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        await db.execute(
            "INSERT INTO domain_allowlist (domain) VALUES (?)", ("api.pea.co.th",)
        )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO domain_allowlist (domain) VALUES (?)", ("api.pea.co.th",)
            )
    finally:
        db.close()


async def test_deleting_tool_cascades_to_its_operations(tmp_path: Path) -> None:
    """soft delete (enabled=false) คือทางหลัก แต่ FK ต้อง cascade ถ้าใครลบแถวจริง ๆ"""
    db = _open(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("billing_tool", "Billing", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tool_id, "get_balance", "plain_read", "{}", "{}", "llm", "read"),
        )
        await db.execute("DELETE FROM tool WHERE id = ?", (tool_id,))
        rows = await db.fetch_all("SELECT * FROM tool_operation WHERE tool_id = ?", (tool_id,))
        assert rows == []
    finally:
        db.close()


async def test_prompt_upsert_by_key(tmp_path: Path) -> None:
    db = _open(tmp_path)
    try:
        await db.execute(
            "INSERT INTO prompt (key, content) VALUES (?, ?)",
            ("system_prompt", "v1 content"),
        )
        await db.execute(
            "UPDATE prompt SET content = ? WHERE key = ?", ("v2 content", "system_prompt")
        )
        row = await db.fetch_one("SELECT content FROM prompt WHERE key = ?", ("system_prompt",))
        assert row["content"] == "v2 content"
    finally:
        db.close()


async def test_legacy_d21_migrations_to_003_enable_declarative_http_tool(tmp_path: Path) -> None:
    """จำลอง DB schema D2.1 เดิม (schema_version=1 ไม่มี http_method/url_template)
    แล้ว migrate จนใช้ declarative HTTP tool ได้
    """
    import json
    import uuid
    import httpx
    from app.agent.declarative_tools import load_declarative_tools
    from app.agent.operation_policy import OperationPolicy
    from app.contracts import ToolCall, ToolResultStatus
    from app.agent.registry import ToolContext

    db_path = tmp_path / "legacy_d21.db"
    conn = sqlite3.connect(str(db_path))
    # สร้าง schema D2.1 ดิบ ๆ
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')));
        INSERT INTO schema_version (version) VALUES (1);

        CREATE TABLE tool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            source TEXT NOT NULL CHECK (source IN ('db', 'code')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE tool_operation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL REFERENCES tool (id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            policy TEXT NOT NULL CHECK (
                policy IN ('grounded_answer', 'write_confirm', 'guided_flow', 'plain_read')
            ),
            input_schema TEXT NOT NULL,
            output_schema TEXT NOT NULL,
            exposure TEXT NOT NULL CHECK (exposure IN ('llm', 'internal')),
            mode TEXT NOT NULL CHECK (mode IN ('read', 'prepare', 'submit')),
            submit_action TEXT,
            limits TEXT,
            client_context TEXT,
            UNIQUE (tool_id, action)
        );
        CREATE TABLE tool_auth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL REFERENCES tool (id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK (type IN ('api_key', 'oauth2')),
            secret_ref TEXT NOT NULL
        );
        CREATE TABLE prompt (
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE domain_allowlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
        );
        """
    )
    # ตรวจว่า tool_operation เดิมไม่มี http_method และ url_template
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tool_operation)").fetchall()}
    assert "http_method" not in cols
    assert "url_template" not in cols
    conn.close()

    # เปิดผ่าน Database class แล้วสั่ง migrate
    db = Database(db_path)
    try:
        db.migrate()
        # schema_version ต้องอัปเดตถึง migration 003
        versions = [row[0] for row in db._conn.execute("SELECT version FROM schema_version").fetchall()]
        assert versions == [1, 2, 3]

        cols_after = {row[1] for row in db._conn.execute("PRAGMA table_info(tool_operation)").fetchall()}
        assert "http_method" in cols_after
        assert "url_template" in cols_after

        # ใส่ tool และ operation ที่ใช้ HTTP
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("sample_http_tool", "Sample Tool", "คำอธิบาย", "db"),
        )
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        }
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "fetch",
                "plain_read",
                json.dumps(schema),
                "{}",
                "llm",
                "read",
                "GET",
                "https://api.example.com/data",
            ),
        )

        handler = lambda request: httpx.Response(200, json={"ok": True})
        bundle = await load_declarative_tools(
            db, app_env="development", allowlist=(), transport=httpx.MockTransport(handler)
        )
        assert len(bundle.tools) == 1
        tool = bundle.tools[0]
        call = ToolCall(call_id=uuid.uuid4(), name="sample_http_tool", action="fetch", input={})
        result = await tool.execute(call, ToolContext(uuid.uuid4(), uuid.uuid4()))
        assert result.status is ToolResultStatus.SUCCESS
        assert result.data == {"ok": True}
    finally:
        db.close()
