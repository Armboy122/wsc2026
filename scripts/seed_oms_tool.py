#!/usr/bin/env python3
"""ย้าย ``oms_tool`` จาก Python plugin ขึ้น declarative tool contract — D2.7

หน้า admin ที่ทำเรื่องนี้ให้ผ่าน UI ยังไม่มี (D3.4) สคริปต์นี้จำลองสิ่งที่แบบฟอร์มนั้นจะเขียน
ลง DB โดยตรง เหมือนที่ ``seed_demo_tool.py`` ทำกับ ``cat_fact_tool`` ของ D2.6 — ต่างกันตรงที่
ตัวนี้พิสูจน์ ``write_confirm`` (สองจังหวะ prepare→submit) และ ``clientContext`` (lat/lon)
ผ่าน contract เดียวกัน ไม่ใช่แค่ ``plain_read``

ตรรกะการ seed อยู่ที่ ``app.db.bootstrap_oms.seed_oms_tool`` (ต้นฉบับเดียวกับ bootstrap
ตอน startup ของ app — ปิดช่องให้ definition สองที่ดริฟท์ออกจากกัน) สคริปต์นี้เหลือหน้าที่
parse argument กับพิมพ์ผลเท่านั้น

ใช้งาน:

    .venv/bin/python scripts/seed_oms_tool.py           # เพิ่ม (ข้ามถ้ามีอยู่แล้ว)
    .venv/bin/python scripts/seed_oms_tool.py --replace # ลบของเดิมแล้วสร้างใหม่
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.db.bootstrap_oms import OMS_TOOL_SLUG, seed_oms_tool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="ลบ tool เดิมแล้วสร้างใหม่ถ้ามีอยู่แล้ว")
    args = parser.parse_args()

    settings = load_settings()
    db = Database()
    db.migrate()
    try:
        tool_id = asyncio.run(
            seed_oms_tool(db, oms_base_url=settings.oms_base_url, replace=args.replace)
        )
        if tool_id is None:
            print(f"'{OMS_TOOL_SLUG}' มีอยู่แล้ว — ไม่ทำอะไร (ใช้ --replace เพื่อสร้างใหม่)")
        else:
            print(
                f"ย้าย '{OMS_TOOL_SLUG}' ขึ้น declarative tool contract แล้ว "
                f"(tool_id={tool_id}, base_url={settings.oms_base_url})"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
