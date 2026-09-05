"""Regression tests for admin form field types and backend schema rules."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from app.tools.schema_subset import validate_schema_subset

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "admin.html"
ADMIN_JS = ROOT / "web" / "admin.js"
FORM = ROOT / "web" / "admin-form.js"


def run_node(expression: str) -> dict:
    script = f'import * as form from "{FORM.as_uri()}"; {expression}'
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def offered_field_types() -> list[str]:
    html = HTML.read_text()
    template = html.split('id="field-row-template"', 1)[1].split("</template>", 1)[0]
    select = template.split('data-field="type"', 1)[1].split("</select>", 1)[0]
    return re.findall(r'<option value="([^"]+)">', select)


def test_dropdown_types_are_validator_accepted() -> None:
    types = offered_field_types()
    assert types == ["string", "integer", "number", "boolean", "array"]
    for field_type in types:
        property_schema = {"type": field_type}
        if field_type == "array":
            property_schema["items"] = {"type": "string"}
        schema = {
            "type": "object",
            "properties": {"value": property_schema},
            "required": [],
            "additionalProperties": False,
        }
        validate_schema_subset(schema)


def test_object_is_not_an_editable_dropdown_type() -> None:
    assert "object" not in offered_field_types()
    html = HTML.read_text()
    assert 'data-field="items-type"' in html
    assert 'data-field-items-wrap' in html


def test_array_builder_has_items_and_preview_uses_save_baseline() -> None:
    baseline = {
        "action": "read",
        "mode": "read",
        "httpMethod": "GET",
        "urlTemplate": "https://example.test",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
            "additionalProperties": False,
        },
    }
    values = json.loads(json.dumps(baseline))
    values["inputSchema"]["properties"]["tags"]["items"]["type"] = "integer"
    result = run_node(
        "const base = " + json.dumps(baseline) + "; const values = "
        + json.dumps(values)
        + "; console.log(JSON.stringify(form.buildOperationPayload(values, base)));"
    )
    assert result["inputSchema"]["properties"]["tags"]["type"] == "array"
    assert result["inputSchema"]["properties"]["tags"]["items"]["type"] == "integer"
    assert 'buildSchemaFromRows(fieldsContainer, JSON.parse(card.dataset.baselineSchema || "{}"))' in ADMIN_JS.read_text()


def test_array_items_schema_is_accepted_by_real_validator() -> None:
    schema = {
        "type": "object",
        "properties": {"tags": {"type": "array", "items": {"type": "integer"}}},
        "required": [],
        "additionalProperties": False,
    }
    validate_schema_subset(schema)


def test_existing_opaque_object_property_round_trips() -> None:
    operation = {
        "action": "read",
        "mode": "read",
        "httpMethod": "GET",
        "urlTemplate": "https://example.test",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"nested": {"type": "string"}},
                    "required": [],
                    "x-vendor": {"opaque": True},
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    }
    result = run_node(
        "const op = " + json.dumps(operation) + "; "
        "console.log(JSON.stringify(form.buildOperationPayload(op, op)));"
    )
    assert result["inputSchema"]["properties"]["payload"] == operation["inputSchema"]["properties"]["payload"]


@pytest.mark.parametrize("item_type", ["string", "integer", "number", "boolean"])
def test_each_array_item_type_is_valid(item_type: str) -> None:
    schema = {
        "type": "object",
        "properties": {"values": {"type": "array", "items": {"type": item_type}}},
        "required": [],
        "additionalProperties": False,
    }
    validate_schema_subset(schema)
