#!/usr/bin/env python3
"""ย้าย ``oms_tool`` จาก Python plugin ขึ้น declarative tool contract — D2.7

หน้า admin ที่ทำเรื่องนี้ให้ผ่าน UI ยังไม่มี (D3.4) สคริปต์นี้จำลองสิ่งที่แบบฟอร์มนั้นจะเขียน
ลง DB โดยตรง เหมือนที่ ``seed_demo_tool.py`` ทำกับ ``cat_fact_tool`` ของ D2.6 — ต่างกันตรงที่
ตัวนี้พิสูจน์ ``write_confirm`` (สองจังหวะ prepare→submit) และ ``clientContext`` (lat/lon)
ผ่าน contract เดียวกัน ไม่ใช่แค่ ``plain_read``

action/schema ของแต่ละ operation มาจาก ``app.plugins.oms.declarative_shape.OMS_OPERATIONS``
(ต้นฉบับเดียวกับที่เทส ``tests/test_agent_orchestration.py`` ฯลฯ ใช้สร้าง ``DeclarativeTool``
ในหน่วยความจำ กันไม่ให้ schema ของ DB จริงกับของเทสดริฟท์ออกจากกัน) — คัดลอกมาจาก
``app/plugins/oms/plugin.yaml`` เดิมทุกประการ (ยังผ่าน allowlist ของ ``validate_schema_subset``
อยู่แล้วเพราะ manifest เดิมก็ตรวจด้วยชุดเดียวกันนี้ตอน D2.2)

``outputSchema`` ปล่อยเป็น ``null`` โดยตั้งใจในทุก operation เพราะ ``app.contracts.OUTPUT_MODELS``
ยังตรวจผลลัพธ์ของ 5 action นี้อย่างเข้มอยู่แล้วที่ชั้น ``ToolRegistry.execute()`` (เหมือนที่
Python plugin เดิมพึ่งชั้นนี้เพียงอย่างเดียวมาตลอด — ดู ``app/agent/tool_shape.py:from_plugin``
comment) การเขียน JSON Schema ซ้อนลึกมาประกบกับของเดิมจึงไม่จำเป็นและเพิ่มความเสี่ยงเปล่า ๆ
ที่จะปฏิเสธ response ที่ถูกต้องอยู่แล้ว

``mode: prepare`` ทั้งสอง operation ไม่มี ``httpMethod``/``urlTemplate`` (เป็น null) ตาม
carve-out ที่เติมใน CONTRACTS-V2.md §1.3/§3.5 ของ D2.7 — prepare ไม่มี side effect จริง
(``DeclarativeTool`` เก็บ payload รอ submit ในหน่วยความจำแทน)

ไม่สร้างแถว ``tool_auth``: ค่าเริ่มต้นของ ``OMS_API_KEY`` ว่างเปล่า (ดู ``.env.example``) และ
``OmsTool`` เดิมก็ไม่ส่ง header ใด ๆ เมื่อไม่มี key เช่นกัน — ถ้าภายหลังต้องใช้ API key จริง
ต้องเติมคอลัมน์ header/scheme ให้ ``tool_auth`` ก่อน (OMS ใช้ ``X-API-Key`` ไม่ใช่
``Authorization: Bearer`` ที่ ``DeclarativeToolAuth`` ตั้งเป็นค่าเริ่มต้น) — ไม่ทำใน 3 วันนี้
เพราะ demo ไม่ได้ตั้ง key จริง

ใช้งาน:

    .venv/bin/python scripts/seed_oms_tool.py           # เพิ่ม (ข้ามถ้ามีอยู่แล้ว)
    .venv/bin/python scripts/seed_oms_tool.py --replace # ลบของเดิมแล้วสร้างใหม่
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.plugins.oms.declarative_shape import OMS_OPERATIONS  # noqa: E402
from app.tools.schema_subset import validate_schema_subset  # noqa: E402

_SLUG = "oms_tool"


async def seed(db: Database, *, oms_base_url: str, replace: bool) -> None:
    existing = await db.fetch_one("SELECT id FROM tool WHERE slug = ?", (_SLUG,))
    if existing is not None:
        if not replace:
            print(f"'{_SLUG}' มีอยู่แล้ว (id={existing['id']}) — ไม่ทำอะไร (ใช้ --replace เพื่อสร้างใหม่)")
            return
        await db.execute("DELETE FROM tool WHERE id = ?", (existing["id"],))  # CASCADE ลบ operation ด้วย

    base = oms_base_url.rstrip("/")
    tool_id = await db.execute(
        "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
        (
            _SLUG,
            "OMS Outage",
            "ตรวจเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลัก หรือเตรียมแจ้งเหตุเมื่อทราบหรือไม่ทราบหมายเลขผู้ใช้ไฟ",
            "db",
        ),
    )
    for operation in OMS_OPERATIONS:
        validate_schema_subset(operation.input_schema)
        url_template = f"{base}/{operation.path}" if operation.path is not None else None
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, "
            "submit_action, http_method, url_template, limits, client_context) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                operation.action,
                operation.policy,
                json.dumps(operation.input_schema, ensure_ascii=False),
                # D2.7: outputSchema ปล่อยว่างไว้เสมอ — app.contracts.OUTPUT_MODELS ตรวจผลลัพธ์
                # ของ 5 action นี้อย่างเข้มอยู่แล้วที่ชั้น ToolRegistry.execute() (ดู docstring บนสุด)
                "null",
                operation.exposure,
                operation.mode,
                operation.submit_action,
                operation.http_method,
                url_template,
                None,
                json.dumps(operation.client_context, ensure_ascii=False) if operation.client_context else None,
            ),
        )
    print(f"ย้าย '{_SLUG}' ขึ้น declarative tool contract แล้ว (tool_id={tool_id}, base_url={base})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="ลบ tool เดิมแล้วสร้างใหม่ถ้ามีอยู่แล้ว")
    args = parser.parse_args()

    settings = load_settings()
    db = Database()
    db.migrate()
    try:
        asyncio.run(seed(db, oms_base_url=settings.oms_base_url, replace=args.replace))
    finally:
        db.close()


if __name__ == "__main__":
    main()
