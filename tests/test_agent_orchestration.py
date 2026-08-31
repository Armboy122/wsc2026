"""พฤติกรรมสนทนาของ Main Agent ก่อนเลือกเรียกเครื่องมือ"""

from __future__ import annotations

import pytest

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence, KnowledgeBackendError
from app.contracts import ChatRequest, Citation, ToolErrorCode
from app.llm import DemoLLMAdapter, LLMClient
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool
from app.tools.sabuy_tool import SabuyTool
from app.tools.voc_tool import VocTool


class FakeKnowledgeBackend:
    def __init__(self, responses: list[GroundedEvidence] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        self.calls.append((query, max_results))
        if self.responses:
            return self.responses.pop(0)
        return GroundedEvidence("", 0, ())


class UnavailableKnowledgeBackend(FakeKnowledgeBackend):
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        self.calls.append((query, max_results))
        raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, "บริการความรู้ไม่พร้อมใช้งาน")


def _registry(knowledge_backend: FakeKnowledgeBackend | None = None) -> ToolRegistry:
    return ToolRegistry(
        [
            KnowledgeTool(knowledge_backend or FakeKnowledgeBackend()),
            SabuyTool(),
            VocTool(),
            OmsTool(),
        ]
    )


def _agent(knowledge_backend: FakeKnowledgeBackend | None = None) -> MainAgent:
    return MainAgent(LLMClient(DemoLLMAdapter()), _registry(knowledge_backend))


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
async def test_knowledge_follow_up_reuses_verified_conversation_context() -> None:
    source_id = "PEA_01_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.docx"
    citation = Citation(
        sourceId=source_id,
        title="บริการขอใช้ไฟฟ้าใหม่สำหรับบุคคลธรรมดา",
        uri="knowledge://source/PEA_01.docx",
        snippet="เอกสารแสดงกรรมสิทธิ์หรือสิทธิครอบครอง",
    )
    backend = FakeKnowledgeBackend(
        [
            GroundedEvidence("เอกสารที่ต้องใช้มีบัตรประชาชนและหลักฐานสิทธิครอบครอง", 1, (citation,)),
            GroundedEvidence("ไม่จำเป็นต้องเป็นเจ้าของบ้าน แต่ต้องมีหลักฐานสิทธิครอบครอง", 1, (citation,)),
            GroundedEvidence("กรณีเช่าบ้านสามารถใช้สัญญาเช่าเป็นหลักฐานได้", 1, (citation,)),
            GroundedEvidence("ยื่นคำขอได้ที่สำนักงาน PEA ในพื้นที่", 1, (citation,)),
        ]
    )
    agent = _agent(backend)

    first = await agent.handle_chat(
        ChatRequest(message="ต้องการขอใช้ไฟฟ้าต้องมีเอกสารอะไรบ้าง")
    )
    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ผู้ขอต้องเป็นเจ้าของบ้านด้วยใช่ไหม",
        )
    )
    third = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ถ้าเช่าบ้านอยู่ล่ะ",
        )
    )
    fourth = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ยื่นที่ไหน",
        )
    )

    assert "ไม่จำเป็นต้องเป็นเจ้าของบ้าน" in second.message
    assert "สัญญาเช่า" in third.message
    assert "สำนักงาน PEA" in fourth.message
    assert len(backend.calls) == 4
    assert "คำถามปัจจุบัน" in backend.calls[1][0]
    assert "ผู้ขอต้องเป็นเจ้าของบ้านด้วยใช่ไหม" in backend.calls[1][0]
    assert source_id in backend.calls[1][0]
    assert "ถ้าเช่าบ้านอยู่ล่ะ" in backend.calls[2][0]
    assert "ยื่นที่ไหน" in backend.calls[3][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unrelated_message",
    [
        "ช่วยแต่งกลอนเกี่ยวกับฟุตบอล",
        "วันนี้อากาศเป็นอย่างไร",
        "ช่วยเขียนโค้ด Python",
    ],
)
async def test_unrelated_request_after_knowledge_is_not_forced_into_knowledge_tool(
    unrelated_message: str,
) -> None:
    citation = Citation(
        sourceId="PEA_01.docx",
        title="บริการขอใช้ไฟฟ้าใหม่",
        uri="knowledge://source/PEA_01.docx",
        snippet="สำเนาบัตรประจำตัวประชาชน",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence("ใช้บัตรประชาชน", 1, (citation,))]
    )
    agent = _agent(backend)
    first = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟฟ้าต้องใช้เอกสารอะไร"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message=unrelated_message,
        )
    )

    assert "ยังไม่รองรับ" in second.message
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_no_evidence_chat_offers_to_forward_the_question_to_staff() -> None:
    backend = FakeKnowledgeBackend([GroundedEvidence("", 0, ())])

    response = await _agent(backend).handle_chat(
        ChatRequest(message="ขอใช้ไฟฟ้าต้องใช้เอกสารอะไร")
    )

    assert "ขอส่งต่อคำถามนี้ให้เจ้าหน้าที่" in response.message
    assert response.citations == ()


@pytest.mark.asyncio
async def test_unavailable_knowledge_chat_offers_to_forward_the_question_to_staff() -> None:
    response = await _agent(UnavailableKnowledgeBackend()).handle_chat(
        ChatRequest(message="ขอใช้ไฟฟ้าต้องใช้เอกสารอะไร")
    )

    assert "ขอส่งต่อคำถามนี้ให้เจ้าหน้าที่" in response.message
    assert response.citations == ()


@pytest.mark.asyncio
async def test_no_evidence_turn_is_not_reused_as_knowledge_context() -> None:
    backend = FakeKnowledgeBackend([GroundedEvidence("", 0, ())])
    agent = _agent(backend)
    first = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟฟ้าต้องใช้เอกสารอะไร"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ผู้ขอต้องเป็นเจ้าของบ้านใช่ไหม",
        )
    )

    assert "ยังไม่รองรับ" in second.message
    assert len(backend.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operational_message", "expected_text"),
    [
        ("ต้องการชำระค่าไฟ", "paymentMethod"),
        ("ขอแจ้งปัญหาไฟฟ้า", "location"),
        ("แจ้งปัญหาการบริการ", "หัวข้อ"),
    ],
)
async def test_operational_intent_replaces_previous_knowledge_context(
    operational_message: str,
    expected_text: str,
) -> None:
    citation = Citation(
        sourceId="PEA_01.docx",
        title="บริการขอใช้ไฟฟ้าใหม่",
        uri="knowledge://source/PEA_01.docx",
        snippet="สำเนาบัตรประจำตัวประชาชน",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence("ใช้บัตรประชาชน", 1, (citation,))]
    )
    agent = _agent(backend)
    first = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟฟ้าต้องใช้เอกสารอะไร"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message=operational_message,
        )
    )

    assert expected_text in second.message
    assert len(backend.calls) == 1


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
