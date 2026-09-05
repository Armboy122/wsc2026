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
        assert [row[0] for row in versions] == [1]
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
