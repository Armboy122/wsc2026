"""registry รูปเดียว สองชั้น: declarative (DB) กับ Python plugin (โค้ด) — D2.3

ตาม ARCHITECTURE-V2.md §3.4: ``slug`` / ``displayName`` / ``description`` / ``operations[]``
/ ``executor`` / ``source`` เป็น shape เดียวที่ทั้งสองชั้นแปลงเข้ามาหา — ``source`` ("db" | "code")
ใช้บอกที่มาให้ admin/health เท่านั้น **ห้ามใช้ตัดสินใจตอน dispatch** เพราะ agent ต้องไม่รู้ว่า
tool ที่กำลังเรียกมาจาก DB หรือโค้ด

ขอบเขตของ D2.3: ประกอบ shape นี้จาก ``LoadedPlugin`` (source="code", มี executor จริงคือ
``PluginRuntime.tool``) และจากแถวใน ``tool``/``tool_operation`` (source="db") ให้พิสูจน์ว่า
สองชั้นแปลงเป็นรูปเดียวกันได้จริง — **ยังไม่ต่อ executor กลางสำหรับ declarative tool**
(HTTP caller ที่ยิงผ่านนโยบาย SSRF ทุกครั้งคือ D2.4) และ **ยังไม่เปลี่ยน ``ToolRegistry`` ให้
dispatch จาก shape นี้** (ต้องรอ D2.5 ที่เลิกอ้าง ``ToolName``/``ToolAction`` enum เป็น string)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import sqlite3

    from app.db import Database
    from app.plugins.loader import LoadedPlugin

ToolSource = Literal["db", "code"]


@dataclass(frozen=True, slots=True)
class ToolOperationShape:
    """หนึ่ง operation ในรูปที่ไม่ผูกกับที่มา — ค่าเป็น plain string/dict เสมอ

    ไม่มี field บอกที่มา (``source`` อยู่ที่ระดับ ``ToolShape`` เท่านั้น) จึงเทียบ equality
    ตรง ๆ ได้ระหว่าง operation ที่มาจาก DB กับที่มาจากปลั๊กอิน — พิสูจน์ว่าค่าที่มีผลต่อ
    dispatch จริง (policy/mode/exposure/limits/clientContext) ไม่ขึ้นกับที่มา
    """

    action: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    exposure: str
    mode: str
    submit_action: str | None
    policy: str
    limits: dict[str, Any] | None
    client_context: dict[str, str] | None
    # DB schema ของ D2.1 ยังไม่มีคอลัมน์นี้ (ตัดจากแผนเต็มเพื่อ 3 วัน) — default ตรงกับ
    # ARCHITECTURE-V2.md §6.2 (ยืนยันด้วยเสียงได้โดยปริยาย) จนกว่าจะเติมคอลัมน์จริง
    voice_confirm: bool = True


@dataclass(frozen=True, slots=True)
class ToolShape:
    """แค็ตตาล็อกของหนึ่ง tool ในรูปเดียวที่ registry ในอนาคตจะกิน ไม่ว่ามาจากชั้นไหน"""

    slug: str
    display_name: str
    description: str
    operations: tuple[ToolOperationShape, ...]
    # code: instance ที่มี .execute()/.reset() (เดิม) | db: None จนกว่า D2.4 จะมี HTTP executor กลาง
    executor: Any
    source: ToolSource

    def operation(self, action: str) -> ToolOperationShape | None:
        return next((op for op in self.operations if op.action == action), None)


def from_plugin(loaded: LoadedPlugin) -> ToolShape:
    """แปลงปลั๊กอิน Python ที่โหลดแล้วเป็น shape เดียวกับ declarative tool (source="code")"""
    manifest = loaded.manifest
    return ToolShape(
        slug=manifest.metadata.id.value,
        display_name=manifest.metadata.name,
        description=manifest.metadata.description,
        operations=tuple(
            ToolOperationShape(
                action=operation.action.value,
                description=operation.description,
                input_schema=operation.input_schema,
                # outputSchema เป็นข้อมูลจริงอยู่นอกขอบเขต D2.2/D2.3 — ปลั๊กอินยังอ้างชื่อคลาสผ่าน
                # output_contract เท่านั้น จึงยังไม่มี dict จริงให้ใส่ที่นี่
                output_schema=None,
                exposure=operation.effective_exposure.value,
                mode=operation.mode.value,
                submit_action=(
                    operation.submit_action.value if operation.submit_action is not None else None
                ),
                policy=operation.effective_policy.value,
                limits=_limits_to_dict(operation.limits),
                client_context=operation.client_context,
            )
            for operation in manifest.operations
        ),
        executor=loaded.tool,
        source="code",
    )


def _limits_to_dict(limits: Any) -> dict[str, Any] | None:
    if limits is None:
        return None
    return {
        "maxCallsPerTurn": limits.max_calls_per_turn,
        "dedupeIdenticalInput": limits.dedupe_identical_input,
    }


def from_db_row(tool_row: sqlite3.Row, operation_rows: list[sqlite3.Row]) -> ToolShape:
    """แปลงแถว ``tool`` + ``tool_operation`` เป็น shape เดียวกับปลั๊กอิน Python (source="db")

    ``executor`` เป็น ``None`` เสมอในตอนนี้ — ไม่มี HTTP caller กลางจนกว่าจะถึง D2.4
    """
    return ToolShape(
        slug=tool_row["slug"],
        display_name=tool_row["display_name"],
        description=tool_row["description"] or "",
        operations=tuple(
            ToolOperationShape(
                action=row["action"],
                # tool_operation ของ D2.1 ไม่มีคอลัมน์ description แยกต่อ operation (ตัดจาก
                # แผนเต็มเพื่อ 3 วัน) — ปล่อยว่างไว้จนกว่าจะเติมคอลัมน์จริง
                description="",
                input_schema=json.loads(row["input_schema"]),
                output_schema=json.loads(row["output_schema"]) if row["output_schema"] else None,
                exposure=row["exposure"],
                mode=row["mode"],
                submit_action=row["submit_action"],
                policy=row["policy"],
                limits=json.loads(row["limits"]) if row["limits"] else None,
                client_context=json.loads(row["client_context"]) if row["client_context"] else None,
            )
            for row in operation_rows
        ),
        executor=None,
        source="db",
    )


async def load_db_tool_shapes(db: Database) -> tuple[ToolShape, ...]:
    """โหลด declarative tool ที่เปิดใช้งานทั้งหมดจาก SQLite แล้วแปลงเป็น shape เดียวกัน

    เครื่องมือที่ปิดอยู่ (``enabled = 0``, soft delete ตาม ARCHITECTURE-V2.md §8.1) ถูกข้าม
    เหมือนปลั๊กอิน Python ที่ ``enabled: false`` ใน manifest
    """
    tool_rows = await db.fetch_all(
        "SELECT * FROM tool WHERE source = 'db' AND enabled = 1 ORDER BY slug"
    )
    shapes: list[ToolShape] = []
    for tool_row in tool_rows:
        operation_rows = await db.fetch_all(
            "SELECT * FROM tool_operation WHERE tool_id = ? ORDER BY action",
            (tool_row["id"],),
        )
        shapes.append(from_db_row(tool_row, list(operation_rows)))
    return tuple(shapes)


def merge_tool_shapes(*groups: tuple[ToolShape, ...]) -> tuple[ToolShape, ...]:
    """รวม shape จากสองชั้นเข้าเป็นแค็ตตาล็อกเดียว — ห้ามมี slug ซ้ำข้ามชั้น

    ลำดับที่ส่งเข้ามาไม่มีความหมายเชิง dispatch (``source`` ไม่ใช่ตัวตัดสินใจ) มีผลแค่กับ
    ลำดับในผลลัพธ์
    """
    merged: list[ToolShape] = []
    seen: set[str] = set()
    for group in groups:
        for shape in group:
            if shape.slug in seen:
                raise ValueError(f"ลงทะเบียนเครื่องมือซ้ำ slug: {shape.slug}")
            seen.add(shape.slug)
            merged.append(shape)
    return tuple(merged)
