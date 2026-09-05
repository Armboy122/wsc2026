"""bootstrap ที่ทำให้ ``oms_tool`` มีอยู่ใน declarative tool catalogue เสมอ — ปิด P1 ของ D2

``data/pea.db`` ถูก ignore และ plugin ของ OMS ถูกปิดแบบ soft delete แล้ว (D2.7) แปลว่า
clone/run ใหม่หรือ DB ว่างจะไม่มี OMS เลย เพราะเดิมสร้างได้เฉพาะจาก
``scripts/seed_oms_tool.py`` ด้วยมือ ฟังก์ชันเดียวในโมดูลนี้เป็น bootstrap ที่ repeatable
และ idempotent:

- มี ``oms_tool`` อยู่แล้ว = **ไม่แตะอะไรเลย** (ห้าม overwrite definition หรือลบ/replace
  config ของผู้ใช้) คืน ``None``
- ยังไม่มี = seed definition จาก ``app.plugins.oms.declarative_shape.OMS_OPERATIONS``
  (ต้นฉบับเดียวกับที่สคริปต์และเทสใช้) ด้วย base URL จาก ``OMS_BASE_URL``

``replace=True`` มีไว้เฉพาะสำหรับสคริปต์ seed ที่รู้ตัวว่ากำลัง migrate — bootstrap ของ
app ต้องเรียกด้วยค่าเริ่มต้น (``replace=False``) เสมอ
"""

from __future__ import annotations

import json
import logging

from app.db import Database
from app.plugins.oms.declarative_shape import OMS_OPERATIONS
from app.tools.schema_subset import validate_schema_subset

logger = logging.getLogger(__name__)

OMS_TOOL_SLUG = "oms_tool"


async def seed_oms_tool(
    db: Database,
    *,
    oms_base_url: str,
    replace: bool = False,
) -> int | None:
    """seed ``oms_tool`` ลง DB ถ้ายังไม่มี — idempotent คืน ``tool_id`` เมื่อสร้างใหม่

    validate schema ของทุก operation **ก่อน** insert แถวแรก เพื่อไม่ให้เหลือ tool ครึ่ง ๆ
    กลาง ๆ หาก definition ผิด allowlist (fail closed แบบไม่ทิ้งขยะใน DB)
    """
    existing = await db.fetch_one("SELECT id FROM tool WHERE slug = ?", (OMS_TOOL_SLUG,))
    if existing is not None:
        if not replace:
            return None
        await db.execute("DELETE FROM tool WHERE id = ?", (existing["id"],))  # CASCADE ลบ operation ด้วย

    base = oms_base_url.rstrip("/")
    for operation in OMS_OPERATIONS:
        validate_schema_subset(operation.input_schema)

    tool_id = await db.execute(
        "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
        (
            OMS_TOOL_SLUG,
            "OMS Outage",
            "ตรวจเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลัก หรือเตรียมแจ้งเหตุเมื่อทราบหรือไม่ทราบหมายเลขผู้ใช้ไฟ",
            "db",
        ),
    )
    for operation in OMS_OPERATIONS:
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
                # ของ 5 action นี้อย่างเข้มอยู่แล้วที่ชั้น ToolRegistry.execute() (ดู OMS_OPERATIONS)
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
    logger.info("seeded declarative tool '%s' (tool_id=%s, base_url=%s)", OMS_TOOL_SLUG, tool_id, base)
    return tool_id
