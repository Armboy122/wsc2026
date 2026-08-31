"""พฤติกรรมสนทนาของ Main Agent ก่อนเลือกเรียกเครื่องมือ"""

from __future__ import annotations

import pytest

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.gemini_file_search import GeminiFileSearchKnowledgeBackend
from app.contracts import ChatRequest
from app.llm import DemoLLMAdapter, LLMClient
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool
from app.tools.sabuy_tool import SabuyTool
from app.tools.voc_tool import VocTool


def _registry() -> ToolRegistry:
    return ToolRegistry(
        [
            KnowledgeTool(GeminiFileSearchKnowledgeBackend()),
            SabuyTool(),
            VocTool(),
            OmsTool(),
        ]
    )


def _agent() -> MainAgent:
    return MainAgent(LLMClient(DemoLLMAdapter()), _registry())


@pytest.mark.asyncio
async def test_incomplete_voc_intent_asks_for_case_details_without_tool_call() -> None:
    response = await _agent().handle_chat(ChatRequest(message="ต้องการร้องเรียนการบริการ"))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "หัวข้อ" in response.message
    assert "รายละเอียด" in response.message


@pytest.mark.asyncio
async def test_incomplete_payment_intent_asks_for_missing_payment_inputs() -> None:
    response = await _agent().handle_chat(ChatRequest(message="ต้องการชำระค่าไฟ"))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "บัญชี" in response.message
    assert "จำนวนเงิน" in response.message
    assert "paymentMethod" in response.message


@pytest.mark.asyncio
async def test_incomplete_outage_report_intent_asks_for_report_inputs() -> None:
    response = await _agent().handle_chat(ChatRequest(message="ต้องการแจ้งไฟดับ"))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "พื้นที่" in response.message
    assert "location" in response.message
    assert "symptoms" in response.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_text"),
    [
        ("ร้องเรียน", "หัวข้อ"),
        ("I want to make a payment", "paymentMethod"),
        ("report an outage", "location"),
    ],
)
async def test_incomplete_write_intent_paraphrases_ask_for_missing_inputs(
    message: str,
    expected_text: str,
) -> None:
    response = await _agent().handle_chat(ChatRequest(message=message))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert expected_text in response.message


@pytest.mark.asyncio
async def test_voc_follow_up_completes_the_intent_from_conversation_history() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="ต้องการร้องเรียนการบริการ"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="subject: เจ้าหน้าที่ให้บริการล่าช้า; detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ",
        )
    )

    assert [result.action.value for result in second.tool_results] == ["prepare_case"]
    assert second.pending_action is not None
    assert second.pending_action.prepared_input["category"] == "service"


@pytest.mark.asyncio
async def test_voc_three_turn_intake_keeps_the_original_intent() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="ร้องเรียน"))
    second = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="subject: บริการล่าช้า")
    )
    third = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ",
        )
    )

    assert second.tool_results == ()
    assert [result.action.value for result in third.tool_results] == ["prepare_case"]
    assert third.pending_action is not None


@pytest.mark.asyncio
async def test_oms_three_turn_intake_keeps_the_original_intent() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="report an outage"))
    second = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="BKK-01")
    )
    third = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="location: ถนนสุขุมวิท; symptoms: ไม่มีไฟฟ้าใช้",
        )
    )

    assert second.tool_results == ()
    assert [result.action.value for result in third.tool_results] == ["prepare_outage_report"]
    assert third.pending_action is not None


@pytest.mark.asyncio
async def test_json_planner_can_request_a_static_clarification() -> None:
    from app.llm import LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                text='{"message":"ignored freeform","toolCalls":[],"directResponse":"voc_details"}'
            )
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="ต้องการร้องเรียน"))

    assert "ignored freeform" not in response.message
    assert "หัวข้อ" in response.message


@pytest.mark.asyncio
async def test_invalid_direct_response_kind_fails_closed() -> None:
    from app.llm import LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter([LLMResponse(direct_response="unknown")])  # type: ignore[arg-type]
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="คำขอทั่วไป"))

    assert "ความรู้ PEA" in response.message
    assert response.tool_results == ()


@pytest.mark.asyncio
async def test_structured_direct_response_never_forwards_freeform_model_text() -> None:
    from app.llm import DirectResponseKind, LLMResponse, ScriptedLLMAdapter

    fabricated = "FABRICATED: ค่าไฟทุกบัญชีเป็นศูนย์"
    adapter = ScriptedLLMAdapter(
        [LLMResponse(text=fabricated, direct_response=DirectResponseKind.VOC_DETAILS)]
    )
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="ต้องการร้องเรียน"))

    assert fabricated not in response.message
    assert "หัวข้อ" in response.message
    assert "รายละเอียด" in response.message


@pytest.mark.asyncio
async def test_unsupported_intent_does_not_call_unrelated_knowledge_tool() -> None:
    response = await _agent().handle_chat(ChatRequest(message="วันนี้อากาศเป็นอย่างไร"))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "ไม่รองรับ" in response.message
