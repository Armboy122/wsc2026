"""ตรวจ input/output instance กับ JSON Schema ของ operation ตอน execute (CONTRACTS-V2 §2.3)

แยกจาก ``app/tools/schema_subset.py`` โดยตั้งใจ — โมดูลนั้นตรวจว่า *schema เอง* อยู่ใน
subset ที่ระบบรับ (ตอน save) โมดูลนี้ตรวจว่า *ข้อมูลจริง* ตรงกับ schema นั้นไหม (ตอน execute)
คนละจังหวะ คนละคำถาม
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class SchemaInstanceError(ValueError):
    """input หรือ output ไม่ตรงกับ schema ที่ operation ประกาศไว้"""


def validate_schema_instance(schema: dict[str, Any], instance: dict[str, Any]) -> None:
    """raise ``SchemaInstanceError`` พร้อม path/ข้อความของ error แรกที่เจอ ไม่มี error = ผ่าน"""
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if not errors:
        return
    first = errors[0]
    path = "/".join(str(segment) for segment in first.path) or "root"
    raise SchemaInstanceError(f"ข้อมูลไม่ตรงกับ schema ที่ {path}: {first.message}")
