"""ทดสอบ persist สถานะเปิด/ปิดของ code tool ลงตาราง tool (แถว source='code') — P4

ความเสี่ยงที่เทสนี้กันไว้:

- สถานะเปิด/ปิดของ code tool ต้องอยู่รอดข้าม restart (boot อ่านกลับจาก DB ได้)
- แถว source='code' ต้องไม่ปนกับ declarative tool (source='db') ที่ list/โหลดอยู่เดิม
- ใช้คอลัมน์ enabled + source ที่ตารางมีอยู่แล้ว จึงไม่ต้อง migrate

ทดสอบที่ repository seam (สัญญาของชั้น DB) ไม่ใช่ SQL ภายใน
"""

from __future__ import annotations

import asyncio

from app.db import Database
from app.db import tool_repository


def _db() -> Database:
    db = Database(":memory:")
    db.migrate()
    return db


def test_disabled_code_tool_slugs_roundtrip() -> None:
    db = _db()
    try:
        # ค่าเริ่มต้น: ยังไม่มี code tool ถูกปิด
        assert asyncio.run(tool_repository.disabled_code_tool_slugs(db)) == ()

        asyncio.run(tool_repository.set_code_tool_enabled(db, "voc_tool", False))
        assert asyncio.run(tool_repository.disabled_code_tool_slugs(db)) == ("voc_tool",)

        # เปิดกลับ — สถานะอัปเดตที่แถวเดิม ไม่เพิ่มแถวซ้ำ
        asyncio.run(tool_repository.set_code_tool_enabled(db, "voc_tool", True))
        assert asyncio.run(tool_repository.disabled_code_tool_slugs(db)) == ()

        row = asyncio.run(db.fetch_one("SELECT * FROM tool WHERE slug = 'voc_tool'"))
        assert row is not None
        assert row["source"] == "code"
        assert row["enabled"] == 1
    finally:
        db.close()


def test_code_tool_row_does_not_leak_into_declarative_paths() -> None:
    """แถว source='code' ต้องไม่ปรากฏในรายการ declarative tool ของ admin/registry"""
    db = _db()
    try:
        asyncio.run(tool_repository.set_code_tool_enabled(db, "voc_tool", False))

        assert asyncio.run(tool_repository.list_tool_definitions(db)) == []
        assert asyncio.run(tool_repository.get_tool_definition(db, "voc_tool")) is None
        assert asyncio.run(tool_repository.set_tool_enabled(db, "voc_tool", True)) is False
    finally:
        db.close()


def test_disabling_multiple_code_tools_keeps_all_rows() -> None:
    db = _db()
    try:
        asyncio.run(tool_repository.set_code_tool_enabled(db, "voc_tool", False))
        asyncio.run(tool_repository.set_code_tool_enabled(db, "other_tool", False))

        assert asyncio.run(tool_repository.disabled_code_tool_slugs(db)) == (
            "other_tool",
            "voc_tool",
        )
    finally:
        db.close()
