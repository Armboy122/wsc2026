"""Behavioral regressions for editing declarative admin tool definitions."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "web" / "admin-form.js"
ADMIN_JS = ROOT / "web" / "admin.js"


def run_node(expression: str) -> dict[str, Any]:
    script = f'import * as form from "{FORM.as_uri()}"; {expression}'
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def operation(action: str, **fields: Any) -> dict[str, Any]:
    return {
        "action": action,
        "policy": "plain_read",
        "exposure": "llm",
        "mode": "read",
        "httpMethod": "GET",
        "urlTemplate": f"https://example.test/{action}",
        "inputSchema": schema(),
        **fields,
    }


def test_saved_definition_round_trips_through_api_and_payload_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_admin_tools import _make_client

    client, _, _ = _make_client(monkeypatch)
    definition = {
        "slug": "edit_contract_e2e",
        "displayName": "Edit contract E2E",
        "description": "metadata",
        "operations": [
            operation(
                "list",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
                        "name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            )
        ],
    }
    assert client.post("/api/v1/admin/tools", json=definition).status_code == 201
    before = client.get("/api/v1/admin/tools/edit_contract_e2e").json()
    payload = run_node(
        "const values = " + json.dumps(before) + "; const base = " + json.dumps(before)
        + "; console.log(JSON.stringify(form.buildToolPayload(values, base)));"
    )
    saved = client.put("/api/v1/admin/tools/edit_contract_e2e", json=payload)
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/admin/tools/edit_contract_e2e").json() == before


def test_code_tool_edit_reason_is_separate_from_toggle_guard() -> None:
    js = ADMIN_JS.read_text()

    assert "definition ของ tool นี้แก้ไขจากหน้าเว็บไม่ได้" in js
    assert "editBtn.title = tool.toggleDisabledReason" not in js
    assert "toggleBtn.title = tool.toggleDisabledReason" in js


def test_authenticated_tool_payload_allows_preserve_header_edit_and_remove() -> None:
    result = run_node(
        "const base = {slug:'tool', displayName:'Tool', enabled:true, hasAuth:true, "
        "source:'db', authHeaderName:'X-API-Key', authScheme:'', operations:["
        + json.dumps(operation("read"))
        + "]};"
        "const values = {slug:'tool', displayName:'Tool', enabled:true, operations:base.operations};"
        "const edited = form.buildToolPayload(values, base);"
        "edited.authHeaderName = 'Authorization'; edited.authScheme = 'Bearer';"
        "const removed = form.buildToolPayload(values, base); removed.authEnvVar = null;"
        "console.log(JSON.stringify({editedLoss: form.detectMetadataLoss(base, edited), "
        "removedLoss: form.detectMetadataLoss(base, removed), edited, removed}));"
    )
    assert result["editedLoss"] == []
    assert result["removedLoss"] == []
    assert result["edited"]["authHeaderName"] == "Authorization"
    assert result["removed"]["authEnvVar"] is None


def test_removing_first_operation_matches_remaining_metadata_by_action() -> None:
    first = operation("first", description="removed")
    second = operation("second", description="keep me", limits={"maxCallsPerTurn": 7})
    baseline = {"slug": "tool", "displayName": "Tool", "operations": [first, second]}
    values = {"slug": "tool", "displayName": "Tool", "operations": [operation("second")]}
    result = run_node(
        "const values = " + json.dumps(values) + "; const base = " + json.dumps(baseline)
        + "; console.log(JSON.stringify(form.buildToolPayload(values, base)));"
    )
    assert result["operations"][0]["limits"] == {"maxCallsPerTurn": 7}
    assert "description" not in result["operations"][0]


def test_array_items_metadata_survives_edit() -> None:
    base = operation("array", inputSchema={"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}}, "required": [], "additionalProperties": False})
    values = copy.deepcopy(base)
    values["inputSchema"]["properties"]["tags"]["items"]["type"] = "integer"
    result = run_node("const v=" + json.dumps(values) + "; const b=" + json.dumps(base) + "; console.log(JSON.stringify(form.buildOperationPayload(v,b)));" )
    assert result["inputSchema"]["properties"]["tags"]["items"] == {"type": "integer", "enum": ["a", "b"]}


def test_nullable_anyof_constraints_survive_edit() -> None:
    prop = {"anyOf": [{"type": "string", "minLength": 3}, {"type": "null"}]}
    base = operation("nullable", inputSchema={"type": "object", "properties": {"name": prop}, "required": [], "additionalProperties": False})
    values = copy.deepcopy(base)
    values["inputSchema"]["properties"]["name"] = {"type": "string", "anyOf": prop["anyOf"]}
    result = run_node("const v=" + json.dumps(values) + "; const b=" + json.dumps(base) + "; console.log(JSON.stringify(form.buildOperationPayload(v,b)));" )
    assert result["inputSchema"]["properties"]["name"]["anyOf"][0]["minLength"] == 3


def test_new_submit_operation_is_available_to_prepare_cards() -> None:
    source = ADMIN_JS.read_text()
    add = source.index('views.addOperationBtn.addEventListener')
    refresh = source.index('querySelectorAll(".operation-card").forEach(syncSubmitField)', add)
    assert refresh < source.index('});', add)
    assert "if ($('[data-op=\"mode\"]', other).value === \"submit\")" in source


def test_build_try_payload_scenarios() -> None:
    # 1. New tool without credential
    new_no_auth = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'GET', urlTemplate: 'https://api.test', input: { q: 'hi' }"
        "})));"
    )
    assert "authEnvVar" not in new_no_auth
    assert "toolSlug" not in new_no_auth
    assert new_no_auth["httpMethod"] == "GET"
    assert new_no_auth["urlTemplate"] == "https://api.test"
    assert new_no_auth["input"] == {"q": "hi"}

    # 2. New tool with credential
    new_with_auth = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'POST', urlTemplate: 'https://api.test', authEnv: 'API_KEY', "
        "authHeader: 'X-API-Key', authScheme: ''"
        "})));"
    )
    assert new_with_auth["authEnvVar"] == "API_KEY"
    assert new_with_auth["authHeaderName"] == "X-API-Key"
    assert new_with_auth["authScheme"] == ""
    assert "toolSlug" not in new_with_auth

    # 3. Existing tool, preserve credential
    edit_preserve = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'GET', urlTemplate: 'https://api.test', toolSlug: 'oms_tool', "
        "hasSavedAuth: true, authHeader: 'X-API-Key', authScheme: ''"
        "})));"
    )
    assert edit_preserve["toolSlug"] == "oms_tool"
    assert "authEnvVar" not in edit_preserve
    assert edit_preserve["authHeaderName"] == "X-API-Key"
    assert edit_preserve["authScheme"] == ""

    # 4. Existing tool, replace credential
    edit_replace = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'GET', urlTemplate: 'https://api.test', toolSlug: 'oms_tool', "
        "hasSavedAuth: true, authEnv: 'NEW_VAR', authHeader: 'Authorization', authScheme: 'Bearer'"
        "})));"
    )
    assert edit_replace["toolSlug"] == "oms_tool"
    assert edit_replace["authEnvVar"] == "NEW_VAR"
    assert edit_replace["authHeaderName"] == "Authorization"
    assert edit_replace["authScheme"] == "Bearer"

    # 5. Existing tool, remove credential
    edit_remove = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'GET', urlTemplate: 'https://api.test', toolSlug: 'oms_tool', "
        "hasSavedAuth: true, removeAuth: true"
        "})));"
    )
    assert edit_remove["toolSlug"] == "oms_tool"
    assert edit_remove["authEnvVar"] is None

    # 6. Existing tool, change header/scheme only
    edit_header_only = run_node(
        "console.log(JSON.stringify(form.buildTryPayload({"
        "httpMethod: 'GET', urlTemplate: 'https://api.test', toolSlug: 'oms_tool', "
        "hasSavedAuth: true, authHeader: 'X-Custom', authScheme: 'Token'"
        "})));"
    )
    assert edit_header_only["toolSlug"] == "oms_tool"
    assert "authEnvVar" not in edit_header_only
    assert edit_header_only["authHeaderName"] == "X-Custom"
    assert edit_header_only["authScheme"] == "Token"
