"""ทดสอบชั้นตรวจสอบ JSON Schema subset (schema_subset) — CONTRACTS-V2 §2

🔒 security boundary: schema นอก allowlist ต้องถูก reject ตอน save
ข้อกำหนดจาก docs/v2/TASKS-3DAYS.md D1.2 / docs/v2/TASKS.md T0.2
"""

from __future__ import annotations

import pytest

from app.tools.schema_subset import SchemaSubsetError, validate_schema_subset


def _object(properties: dict, **extra: object) -> dict:
    """สร้าง schema object กลางที่ถูกต้อง (type object + additionalProperties false)"""
    schema: dict = {"type": "object", "additionalProperties": False, "properties": properties}
    schema.update(extra)
    return schema


def _object_with_depth(layers: int) -> dict:
    """schema object ซ้อนกัน ``layers`` ชั้น (ชั้นที่ 1 = root)"""
    schema: dict = {"type": "object", "additionalProperties": False}
    node = schema
    for _ in range(1, layers):
        child: dict = {"type": "object", "additionalProperties": False}
        node["properties"] = {"inner": child}
        node = child
    return schema


# ---------------------------------------------------------------------------
# รับของที่ควรรับ (CONTRACTS-V2 §2.1)
# ---------------------------------------------------------------------------


def test_accepts_minimal_object():
    validate_schema_subset({"type": "object", "additionalProperties": False, "properties": {}})


def test_accepts_required_and_description():
    schema = _object(
        {"customerId": {"type": "string", "description": "รหัสลูกค้า 8 หลัก"}},
        required=["customerId"],
    )
    validate_schema_subset(schema)


@pytest.mark.parametrize(
    "value",
    ["string", "number", "integer", "boolean", "null", "array"],
)
def test_accepts_all_simple_types(value: str):
    validate_schema_subset(_object({"x": {"type": value}}))


def test_accepts_nested_object_with_additional_properties_false():
    schema = _object(
        {
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": ["enabled"],
                "properties": {"enabled": {"type": "boolean"}},
            }
        }
    )
    validate_schema_subset(schema)


def test_accepts_enum_const_default():
    schema = _object(
        {
            "status": {"enum": ["open", "closed"], "description": "สถานะ"},
            "limit": {"const": 5, "default": 0},
            "note": {"type": "string", "default": ""},
        }
    )
    validate_schema_subset(schema)


def test_accepts_array_items_and_minitems_0_or_1():
    validate_schema_subset(_object({"tags": {"type": "array", "items": {"type": "string"}, "minItems": 0}}))
    validate_schema_subset(_object({"tags": {"type": "array", "items": {"type": "string"}, "minItems": 1}}))


def test_accepts_anyof():
    schema = _object({"value": {"anyOf": [{"type": "string"}, {"type": "null"}]}})
    validate_schema_subset(schema)


def test_accepts_same_file_defs_and_ref():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["home", "work"],
        "properties": {
            "home": {"$ref": "#/$defs/address"},
            "work": {"$ref": "#/$defs/address"},
        },
        "$defs": {
            "address": {
                "type": "object",
                "additionalProperties": False,
                "required": ["zip"],
                "properties": {"zip": {"type": "string"}, "city": {"type": "string"}},
            }
        },
    }
    validate_schema_subset(schema)


def test_accepts_depth_five():
    validate_schema_subset(_object_with_depth(5))


# ---------------------------------------------------------------------------
# reject: keyword ที่ห้ามตาม §2.2 / ผิด allowlist §2.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("keyword", "payload"),
    [
        ("oneOf", {"oneOf": [{"type": "string"}, {"type": "integer"}]}),
        ("not", {"not": {"type": "string"}}),
        ("if", {"if": {"type": "string"}}),
        ("then", {"then": {"type": "string"}}),
        ("else", {"else": {"type": "string"}}),
        ("patternProperties", {"patternProperties": {"^x": {"type": "string"}}}),
        ("dependentRequired", {"dependentRequired": {"a": ["b"]}}),
        ("unevaluatedProperties", {"unevaluatedProperties": False}),
        ("contains", {"type": "array", "items": {"type": "string"}, "contains": {"type": "string"}}),
        ("uniqueItems", {"type": "array", "items": {"type": "string"}, "uniqueItems": True}),
        ("pattern", {"type": "string", "pattern": "^[a-z]+$"}),
        ("minimum", {"type": "number", "minimum": 0}),
        ("maximum", {"type": "number", "maximum": 10}),
        ("exclusiveMinimum", {"type": "number", "exclusiveMinimum": 0}),
        ("exclusiveMaximum", {"type": "number", "exclusiveMaximum": 10}),
        ("multipleOf", {"type": "number", "multipleOf": 0.5}),
        ("minLength", {"type": "string", "minLength": 1}),
        ("maxLength", {"type": "string", "maxLength": 5}),
    ],
)
def test_rejects_each_banned_keyword(keyword: str, payload: dict):
    schema = _object({"x": payload})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    message = str(exc_info.value)
    assert f'"{keyword}"' in message, f"ข้อความต้องบอก keyword: {message}"
    assert "root/properties/x" in message, f"ข้อความต้องบอก path: {message}"


def test_rejects_unknown_keyword_title():
    schema = _object({"x": {"type": "string", "title": "ชื่อที่เห็น"}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert '"title"' in str(exc_info.value)


def test_rejects_root_without_additional_properties_false():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_additional_properties_true():
    schema = {"type": "object", "additionalProperties": True, "properties": {"a": {"type": "string"}}}
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_additional_properties_schema():
    schema = {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "properties": {"a": {"type": "string"}},
    }
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_nested_object_missing_additional_properties_false():
    schema = _object({"meta": {"type": "object", "properties": {"a": {"type": "string"}}}})
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_root_type_not_object():
    for schema in ({"type": "string"}, {"type": "array", "items": {"type": "string"}}, {"type": "object"}):
        with pytest.raises(SchemaSubsetError):
            validate_schema_subset(schema)


def test_rejects_type_list_form():
    schema = _object({"x": {"type": ["string", "null"]}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert '"type"' in str(exc_info.value)


def test_rejects_min_items_above_one():
    schema = _object({"x": {"type": "array", "items": {"type": "string"}, "minItems": 2}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "minItems" in str(exc_info.value)


def test_rejects_items_as_array_of_schemas():
    schema = _object({"x": {"type": "array", "items": [{"type": "string"}]}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "items" in str(exc_info.value)


def test_rejects_min_items_without_array_type():
    schema = _object({"x": {"type": "string", "minItems": 1}})
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_properties_without_object_type():
    schema = _object({"x": {"type": "string", "properties": {"a": {"type": "string"}}}})
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_enum_with_object_member():
    schema = _object({"x": {"enum": ["ok", {"nested": True}]}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "enum" in str(exc_info.value)


def test_rejects_const_with_nan():
    schema = _object({"x": {"const": float("nan")}})
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_external_ref():
    schema = _object({"x": {"$ref": "https://example.com/schema.json"}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "$ref" in str(exc_info.value)


def test_rejects_ref_not_pointing_to_defs():
    schema = _object({"x": {"$ref": "#/properties/other"}})
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_ref_to_missing_def():
    schema = _object({"x": {"$ref": "#/$defs/nope"}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "nope" in str(exc_info.value)


def test_rejects_recursive_ref():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "$defs": {"node": {"$ref": "#/$defs/node"}},
    }
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "$ref" in str(exc_info.value)


def test_rejects_mutually_recursive_defs():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"a": {"$ref": "#/$defs/a"}},
        "$defs": {
            "a": {"$ref": "#/$defs/b"},
            "b": {"$ref": "#/$defs/a"},
        },
    }
    with pytest.raises(SchemaSubsetError):
        validate_schema_subset(schema)


def test_rejects_nested_defs_below_root():
    schema = _object({"x": {"type": "object", "additionalProperties": False, "$defs": {"a": {"type": "string"}}}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "$defs" in str(exc_info.value)


# ---------------------------------------------------------------------------
# จับ typo / schema ที่ผิดตาม JSON Schema เอง (ต้องเรียก check_schema ก่อนเสมอ)
# ---------------------------------------------------------------------------


def test_catches_type_typo_at_root():
    schema = {"type": "objct"}
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    message = str(exc_info.value)
    assert '"type"' in message and "objct" in message and "root" in message


def test_catches_type_typo_nested():
    schema = _object({"a": {"type": "objct"}})
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    message = str(exc_info.value)
    assert '"type"' in message and "objct" in message and "properties/a" in message


def test_rejects_required_as_string():
    schema = {"type": "object", "additionalProperties": False, "required": "customerId"}
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(schema)
    assert "required" in str(exc_info.value)


def test_rejects_non_dict_schema():
    for schema in ("not-a-dict", None, [1, 2]):
        with pytest.raises(SchemaSubsetError):
            validate_schema_subset(schema)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ความลึก
# ---------------------------------------------------------------------------


def test_rejects_depth_six():
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(_object_with_depth(6))
    message = str(exc_info.value)
    assert "ลึกเกิน" in message and "root" in message


def test_error_message_is_thai_with_keyword_and_path():
    with pytest.raises(SchemaSubsetError) as exc_info:
        validate_schema_subset(_object({"x": {"type": "string", "pattern": "^a"}}))
    message = str(exc_info.value)
    # ต้องเป็นข้อความไทยที่บอกทั้ง keyword และ path
    assert any("\u0e01" <= ch <= "\u0e5b" for ch in message)
    assert '"pattern"' in message
    assert "root/properties/x" in message
