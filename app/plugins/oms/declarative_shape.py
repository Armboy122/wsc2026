"""นิยาม operation ของ ``oms_tool`` หนึ่งเดียวที่ ``scripts/seed_oms_tool.py`` (เขียนแถวจริง
ลง SQLite) และเทสที่ต้องการ ``DeclarativeTool`` ของ OMS แบบไม่พึ่ง DB ใช้ร่วมกัน — D2.7

กันไม่ให้ schema ของทั้งสองที่ดริฟท์ออกจากกัน เป็นต้นฉบับเดียวที่คัดลอกมาจาก
``app/plugins/oms/plugin.yaml`` เดิมทุกประการ (D2.6 proof point ตัวแรกมีแค่ ``plain_read``
เท่านั้น จึงไม่เคยต้องมีโมดูลแบบนี้มาก่อน) ``mode: prepare`` ทั้งสอง operation ไม่มี path
(เป็น null ทั้ง httpMethod/urlTemplate ตาม carve-out ของ D2.7 ใน CONTRACTS-V2.md §1.3) เพราะ
``write_confirm`` ต้องไม่มี side effect จริงตอนเตรียมรายการ — ดู ``app/tools/declarative_tool.py``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.agent.tool_shape import ToolOperationShape, ToolShape
from app.tools.declarative_executor import DeclarativeToolExecutor
from app.tools.declarative_tool import DeclarativeTool

_IDEMPOTENCY_KEY_SCHEMA_PROPERTY = {
    "type": "string",
    "description": "กันการส่งซ้ำจากการเรียกซ้ำ",
}

SUBMIT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pendingActionId": {
            "type": "string",
            "description": "รหัสของรายการที่เตรียมไว้และผู้ใช้ยืนยันแล้ว",
        },
        "idempotencyKey": _IDEMPOTENCY_KEY_SCHEMA_PROPERTY,
    },
    "required": ["pendingActionId", "idempotencyKey"],
    "additionalProperties": False,
}

GET_OUTAGE_BY_CA_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "caNumber": {"type": "string", "description": "หมายเลขผู้ใช้ไฟ 12 หลัก"},
    },
    "required": ["caNumber"],
    "additionalProperties": False,
}

PREPARE_OUTAGE_WITH_CA_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "caNumber": {"type": "string", "description": "หมายเลขผู้ใช้ไฟ 12 หลัก"},
        "description": {"type": "string", "description": "อาการที่ผู้ใช้แจ้ง"},
        "contactPhone": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "เบอร์ติดต่อกลับ (ไม่บังคับ)",
        },
        "locationNote": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "จุดสังเกตเพิ่มเติมของสถานที่ (ไม่บังคับ)",
        },
        "idempotencyKey": _IDEMPOTENCY_KEY_SCHEMA_PROPERTY,
    },
    "required": ["caNumber", "description", "idempotencyKey"],
    "additionalProperties": False,
}

PREPARE_ANONYMOUS_OUTAGE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "อาการที่ผู้ใช้แจ้ง"},
        "location": {"type": "string", "description": "สถานที่เกิดเหตุ"},
        "contactPhone": {"type": "string", "description": "เบอร์ติดต่อกลับ"},
        "idempotencyKey": _IDEMPOTENCY_KEY_SCHEMA_PROPERTY,
        # ไม่มี CA จึงหา MST GIS ไม่ได้ — เติมจาก ChatRequest.clientLocation แทนผ่าน
        # clientContext ด้านล่าง ไม่ใช่ค่าที่ LLM สร้างเอง (main_agent._inject_client_context)
        "lat": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "description": "พิกัดละติจูดจากอุปกรณ์ผู้ใช้ (เติมจาก clientContext ไม่ใช่ให้ LLM กรอกเอง)",
        },
        "lon": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "description": "พิกัดลองจิจูดจากอุปกรณ์ผู้ใช้ (เติมจาก clientContext ไม่ใช่ให้ LLM กรอกเอง)",
        },
    },
    "required": ["description", "location", "contactPhone", "idempotencyKey"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class OmsOperationDefinition:
    action: str
    policy: str
    input_schema: dict[str, Any]
    exposure: str
    mode: str
    submit_action: str | None
    http_method: str | None
    # path ต่อท้าย base_url ของ OMS — None เฉพาะ mode=prepare (ไม่มี HTTP call จริง)
    path: str | None
    client_context: dict[str, str] | None


OMS_OPERATIONS: tuple[OmsOperationDefinition, ...] = (
    OmsOperationDefinition(
        action="get_outage_by_ca",
        policy="plain_read",
        input_schema=GET_OUTAGE_BY_CA_INPUT_SCHEMA,
        exposure="llm",
        mode="read",
        submit_action=None,
        http_method="GET",
        path="outages/by-ca/{caNumber}",
        client_context=None,
    ),
    OmsOperationDefinition(
        action="prepare_outage_with_ca",
        policy="write_confirm",
        input_schema=PREPARE_OUTAGE_WITH_CA_INPUT_SCHEMA,
        exposure="llm",
        mode="prepare",
        submit_action="submit_outage_with_ca",
        http_method=None,
        path=None,
        client_context=None,
    ),
    OmsOperationDefinition(
        action="submit_outage_with_ca",
        policy="write_confirm",
        input_schema=SUBMIT_INPUT_SCHEMA,
        exposure="internal",
        mode="submit",
        submit_action=None,
        http_method="POST",
        path="outages",
        client_context=None,
    ),
    OmsOperationDefinition(
        action="prepare_anonymous_outage",
        policy="write_confirm",
        input_schema=PREPARE_ANONYMOUS_OUTAGE_INPUT_SCHEMA,
        exposure="llm",
        mode="prepare",
        submit_action="submit_anonymous_outage",
        http_method=None,
        path=None,
        # เดิมเติมพิกัดเบราว์เซอร์เฉพาะจุดนี้ตรง ๆ ใน main_agent.py (12 จุด hardcode ของ D1.5)
        # ตอนนี้เป็นข้อมูลของ operation เอง agent เติมให้โดยไม่รู้ว่าเป็น OMS
        client_context={"lat": "lat", "lon": "lon"},
    ),
    OmsOperationDefinition(
        action="submit_anonymous_outage",
        policy="write_confirm",
        input_schema=SUBMIT_INPUT_SCHEMA,
        exposure="internal",
        mode="submit",
        submit_action=None,
        http_method="POST",
        path="outages/anonymous",
        client_context=None,
    ),
)


def oms_tool_shape(base_url: str) -> ToolShape:
    """สร้าง ``ToolShape`` (source="db") ของ ``oms_tool`` ในหน่วยความจำ ไม่ต้องมี DB จริง —
    ใช้ทั้งใน ``scripts/seed_oms_tool.py`` (แปลงเป็นแถว SQL) และเทสที่ต้องการ ``DeclarativeTool``
    ของ OMS โดยไม่พึ่ง SQLite
    """
    base = base_url.rstrip("/")
    return ToolShape(
        slug="oms_tool",
        display_name="OMS Outage",
        description=(
            "ตรวจเหตุไฟฟ้าขัดข้องด้วยหมายเลขผู้ใช้ไฟ 12 หลัก "
            "หรือเตรียมแจ้งเหตุเมื่อทราบหรือไม่ทราบหมายเลขผู้ใช้ไฟ"
        ),
        operations=tuple(
            ToolOperationShape(
                action=op.action,
                description="",
                input_schema=op.input_schema,
                output_schema=None,
                exposure=op.exposure,
                mode=op.mode,
                submit_action=op.submit_action,
                policy=op.policy,
                limits=None,
                client_context=op.client_context,
                http_method=op.http_method,
                url_template=f"{base}/{op.path}" if op.path is not None else None,
            )
            for op in OMS_OPERATIONS
        ),
        executor=None,
        source="db",
    )


def oms_declarative_tool(
    base_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    app_env: str = "development",
    allowlist: tuple[str, ...] = (),
) -> DeclarativeTool:
    """สร้าง ``DeclarativeTool`` ของ ``oms_tool`` พร้อมใช้ในเทส — ยิงผ่าน ``transport`` ที่ฉีดมา
    แทน ``OmsTool`` เดิมที่ย้ายขึ้น declarative contract แล้ว"""
    executor = DeclarativeToolExecutor(app_env=app_env, allowlist=allowlist, transport=transport)
    return DeclarativeTool(oms_tool_shape(base_url), executor)
