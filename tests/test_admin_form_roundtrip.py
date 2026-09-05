"""Regression tests for the admin form's metadata-preserving round trip."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
FORM = ROOT / "web" / "admin-form.js"
HTML = ROOT / "web" / "admin.html"


def run_node(expression: str) -> dict:
    script = f'import * as form from "{FORM.as_uri()}"; {expression}'
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def oms_operation() -> dict:
    return {
        "action": "prepare_outage_with_ca",
        "policy": "write_confirm",
        "exposure": "llm",
        "mode": "prepare",
        "submitAction": "submit_outage_with_ca",
        "httpMethod": None,
        "urlTemplate": None,
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactPhone": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "enum": [None, "0800000000"],
                    "default": None,
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
        "limits": {"maxCallsPerTurn": 1},
        "clientContext": {"lat": "lat", "lon": "lon"},
    }


def test_oms_operation_round_trip_preserves_schema_and_metadata() -> None:
    operation = oms_operation()
    result = run_node(
        "const op = "
        + json.dumps(operation)
        + "; console.log(JSON.stringify(form.buildOperationPayload(op, op)));"
    )
    assert result == operation


def test_dom_template_has_every_selector_used_for_nullable_round_trip() -> None:
    html = HTML.read_text()
    for selector in ("name", "type", "required", "nullable", "description"):
        assert f'data-field="{selector}"' in html


def test_unknown_operation_metadata_is_preserved() -> None:
    operation = oms_operation() | {"vendorMetadata": {"retention": "short"}}
    result = run_node(
        "const op = "
        + json.dumps(operation)
        + "; console.log(JSON.stringify(form.buildOperationPayload(op, op)));"
    )
    assert result["vendorMetadata"] == {"retention": "short"}


def test_metadata_loss_is_reported_with_field_name() -> None:
    operation = oms_operation()
    candidate = json.loads(json.dumps(operation))
    del candidate["inputSchema"]["properties"]["contactPhone"]
    result = run_node(
        "const base = "
        + json.dumps(operation)
        + "; const candidate = "
        + json.dumps(candidate)
        + "; console.log(JSON.stringify(form.detectMetadataLoss(base, candidate)));"
    )
    assert "inputSchema.properties.contactPhone" in result


def test_auth_environment_name_is_never_restored_from_baseline() -> None:
    operation = oms_operation()
    baseline = {"slug": "oms_tool", "displayName": "OMS", "authEnvVar": "OMS_KEY", "operations": [operation]}
    values = {"slug": "oms_tool", "displayName": "OMS", "operations": [operation]}
    result = run_node(
        "const base = "
        + json.dumps(baseline)
        + "; const values = "
        + json.dumps(values)
        + "; console.log(JSON.stringify(form.buildToolPayload(values, base)));"
    )
    assert "authEnvVar" not in result
