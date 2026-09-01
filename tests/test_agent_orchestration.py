"""พฤติกรรมสนทนาของ Main Agent ก่อนเลือกเรียกเครื่องมือ"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence, KnowledgeBackendError
from app.contracts import (
    ChatRequest,
    Citation,
    ToolAction,
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
)
from app.llm import DemoLLMAdapter, LLMClient
from app.llm.prompting import SYSTEM_PROMPT
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool


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
    """ใช้ OMS transport จำลองเพื่อกัน test ติดต่อปลายทางภายนอก"""
    def oms_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"caNumber": "100000000003", "customerFound": True, "network": {"meterId": "M", "transformerId": "T", "feederId": "F"}, "activeEvent": None, "recommendedAction": "CREATE_METER_EVENT"})
        if request.url.path == "/api/v1/outages/anonymous":
            return httpx.Response(201, json={"reportId": "OMS-ANON-1", "status": "RECEIVED", "message": "รับแจ้งแล้ว", "location": None})
        return httpx.Response(201, json={"eventId": "OMS-METER-1", "caNumber": "100000000003", "level": "METER", "status": "RECEIVED", "message": "รับแจ้งแล้ว", "location": {"lat": 6.42, "lon": 101.8, "gisType": "POINT"}})
    return ToolRegistry(
        [
            KnowledgeTool(knowledge_backend or FakeKnowledgeBackend()),
            OmsTool(base_url="http://oms.test/api/v1/oms", transport=httpx.MockTransport(oms_handler)),
        ]
    )


def _agent(knowledge_backend: FakeKnowledgeBackend | None = None) -> MainAgent:
    return MainAgent(LLMClient(DemoLLMAdapter()), _registry(knowledge_backend))


def test_system_prompt_defines_outage_status_follow_up_behavior() -> None:
    assert "การติดตามสถานะเหตุที่เคยตรวจแล้ว" in SYSTEM_PROMPT
    assert "get_outage_by_ca" in SYSTEM_PROMPT
    assert "ระบบยืนยันได้เพียงว่าเหตุอยู่ระหว่างดำเนินการ" in SYSTEM_PROMPT
    assert "ห้ามใช้ `unsupported`" in SYSTEM_PROMPT
    assert "คำขอบคุณ" in SYSTEM_PROMPT
    assert "thanks" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_text_agent_answers_thanks_naturally() -> None:
    response = await _agent().handle_chat(ChatRequest(message="ขอบคุณครับ"))

    assert response.message.startswith("ยินดีครับ")
    assert "สวัสดีครับ" not in response.message
    assert response.tool_results == ()


@pytest.mark.asyncio
async def test_thanks_does_not_swallow_follow_up_request() -> None:
    response = await _agent().handle_chat(
        ChatRequest(message="ขอบคุณครับ ช่วยแจ้งไฟฟ้าขัดข้องต่อด้วย")
    )

    assert not response.message.startswith("ยินดีครับ")
    assert "หมายเลขผู้ใช้ไฟ" in response.message


def _error_result(action: ToolAction, code: ToolErrorCode) -> ToolResult:
    return ToolResult(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=action,
        status=ToolResultStatus.ERROR,
        data=None,
        error=ToolError(code=code, message="ข้อผิดพลาดจำลอง"),
        citations=(),
        simulation=True,
    )


def test_invalid_ca_error_tells_user_the_rule_and_how_to_retry() -> None:
    """Regression: CA ผิดรูปแบบต้องบอกกติกา 12 หลักและทางเลือกแจ้งแบบไม่มี CA แทนข้อความกลาง ๆ"""
    from app.agent.main_agent import _operational_error_fact

    fact = _operational_error_fact(_error_result(ToolAction.OMS_GET_OUTAGE_BY_CA, ToolErrorCode.INVALID_INPUT))
    assert "12 หลัก" in fact
    assert "อาการที่เกิดขึ้น สถานที่ และเบอร์โทร" in fact
    # ข้อความถึงผู้ใช้ต้องเป็นภาษาคน ไม่ใช่ชื่อฟิลด์ภาษาอังกฤษแบบ schema
    assert "description" not in fact and "contactPhone" not in fact

    prepare_fact = _operational_error_fact(_error_result(ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, ToolErrorCode.INVALID_INPUT))
    assert "12 หลัก" in prepare_fact


@pytest.mark.asyncio
async def test_oms_three_turn_anonymous_intake_keeps_the_original_intent() -> None:
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="report an outage"))
    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="description: ไม่มีไฟฟ้าใช้",
        )
    )
    third = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="location: ถนนสุขุมวิท; contactPhone: 0812345678",
        )
    )

    assert second.tool_results == ()
    assert [result.action.value for result in third.tool_results] == [
        "prepare_anonymous_outage"
    ]
    assert third.pending_action is not None
    assert third.pending_action.prepared_input["location"] == "ถนนสุขุมวิท"


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
        ("report an outage", "อาการที่เกิดขึ้น"),
        ("check outage status", "12 หลัก"),
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
async def test_json_planner_legacy_voc_response_fails_closed() -> None:
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

    assert "ไม่รองรับ" in response.message
    assert "ignored freeform" not in response.message
    assert "เลือกประเภทเรื่อง" not in response.message
    assert response.tool_results == ()
    assert response.pending_action is None


@pytest.mark.asyncio
async def test_legacy_voc_direct_response_does_not_persist_context() -> None:
    from app.llm import DirectResponseKind, LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [LLMResponse(direct_response=DirectResponseKind.VOC_DETAILS)]
    )
    agent = MainAgent(LLMClient(adapter), _registry())
    first = await agent.handle_chat(ChatRequest(message="ร้องเรียนการบริการหน่อย"))

    second = await agent.handle_chat(
        ChatRequest(
            conversationId=first.conversation_id,
            message="ข้อความถัดไป",
        )
    )

    assert "ไม่รองรับ" in first.message
    assert "เลือกประเภทเรื่อง" not in first.message
    assert "บริการผู้ช่วยไม่พร้อมใช้งาน" in second.message
    assert "เลือกประเภทเรื่อง" not in second.message
    assert first.tool_results == second.tool_results == ()
    assert first.pending_action is second.pending_action is None


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
    assert "ไม่รองรับ" in response.message
    assert "เลือกประเภทเรื่อง" not in response.message
    assert response.tool_results == ()
    assert response.pending_action is None


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
async def test_followup_after_outage_check_does_not_ask_for_the_ca_again() -> None:
    """Regression: คำถามต่อเนื่องหลังตรวจเหตุสำเร็จเคยถูกตอบด้วยแม่แบบขอ CA ซ้ำ

    ``_safe_direct_message`` เคยทิ้งข้อความของโมเดลทุกกรณีที่ไม่มี ``directResponse``
    ผู้ใช้ที่เพิ่งให้หมายเลขผู้ใช้ไฟจึงถูกถามซ้ำทั้งที่ระบบมีคำตอบอยู่แล้ว
    """
    from app.llm import LLMResponse, ScriptedLLMAdapter

    followup_text = "ใช่ครับ ขณะนี้เจ้าหน้าที่กำลังดำเนินการแก้ไขเหตุไฟฟ้าขัดข้องอยู่ครับ"
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
            LLMResponse(text="ตรวจสอบเรียบร้อยแล้วครับ"),
            LLMResponse(text=followup_text),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry())

    first = await agent.handle_chat(ChatRequest(message="ไฟดับ ตรวจสอบ ca 100000000003"))
    second = await agent.handle_chat(
        ChatRequest(
            message="งั้นเจ้าหน้าที่กำลังดำเนินการใช่ไหม",
            conversation_id=first.conversation_id,
        )
    )

    assert second.message == followup_text
    assert "กรุณาแจ้งหมายเลขผู้ใช้ไฟ" not in second.message


@pytest.mark.asyncio
async def test_mislabeled_oms_ca_followup_after_outage_check_uses_model_text() -> None:
    """Regression: โมเดลติดป้าย oms_ca_number ผิดบนคำถามต่อเนื่องหลังตรวจเหตุสำเร็จ

    ``_safe_direct_message`` เคยให้ ``directResponse`` มีสิทธิ์ชนะข้อความของโมเดลเสมอ
    คำถามอย่าง "แสดงว่าช่างกำลังมาใช่ไหม" จึงถูกตอบด้วยแม่แบบขอ CA ซ้ำอีกครั้ง
    ทั้งที่บทสนทนามีผล OMS ที่สำเร็จอยู่แล้ว
    """
    from app.llm import DirectResponseKind, LLMResponse, ScriptedLLMAdapter

    followup_text = "ใช่ครับ ช่างการไฟฟ้ากำลังเดินทางไปแก้ไขที่หม้อแปลงครับ"
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
            LLMResponse(text="ตรวจสอบเรียบร้อยแล้วครับ"),
            LLMResponse(text=followup_text, direct_response=DirectResponseKind.OMS_CA_NUMBER),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry())

    first = await agent.handle_chat(ChatRequest(message="ไฟดับ ตรวจสอบ ca 100000000003"))
    second = await agent.handle_chat(
        ChatRequest(
            message="แสดงว่าช่างกำลังมาใช่ไหมครับ",
            conversation_id=first.conversation_id,
        )
    )

    assert second.message == followup_text
    assert "กรุณาแจ้งหมายเลขผู้ใช้ไฟ" not in second.message


@pytest.mark.asyncio
async def test_free_text_without_grounded_outage_still_uses_safe_template() -> None:
    """ไม่มีผล OMS ในบทสนทนา ต้องไม่ปล่อยข้อความอิสระของโมเดลออกไป"""
    from app.llm import LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter([LLMResponse(text="ไฟจะมาภายใน 10 นาทีครับ")])
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="อีกนานไหมกว่าไฟจะมา"))

    assert "10 นาที" not in response.message


@pytest.mark.asyncio
async def test_outage_report_asks_for_ca_before_anonymous_inputs() -> None:
    """Regression: แจ้งไฟดับโดยไม่มีข้อมูล ต้องถาม CA ก่อน ไม่กระโดดไปขอ 3 อย่างแบบ anonymous"""
    agent = _agent()
    first = await agent.handle_chat(ChatRequest(message="แจ้งไฟดับหน่อยครับ"))
    assert "หมายเลขผู้ใช้ไฟ" in first.message
    assert "(CA)" in first.message
    assert "3 อย่างนี้" in first.message  # บอกทางเลือกไว้เผื่อไม่มี CA
