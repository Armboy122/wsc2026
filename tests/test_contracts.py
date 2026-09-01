"""ทดสอบสัญญา MVP สองเครื่องมือผ่านทางเข้าสาธารณะและ MainAgent แบบแยกเครือข่าย"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import (
    ChatRequest,
    Citation,
    ToolAction,
    ToolCall,
    ToolName,
)
from app.llm import DemoLLMAdapter, LLMClient, LLMResponse, ScriptedLLMAdapter
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool


class _KnowledgeBackend:
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        citation = Citation(
            sourceId="PEA_DEMO.docx",
            title="คู่มือความปลอดภัย",
            uri="knowledge://source/PEA_DEMO.docx",
            snippet="ปฏิบัติตามคำแนะนำด้านความปลอดภัยของ PEA",
        )
        return GroundedEvidence(
            "ปฏิบัติตามคำแนะนำด้านความปลอดภัยของ PEA",
            1,
            (citation,),
        )


def _isolated_registry(post_counter: list[int] | None = None) -> ToolRegistry:
    """สร้าง registry สองเครื่องมือที่ห้ามออกเครือข่ายจริง"""

    def oms_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "caNumber": "100000000003",
                    "customerFound": True,
                    "network": {
                        "meterId": "M-DEMO",
                        "transformerId": "T-DEMO",
                        "feederId": "F-DEMO",
                    },
                    "activeEvent": None,
                    "recommendedAction": "CREATE_METER_EVENT",
                },
            )
        if post_counter is not None:
            post_counter[0] += 1
        if request.url.path.endswith("/outages/anonymous"):
            return httpx.Response(
                201,
                json={
                    "reportId": "OMS-ANON-DEMO",
                    "status": "RECEIVED",
                    "message": "รับแจ้งแล้ว",
                    "location": None,
                },
            )
        return httpx.Response(
            201,
            json={
                "eventId": "OMS-METER-DEMO",
                "caNumber": "100000000003",
                "level": "METER",
                "status": "RECEIVED",
                "message": "รับแจ้งแล้ว",
                "location": {"lat": 6.42, "lon": 101.8, "gisType": "POINT"},
            },
        )

    return ToolRegistry(
        [
            KnowledgeTool(_KnowledgeBackend()),
            OmsTool(base_url="http://oms.test/api/v1/oms", transport=httpx.MockTransport(oms_handler)),
        ]
    )


@pytest.fixture
def client() -> TestClient:
    # เปลี่ยนเฉพาะ DI ของ test เพื่อไม่ให้การทดสอบเรียก LLM, Knowledge หรือ OMS ภายนอก
    from app.core.di import agent_service
    from app.main import app

    agent_service.set_agent(MainAgent(LLMClient(DemoLLMAdapter()), _isolated_registry()))
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


def test_composition_registers_enabled_tools_and_serves_ui(client: TestClient) -> None:
    from app.main import tool_registry

    assert tool_registry.names == frozenset({ToolName.KNOWLEDGE, ToolName.OMS, ToolName.VOC})
    response = client.get("/")
    assert response.status_code == 200
    assert "PEA One Agent" in response.text


def test_oms_get_by_ca_is_typed_simulated_and_redacted(client: TestClient) -> None:
    body = chat(client, "check outage status for customer 100000000003")
    result = next(item for item in body["toolResults"] if item["action"] == "get_outage_by_ca")
    assert result["simulation"] is True
    assert result["data"]["caNumber"] == "100000000003"
    assert "M-DEMO" not in body["message"]
    assert "T-DEMO" not in body["message"]
    assert "F-DEMO" not in body["message"]


def test_anonymous_prepare_confirm_is_explicit_and_idempotent(client: TestClient) -> None:
    body = chat(
        client,
        "report a power outage; description: no power; location: demo lobby; contactPhone: 0800000001",
    )
    assert all(item["action"] != "submit_anonymous_outage" for item in body["toolResults"])
    pending = body["pendingAction"]
    assert pending["status"] == "pending_confirmation"
    assert pending["prepareAction"] == "prepare_anonymous_outage"

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


def test_anonymous_prepare_reject_is_terminal(client: TestClient) -> None:
    body = chat(
        client,
        "report a power outage; description: no power; location: demo lobby; contactPhone: 0800000002",
    )
    action_id = body["pendingAction"]["pendingActionId"]
    rejected = client.post(
        f"/api/v1/actions/{action_id}/reject",
        json={"reason": "ยกเลิกการสาธิต"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["pendingAction"]["status"] == "rejected"
    assert client.post(f"/api/v1/actions/{action_id}/confirm", json={}).status_code == 409


def test_prepared_input_is_reviewable_but_internal_key_is_hidden(client: TestClient) -> None:
    body = chat(
        client,
        "report a power outage; description: intermittent power; location: demo gate; contactPhone: 0800000003",
    )
    prepared = body["pendingAction"]["preparedInput"]
    assert prepared["description"] == "intermittent power"
    assert prepared["location"] == "demo gate"
    assert prepared["contactPhone"] == "0800000003"
    assert prepared["idempotencyKey"] == "[redacted]"


def test_multi_tool_uses_oms_and_knowledge_without_fake_citations(client: TestClient) -> None:
    body = chat(client, "outage status for customer 100000000003 and safety guidance")
    assert [item["name"] for item in body["toolResults"]] == [
        "oms_tool",
        "knowledge_tool",
    ]
    assert body["toolResults"][0]["simulation"] is True
    assert body["toolResults"][1]["simulation"] is False
    assert body["citations"]


def test_reset_clears_trace_and_pending_state(client: TestClient) -> None:
    body = chat(
        client,
        "report a power outage; description: no power; location: demo lobby; contactPhone: 0800000004",
    )
    action_id = body["pendingAction"]["pendingActionId"]
    trace_id = body["traceId"]
    assert client.post("/api/v1/reset", json={}).status_code == 200
    assert client.get(f"/api/v1/traces/{trace_id}").status_code == 404
    assert client.post(f"/api/v1/actions/{action_id}/confirm", json={}).status_code == 404


def test_llm_catalogue_never_advertises_internal_submit_actions() -> None:
    """แค็ตตาล็อกที่ compile จาก manifest จริงต้องไม่เปิด submit action ให้ LLM"""
    from app.agent.registry import BUILT_IN_CATALOGUE
    from app.core.config import load_settings
    from app.plugins import load_plugins

    plugins = load_plugins(load_settings())
    catalogue = BUILT_IN_CATALOGUE + tuple(plugin.tool_definition for plugin in plugins)
    advertised = {action for tool in catalogue for action in tool.actions}
    assert advertised == {
        "search",
        "get_outage_by_ca",
        "prepare_outage_with_ca",
        "prepare_anonymous_outage",
        "list_categories",
        "prepare_case",
        "get_case",
    }


@pytest.mark.asyncio
async def test_tool_facts_replace_contradictory_model_text() -> None:
    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.OMS,
                        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
                        input={"caNumber": "100000000003"},
                    ),
                )
            ),
            LLMResponse(text="FABRICATED: พื้นที่นี้ปลอดภัยแน่นอน"),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _isolated_registry())
    response = await agent.handle_chat(ChatRequest(message="check outage 100000000003"))
    assert "FABRICATED" not in response.message
    assert response.tool_results[0].action is ToolAction.OMS_GET_OUTAGE_BY_CA


@pytest.mark.asyncio
async def test_no_tool_response_never_exposes_reasoning_or_ungrounded_facts() -> None:
    leaked = "Analysis: อัตราค่าไฟอย่างเป็นทางการคือ 1.23 บาทต่อหน่วย"
    agent = MainAgent(
        LLMClient(ScriptedLLMAdapter([LLMResponse(text=leaked)])),
        _isolated_registry(),
    )
    response = await agent.handle_chat(ChatRequest(message="บอกข้อมูลที่แต่งขึ้น"))
    assert leaked not in response.message
    assert "ไม่สามารถเปิดเผยกระบวนการคิด" in response.message
    assert leaked not in str(agent.get_trace(response.trace_id).model_dump(mode="json"))


@pytest.mark.asyncio
async def test_multiple_oms_prepare_calls_fail_closed_before_execution() -> None:
    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.OMS,
                        action=ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
                        input={
                            "caNumber": "100000000003",
                            "description": "no power",
                            "idempotencyKey": "known-prepare",
                        },
                    ),
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.OMS,
                        action=ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE,
                        input={
                            "description": "fallen wire",
                            "location": "demo gate",
                            "contactPhone": "0800000005",
                            "idempotencyKey": "anonymous-prepare",
                        },
                    ),
                )
            )
        ]
    )
    agent = MainAgent(LLMClient(adapter), _isolated_registry())
    response = await agent.handle_chat(ChatRequest(message="prepare two writes"))
    assert response.pending_action is None
    assert response.tool_results == ()
    assert "มากกว่าหนึ่งรายการ" in response.message


@pytest.mark.asyncio
async def test_concurrent_confirms_share_one_oms_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    post_counter = [0]
    agent = MainAgent(
        LLMClient(DemoLLMAdapter()),
        _isolated_registry(post_counter),
    )
    chat_response = await agent.handle_chat(
        ChatRequest(
            message="report a power outage; description: no power; location: demo lobby; contactPhone: 0800000006"
        )
    )
    assert chat_response.pending_action is not None
    pending_id = chat_response.pending_action.pending_action_id
    original_execute = agent._execute_internal
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_execute(call, conversation_id, trace_id):
        if call.action is ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE:
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
    assert post_counter == [1]
