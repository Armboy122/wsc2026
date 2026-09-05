#!/usr/bin/env python3
"""ใส่ declarative tool ตัวอย่างหนึ่งตัวลง SQLite — ตัวพิสูจน์ contract ของ D2.6

หน้า admin ที่ทำเรื่องนี้ให้ผ่าน UI ยังไม่มี (D3.4) สคริปต์นี้จำลองสิ่งที่แบบฟอร์มนั้นจะเขียน
ลง DB โดยตรง เพื่อพิสูจน์ว่า path เต็ม (DB → ToolShape → DeclarativeTool → executor →
agent เรียกได้) ใช้งานได้จริงก่อนมีหน้าเว็บ

tool ตัวอย่าง: ``cat_fact_tool`` ยิง GET ไปยัง https://catfact.ninja/fact ซึ่งเป็นบริการ
สาธารณะที่ตอบ JSON จริง ไม่ต้องมี API key — เลือกเพราะปลอดภัย เสถียร และพิสูจน์กลไก
แทนค่า query param (``maxLength``) ได้โดยไม่ต้องมี path parameter

ใช้งาน:

    .venv/bin/python scripts/seed_demo_tool.py           # เพิ่ม (ข้ามถ้ามีอยู่แล้ว)
    .venv/bin/python scripts/seed_demo_tool.py --replace # ลบของเดิมแล้วสร้างใหม่
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Database  # noqa: E402 - ต้องตั้ง sys.path ให้ import แพ็กเกจ app ได้ก่อน

_SLUG = "cat_fact_tool"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # ชื่อ field ต้องตรงกับชื่อ query parameter จริงของ catfact.ninja เป๊ะ (max_length ไม่ใช่
        # maxLength) เพราะกลไกแทนค่าเอา field ที่เหลือไปเป็น query string ตรง ๆ ไม่แปลงชื่อให้
        "max_length": {
            "type": "integer",
            "description": "ความยาวสูงสุดของข้อเท็จจริงที่ต้องการ (ตัวอักษร) ไม่ระบุ = ไม่จำกัด",
        },
    },
    "required": [],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "fact": {"type": "string"},
        "length": {"type": "integer"},
    },
    "required": ["fact"],
    "additionalProperties": False,
}


async def seed(db: Database, *, replace: bool) -> None:
    existing = await db.fetch_one("SELECT id FROM tool WHERE slug = ?", (_SLUG,))
    if existing is not None:
        if not replace:
            print(f"'{_SLUG}' มีอยู่แล้ว (id={existing['id']}) — ไม่ทำอะไร (ใช้ --replace เพื่อสร้างใหม่)")
            return
        await db.execute("DELETE FROM tool WHERE id = ?", (existing["id"],))  # CASCADE ลบ operation ด้วย

    tool_id = await db.execute(
        "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
        (_SLUG, "สุ่มข้อเท็จจริงเกี่ยวกับแมว", "ดึงข้อเท็จจริงเกี่ยวกับแมวแบบสุ่มจากบริการสาธารณะ catfact.ninja", "db"),
    )
    await db.execute(
        "INSERT INTO tool_operation "
        "(tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tool_id,
            "get_random_fact",
            "plain_read",
            json.dumps(_INPUT_SCHEMA, ensure_ascii=False),
            json.dumps(_OUTPUT_SCHEMA, ensure_ascii=False),
            "llm",
            "read",
            "GET",
            "https://catfact.ninja/fact",
        ),
    )
    print(f"สร้าง '{_SLUG}' แล้ว (tool_id={tool_id}) — ลองยิงจริงด้วย ./scripts/evaluate หรือแชตถาม 'สุ่มข้อเท็จจริงเกี่ยวกับแมวให้หน่อย'")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="ลบ tool เดิมแล้วสร้างใหม่ถ้ามีอยู่แล้ว")
    args = parser.parse_args()

    db = Database()
    db.migrate()
    try:
        asyncio.run(seed(db, replace=args.replace))
    finally:
        db.close()


if __name__ == "__main__":
    main()
