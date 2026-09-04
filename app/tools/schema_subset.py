"""ชั้นตรวจสอบ JSON Schema subset ที่ระบบรับ (CONTRACTS-V2 §2)

ระบบรับเฉพาะ JSON Schema subset ที่ allowlist ไว้เท่านั้น ไม่งั้น tool ที่
"บันทึกผ่านแต่รันไม่ได้" (เช่น schema ที่ Anthropic strict mode ตอบ 400 หรือ
keyword ที่ jsonschema กลืนเงียบ) จะกลายเป็นบั๊กที่หาสาเหตุยากที่สุด

หลักการของโมดูลนี้:
1. เรียก ``jsonschema.Draft202012Validator.check_schema()`` ก่อนเสมอ
   เพื่อจับ schema ที่ผิดตามสเปก JSON Schema เอง (เช่น typo ``{"type": "objct"}``)
2. ตรวจ allowlist ตาม CONTRACTS-V2 §2.1 / reject list §2.2
3. ข้อความ error เป็นภาษาไทย ระบุ **keyword** ที่ผิดและ **path** ที่ผิด
   (path เป็น JSON Pointer ต่อจาก root เช่น ``root/properties/ca``)

subset ที่ยอมรับ:
- root ต้องเป็น ``type: object`` + ``additionalProperties: false``
- ``type`` รับเฉพาะ: string · number · integer · boolean · null · object · array
- ค่า: ``enum`` (สมาชิกเป็น primitive เท่านั้น) · ``const``
- โครงสร้าง: ``anyOf`` · ``$defs`` / ``$ref`` ภายในไฟล์เดียวกัน (``#/$defs/<ชื่อ>``)
- array: ``items`` (schema เดียว) · ``minItems`` เฉพาะ 0 หรือ 1
- อื่น: ``required`` · ``description`` · ``default``
- object ทุกตัวต้องมี ``additionalProperties: false``
- ความลึกไม่เกิน 5 ชั้น (นับทุกชั้นของ properties/items ที่ซ้อนกัน)
"""

from __future__ import annotations

import math
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

MAX_SCHEMA_DEPTH = 5

# keyword ทั้งหมดที่ระบบอนุญาต — นอกเหนือจากนี้ = reject (allowlist ตาม §2.1)
_ALLOWED_KEYWORDS = frozenset({
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "enum",
    "const",
    "anyOf",
    "$defs",
    "$ref",
    "description",
    "default",
})

_ALLOWED_TYPES = frozenset({
    "string",
    "number",
    "integer",
    "boolean",
    "null",
    "object",
    "array",
})

# keyword ที่ใช้ได้เฉพาะกับ object/array (กัน keyword ตกหล่นเงียบ)
_OBJECT_KEYWORDS = ("properties", "required", "additionalProperties")
_ARRAY_KEYWORDS = ("items", "minItems")


class SchemaSubsetError(ValueError):
    """schema ไม่อยู่ใน subset ที่ระบบยอมรับ

    ข้อความภาษาไทย ระบุ keyword และ path ที่ผิดเสมอ
    """


def validate_schema_subset(schema: Any) -> None:
    """ตรวจ schema ว่าอยู่ใน subset ที่ระบบรับหรือไม่ ถ้าผิด raise ``SchemaSubsetError``

    เรียก ``check_schema()`` ก่อนเสมอ ตาม CONTRACTS-V2 §2.3
    """
    if not isinstance(schema, dict):
        raise SchemaSubsetError(
            "ที่ root: schema ต้องเป็น JSON object (รับเฉพาะ dict เท่านั้น)"
        )

    # 1) ให้ jsonschema จับ schema ที่ผิดตามสเปก JSON Schema 2020-12 ก่อนเสมอ
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SchemaSubsetError(_translate_schema_error(exc)) from exc

    # 2) ตรวจ allowlist / reject list ของ subset
    _require_root_object(schema)

    defs = schema.get("$defs", {})
    ctx: dict[str, Any] = {"defs": defs if isinstance(defs, dict) else {}, "stack": []}
    _walk(schema, path="root", depth=1, ctx=ctx)


def _require_root_object(schema: dict[str, Any]) -> None:
    """root ต้องเป็น ``type: object`` + ``additionalProperties: false`` (CONTRACTS-V2 §2.1)"""
    if schema.get("type") != "object":
        raise SchemaSubsetError('ที่ root: ต้องประกาศ type: "object" เท่านั้น (รับเฉพาะ object)')
    if schema.get("additionalProperties") is not False:
        raise SchemaSubsetError(
            'ที่ root: object ทุกตัวต้องมี "additionalProperties": false (ตอนนี้ไม่มีหรือไม่ใช่ false)'
        )


def _walk(node: Any, *, path: str, depth: int, ctx: dict[str, Any]) -> None:
    """เดิน schema แบบวนซ้ำ ตรวจ allowlist/reject list ทีละ node"""
    if depth > MAX_SCHEMA_DEPTH:
        raise SchemaSubsetError(
            f"schema ลึกเกิน {MAX_SCHEMA_DEPTH} ชั้น ที่ {path} "
            "(ขีดจำกัดของระบบคือ 5 ชั้น)"
        )
    if not isinstance(node, dict):
        raise SchemaSubsetError(f"ที่ {path}: subschema ต้องเป็น JSON object (dict)")

    # allowlist: keyword ที่ไม่อยู่ในรายการรับ = reject (รวม reject list §2.2)
    for key in node:
        if key not in _ALLOWED_KEYWORDS:
            raise SchemaSubsetError(
                f'ที่ {path}: keyword "{key}" ไม่อยู่ในรายการที่ระบบรองรับ '
                "(CONTRACTS-V2 §2.1 รับเฉพาะรายการที่ประกาศไว้ / §2.2 ปฏิเสธ)"
            )

    if "$defs" in node:
        if path != "root":
            raise SchemaSubsetError(
                f'ที่ {path}: "$defs" ใช้ได้ที่ root เท่านั้น ($ref ชี้ได้เฉพาะ "#/$defs/<ชื่อ>")'
            )
        defs = node["$defs"]
        if not isinstance(defs, dict):
            raise SchemaSubsetError(f'ที่ {path}: "$defs" ต้องเป็น object')
        for name, subschema in defs.items():
            _walk(subschema, path=f"{path}/$defs/{_escape_segment(name)}", depth=depth, ctx=ctx)

    if "$ref" in node:
        _expand_ref(node, path=path, depth=depth, ctx=ctx)
        return

    _check_type(node, path)
    _check_object_keywords(node, path)
    _check_array_keywords(node, path)
    _check_enum_and_const(node, path)
    _check_children(node, path=path, depth=depth, ctx=ctx)


def _check_type(node: dict[str, Any], path: str) -> None:
    """``type`` ต้องเป็นชื่อชนิดเดียวในรายการที่รองรับ"""
    value = node.get("type")
    if value is None:
        return
    if not isinstance(value, str) or value not in _ALLOWED_TYPES:
        raise SchemaSubsetError(
            f'ที่ {path}: keyword "type" มีค่า {value!r} ที่ไม่รองรับ '
            "(รับเฉพาะ string/number/integer/boolean/null/object/array)"
        )


def _check_object_keywords(node: dict[str, Any], path: str) -> None:
    """``properties``/``required``/``additionalProperties`` ใช้กับ object เท่านั้น
    และ object ทุกตัวต้องมี ``additionalProperties: false``"""
    obj_type = node.get("type") == "object"
    for kw in _OBJECT_KEYWORDS:
        if kw in node and not obj_type:
            raise SchemaSubsetError(
                f'ที่ {path}: keyword "{kw}" ใช้กับ type: "object" เท่านั้น '
                f"(ประกาศ type: \"object\" ไว้ที่ node นี้ก่อน)"
            )
    if obj_type and node.get("additionalProperties") is not False:
        raise SchemaSubsetError(
            f'ที่ {path}: object ทุกตัวต้องมี "additionalProperties": false '
            "(ตอนนี้ไม่มีหรือไม่ใช่ false)"
        )


def _check_array_keywords(node: dict[str, Any], path: str) -> None:
    """``items``/``minItems`` ใช้กับ array เท่านั้น และ ``minItems`` รับแค่ 0 หรือ 1"""
    array_type = node.get("type") == "array"
    for kw in _ARRAY_KEYWORDS:
        if kw in node and not array_type:
            raise SchemaSubsetError(
                f'ที่ {path}: keyword "{kw}" ใช้กับ type: "array" เท่านั้น '
                "(ประกาศ type: \"array\" ไว้ที่ node นี้ก่อน)"
            )
    if "minItems" in node and node["minItems"] not in (0, 1):
        raise SchemaSubsetError(
            f'ที่ {path}: "minItems" ต้องเป็น 0 หรือ 1 เท่านั้น (ตอนนี้ {node["minItems"]})'
        )


def _check_enum_and_const(node: dict[str, Any], path: str) -> None:
    """``enum`` สมาชิกต้องเป็น primitive เท่านั้น · ``const`` ต้องเป็นค่า JSON"""
    if "enum" in node:
        for index, member in enumerate(node["enum"]):
            if not _is_json_primitive(member):
                raise SchemaSubsetError(
                    f"ที่ {path}/enum/{index}: สมาชิกของ \"enum\" ต้องเป็น primitive "
                    "(string/number/boolean/null) เท่านั้น ไม่รับ object/array"
                )
    if "const" in node and not _is_json_primitive(node["const"]):
        # const รองรับค่า JSON ใดก็ได้ ยกเว้นค่าที่ไม่ใช่ JSON (เช่น NaN/infinity)
        if not _is_json_value(node["const"]):
            raise SchemaSubsetError(
                f'ที่ {path}: ค่าของ "const" ไม่ใช่ค่า JSON ที่ถูกต้อง'
            )


def _check_children(node: dict[str, Any], *, path: str, depth: int, ctx: dict[str, Any]) -> None:
    """ลงลึกในโครงสร้างย่อย: properties/items นับความลึกเพิ่ม 1 · anyOf/$defs ไม่นับ"""
    if "properties" in node:
        properties = node["properties"]
        if not isinstance(properties, dict):
            raise SchemaSubsetError(f'ที่ {path}: "properties" ต้องเป็น object')
        for name, subschema in properties.items():
            _walk(
                subschema,
                path=f"{path}/properties/{_escape_segment(name)}",
                depth=depth + 1,
                ctx=ctx,
            )

    if "anyOf" in node:
        for index, subschema in enumerate(node["anyOf"]):
            _walk(subschema, path=f"{path}/anyOf/{index}", depth=depth, ctx=ctx)

    if "items" in node:
        items = node["items"]
        if not isinstance(items, dict):
            raise SchemaSubsetError(
                f'ที่ {path}: "items" ต้องเป็น schema object เดียว (ไม่รับรายการ schemas)'
            )
        _walk(items, path=f"{path}/items", depth=depth + 1, ctx=ctx)


def _expand_ref(node: dict[str, Any], *, path: str, depth: int, ctx: dict[str, Any]) -> None:
    """ตรวจ ``$ref``: ต้องชี้ภายในไฟล์ (``#/$defs/<ชื่อ>``) · ต้องมีใน ``$defs`` · ต้องไม่วนซ้ำ"""
    ref = node["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#"):
        raise SchemaSubsetError(
            f'ที่ {path}: "$ref" ชี้ schema ภายนอกไฟล์ไม่ได้: {ref!r} '
            "(ต้องเป็น \"#/$defs/<ชื่อ>\" ภายในไฟล์เดียวกันเท่านั้น)"
        )

    # รูปแบบที่รับ: #/$defs/<ชื่อ> ตรง ๆ เท่านั้น
    if not ref.startswith("#/$defs/") or "/" in ref[len("#/$defs/"):]:
        raise SchemaSubsetError(
            f'ที่ {path}: "$ref" ต้องเป็น "#/$defs/<ชื่อ>" ภายในไฟล์เดียวกัน '
            f"(ตอนนี้ {ref!r})"
        )
    name = _unescape_segment(ref[len("#/$defs/"):])
    defs = ctx["defs"]
    if name not in defs:
        raise SchemaSubsetError(
            f'ที่ {path}: "$ref" อ้าง "{name}" แต่ไม่มีนิยาม "{name}" ใน "$defs"'
        )
    if name in ctx["stack"]:
        raise SchemaSubsetError(
            f'ที่ {path}: "$ref" เป็น recursive schema (วนกลับมาที่ "{name}") '
            "— ระบบไม่รองรับ schema ที่วนซ้ำได้"
        )

    # keyword ตัวอื่น (type/properties/...) ถูกละเว้นโดยสเปก 2020-12 เมื่อมี $ref
    # ⇒ ให้ reject เพื่อไม่ให้ keyword ตกหล่นเงียบ
    ignored = [
        k
        for k in node
        if k in _ALLOWED_KEYWORDS and k not in ("$ref", "$defs", "description", "default")
    ]
    if ignored:
        raise SchemaSubsetError(
            f'ที่ {path}: keyword "$ref" ใช้ร่วมกับ keyword "{ignored[0]}" ไม่ได้ '
            "(JSON Schema 2020-12 จะละเว้น keyword อื่นเมื่อมี $ref)"
        )

    # def ที่ถูกอ้าง = schema ที่มาแทนที่ node นี้ ⇒ เดินด้วย depth/path เดียวกัน
    ctx["stack"].append(name)
    try:
        _walk(defs[name], path=path, depth=depth, ctx=ctx)
    finally:
        ctx["stack"].pop()


def _is_json_primitive(value: Any) -> bool:
    """primitive JSON: string · number (finite) · integer · boolean · null"""
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _is_json_value(value: Any) -> bool:
    """ค่า JSON ที่ถูกต้อง (dict/list ก็ได้ แต่ห้าม NaN/infinity)"""
    if _is_json_primitive(value):
        return True
    if isinstance(value, (dict, list)):
        return True
    return False


def _escape_segment(segment: str) -> str:
    """escape ชื่อ segment ตาม RFC 6901 (JSON Pointer)"""
    return segment.replace("~", "~0").replace("/", "~1")


def _unescape_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _translate_schema_error(exc: SchemaError) -> str:
    """แปลง SchemaError จาก check_schema() เป็นข้อความไทยที่บอก keyword และ path

    ``exc.path`` คือ path ใน schema ที่ผู้ใช้ส่งเข้ามา (ไม่ใช่ meta-schema)
    """
    segments = list(exc.path)
    path = _path_from_segments(segments)

    # กรณีที่คุ้นเคยที่สุด: ค่าของ keyword "type" ไม่ใช่ชนิดที่รองรับ (เช่น typo "objct")
    if segments and segments[-1] == "type":
        parent = _path_from_segments(segments[:-1])
        value = getattr(exc, "instance", "<ไม่ทราบค่า>")
        return (
            f'ที่ {parent}: keyword "type" มีค่า "{value}" ที่ไม่ใช่ชนิดที่ระบบรองรับ '
            "(รับเฉพาะ string/number/integer/boolean/null/object/array)"
        )

    keyword = segments[-1] if segments and isinstance(segments[-1], str) else exc.validator
    reason = getattr(exc, "message", None) or str(exc)
    reason = str(reason).splitlines()[0]
    return (
        f"ที่ {path}: ค่า/โครงสร้างของ schema ไม่ผ่านการตรวจ JSON Schema 2020-12 "
        f'(keyword: "{keyword}") — {reason}'
    )


def _path_from_segments(segments: list[Any]) -> str:
    if not segments:
        return "root"
    rendered = "/".join(_escape_segment(str(seg)) for seg in segments)
    return f"root/{rendered}"
