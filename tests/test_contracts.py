"""Lead-owned public-entry smoke tests for the frozen MVP contracts."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.contracts import ToolName


@pytest.fixture
def client() -> TestClient:
    # Import the composition root lazily so platform unit tests that replace the
    # global DI container cannot be polluted during pytest collection.
    from app.main import app, main_agent
    from app.core.di import agent_service

    agent_service.set_agent(main_agent)
    with TestClient(app) as test_client:
        assert test_client.post("/api/v1/reset", json={}).status_code == 200
        yield test_client


def chat(client: TestClient, message: str) -> dict:
    response = client.post("/api/v1/chat", json={"message": message})
    assert response.status_code == 200, response.text
    body = response.json()
    UUID(body["conversationId"])
    UUID(body["traceId"])
    return body


def test_composition_registers_exactly_four_tools_and_serves_ui(client: TestClient) -> None:
    from app.main import tool_registry

    assert tool_registry.names == frozenset(ToolName)
    response = client.get("/")
    assert response.status_code == 200
    assert "PEA One Agent" in response.text
    assert "SIMULATED BACKEND" in response.text


def test_oms_status_is_simulated_and_safety_first(client: TestClient) -> None:
    body = chat(client, "Check outage status for BKK-01")
    result = next(item for item in body["toolResults"] if item["action"] == "get_outage_status")
    assert result["simulation"] is True
    assert result["data"]["areaCode"] == "BKK-01"
    safety = result["data"]["safetyMessage"]
    assert safety
    assert body["message"].startswith(safety)


def test_sabuy_prepare_confirm_is_explicit_and_idempotent(client: TestClient) -> None:
    body = chat(client, "Pay 10 THB for account PEA-1001; paymentMethod: demo_card")
    assert all(item["action"] != "submit_payment" for item in body["toolResults"])
    pending = body["pendingAction"]
    assert pending["status"] == "pending_confirmation"
    assert pending["prepareAction"] == "prepare_payment"

    action_id = pending["pendingActionId"]
    first = client.post(f"/api/v1/actions/{action_id}/confirm", json={})
    second = client.post(f"/api/v1/actions/{action_id}/confirm", json={})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["pendingAction"]["status"] == "submitted"
    assert first.json()["toolResult"]["simulation"] is True

    trace = client.get(f"/api/v1/traces/{first.json()['traceId']}")
    assert trace.status_code == 200
    assert [event["kind"] for event in trace.json()["events"]].count("action_submitted") == 1


def test_voc_prompt_prepares_then_rejects_terminally(client: TestClient) -> None:
    body = chat(
        client,
        "Complaint; subject: Incorrect electricity bill; detail: The displayed total differs from my statement",
    )
    pending = body["pendingAction"]
    assert pending["prepareAction"] == "prepare_case"
    action_id = pending["pendingActionId"]

    rejected = client.post(f"/api/v1/actions/{action_id}/reject", json={"reason": "Cancel demo"})
    assert rejected.status_code == 200
    assert rejected.json()["pendingAction"]["status"] == "rejected"
    assert client.post(f"/api/v1/actions/{action_id}/confirm", json={}).status_code == 409


def test_thai_knowledge_prompt_routes_to_hosted_knowledge(client: TestClient) -> None:
    body = chat(client, "ค้นหาข้อมูลอัตราค่าไฟ On-Peak และช่วงเวลาที่ใช้")
    assert [item["name"] for item in body["toolResults"]] == ["knowledge_tool"]


def test_thai_payment_preserves_user_amount(client: TestClient) -> None:
    body = chat(client, "ฉันต้องการชำระค่าไฟ 350 บาท ด้วยบัตร สำหรับบัญชี PEA-1001")
    pending = body["pendingAction"]
    assert pending["prepareAction"] == "prepare_payment"
    assert pending["preparedInput"]["amountThb"] == "350.00"


def test_multi_tool_uses_oms_and_knowledge_without_fake_citations(client: TestClient) -> None:
    body = chat(client, "Check outage BKK-01 and search safety policy information")
    names = [item["name"] for item in body["toolResults"]]
    assert names == ["oms_tool", "knowledge_tool"]
    assert body["toolResults"][0]["simulation"] is True
    assert body["toolResults"][1]["simulation"] is False
    if body["toolResults"][1]["status"] == "error":
        assert body["toolResults"][1]["citations"] == []
        assert body["citations"] == []


def test_reset_clears_trace_and_pending_state(client: TestClient) -> None:
    body = chat(client, "Pay 10 THB for account PEA-1001; paymentMethod: demo_card")
    action_id = body["pendingAction"]["pendingActionId"]
    trace_id = body["traceId"]
    assert client.post("/api/v1/reset", json={}).status_code == 200
    assert client.get(f"/api/v1/traces/{trace_id}").status_code == 404
    assert client.post(f"/api/v1/actions/{action_id}/confirm", json={}).status_code == 404
