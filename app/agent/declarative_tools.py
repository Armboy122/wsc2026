"""โหลด declarative tool ที่เปิดใช้งานทั้งหมดจาก DB แล้วประกอบเป็นสิ่งที่ ``ToolRegistry``
และแค็ตตาล็อกของ Main Agent ต้องการ — D2.6

คู่กับ ``app/plugins/loader.py`` (โหลด Python plugin จากไฟล์) โมดูลนี้โหลดจาก SQLite แทน
แต่ผลลัพธ์หน้าตาเดียวกัน: ``Tool`` ที่ ``ToolRegistry`` เรียกได้ + ``ToolDefinition`` ที่
แค็ตตาล็อกของ LLM เห็น + ``OperationSpec`` ต่อ action ที่ Main Agent ใช้ตัดสิน policy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import httpx

from app.agent.operation_policy import OperationLimits, OperationPolicy, OperationSpec
from app.agent.tool_shape import ToolOperationShape, from_db_row
from app.db import Database
from app.llm.models import ToolDefinition
from app.tools.declarative_executor import DeclarativeToolAuth, DeclarativeToolExecutor
from app.tools.declarative_tool import DeclarativeTool
from app.tools.declarative_validator import (
    DeclarativeValidationError,
    sanitize_validation_error_message,
    validate_declarative_tool_shape,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DisabledTool:
    """tool ที่ลงทะเบียนใน DB แต่ fail closed ตอนโหลด — หน้า admin ต้องแสดงพร้อมเหตุผล (D3.3)

    ``reason`` ผ่าน ``sanitize_validation_error_message`` แล้ว (ไม่รั่ว URL/secret)
    """

    slug: str
    reason: str


@dataclass(frozen=True, slots=True)
class DeclarativeToolBundle:
    """ผลลัพธ์ของการโหลด declarative tool ทั้งหมด — ส่งตรงเข้า ``ToolRegistry(...)`` ได้เลย"""

    tools: tuple[DeclarativeTool, ...]
    catalogue: tuple[ToolDefinition, ...]
    operation_specs: dict[tuple[str, str], OperationSpec]
    # tool ที่ถูกข้ามเพราะ definition ผิด — แสดงในหน้า admin พร้อมเหตุผล กัน "หายเงียบ" (D3.3)
    disabled: tuple[DisabledTool, ...] = ()


async def load_declarative_tools(
    db: Database,
    *,
    app_env: str | None,
    allowlist: Iterable[str] = (),
    transport: httpx.BaseTransport | None = None,
) -> DeclarativeToolBundle:
    """อ่านทุกแถวใน ``tool`` ที่ ``source='db'`` และ ``enabled=1`` แล้วประกอบเป็น Tool

    tool ที่ปิดอยู่ (soft delete, ARCHITECTURE-V2.md §8.1) หรือ tool ที่ definition เสีย (fail closed)
    ถูกข้าม เพื่อไม่ให้แถวที่เสียทำให้ app ทั้งระบบล้ม และไม่ให้ LLM เห็นหรือ dispatch ได้
    """
    tool_rows = await db.fetch_all(
        "SELECT * FROM tool WHERE source = 'db' AND enabled = 1 ORDER BY slug"
    )
    tools: list[DeclarativeTool] = []
    catalogue: list[ToolDefinition] = []
    operation_specs: dict[tuple[str, str], OperationSpec] = {}
    disabled: list[DisabledTool] = []
    for tool_row in tool_rows:
        operation_rows = await db.fetch_all(
            "SELECT * FROM tool_operation WHERE tool_id = ? ORDER BY action",
            (tool_row["id"],),
        )
        try:
            shape = from_db_row(tool_row, list(operation_rows))
            validate_declarative_tool_shape(shape, app_env=app_env, allowlist=allowlist)
        except Exception as exc:
            safe_message = sanitize_validation_error_message(str(exc))
            logger.warning(
                "Declarative tool '%s' (id=%s) failed validation and was disabled: %s",
                tool_row["slug"],
                tool_row["id"],
                safe_message,
            )
            disabled.append(DisabledTool(slug=tool_row["slug"], reason=safe_message))
            continue

        auth_row = await db.fetch_one(
            "SELECT * FROM tool_auth WHERE tool_id = ?", (tool_row["id"],)
        )
        # P1: header_name/scheme มาจาก DB ได้แล้ว (migration 003) — NULL ของแถวเดิม
        # ต้อง fallback เป็น Authorization/Bearer เพื่อให้ tool เดิมพฤติกรรมไม่เปลี่ยน
        # scheme ว่าง = ส่งค่า secret ตรง ๆ ไม่มี prefix (กรณี X-API-Key)
        auth = (
            DeclarativeToolAuth(
                env_var=auth_row["secret_ref"],
                header_name=auth_row["header_name"] or "Authorization",
                scheme=auth_row["scheme"] if auth_row["scheme"] is not None else "Bearer",
            )
            if auth_row is not None
            else None
        )
        executor = DeclarativeToolExecutor(app_env=app_env, allowlist=allowlist, transport=transport)
        tools.append(DeclarativeTool(shape, executor, auth=auth))

        llm_operations = tuple(op for op in shape.operations if op.exposure == "llm")
        catalogue.append(
            ToolDefinition(
                name=shape.slug,
                description=shape.description,
                actions=tuple(op.action for op in llm_operations),
                input_schemas={op.action: op.input_schema for op in llm_operations},
            )
        )
        for operation in shape.operations:
            operation_specs[(shape.slug, operation.action)] = _operation_spec_from_shape(operation)

    return DeclarativeToolBundle(
        tools=tuple(tools),
        catalogue=tuple(catalogue),
        operation_specs=operation_specs,
        disabled=tuple(disabled),
    )


def _operation_spec_from_shape(operation: ToolOperationShape) -> OperationSpec:
    limits = None
    if operation.limits:
        limits = OperationLimits(
            max_calls_per_turn=operation.limits.get("maxCallsPerTurn"),
            dedupe_identical_input=operation.limits.get("dedupeIdenticalInput"),
        )
    return OperationSpec(
        policy=OperationPolicy(operation.policy),
        mode=operation.mode,
        exposure=operation.exposure,
        submit_action=operation.submit_action,
        limits=limits,
        client_context=operation.client_context,
    )
