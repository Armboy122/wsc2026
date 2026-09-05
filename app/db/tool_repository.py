"""repository ของตาราง tool/tool_operation/tool_auth — D3.3/D3.4

ชั้นเดียวที่แตะตาราง tool config ทั้งสาม เพื่อไม่ให้ SQL กระจัดกระจายใน route handler
ทุกฟังก์ชันรับ/คืนข้อมูลรูปเดียวกับ ``ToolShape`` (plain dict รูปแบบ camelCase ตาม
CONTRACTS-V2 §กฎทั่วไป 1) โดยไม่ validate นโยบายใด ๆ — validation อยู่ที่
``app.core.tool_admin`` (จุดเดียวกับที่ loader ใช้)

``description`` ต่อ operation ยังไม่มีคอลัมน์ใน DB (ตัดตาม D2.1) — คืนค่าว่างเสมอ
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.agent.tool_shape import ToolShape
from app.db import Database


async def list_tool_definitions(db: Database) -> list[dict[str, Any]]:
    """คืน tool ทุกแถว (รวมที่ enabled=0) พร้อม operation ครบ — สำหรับหน้ารายการ (D3.3)"""
    tool_rows = await db.fetch_all("SELECT * FROM tool WHERE source = 'db' ORDER BY slug")
    definitions: list[dict[str, Any]] = []
    for tool_row in tool_rows:
        operation_rows = await db.fetch_all(
            "SELECT * FROM tool_operation WHERE tool_id = ? ORDER BY action",
            (tool_row["id"],),
        )
        auth_row = await db.fetch_one(
            "SELECT 1 FROM tool_auth WHERE tool_id = ? LIMIT 1", (tool_row["id"],)
        )
        definitions.append(
            _definition_from_rows(tool_row, operation_rows, has_auth=auth_row is not None)
        )
    return definitions


async def get_tool_definition(db: Database, slug: str) -> dict[str, Any] | None:
    """คืน definition ของ tool หนึ่งตัว หรือ ``None`` เมื่อไม่มี (เฉพาะ source: db)"""
    tool_row = await db.fetch_one(
        "SELECT * FROM tool WHERE source = 'db' AND slug = ?", (slug,)
    )
    if tool_row is None:
        return None
    operation_rows = await db.fetch_all(
        "SELECT * FROM tool_operation WHERE tool_id = ? ORDER BY action",
        (tool_row["id"],),
    )
    auth_row = await db.fetch_one(
        "SELECT 1 FROM tool_auth WHERE tool_id = ? LIMIT 1", (tool_row["id"],)
    )
    return _definition_from_rows(tool_row, operation_rows, has_auth=auth_row is not None)


async def save_tool(
    db: Database,
    shape: ToolShape,
    *,
    enabled: bool,
    auth_env_var: str | None,
    preserve_auth: bool = False,
) -> None:
    """เขียน definition หนึ่งชุดลง DB ในธุรกรรมเดียว (upsert ตาม slug)

    - มี slug นี้อยู่แล้ว = แทนที่ operation และ auth ตาม ``preserve_auth``
    - ยังไม่มี = สร้างใหม่ (omit/null = ไม่มี auth)
    - ``auth_env_var`` เป็น *ชื่อ* environment variable เท่านั้น (tool_auth.secret_ref,
      CONTRACTS-V2 §10.2) — ค่าจริงของ secret ไม่เคยผ่านฟังก์ชันนี้
    """
    operations_payload = [
        (
            op.action,
            op.policy,
            json.dumps(op.input_schema, ensure_ascii=False),
            json.dumps(op.output_schema) if op.output_schema is not None else "null",
            op.exposure,
            op.mode,
            op.submit_action,
            json.dumps(op.limits, ensure_ascii=False) if op.limits is not None else None,
            json.dumps(op.client_context, ensure_ascii=False)
            if op.client_context is not None
            else None,
            op.http_method,
            op.url_template,
        )
        for op in shape.operations
    ]

    def _write(conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT id FROM tool WHERE slug = ?", (shape.slug,)).fetchone()
        if existing is None:
            cursor = conn.execute(
                "INSERT INTO tool (slug, display_name, description, enabled, source) "
                "VALUES (?, ?, ?, ?, 'db')",
                (shape.slug, shape.display_name, shape.description, int(enabled)),
            )
            tool_id = cursor.lastrowid
            assert tool_id is not None
        else:
            tool_id = existing["id"]
            conn.execute(
                "UPDATE tool SET display_name = ?, description = ?, enabled = ? WHERE id = ?",
                (shape.display_name, shape.description, int(enabled), tool_id),
            )
            conn.execute("DELETE FROM tool_operation WHERE tool_id = ?", (tool_id,))
            if not preserve_auth:
                conn.execute("DELETE FROM tool_auth WHERE tool_id = ?", (tool_id,))
        conn.executemany(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, "
            "submit_action, limits, client_context, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(tool_id, *payload) for payload in operations_payload],
        )
        if auth_env_var:
            conn.execute(
                "INSERT INTO tool_auth (tool_id, type, secret_ref) VALUES (?, 'api_key', ?)",
                (tool_id, auth_env_var),
            )

    await db.run_in_transaction(_write)


async def set_tool_enabled(db: Database, slug: str, enabled: bool) -> bool:
    """เปิด/ปิด tool (soft delete ตาม ARCHITECTURE-V2.md §8.1) — คืน False เมื่อไม่พบ slug"""
    cursor_row = await db.fetch_one(
        "SELECT id FROM tool WHERE slug = ? AND source = 'db'", (slug,)
    )
    if cursor_row is None:
        return False
    await db.execute("UPDATE tool SET enabled = ? WHERE id = ?", (int(enabled), cursor_row["id"]))
    return True


def _definition_from_rows(
    tool_row: sqlite3.Row, operation_rows: list[sqlite3.Row], *, has_auth: bool
) -> dict[str, Any]:
    return {
        "hasAuth": has_auth,
        "slug": tool_row["slug"],
        "displayName": tool_row["display_name"],
        "description": tool_row["description"] or "",
        "enabled": bool(tool_row["enabled"]),
        "source": tool_row["source"],
        "operations": [
            {
                "action": row["action"],
                "description": "",
                "policy": row["policy"],
                "exposure": row["exposure"],
                "mode": row["mode"],
                "submitAction": row["submit_action"],
                "httpMethod": row["http_method"],
                "urlTemplate": row["url_template"],
                "inputSchema": json.loads(row["input_schema"]),
                "outputSchema": json.loads(row["output_schema"])
                if row["output_schema"] and row["output_schema"] != "null"
                else None,
                "limits": json.loads(row["limits"]) if row["limits"] else None,
                "clientContext": json.loads(row["client_context"])
                if row["client_context"]
                else None,
            }
            for row in operation_rows
        ],
    }
