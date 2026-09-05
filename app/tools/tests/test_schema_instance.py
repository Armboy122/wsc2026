"""ทดสอบ validate_schema_instance — CONTRACTS-V2 §2.3 (execute: validate input ด้วย jsonschema)"""

from __future__ import annotations

import pytest

from app.tools.schema_instance import SchemaInstanceError, validate_schema_instance

_SCHEMA = {
    "type": "object",
    "properties": {
        "maxLength": {"type": "integer"},
    },
    "required": [],
    "additionalProperties": False,
}


def test_valid_instance_passes():
    validate_schema_instance(_SCHEMA, {"maxLength": 20})


def test_empty_instance_passes_when_nothing_required():
    validate_schema_instance(_SCHEMA, {})


def test_wrong_type_rejected():
    with pytest.raises(SchemaInstanceError):
        validate_schema_instance(_SCHEMA, {"maxLength": "twenty"})


def test_additional_property_rejected():
    with pytest.raises(SchemaInstanceError):
        validate_schema_instance(_SCHEMA, {"maxLength": 20, "extra": "nope"})


def test_missing_required_field_rejected():
    schema = {**_SCHEMA, "required": ["maxLength"]}
    with pytest.raises(SchemaInstanceError):
        validate_schema_instance(schema, {})
