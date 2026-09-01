"""พฤติกรรมสนทนาของ Main Agent ก่อนเลือกเรียกเครื่องมือ"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence, KnowledgeBackendError
from app.contracts import (
    ChatRequest,
    Citation,
    ToolAction,
    ToolCall,
    ToolErrorCode,
    ToolName,
    ToolResultStatus,
)
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
    assert "เลือกประเภทเรื่อง" not in response.message


@pytest.mark.asyncio
async def test_voc_intake_uses_plain_language_and_recognises_service_category() -> None:
    response = await _agent().handle_chat(
        ChatRequest(message="อยากร้องเรียนการให้บริการหน่อยครับ")
    )

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "หัวข้อ" in response.message
    assert "เลือกประเภทเรื่อง" not in response.message
    assert "`" not in response.message


@pytest.mark.asyncio
async def test_voc_category_selection_advances_without_repeating_choices() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="อยากร้องเรียนครับ"))
    response = await agent.handle_chat(
        ChatRequest(conversationId=first.conversation_id, message="1. แจ้งปัญหาคุณภาพไฟฟ้า")
    )

    assert "1. แจ้งปัญหาคุณภาพไฟฟ้า" in first.message
    assert "6. ชื่นชม เสนอแนะ ข้อคิดเห็น" in first.message
    assert response.tool_results == ()
    assert "หัวข้อ" in response.message
    assert "เลือกประเภทเรื่อง" not in response.message
    assert "power_quality" not in response.message
    assert "{" not in response.message


@pytest.mark.asyncio
async def test_generic_topic_question_does_not_route_to_voc_without_complaint_context() -> None:
    response = await _agent().handle_chat(
        ChatRequest(message="มีหัวข้ออะไรบ้างเกี่ยวกับค่าไฟ")
    )

    assert [result.action.value for result in response.tool_results] == ["search"]
    assert all(result.name.value != "voc_tool" for result in response.tool_results)


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
        ("ร้องเรียน", "เลือกประเภทเรื่อง"),
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
            message="subject: เจ้าหน้าที่ให้บริการล่าช้า; detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ; contactName: สมชาย ใจดี; contactPhone: 0812345678; location: ถนนสุขุมวิท กรุงเทพฯ",
        )
    )

    assert [result.action.value for result in second.tool_results] == ["prepare_case"]
    assert second.pending_action is not None
    assert second.pending_action.prepared_input["category"] == "service"
    assert second.message.startswith("เตรียมเรื่องร้องเรียนประเภท แจ้งปัญหาด้านบริการ")
    assert " service" not in second.message
    assert " service" not in second.pending_action.summary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category_label", "expected_category"),
    [
        ("แจ้งปัญหาคุณภาพไฟฟ้า", "power_quality"),
        ("ชื่นชม เสนอแนะ ข้อคิดเห็น", "stakeholder_feedback"),
    ],
)
async def test_voc_category_choice_is_used_when_preparing_case(
    category_label: str,
    expected_category: str,
) -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="อยากร้องเรียนครับ"))
    response = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message=(
                f"{category_label}; subject: ทดสอบหัวข้อ; detail: ทดสอบรายละเอียด; "
                "contactName: สมชาย ใจดี; contactPhone: 0812345678; "
                "location: ถนนสุขุมวิท"
            ),
        )
    )

    assert response.pending_action is not None
    assert response.pending_action.prepared_input["category"] == expected_category


@pytest.mark.asyncio
async def test_voc_follow_up_asks_step_by_step_for_missing_fields() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="ต้องการร้องเรียนการบริการ"))

    # มีแค่ subject + detail → ต้องถามชื่อผู้แจ้งก่อน
    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="subject: เจ้าหน้าที่ให้บริการล่าช้า; detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ",
        )
    )
    assert second.tool_results == ()
    assert second.pending_action is None
    assert "ชื่อผู้ร้องเรียน" in second.message

    # เพิ่มชื่อ → ต้องถามเบอร์โทรก่อน
    third = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="contactName: สมชาย ใจดี",
        )
    )
    assert third.tool_results == ()
    assert "เบอร์โทร" in third.message

    # เพิ่มเบอร์โทร → ต้องถามสถานที่ก่อน
    fourth = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="contactPhone: 0812345678",
        )
    )
    assert fourth.tool_results == ()
    assert "สถานที่" in fourth.message

    # ครบทุกฟิลด์ → เตรียมเคส
    fifth = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="location: ถนนสุขุมวิท กรุงเทพฯ",
        )
    )
    assert [result.action.value for result in fifth.tool_results] == ["prepare_case"]
    assert fifth.pending_action is not None


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
            message="detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ; contactName: สมชาย ใจดี; contactPhone: 0812345678; location: ถนนสุขุมวิท",
        )
    )

    assert second.tool_results == ()
    assert [result.action.value for result in third.tool_results] == ["prepare_case"]
    assert third.pending_action is not None


@pytest.mark.asyncio
async def test_voc_tracking_uses_voc_id_and_key() -> None:
    agent = _agent()
    first = await agent.handle_chat(
        ChatRequest(
            message="ต้องการร้องเรียนการบริการ; subject: บริการล่าช้า; detail: ไม่มีการติดต่อกลับ; contactName: สมชาย ใจดี; contactPhone: 0812345678; location: ถนนสุขุมวิท"
        )
    )
    assert [result.action.value for result in first.tool_results] == ["prepare_case"]
    assert first.pending_action is not None

    confirmed = await agent.confirm_pending_action(first.pending_action.pending_action_id)
    submitted = confirmed.tool_result
    assert submitted is not None and submitted.status is ToolResultStatus.SUCCESS
    voc_id = submitted.data["vocId"]
    tracking_key = submitted.data["trackingKey"]

    tracked = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message=f"ติดตามเรื่องร้องเรียน; vocId: {voc_id}; trackingKey: {tracking_key}",
        )
    )
    assert [result.action.value for result in tracked.tool_results] == ["get_case"]
    assert tracked.tool_results[0].data["status"] == "submitted"
    assert tracked.tool_results[0].data["vocId"] == voc_id


@pytest.mark.asyncio
async def test_voc_tracking_without_key_asks_for_inputs() -> None:
    agent = _agent()
    response = await agent.handle_chat(
        ChatRequest(message="ติดตามเรื่องร้องเรียน; vocId: SIM-CASE-000001")
    )
    assert response.tool_results == ()
    assert response.pending_action is None
    assert "คีย์ติดตาม" in response.message


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
    assert "เลือกประเภทเรื่อง" in response.message


@pytest.mark.asyncio
async def test_provider_failure_during_voc_intake_keeps_the_clarification_flow() -> None:
    from app.llm import DirectResponseKind, LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [LLMResponse(direct_response=DirectResponseKind.VOC_DETAILS)]
    )
    agent = MainAgent(LLMClient(adapter), _registry())
    first = await agent.handle_chat(ChatRequest(message="ร้องเรียนการบริการหน่อย"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ไฟดับบ่อยมากที่บ้านฉัน",
        )
    )

    assert "บริการผู้ช่วยไม่พร้อมใช้งาน" not in second.message
    assert "รายละเอียด" in second.message
    assert "`" not in second.message
    assert second.tool_results == ()


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
    assert "เลือกประเภทเรื่อง" in response.message


@pytest.mark.asyncio
async def test_unsupported_intent_does_not_call_unrelated_knowledge_tool() -> None:
    response = await _agent().handle_chat(ChatRequest(message="วันนี้อากาศเป็นอย่างไร"))

    assert response.tool_results == ()
    assert response.pending_action is None
    assert "ไม่รองรับ" in response.message


@pytest.mark.asyncio
async def test_agent_loop_is_bounded_to_twelve_tool_calls() -> None:
    from app.llm import LLMResponse, ScriptedLLMAdapter

    citation = Citation(
        sourceId="LOOP_BOUNDARY",
        title="ขอบเขตลูป",
        uri="knowledge://source/loop-boundary.docx",
        snippet="ข้อมูลที่ตรวจสอบแล้ว",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence(f"คำตอบ {index}", 1, (citation,)) for index in range(12)]
    )
    responses = [
        LLMResponse(
            tool_calls=(
                ToolCall(
                    call_id=uuid4(),
                    name=ToolName.KNOWLEDGE,
                    action=ToolAction.KNOWLEDGE_SEARCH,
                    input={"query": f"คำถาม {index}", "maxResults": 1},
                ),
            )
        )
        for index in range(13)
    ]
    agent = MainAgent(LLMClient(ScriptedLLMAdapter(responses)), _registry(backend))

    response = await agent.handle_chat(ChatRequest(message="ทดสอบขอบเขตลูป"))

    assert len(backend.calls) == 12
    assert len(response.tool_results) == 12


@pytest.mark.asyncio
async def test_repeated_identical_knowledge_call_uses_first_grounded_result_only() -> None:
    from app.llm import LLMResponse, ScriptedLLMAdapter

    citation = Citation(
        sourceId="PEA_NEW_SERVICE",
        title="เอกสารขอใช้ไฟฟ้าใหม่",
        uri="knowledge://source/new-service.docx",
        snippet="ใช้สำเนาบัตรประชาชนและทะเบียนบ้าน",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence("ใช้สำเนาบัตรประชาชนและทะเบียนบ้าน", 1, (citation,))]
    )
    first_call = ToolCall(
        call_id=uuid4(),
        name=ToolName.KNOWLEDGE,
        action=ToolAction.KNOWLEDGE_SEARCH,
        input={"query": "ขอใช้ไฟใหม่ใช้เอกสารอะไร", "maxResults": 3},
    )
    repeated_call = first_call.model_copy(update={"call_id": uuid4()})
    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(tool_calls=(first_call,)),
            LLMResponse(tool_calls=(repeated_call,)),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry(backend))

    response = await agent.handle_chat(
        ChatRequest(message="ขอใช้ไฟใหม่ใช้เอกสารอะไร")
    )

    assert len(backend.calls) == 1
    assert len(response.tool_results) == 1
    assert response.message == "ใช้สำเนาบัตรประชาชนและทะเบียนบ้าน"
    assert response.citations == (citation,)
    assert "ยังไม่พบคำตอบ" not in response.message


@pytest.mark.asyncio
async def test_grounded_multi_applicant_answer_asks_useful_clarification() -> None:
    citation = Citation(
        sourceId="NEW_SERVICE",
        title="เอกสารขอใช้ไฟฟ้าใหม่",
        uri="knowledge://source/new-service.docx",
        snippet="เอกสารแตกต่างกันสำหรับบุคคลธรรมดาและนิติบุคคล",
    )
    backend = FakeKnowledgeBackend(
        [
            GroundedEvidence(
                "บุคคลธรรมดาใช้บัตรประชาชน ส่วนนิติบุคคลใช้หนังสือรับรองบริษัท",
                1,
                (citation,),
            )
        ]
    )

    response = await _agent(backend).handle_chat(
        ChatRequest(message="ขอใช้ไฟใหม่ต้องเตรียมเอกสารอะไรบ้าง")
    )

    assert "บุคคลธรรมดาหรือนิติบุคคล" in response.message
    assert response.citations == (citation,)
    assert "หนังสือรับรองบริษัท" not in response.message


@pytest.mark.asyncio
async def test_explicit_voc_category_advances_without_repeating_category_choices() -> None:
    response = await _agent().handle_chat(
        ChatRequest(message="อยากร้องเรียนเรื่องคุณภาพของไฟฟ้า")
    )

    assert response.pending_action is None
    assert "หัวข้อ" in response.message
    assert "เลือกประเภทเรื่อง" not in response.message
    assert "1. แจ้งปัญหาคุณภาพไฟฟ้า" not in response.message


@pytest.mark.asyncio
async def test_knowledge_question_interrupts_and_then_resumes_voc_intake() -> None:
    citation = Citation(
        sourceId="POWER_QUALITY",
        title="คุณภาพไฟฟ้า",
        uri="knowledge://source/power-quality.docx",
        snippet="ไฟตกอาจเกี่ยวข้องกับแรงดันไฟฟ้าไม่คงที่",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence("ไฟตกอาจเกี่ยวข้องกับแรงดันไฟฟ้าไม่คงที่", 1, (citation,))]
    )
    agent = _agent(backend)
    started = await agent.handle_chat(
        ChatRequest(message="อยากร้องเรียนเรื่องคุณภาพของไฟฟ้า")
    )

    knowledge = await agent.handle_chat(
        ChatRequest(
            conversationId=started.conversation_id,
            message="ไฟตกเกิดจากอะไร",
        )
    )
    resumed = await agent.handle_chat(
        ChatRequest(conversationId=started.conversation_id, message="ดำเนินต่อ")
    )

    assert [result.action.value for result in knowledge.tool_results] == ["search"]
    assert knowledge.citations == (citation,)
    assert "แรงดันไฟฟ้าไม่คงที่" in knowledge.message
    assert "หัวข้อ" in resumed.message
    assert "เลือกประเภทเรื่อง" not in resumed.message
