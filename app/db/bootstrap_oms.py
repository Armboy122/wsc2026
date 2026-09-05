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
import sqlite3

from app.db import Database
from app.plugins.oms.declarative_shape import OMS_OPERATIONS
from app.tools.schema_subset import validate_schema_subset

logger = logging.getLogger(__name__)

OMS_TOOL_SLUG = "oms_tool"

# P1: OMS ต้องการ ``X-API-Key: <key>`` ไม่ใช่ ``Authorization: Bearer`` — ชื่อ env var
# เก็บใน tool_auth.secret_ref (ค่าจริงอยู่นอก DB ตาม CONTRACTS-V2 §10.2) header/scheme
# เก็บต่อแถวได้หลัง migration 003 (scheme ว่าง = ส่งค่าตรง ๆ ไม่มี prefix)
OMS_AUTH_ENV_VAR = "OMS_API_KEY"
OMS_AUTH_HEADER_NAME = "X-API-Key"
OMS_AUTH_SCHEME = ""


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
    base = oms_base_url.rstrip("/")
    for operation in OMS_OPERATIONS:
        validate_schema_subset(operation.input_schema)

    def _write(conn: sqlite3.Connection) -> int | None:
        existing = conn.execute(
            "SELECT id FROM tool WHERE slug = ?", (OMS_TOOL_SLUG,)
        ).fetchone()
        if existing is not None:
            if not replace:
                # Existing state, including an intentional auth removal, is authoritative.
                return None
            conn.execute("DELETE FROM tool WHERE id = ?", (existing["id"],))

        cursor = conn.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            (
                OMS_TOOL_SLUG,
                "OMS Outage",
                "ตรวจเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลัก หรือเตรียมแจ้งเหตุเมื่อทราบหรือไม่ทราบหมายเลขผู้ใช้ไฟ",
                "db",
            ),
        )
        tool_id = cursor.lastrowid
        assert tool_id is not None
        for operation in OMS_OPERATIONS:
            url_template = f"{base}/{operation.path}" if operation.path is not None else None
            conn.execute(
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
                    json.dumps(operation.client_context, ensure_ascii=False)
                    if operation.client_context
                    else None,
                ),
            )
        conn.execute(
            "INSERT INTO tool_auth (tool_id, type, secret_ref, header_name, scheme) "
            "VALUES (?, 'api_key', ?, ?, ?)",
            (tool_id, OMS_AUTH_ENV_VAR, OMS_AUTH_HEADER_NAME, OMS_AUTH_SCHEME),
        )
        return tool_id

    tool_id = await db.run_in_transaction(_write)
    if tool_id is None:
        return None
    logger.info("seeded declarative tool '%s' (tool_id=%s, base_url=%s)", OMS_TOOL_SLUG, tool_id, base)
    logger.info(
        "seeded tool_auth for '%s' (header=%s, scheme=<empty>)",
        OMS_TOOL_SLUG,
        OMS_AUTH_HEADER_NAME,
    )
    return tool_id
