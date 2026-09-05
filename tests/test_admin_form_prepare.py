from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "web" / "admin-form.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_prepare_submit_payload_rules_and_mode_round_trip() -> None:
    script = r'''
import { buildOperationPayload, buildToolPayload, validateToolPayload } from "./web/admin-form.js";
const read = { action: "get", mode: "read", policy: "plain_read", exposure: "llm", httpMethod: "GET", urlTemplate: "https://example.test/{id}" };
const prepare = buildOperationPayload({ ...read, mode: "prepare", policy: "write_confirm", submitAction: "send", urlTemplate: "https://must-not-send.test" });
if (prepare.httpMethod !== null || prepare.urlTemplate !== null || prepare.submitAction !== "send") throw new Error(JSON.stringify(prepare));
const backToRead = buildOperationPayload({ ...prepare, mode: "read", httpMethod: read.httpMethod, urlTemplate: read.urlTemplate });
if (backToRead.urlTemplate !== read.urlTemplate) throw new Error("read URL was not preserved by caller state");
const payload = buildToolPayload({ slug: "demo", displayName: "Demo", operations: [prepare, { action: "send", mode: "submit", policy: "write_confirm", exposure: "llm", httpMethod: "POST", urlTemplate: "https://example.test" }] });
if (payload.operations[1].exposure !== "internal" || validateToolPayload(payload) !== null) throw new Error(JSON.stringify(payload));
'''
    result = subprocess.run(
        [shutil.which("node") or "node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_api_accepts_prepare_submit_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_admin_tools import _make_client

    client, _, _ = _make_client(monkeypatch)
    schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    definition = {
        "slug": "prepare_submit_demo", "displayName": "Prepare submit demo",
        "operations": [
            {"action": "prepare", "policy": "write_confirm", "exposure": "llm", "mode": "prepare", "submitAction": "submit", "httpMethod": None, "urlTemplate": None, "inputSchema": schema},
            {"action": "submit", "policy": "write_confirm", "exposure": "internal", "mode": "submit", "httpMethod": "POST", "urlTemplate": "https://example.test/items", "inputSchema": schema},
        ],
    }
    response = client.post("/api/v1/admin/tools", json=definition)
    assert response.status_code == 201, response.text
    saved = client.get("/api/v1/admin/tools/prepare_submit_demo")
    assert saved.status_code == 200
    operation = saved.json()["operations"][0]
    assert operation["httpMethod"] is None
    assert operation["urlTemplate"] is None
    assert operation["submitAction"] == "submit"
