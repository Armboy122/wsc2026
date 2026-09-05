"""D2.3: registry รูปเดียวสองชั้น (ARCHITECTURE-V2.md §3.4)

พิสูจน์ว่า declarative tool (แถวใน SQLite) และ Python plugin ที่โหลดผ่าน manifest
แปลงเข้าหา ``ToolShape``/``ToolOperationShape`` เดียวกันได้ และ ``source`` ไม่มีผลต่อ
ค่าที่ใช้ตัดสิน dispatch จริง (policy/mode/exposure/limits/clientContext)

ยังไม่ทดสอบการ dispatch จริง — ``ToolRegistry`` ยังไม่ผูกกับ shape นี้ (รอ D2.4 executor
กลางและ D2.5 ที่เลิกอ้าง ToolName/ToolAction เป็น string)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.tool_shape import (
    ToolOperationShape,
    from_db_row,
    from_plugin,
    load_db_tool_shapes,
    merge_tool_shapes,
)
from app.contracts import ToolName
from app.core.config import load_settings
from app.db import Database
from app.plugins import load_plugins


def _oms_plugin():
    plugins = load_plugins(load_settings())
    return next(plugin for plugin in plugins if plugin.manifest.metadata.id is ToolName.OMS)


def test_from_plugin_produces_a_code_sourced_shape_matching_the_real_manifest() -> None:
    plugin = _oms_plugin()

    shape = from_plugin(plugin)

    assert shape.slug == "oms_tool"
    assert shape.source == "code"
    assert shape.executor is plugin.tool
    read_op = shape.operation("get_outage_by_ca")
    assert read_op is not None
    assert read_op.policy == "plain_read"
    assert read_op.mode == "read"
    assert read_op.exposure == "llm"
    assert read_op.input_schema == {
        "type": "object",
        "properties": {
            "caNumber": {"type": "string", "description": "หมายเลขผู้ใช้ไฟ 12 หลัก"},
        },
        "required": ["caNumber"],
        "additionalProperties": False,
    }
    # submit ต้อง internal เสมอ — ยังเป็นข้อบังคับเดียวกันไม่ว่า shape จะมาจากชั้นไหน
    submit_op = shape.operation("submit_outage_with_ca")
    assert submit_op is not None
    assert submit_op.exposure == "internal"


async def test_from_db_row_produces_a_db_sourced_shape(tmp_path: Path) -> None:
    db = Database(tmp_path / "pea.db")
    db.migrate()
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("billing_tool", "Billing", "จ่ายบิลออนไลน์", "db"),
        )
        input_schema = {
            "type": "object",
            "properties": {"accountRef": {"type": "string"}},
            "required": ["accountRef"],
            "additionalProperties": False,
        }
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tool_id, "get_balance", "plain_read", json.dumps(input_schema), "{}", "llm", "read"),
        )
        tool_row = await db.fetch_one("SELECT * FROM tool WHERE id = ?", (tool_id,))
        operation_rows = await db.fetch_all(
            "SELECT * FROM tool_operation WHERE tool_id = ?", (tool_id,)
        )

        shape = from_db_row(tool_row, list(operation_rows))

        assert shape.slug == "billing_tool"
        assert shape.source == "db"
        assert shape.executor is None
        op = shape.operation("get_balance")
        assert op is not None
        assert op.policy == "plain_read"
        assert op.mode == "read"
        assert op.exposure == "llm"
        assert op.input_schema == input_schema
    finally:
        db.close()


def test_db_and_plugin_operations_are_the_same_shape_when_data_matches() -> None:
    """ค่าที่มีผลต่อ dispatch ต้องเทียบเท่ากันได้ตรง ๆ ไม่ว่า operation จะมาจากชั้นไหน"""
    plugin_op = from_plugin(_oms_plugin()).operation("get_outage_by_ca")
    assert plugin_op is not None

    db_op = ToolOperationShape(
        action=plugin_op.action,
        description="",  # tool_operation ของ D2.1 ไม่มีคอลัมน์ description ต่อ operation
        input_schema=plugin_op.input_schema,
        output_schema=None,
        exposure=plugin_op.exposure,
        mode=plugin_op.mode,
        submit_action=plugin_op.submit_action,
        policy=plugin_op.policy,
        limits=plugin_op.limits,
        client_context=plugin_op.client_context,
    )

    assert db_op.action == plugin_op.action
    assert db_op.policy == plugin_op.policy
    assert db_op.mode == plugin_op.mode
    assert db_op.exposure == plugin_op.exposure
    assert db_op.input_schema == plugin_op.input_schema
    assert db_op.limits == plugin_op.limits
    assert db_op.client_context == plugin_op.client_context


def test_merge_tool_shapes_combines_code_and_db_layers_into_one_catalogue() -> None:
    code_shape = from_plugin(_oms_plugin())
    db_shape = from_db_row(
        {"slug": "billing_tool", "display_name": "Billing", "description": ""},
        [],
    )

    merged = merge_tool_shapes((code_shape,), (db_shape,))

    slugs = {shape.slug: shape.source for shape in merged}
    assert slugs == {"oms_tool": "code", "billing_tool": "db"}


def test_merge_tool_shapes_rejects_duplicate_slug_across_layers() -> None:
    code_shape = from_plugin(_oms_plugin())
    conflicting_db_shape = from_db_row(
        {"slug": "oms_tool", "display_name": "Fake OMS", "description": ""},
        [],
    )

    with pytest.raises(ValueError, match="ลงทะเบียนเครื่องมือซ้ำ"):
        merge_tool_shapes((code_shape,), (conflicting_db_shape,))


async def test_load_db_tool_shapes_skips_disabled_tools(tmp_path: Path) -> None:
    db = Database(tmp_path / "pea.db")
    db.migrate()
    try:
        await db.execute(
            "INSERT INTO tool (slug, display_name, source, enabled) VALUES (?, ?, ?, ?)",
            ("active_tool", "Active", "db", 1),
        )
        await db.execute(
            "INSERT INTO tool (slug, display_name, source, enabled) VALUES (?, ?, ?, ?)",
            ("disabled_tool", "Disabled", "db", 0),
        )

        shapes = await load_db_tool_shapes(db)

        assert [shape.slug for shape in shapes] == ["active_tool"]
    finally:
        db.close()


async def test_load_db_tool_shapes_ignores_rows_mirrored_from_code(tmp_path: Path) -> None:
    """tool.source มีไว้ให้ admin/health อ่าน — ต้องไม่ทำให้ loader ลองสร้าง shape จาก
    แถวที่จริง ๆ เป็นปลั๊กอิน Python (ยังไม่มีอะไร mirror แบบนี้ตอนนี้ แต่ป้องกันไว้ก่อน)"""
    db = Database(tmp_path / "pea.db")
    db.migrate()
    try:
        await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("oms_tool", "OMS (mirrored)", "code"),
        )
        await db.execute(
            "INSERT INTO tool (slug, display_name, source) VALUES (?, ?, ?)",
            ("billing_tool", "Billing", "db"),
        )

        shapes = await load_db_tool_shapes(db)

        assert [shape.slug for shape in shapes] == ["billing_tool"]
    finally:
        db.close()
