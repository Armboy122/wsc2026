"""MainAgent contract tests (isolated network); public Chat routes were removed in Story 3 Ticket 001."""

from __future__ import annotations

from uuid import uuid4


import httpx
import pytest

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
from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.oms.response import OmsResponsePolicy
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
        ],
        response_policies=(OmsResponsePolicy(),),
    )


def test_llm_catalogue_never_advertises_internal_submit_actions() -> None:
    """แค็ตตาล็อกที่ compile จาก manifest จริงต้องไม่เปิด submit action ให้ LLM"""
    from app.agent.registry import BUILT_IN_CATALOGUE
    from app.plugins import load_plugins
    from app.plugins.tests._legacy_settings import legacy_plugin_settings as load_settings

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
        LLMClient(DemoLLMAdapter((OmsDemoBehavior(),))),
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


def test_redacted_key_still_allows_internal_submission() -> None:
    """การปกปิดต้องเกิดตอน serialize เท่านั้น ไม่ใช่ทำให้ค่าภายในหายไป"""
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.contracts import PendingAction, PendingActionStatus, ToolAction, ToolName

    now = datetime.now(UTC)
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_name=ToolName.OMS,
        prepare_action=ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE,
        submit_action=ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE,
        prepared_input={"description": "no power"},
        summary="เตรียมรายการแล้ว",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="PAN-123456",
        created_at=now,
        updated_at=now,
    )

    assert pending.idempotency_key == "PAN-123456"
    assert pending.model_dump(by_alias=True)["idempotencyKey"] == "[redacted]"
