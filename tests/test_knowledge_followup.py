"""Regression coverage for grounded knowledge follow-ups."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.main_agent import MainAgent, _CAPABILITY_MESSAGE
from app.agent.operation_policy import OperationPolicy, OperationSpec
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import Citation, ChatRequest, ToolCall, ToolError, ToolErrorCode, ToolResult, ToolResultStatus, ToolName, ToolAction
from app.llm import LLMClient, LLMResponse, ScriptedLLMAdapter, ToolDefinition
from app.plugins.oms.response import OmsResponsePolicy
from app.plugins.voc.response import VocResponsePolicy
from app.tools.knowledge_tool import KnowledgeTool
from tests.test_agent_orchestration import FakeKnowledgeBackend, _registry


_CITATION = Citation(
    sourceId="PEA_01.docx",
    title="บริการขอใช้ไฟฟ้าใหม่",
    uri="knowledge://source/PEA_01.docx",
    snippet="สำเนาบัตรประชาชน",
)


def _knowledge_call() -> ToolCall:
    return ToolCall(
        call_id=uuid4(),
        name=ToolName.KNOWLEDGE,
        action=ToolAction.KNOWLEDGE_SEARCH,
        input={"query": "ขอใช้มิเตอร์ใหม่ต้องใช้เอกสารอะไร", "maxResults": 3},
    )


@pytest.mark.asyncio
async def test_knowledge_answer_allows_llm_formatting_followup_without_tool_call() -> None:
    call = _knowledge_call()
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text="พบเอกสารอ้างอิงแล้วครับ"),
        LLMResponse(text="1. บัตรประชาชน 2. หลักฐานสิทธิครอบครอง 3. แบบคำขอ"),
    ])
    backend = FakeKnowledgeBackend([
        GroundedEvidence("เอกสารที่ต้องใช้มีบัตรประชาชนและหลักฐานสิทธิครอบครอง", 1, (_CITATION,))
    ])
    agent = MainAgent(LLMClient(adapter), _registry(backend))

    first = await agent.handle_chat(ChatRequest(message="ขอใช้มิเตอร์ใหม่ ต้องใช้เอกสารอะไรบ้าง"))
    second = await agent.handle_chat(ChatRequest(
        conversationId=first.conversation_id,
        message="ลิสเป็นรายการ 1 2 3 ให้ฉันได้ป่ะ",
    ))

    assert second.tool_results == ()
    assert second.message != _CAPABILITY_MESSAGE
    assert second.message.startswith("1.")


class _PlainReadTool:
    name = "plain_tool"

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"value": "อ่านแล้ว"},
            simulation=True,
        )

    def reset(self) -> None:
        return None


@pytest.mark.asyncio
async def test_plain_read_result_does_not_mark_conversation_grounded() -> None:
    call = ToolCall(call_id=uuid4(), name="plain_tool", action="read", input={})
    adapter = ScriptedLLMAdapter([LLMResponse(tool_calls=(call,)), LLMResponse(text="อ่านแล้วครับ"), LLMResponse(text="ติดตามผล")])
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), _PlainReadTool()],
        catalogue=(ToolDefinition("plain_tool", "อ่านข้อมูล", ("read",)),),
        operation_specs={("plain_tool", "read"): OperationSpec()},
    )
    agent = MainAgent(LLMClient(adapter), registry)
    first = await agent.handle_chat(ChatRequest(message="อ่านข้อมูล"))
    second = await agent.handle_chat(ChatRequest(conversationId=first.conversation_id, message="ต่อด้วย"))

    assert first.conversation_id not in agent._grounded_conversations
    assert second.message == _CAPABILITY_MESSAGE


@pytest.mark.asyncio
async def test_failed_grounded_result_does_not_mark_conversation_grounded() -> None:
    call = _knowledge_call()
    adapter = ScriptedLLMAdapter([LLMResponse(tool_calls=(call,)), LLMResponse(text="ค้นหาไม่สำเร็จครับ"), LLMResponse(text="ติดตามผล")])
    agent = MainAgent(LLMClient(adapter), _registry())
    # Backend ที่ไม่มีหลักฐานทำให้ KnowledgeTool คืนผล error จริง
    class FailingBackend(FakeKnowledgeBackend):
        async def search(self, query: str, max_results: int) -> GroundedEvidence:
            raise RuntimeError("backend down")

    agent = MainAgent(LLMClient(adapter), _registry(FailingBackend()))
    first = await agent.handle_chat(ChatRequest(message="ค้นหาความรู้"))
    second = await agent.handle_chat(ChatRequest(conversationId=first.conversation_id, message="ต่อด้วย"))

    assert first.conversation_id not in agent._grounded_conversations
    assert second.message == _CAPABILITY_MESSAGE


def test_existing_oms_and_voc_ground_followup_policies_remain_enabled() -> None:
    success_oms = ToolResult(
        call_id=uuid4(), name=ToolName.OMS, action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        status=ToolResultStatus.SUCCESS, data={"activeEvent": None}, simulation=True,
    )
    success_voc = ToolResult(
        call_id=uuid4(), name=ToolName.VOC, action=ToolAction.VOC_GET_CASE,
        status=ToolResultStatus.SUCCESS, data={"caseId": "VOC-1"}, simulation=True,
    )
    assert OmsResponsePolicy().grounds_followup(success_oms)
    assert VocResponsePolicy().grounds_followup(success_voc)
