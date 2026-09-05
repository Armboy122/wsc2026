"""Regression coverage for grounded knowledge follow-ups."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.main_agent import MainAgent, _CAPABILITY_MESSAGE
from app.agent.operation_policy import OperationPolicy, OperationSpec
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import (
    Citation,
    ChatRequest,
    ToolAction,
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolResult,
    ToolResultStatus,
    ToolName,
    TraceEventKind,
)
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


class _PolicyGroundedTool:
    """Synthetic non-knowledge slug for testing policy-owned grounding behavior."""

    name = "document_answer_tool"
    actions = frozenset({"answer"})

    def __init__(self, citations: tuple[Citation, ...]) -> None:
        self._citations = citations

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"answerContext": "คำตอบจากเอกสารที่ตรวจสอบแล้ว"},
            citations=self._citations,
            simulation=True,
        )

    def reset(self) -> None:
        return None


class _ErrorWithCitationsTool:
    name = "error_citation_tool"
    actions = frozenset({"read"})

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            error=ToolError(code=ToolErrorCode.INTERNAL, message="internal tool detail"),
            citations=(_CITATION,),
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
async def test_error_result_citations_are_rejected_for_plain_read() -> None:
    call = ToolCall(call_id=uuid4(), name="error_citation_tool", action="read", input={})
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text="รายละเอียดภายใน"),
        LLMResponse(text="ขยายคำตอบ"),
    ])
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), _ErrorWithCitationsTool()],
        catalogue=(ToolDefinition("error_citation_tool", "อ่านข้อมูล", ("read",)),),
        operation_specs={("error_citation_tool", "read"): OperationSpec()},
    )
    agent = MainAgent(LLMClient(adapter), registry)

    first = await agent.handle_chat(ChatRequest(message="อ่านข้อมูล"))
    second = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="ขยายคำตอบ")
    )

    result = first.tool_results[0]
    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert result.data is None
    assert result.citations == ()
    assert first.citations == ()
    assert "internal tool detail" not in result.error.message
    assert second.message == _CAPABILITY_MESSAGE
    trace = agent.get_trace(first.trace_id)
    assert any(event.kind is TraceEventKind.POLICY_REJECTED for event in trace.events)


@pytest.mark.asyncio
async def test_grounded_policy_is_slug_agnostic_and_requires_citation() -> None:
    call = ToolCall(call_id=uuid4(), name="document_answer_tool", action="answer", input={})
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text="แต่งคำตอบเอง"),
        LLMResponse(text="ขยายคำตอบ"),
    ])
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), _PolicyGroundedTool(())],
        catalogue=(ToolDefinition("document_answer_tool", "ตอบจากเอกสาร", ("answer",)),),
        operation_specs={
            ("document_answer_tool", "answer"): OperationSpec(
                policy=OperationPolicy.GROUNDED_ANSWER,
            )
        },
    )
    agent = MainAgent(LLMClient(adapter), registry)

    response = await agent.handle_chat(ChatRequest(message="ถามเอกสาร"))
    followup = await agent.handle_chat(
        ChatRequest(conversationId=response.conversation_id, message="ขยายคำตอบ")
    )

    assert response.tool_results[0].name == "document_answer_tool"
    assert response.tool_results[0].status is ToolResultStatus.ERROR
    assert response.tool_results[0].error is not None
    assert response.tool_results[0].error.code is ToolErrorCode.INTERNAL
    assert "คำตอบจากเอกสารที่ตรวจสอบแล้ว" not in response.tool_results[0].error.message
    assert response.tool_results[0].data is None
    assert response.citations == ()
    assert "ขอส่งต่อคำถามนี้ให้เจ้าหน้าที่" in response.message
    assert followup.tool_results == ()
    assert followup.message == _CAPABILITY_MESSAGE
    assert response.conversation_id not in agent._grounded_conversations
    assert followup.conversation_id not in agent._grounded_conversations
    trace = agent.get_trace(response.trace_id)
    assert any(event.kind is TraceEventKind.POLICY_REJECTED for event in trace.events)


@pytest.mark.asyncio
async def test_grounded_policy_positive_synthetic_slug_preserves_citations_and_followup() -> None:
    citation = Citation(
        sourceId="DOC-1",
        title="เอกสารทดสอบ",
        uri="knowledge://source/DOC-1.docx",
        snippet="คำตอบจากเอกสารที่ตรวจสอบแล้ว",
    )
    call = ToolCall(call_id=uuid4(), name="document_answer_tool", action="answer", input={})
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text="ผลจากเอกสาร"),
        LLMResponse(text="ขยายคำตอบ"),
    ])
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), _PolicyGroundedTool((citation,))],
        catalogue=(ToolDefinition("document_answer_tool", "ตอบจากเอกสาร", ("answer",)),),
        operation_specs={
            ("document_answer_tool", "answer"): OperationSpec(
                policy=OperationPolicy.GROUNDED_ANSWER,
            )
        },
    )
    agent = MainAgent(LLMClient(adapter), registry)

    first = await agent.handle_chat(ChatRequest(message="ถามเอกสาร"))
    second = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="ขยายคำตอบ")
    )

    assert first.tool_results[0].name == "document_answer_tool"
    assert first.tool_results[0].status is ToolResultStatus.SUCCESS
    assert first.citations == (citation,)
    assert "คำตอบจากเอกสารที่ตรวจสอบแล้ว" in first.message
    assert second.tool_results == ()
    assert second.message == "ขยายคำตอบ"


@pytest.mark.asyncio
async def test_followup_policy_does_not_depend_on_knowledge_tool_name() -> None:
    backend = FakeKnowledgeBackend([
        GroundedEvidence("คำตอบจากเอกสาร", 1, (_CITATION,))
    ])
    call = _knowledge_call()
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text="ผลจากเครื่องมือ"),
        LLMResponse(text="ขยายคำตอบ"),
    ])
    registry = ToolRegistry(
        [KnowledgeTool(backend)],
        operation_specs={
            (ToolName.KNOWLEDGE.value, ToolAction.KNOWLEDGE_SEARCH.value): OperationSpec(
                policy=OperationPolicy.PLAIN_READ,
            )
        },
    )
    agent = MainAgent(LLMClient(adapter), registry)

    first = await agent.handle_chat(ChatRequest(message="ถามเอกสาร"))
    second = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="ขยายคำตอบ")
    )

    assert first.tool_results[0].status is ToolResultStatus.ERROR
    assert first.tool_results[0].error is not None
    assert first.tool_results[0].error.code is ToolErrorCode.INTERNAL
    assert first.tool_results[0].data is None
    assert first.tool_results[0].citations == ()
    assert first.citations == ()
    assert first.conversation_id not in agent._grounded_conversations
    assert second.message == _CAPABILITY_MESSAGE
    trace = agent.get_trace(first.trace_id)
    assert any(event.kind is TraceEventKind.POLICY_REJECTED for event in trace.events)


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
