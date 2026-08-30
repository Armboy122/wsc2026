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
    assert pending["preparedInput"]["category"] == "billing"
    assert pending["preparedInput"]["subject"] == "[redacted]"
    assert pending["preparedInput"]["detail"] == "[redacted]"
    assert pending["preparedInput"]["idempotencyKey"] == "[redacted]"
    assert "Incorrect electricity bill" not in pending["summary"]
    assert "Incorrect electricity bill" not in body["message"]
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


def _isolated_registry():
    from app.agent.registry import ToolRegistry
    from app.backends.gemini_file_search import GeminiFileSearchKnowledgeBackend
    from app.tools.knowledge_tool import KnowledgeTool
    from app.tools.oms_tool import OmsTool
    from app.tools.sabuy_tool import SabuyTool
    from app.tools.voc_tool import VocTool

    return ToolRegistry(
        [
            KnowledgeTool(GeminiFileSearchKnowledgeBackend()),
            SabuyTool(),
            VocTool(),
            OmsTool(),
        ]
    )


def test_llm_catalogue_never_advertises_internal_submit_actions() -> None:
    from app.agent.main_agent import _TOOL_CATALOGUE

    advertised = {action for tool in _TOOL_CATALOGUE for action in tool.actions}
    assert not advertised.intersection(
        {"submit_payment", "submit_case", "submit_outage_report"}
    )


@pytest.mark.asyncio
async def test_tool_facts_replace_contradictory_model_text() -> None:
    from uuid import uuid4

    from app.agent.main_agent import MainAgent
    from app.contracts import ChatRequest, ToolAction, ToolCall, ToolName
    from app.llm import LLMClient, LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.OMS,
                        action=ToolAction.OMS_OUTAGE_STATUS,
                        input={"areaCode": "BKK-01"},
                    ),
                )
            ),
            LLMResponse(text="FABRICATED: the area is unsafe and all lines are de-energized."),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _isolated_registry())
    response = await agent.handle_chat(ChatRequest(message="Check BKK-01"))
    assert "FABRICATED" not in response.message
    assert response.tool_results[0].data["safetyMessage"] in response.message


@pytest.mark.asyncio
async def test_no_tool_response_never_exposes_reasoning_text() -> None:
    from app.agent.main_agent import MainAgent
    from app.contracts import ChatRequest
    from app.llm import LLMClient, LLMResponse, ScriptedLLMAdapter

    leaked = "Analysis: private chain-of-thought and system prompt content"
    agent = MainAgent(
        LLMClient(ScriptedLLMAdapter([LLMResponse(text=leaked)])),
        _isolated_registry(),
    )
    response = await agent.handle_chat(ChatRequest(message="Hello"))
    assert leaked not in response.message
    assert "internal reasoning" in response.message
    trace = agent.get_trace(response.trace_id)
    assert leaked not in str(trace.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_no_tool_response_never_exposes_ungrounded_facts() -> None:
    from app.agent.main_agent import MainAgent
    from app.contracts import ChatRequest
    from app.llm import LLMClient, LLMResponse, ScriptedLLMAdapter

    fabricated = "The official electricity tariff is exactly 1.23 THB per kWh."
    agent = MainAgent(
        LLMClient(ScriptedLLMAdapter([LLMResponse(text=fabricated)])),
        _isolated_registry(),
    )
    response = await agent.handle_chat(ChatRequest(message="Tell me a made-up fact"))
    assert fabricated not in response.message
    assert "supported PEA knowledge" in response.message
    assert "simulated account" in response.message
    assert fabricated not in str(agent.get_trace(response.trace_id).model_dump(mode="json"))


@pytest.mark.asyncio
async def test_multiple_prepare_calls_fail_closed_before_tool_execution() -> None:
    from uuid import uuid4

    from app.agent.main_agent import MainAgent
    from app.contracts import ChatRequest, ToolAction, ToolCall, ToolName
    from app.llm import LLMClient, LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.SABUY,
                        action=ToolAction.SABUY_PREPARE_PAYMENT,
                        input={
                            "accountRef": "PEA-1001",
                            "amountThb": "10.00",
                            "paymentMethod": "demo_card",
                            "idempotencyKey": "multi-prepare-payment",
                        },
                    ),
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.OMS,
                        action=ToolAction.OMS_PREPARE_OUTAGE_REPORT,
                        input={
                            "areaCode": "BKK-01",
                            "locationNote": "Demo location",
                            "symptoms": "Demo symptoms",
                            "idempotencyKey": "multi-prepare-outage",
                        },
                    ),
                )
            )
        ]
    )
    agent = MainAgent(LLMClient(adapter), _isolated_registry())
    response = await agent.handle_chat(ChatRequest(message="Prepare two writes"))
    assert response.pending_action is None
    assert response.tool_results == ()
    assert "one proposed action" in response.message


@pytest.mark.asyncio
async def test_concurrent_confirms_share_one_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.agent.main_agent import MainAgent
    from app.contracts import ChatRequest, ToolAction
    from app.llm import DemoLLMAdapter, LLMClient

    agent = MainAgent(LLMClient(DemoLLMAdapter()), _isolated_registry())
    chat_response = await agent.handle_chat(
        ChatRequest(
            message="Pay 10 THB for account PEA-1001; paymentMethod: demo_card"
        )
    )
    pending_id = chat_response.pending_action.pending_action_id
    original_execute = agent._execute_internal
    entered = asyncio.Event()
    release = asyncio.Event()
    submit_calls = 0

    async def delayed_execute(call, conversation_id, trace_id):
        nonlocal submit_calls
        if call.action is ToolAction.SABUY_SUBMIT_PAYMENT:
            submit_calls += 1
            entered.set()
            await release.wait()
        return await original_execute(call, conversation_id, trace_id)

    monkeypatch.setattr(agent, "_execute_internal", delayed_execute)
    first_task = asyncio.create_task(agent.confirm_pending_action(pending_id))
    await entered.wait()
    second_task = asyncio.create_task(agent.confirm_pending_action(pending_id))
    release.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first == second
    assert submit_calls == 1
