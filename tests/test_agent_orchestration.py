"""พฤติกรรมสนทนาของ Main Agent ก่อนเลือกเรียกเครื่องมือ"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.agent.main_agent import (
    MainAgent,
    _MAX_KNOWLEDGE_SEARCHES_PER_TURN,
    _MAX_TOOL_STEPS,
    _knowledge_fact,
)
from app.agent.registry import ToolRegistry
from app.agent.response_policy import ErrorPresentation
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
from app.llm import DemoLLMAdapter, LLMClient, LLMResponse, ScriptedLLMAdapter, ToolDefinition
from app.llm.prompting import SYSTEM_PROMPT
from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.oms.response import OmsResponsePolicy
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
        ],
        response_policies=(OmsResponsePolicy(),),
    )


def _agent(knowledge_backend: FakeKnowledgeBackend | None = None) -> MainAgent:
    return MainAgent(
        LLMClient(DemoLLMAdapter((OmsDemoBehavior(),))),
        _registry(knowledge_backend),
    )


def test_system_prompt_is_generic_and_outage_policy_is_plugin_owned() -> None:
    from app.plugins.oms.response import OmsResponsePolicy

    assert "การติดตามสถานะเหตุที่เคยตรวจแล้ว" in SYSTEM_PROMPT
    assert "OMS" not in SYSTEM_PROMPT and "VOC" not in SYSTEM_PROMPT
    assert "คำขอบคุณ" in SYSTEM_PROMPT
    assert "thanks" in SYSTEM_PROMPT
    assert "oms_tool.get_outage_by_ca" in OmsResponsePolicy.planner_instructions


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


def test_existing_oms_outage_is_presented_as_a_human_status_not_raw_enum() -> None:
    result = ToolResult(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        status=ToolResultStatus.SUCCESS,
        data={
            "caNumber": "020008084480",
            "customerFound": True,
            "network": {"meterId": "M", "transformerId": "T", "feederId": "F"},
            "activeEvent": {"status": "RECEIVED", "message": "ไฟฟ้าดับ"},
            "recommendedAction": "CREATE_METER_EVENT",
        },
        simulation=True,
    )

    message = OmsResponsePolicy().result_fact(result)

    assert message is not None
    assert "มีเหตุไฟฟ้าขัดข้อง" in message
    assert "รับแจ้งแล้ว" in message
    assert "ไฟฟ้าดับ" in message
    assert not message.startswith("สถานะ RECEIVED:")


def test_voice_like_operational_wrapper_keeps_the_typed_oms_fact_verbatim() -> None:
    from app.agent.main_agent import _authoritative_message
    from app.agent.response_policy import ResponsePolicies

    result = ToolResult(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        status=ToolResultStatus.SUCCESS,
        data={
            "caNumber": "020008084480",
            "customerFound": True,
            "network": {"meterId": "M", "transformerId": "T", "feederId": "F"},
            "activeEvent": {"status": "RECEIVED", "message": "ไฟฟ้าดับ"},
            "recommendedAction": "CREATE_METER_EVENT",
        },
        simulation=True,
    )
    fact = OmsResponsePolicy().result_fact(result)
    assert fact is not None

    message = _authoritative_message(
        f"ตรวจสอบแล้วครับ {fact}",
        [result],
        None,
        response_policies=ResponsePolicies((OmsResponsePolicy(),)),
    )

    assert message == f"ตรวจสอบแล้วครับ {fact}"


def test_unsafe_operational_wrapper_uses_deterministic_fact() -> None:
    from app.agent.main_agent import _authoritative_message
    from app.agent.response_policy import ResponsePolicies

    result = ToolResult(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        status=ToolResultStatus.SUCCESS,
        data={
            "caNumber": "020008084480",
            "customerFound": True,
            "network": {"meterId": "M", "transformerId": "T", "feederId": "F"},
            "activeEvent": {"status": "RECEIVED", "message": "ไฟฟ้าดับ"},
            "recommendedAction": "CREATE_METER_EVENT",
        },
        simulation=True,
    )
    fact = OmsResponsePolicy().result_fact(result)
    assert fact is not None

    message = _authoritative_message(
        f"{fact} ช่างจะถึงภายใน 10 นาทีครับ",
        [result],
        None,
        response_policies=ResponsePolicies((OmsResponsePolicy(),)),
    )

    assert message == fact
    assert "10 นาที" not in message


def test_invalid_ca_error_tells_user_the_rule_and_how_to_retry() -> None:
    """Regression: CA ผิดรูปแบบต้องบอกกติกา 12 หลักและทางเลือกแจ้งแบบไม่มี CA แทนข้อความกลาง ๆ"""
    from app.agent.main_agent import _operational_error_fact
    from app.agent.response_policy import ResponsePolicies
    from app.plugins.oms.response import OmsResponsePolicy

    policies = ResponsePolicies((OmsResponsePolicy(),))
    fact = _operational_error_fact(
        _error_result(ToolAction.OMS_GET_OUTAGE_BY_CA, ToolErrorCode.INVALID_INPUT), policies
    )
    assert "12 หลัก" in fact
    assert "อาการที่เกิดขึ้น สถานที่ และเบอร์โทร" in fact
    # ข้อความถึงผู้ใช้ต้องเป็นภาษาคน ไม่ใช่ชื่อฟิลด์ภาษาอังกฤษแบบ schema
    assert "description" not in fact and "contactPhone" not in fact

    prepare_fact = _operational_error_fact(
        _error_result(ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, ToolErrorCode.INVALID_INPUT), policies
    )
    assert "12 หลัก" in prepare_fact


class _SecretErrorOms:
    name = ToolName.OMS

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="upstream api_key=super-secret customer=999",
            ),
            simulation=True,
        )

    def reset(self) -> None:
        return None


def _invalid_oms_presentation() -> ErrorPresentation:
    presentation = OmsResponsePolicy().error_presentation(
        _error_result(ToolAction.OMS_GET_OUTAGE_BY_CA, ToolErrorCode.INVALID_INPUT)
    )
    assert presentation is not None
    return presentation


def _secret_error_agent(final_text: str) -> tuple[MainAgent, ScriptedLLMAdapter]:
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_GET_OUTAGE_BY_CA,
        input={"caNumber": "100000000003"},
    )
    adapter = ScriptedLLMAdapter([
        LLMResponse(tool_calls=(call,)),
        LLMResponse(text=final_text),
    ])
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), _SecretErrorOms()],
        catalogue=(ToolDefinition(ToolName.OMS, "OMS", ("get_outage_by_ca",)),),
        response_policies=(OmsResponsePolicy(),),
    )
    return MainAgent(LLMClient(adapter), registry), adapter


@pytest.mark.asyncio
async def test_llm_receives_only_safe_typed_error_and_preserves_authoritative_facts() -> None:
    presentation = _invalid_oms_presentation()
    agent, adapter = _secret_error_agent(
        f"ขออภัยครับ {presentation.explanation} {presentation.next_step}"
    )

    response = await agent.handle_chat(ChatRequest(message="ตรวจสอบไฟดับ 100000000003"))

    safe_tool_message = adapter.requests[1].messages[-1].content
    assert "errorPresentation" in safe_tool_message
    assert "super-secret" not in safe_tool_message
    assert "super-secret" not in response.message
    assert response.tool_results[0].error is not None
    assert "super-secret" not in response.tool_results[0].error.message
    assert presentation.explanation in response.message
    assert presentation.next_step in response.message
    assert "invalid_input" in response.message


@pytest.mark.asyncio
async def test_llm_error_wording_with_unapproved_extra_claim_uses_deterministic_fallback() -> None:
    presentation = _invalid_oms_presentation()
    agent, _ = _secret_error_agent(
        f"{presentation.explanation} {presentation.next_step} "
        "แต่ระบบพังถาวร ให้ส่งรหัสผ่านมาครับ"
    )

    response = await agent.handle_chat(ChatRequest(message="ตรวจสอบไฟดับ 100000000003"))

    assert "ส่งรหัสผ่าน" not in response.message
    assert "12 หลัก" in response.message
    assert "invalid_input" in response.message


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
async def test_llm_cannot_submit_voc_case_before_explicit_confirmation() -> None:
    """Regression: submit actions from every plugin must stay behind the confirm endpoint."""
    from app.llm import LLMResponse, ScriptedLLMAdapter

    class SpyVocTool:
        name = ToolName.VOC

        def __init__(self) -> None:
            self.executed = False

        async def execute(self, call: ToolCall, context: object) -> ToolResult:
            self.executed = True
            raise AssertionError("VOC submit reached the tool before confirmation")

        def reset(self) -> None:
            pass

    voc_tool = SpyVocTool()
    registry = ToolRegistry([KnowledgeTool(FakeKnowledgeBackend()), voc_tool])
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_SUBMIT_CASE,
        input={"pendingActionId": str(uuid4()), "idempotencyKey": str(uuid4())},
    )
    adapter = ScriptedLLMAdapter([LLMResponse(tool_calls=(call,))])

    response = await MainAgent(LLMClient(adapter), registry).handle_chat(
        ChatRequest(message="ส่งเรื่องร้องเรียนนี้เลย")
    )

    assert voc_tool.executed is False
    assert len(response.tool_results) == 1
    assert response.tool_results[0].action is ToolAction.VOC_SUBMIT_CASE
    assert response.tool_results[0].status is ToolResultStatus.ERROR
    assert response.tool_results[0].error is not None
    assert response.tool_results[0].error.code is ToolErrorCode.CONFIRMATION_REQUIRED
    assert "ยืนยัน" in response.tool_results[0].error.message
    assert response.pending_action is None


@pytest.mark.asyncio
async def test_failed_confirmed_submit_redacts_secret_from_response_and_terminal_state() -> None:
    class SecretFailingSubmitOms:
        name = ToolName.OMS

        async def execute(self, call: ToolCall, context: object) -> ToolResult:
            if call.action is ToolAction.OMS_PREPARE_OUTAGE_WITH_CA:
                return ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    action=call.action,
                    status=ToolResultStatus.SUCCESS,
                    data={"summary": "เตรียมแจ้งเหตุไฟดับ"},
                    simulation=True,
                )
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                action=call.action,
                status=ToolResultStatus.ERROR,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL,
                    message="upstream token=submit-super-secret customer=999",
                ),
                simulation=True,
            )

        def reset(self) -> None:
            return None

    prepare_call = ToolCall(
        call_id=uuid4(),
        name=ToolName.OMS,
        action=ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
        input={
            "caNumber": "100000000003",
            "description": "ไฟดับ",
            "idempotencyKey": "idem-submit-error",
        },
    )
    registry = ToolRegistry(
        [KnowledgeTool(FakeKnowledgeBackend()), SecretFailingSubmitOms()],
        catalogue=(ToolDefinition(ToolName.OMS, "OMS", ("prepare_outage_with_ca",)),),
        response_policies=(OmsResponsePolicy(),),
    )
    agent = MainAgent(
        LLMClient(ScriptedLLMAdapter([LLMResponse(tool_calls=(prepare_call,))])),
        registry,
    )

    prepared = await agent.handle_chat(ChatRequest(message="เตรียมแจ้งไฟดับ"))
    assert prepared.pending_action is not None
    decision = await agent.confirm_pending_action(prepared.pending_action.pending_action_id)

    assert decision.tool_result is not None and decision.tool_result.error is not None
    assert "submit-super-secret" not in decision.tool_result.error.message
    assert decision.pending_action.submission_result is not None
    assert decision.pending_action.submission_result.error is not None
    assert "submit-super-secret" not in decision.pending_action.submission_result.error.message
    assert decision.pending_action.status.value == "failed"


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
    from app.llm import LLMResponse, ScriptedLLMAdapter

    fabricated = "FABRICATED: ค่าไฟทุกบัญชีเป็นศูนย์"
    adapter = ScriptedLLMAdapter(
        [LLMResponse(text=fabricated, direct_response="unsupported")]
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
async def test_knowledge_searches_are_bounded_before_the_tool_step_limit() -> None:
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

    # การค้นหาความรู้ถูกจำกัดต่อเทิร์น จึงเหลือเท่าเพดาน ไม่ใช่ขีดจำกัดลูปเครื่องมือเต็ม
    assert len(backend.calls) == _MAX_KNOWLEDGE_SEARCHES_PER_TURN
    assert len(response.tool_results) == _MAX_KNOWLEDGE_SEARCHES_PER_TURN


@pytest.mark.asyncio
async def test_agent_loop_is_still_bounded_by_the_tool_step_limit() -> None:
    """เพดานค้นหาความรู้ไม่ได้แทนขีดจำกัดลูปเครื่องมือ เครื่องมืออื่นยังต้องถูกจำกัดที่ ``_MAX_TOOL_STEPS``"""
    from app.llm import LLMResponse, ScriptedLLMAdapter

    # OMS อ่านสถานะไม่ติดเพดาน Knowledge จึงใช้ตรวจขีดจำกัดลูปเครื่องมือที่แท้จริงได้
    responses = [
        LLMResponse(
            tool_calls=(
                ToolCall(
                    call_id=uuid4(),
                    name=ToolName.OMS,
                    action=ToolAction.OMS_GET_OUTAGE_BY_CA,
                    input={"caNumber": f"10000000{index:04d}"},
                ),
            )
        )
        for index in range(_MAX_TOOL_STEPS + 5)
    ]
    agent = MainAgent(LLMClient(ScriptedLLMAdapter(responses)), _registry())

    response = await agent.handle_chat(ChatRequest(message="ทดสอบขีดจำกัดลูปเครื่องมือ"))

    assert len(response.tool_results) <= _MAX_TOOL_STEPS


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
async def test_knowledge_search_cap_stops_reworded_repeats_and_keeps_grounded_answer() -> None:
    """Regression: planner ขยายถ้อยคำค้นหาใหม่ทุกรอบ ทำให้ guard กัน input ซ้ำจับไม่ได้

    เทิร์นเดียวเคยยิง knowledge search ถึง 5 ครั้ง เปลืองโควตาและท่วมแผงอ้างอิง
    ตอนนี้จึงจำกัดจำนวนค้นหาต่อเทิร์น แล้วเรียบเรียงคำตอบจากผลที่ค้นได้แล้ว
    """
    from app.llm import LLMResponse, ScriptedLLMAdapter

    citation = Citation(
        sourceId="PEA_NEW_SERVICE",
        title="เอกสารขอใช้ไฟฟ้าใหม่",
        uri="knowledge://source/new-service.docx",
        snippet="ขอใช้ไฟฟ้าใหม่ยื่นได้ที่สำนักงานการไฟฟ้าเขตพื้นที่บริการ",
    )
    backend = FakeKnowledgeBackend(
        [GroundedEvidence("ขอใช้ไฟฟ้าใหม่ยื่นได้ที่สำนักงานการไฟฟ้าเขตพื้นที่บริการ", 1, (citation,))]
    )
    # คำค้นต่างกันทุกครั้ง จึงไม่โดน guard กัน input ซ้ำตรง ๆ
    responses = [
        LLMResponse(
            tool_calls=(
                ToolCall(
                    call_id=uuid4(),
                    name=ToolName.KNOWLEDGE,
                    action=ToolAction.KNOWLEDGE_SEARCH,
                    input={"query": f"ช่องทางขอใช้ไฟฟ้าใหม่ แบบที่ {index}", "maxResults": 3},
                ),
            )
        )
        for index in range(5)
    ]
    agent = MainAgent(LLMClient(ScriptedLLMAdapter(responses)), _registry(backend))

    response = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟฟ้าใหม่ทำได้ที่ไหน"))

    assert len(backend.calls) == _MAX_KNOWLEDGE_SEARCHES_PER_TURN
    assert len(response.tool_results) == _MAX_KNOWLEDGE_SEARCHES_PER_TURN
    assert response.message == "ขอใช้ไฟฟ้าใหม่ยื่นได้ที่สำนักงานการไฟฟ้าเขตพื้นที่บริการ"
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
    # หลักฐานที่ยืนยันแล้วต้องไม่ถูกทิ้ง — คำถามต่อเนื่องเติมท้ายคำตอบเดิม
    assert "หนังสือรับรองบริษัท" in response.message


def test_channel_question_with_links_keeps_grounded_answer_unchanged() -> None:
    """Regression: คำถามช่องทาง/ลิงก์เคยถูกแทนที่ด้วยคำถามขอประเภทผู้ขอ ทำให้ URL หายไป"""
    answer = (
        "ยื่นคำขอออนไลน์ได้ที่ https://sabuyservice.pea.co.th/ "
        "ลิงก์บุคคลธรรมดา https://eservice.pea.co.th/cos/individual/ "
        "ลิงก์นิติบุคคล https://eservice.pea.co.th/cos/Corporate/"
    )
    for question in (
        "ขอมิเตอร์ใหม่ ยื่นเรื่องออนไลน์ได้ที่ไหน ขอลิงก์ด้วย",
        "แล้วสามารถไปทำบริการที่ไหนได้บ้างหรือต้องไปที่การไฟฟ้าอย่างเดียวหล่ะ",
    ):
        assert _knowledge_fact(answer, question) == answer


def test_documents_question_spans_applicant_types_appends_clarification() -> None:
    answer = "เอกสารสำหรับบุคคลธรรมดาและนิติบุคคลแตกต่างกัน"
    out = _knowledge_fact(answer, "ขอใช้ไฟใหม่ต้องเตรียมเอกสารอะไรบ้าง")

    assert "เอกสารสำหรับบุคคลธรรมดาและนิติบุคคลแตกต่างกัน" in out
    assert "บุคคลธรรมดาหรือนิติบุคคล" in out


def test_user_already_named_applicant_type_passes_through() -> None:
    answer = "บุคคลธรรมดาและนิติบุคคลใช้เอกสารต่างกัน"
    assert _knowledge_fact(answer, "นิติบุคคลขอใช้ไฟใหม่ต้องใช้เอกสารอะไร") == answer


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
    from app.llm import LLMResponse, ScriptedLLMAdapter

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
            LLMResponse(text=followup_text, direct_response="oms_ca_number"),
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


_TRUNCATED_PLANNER_JSON = '{"message": "", "toolCalls": [{"name": "knowledge_tool", "action": "search", "input": {"query": "คำถาม"}]'


@pytest.mark.asyncio
async def test_malformed_planner_json_twice_returns_honest_limitation_message() -> None:
    """Regression: planner JSON เสียหายซ้ำสองครั้ง ต้องบอกข้อจำกัดตรง ๆ ไม่ใช้ข้อความความสามารถทั่วไป"""
    from app.agent.main_agent import _CAPABILITY_MESSAGE, _PLANNER_PARSE_FAILURE_MESSAGE
    from app.llm import LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter([LLMResponse(text=_TRUNCATED_PLANNER_JSON) for _ in range(2)])
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟใหม่ใช้เอกสารอะไร"))

    assert response.message == _PLANNER_PARSE_FAILURE_MESSAGE
    assert response.message != _CAPABILITY_MESSAGE
    trace = agent.get_trace(response.trace_id)
    parse_errors = [event for event in trace.events if event.kind.value == "error" and event.data.get("stage") == "planner_parse"]
    assert len(parse_errors) == 2


@pytest.mark.asyncio
async def test_malformed_planner_json_retries_once_and_runs_tool() -> None:
    """planner เสียหายครั้งเดียวแล้วตอบถูกต้องในครั้งถัดไป ต้องเรียกเครื่องมือและตอบด้วยหลักฐานจริง"""
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
    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(text=_TRUNCATED_PLANNER_JSON),
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        call_id=uuid4(),
                        name=ToolName.KNOWLEDGE,
                        action=ToolAction.KNOWLEDGE_SEARCH,
                        input={"query": "ขอใช้ไฟใหม่ใช้เอกสารอะไร", "maxResults": 1},
                    ),
                )
            ),
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry(backend))

    response = await agent.handle_chat(ChatRequest(message="ขอใช้ไฟใหม่ใช้เอกสารอะไร"))

    assert len(backend.calls) == 1
    assert response.citations[0].source_id == "PEA_NEW_SERVICE"
    assert "สำเนาบัตรประชาชน" in response.message
    trace = agent.get_trace(response.trace_id)
    parse_errors = [event for event in trace.events if event.kind.value == "error" and event.data.get("stage") == "planner_parse"]
    assert len(parse_errors) == 1


@pytest.mark.asyncio
async def test_valid_json_direct_response_without_tool_calls_is_unchanged() -> None:
    """JSON ของ planner ที่สมบูรณ์และไม่มี toolCalls ยังเดินเส้นทางข้อความตรงเดิม"""
    from app.agent.main_agent import _CAPABILITY_MESSAGE
    from app.llm import LLMResponse, ScriptedLLMAdapter

    adapter = ScriptedLLMAdapter(
        [
            LLMResponse(
                text='{"message": "ตรวจสอบเรียบร้อยแล้วครับ", "toolCalls": [], "directResponse": null}'
            )
        ]
    )
    agent = MainAgent(LLMClient(adapter), _registry())

    response = await agent.handle_chat(ChatRequest(message="คำถามทั่วไป"))

    # ข้อความอิสระจากโมเดลยังถูกบังคับเป็นแม่แบบปลอดภัยเหมือนเดิม ไม่ใช่ข้อความข้อจำกัดใหม่
    assert response.message == _CAPABILITY_MESSAGE
    assert response.tool_results == ()


@pytest.mark.asyncio
async def test_disabled_plugin_cannot_render_its_direct_response() -> None:
    """A provider label cannot revive presentation from a plugin that was not enabled."""
    from app.llm import LLMResponse, ScriptedLLMAdapter

    registry = ToolRegistry([KnowledgeTool(FakeKnowledgeBackend())])
    agent = MainAgent(
        LLMClient(ScriptedLLMAdapter([LLMResponse(direct_response="oms_outage_start")])),
        registry,
    )

    response = await agent.handle_chat(ChatRequest(message="แจ้งเหตุไฟดับ"))

    assert "หมายเลขผู้ใช้ไฟ" not in response.message
    assert "ความรู้ PEA" in response.message
