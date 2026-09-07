"""VOC guided flow: session routing, stale answers, consent, and cancellation."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportOptionalMemberAccess=false, reportOptionalSubscript=false

from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio

from app.backends import BackendError
from app.contracts import ToolAction, ToolErrorCode, ToolName
from app.plugins.tests.test_voc_intake import _catalog
from app.plugins.voc.flow import _MAX_STEP_RETRIES, VocGuidedFlow
from app.plugins.voc.intake import (
    CONSENT_DECLINE,
    STEP_CA_NUMBER,
    STEP_CONSENT,
    STEP_DETAIL,
    STEP_LOCATION_TEXT,
    VocIntakeState,
)


class FakeVocTool:
    def __init__(self, catalog: dict | None = None, *, error: BackendError | None = None) -> None:
        self._catalog = catalog if catalog is not None else _catalog()
        self._error = error
        self.catalog_calls = 0

    def get_catalog(self) -> dict:
        self.catalog_calls += 1
        if self._error is not None:
            raise self._error
        return self._catalog


def _flow(tool: FakeVocTool | None = None) -> tuple[VocGuidedFlow, FakeVocTool]:
    resolved = tool or FakeVocTool()
    return VocGuidedFlow(resolved, consent_notice_version="TEST-PDPA-1"), resolved


async def _answer(flow: VocGuidedFlow, conversation_id, turn, value: str):
    return await flow.advance(conversation_id, "", turn.prompt.prompt_id, value)


async def test_flow_starts_only_for_case_intent() -> None:
    flow, _ = _flow()

    generic = await flow.start(uuid4(), "ร้องเรียนบริการหน่อย")
    assert generic is not None and generic.prompt is not None
    assert generic.prompt.prompt_id == STEP_DETAIL
    assert await flow.start(uuid4(), "อัตราค่าไฟคิดยังไง") is None
    # การติดตามเรื่องเป็นคนละงาน ต้องปล่อยให้เส้นทางปกติจัดการ
    assert await flow.start(uuid4(), "ติดตามเรื่องร้องเรียน") is None
    # คำถามขอข้อมูลต้องได้คำตอบ ไม่ใช่ถูกลากเข้าโฟลว์เปิดเรื่อง
    assert await flow.start(uuid4(), "มีประเภทเรื่องร้องเรียนอะไรบ้าง") is None
    assert await flow.start(uuid4(), "ขอดูประเภทเรื่องร้องเรียน") is None


async def test_labelled_ca_is_retained_without_model_access() -> None:
    flow, _ = _flow()

    turn = await flow.start(uuid4(), "ร้องเรียนบริการ CA 100000000003")

    assert turn is not None and turn.prompt is not None
    conversation_id = next(iter(flow._states))
    assert flow._states[conversation_id].answers[STEP_CA_NUMBER] == "100000000003"


async def test_detailed_narrative_before_intent_is_retained_as_detail() -> None:
    flow, _ = _flow()

    turn = await flow.start(uuid4(), "พนักงานพูดไม่สุภาพ เลยอยากร้องเรียนบริการ")

    assert turn is not None and turn.prompt is not None
    assert turn.prompt.prompt_id == "voc_sub_issue"


async def test_labelled_ca_survives_journey_selection_and_unsupported_journeys_drop_it() -> None:
    flow, _ = _flow()
    ca_message = "ร้องเรียน CA 100000000003"

    supported_id = uuid4()
    supported = await flow.start(supported_id, ca_message)
    assert supported is not None and supported.prompt is not None
    assert supported.prompt.prompt_id == "voc_journey"
    supported = await flow.advance(
        supported_id, "SERVICE_ISSUE", supported.prompt.prompt_id, "SERVICE_ISSUE"
    )
    assert supported is not None
    assert flow._states[supported_id].answers[STEP_CA_NUMBER] == "100000000003"

    anonymous_id = uuid4()
    anonymous = await flow.start(anonymous_id, ca_message)
    assert anonymous is not None and anonymous.prompt is not None
    anonymous = await flow.advance(
        anonymous_id, "TIP_OFF", anonymous.prompt.prompt_id, "TIP_OFF"
    )
    assert anonymous is not None
    assert STEP_CA_NUMBER not in flow._states[anonymous_id].answers


async def test_long_opening_requests_shorter_detail_before_storing_or_preparing() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    long_opening = "ร้องเรียนบริการ " + ("ก" * 2001)

    turn = await flow.start(conversation_id, long_opening)

    assert turn is not None and turn.prompt is not None
    assert turn.prompt.prompt_id == STEP_DETAIL
    assert "2,000" in turn.message
    assert STEP_DETAIL not in flow._states[conversation_id].answers
    assert not turn.has_tool_call

    safe_detail = "ก" * 2000
    continued = await flow.advance(conversation_id, safe_detail, turn.prompt.prompt_id, None)

    assert continued is not None and not continued.has_tool_call
    assert flow._states[conversation_id].answers[STEP_DETAIL] == safe_detail
    assert len(flow._states[conversation_id].answers["voc_subject"]) == 140


async def test_unambiguous_opening_message_preselects_the_journey() -> None:
    """ข้อความที่ระบุประเภทชัดเจนต้องไม่ถูกถามซ้ำอีกรอบ"""
    flow, _ = _flow()

    turn = await flow.start(uuid4(), "อยากร้องเรียน แจ้งปัญหาด้านบริการ")

    assert turn is not None and turn.prompt is not None
    assert turn.prompt.prompt_id == STEP_DETAIL


async def test_consent_requires_exact_current_response() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        assert turn is not None
        if turn.prompt is None or turn.prompt.prompt_id == STEP_CONSENT:
            break
        value = turn.prompt.options[0].value if turn.prompt.options else "ข้อมูลทดสอบ"
        turn = await _answer(flow, conversation_id, turn, value)

    assert turn is not None and turn.prompt is not None
    assert turn.prompt.prompt_id == STEP_CONSENT
    not_exact = await flow.advance(conversation_id, "ยินยอมครับ", None, None)
    assert not_exact is not None and not_exact.prompt is not None
    assert not_exact.prompt.prompt_id == STEP_CONSENT


async def test_answer_for_a_previous_question_is_not_accepted() -> None:
    """กดปุ่มของคำถามเก่าต้องได้คำถามปัจจุบันกลับ ไม่ใช่ถูกบันทึกผิดขั้น"""
    flow, _ = _flow()
    conversation_id = uuid4()
    first = await flow.start(conversation_id, "ร้องเรียนบริการ")
    second = await _answer(flow, conversation_id, first, "พนักงานพูดไม่สุภาพ")

    replayed = await flow.advance(conversation_id, "", first.prompt.prompt_id, "ข้อมูลเก่าที่ไม่ควรรับ")

    assert replayed is not None
    assert replayed.prompt is not None
    assert replayed.prompt.prompt_id == second.prompt.prompt_id


class _EnrichingPrefiller:
    async def prefill(self, flow, state, message):
        return state.with_answer(STEP_LOCATION_TEXT, "กรุงเทพมหานคร")


async def test_unresolved_choice_persists_enriched_facts() -> None:
    flow = VocGuidedFlow(
        FakeVocTool(), consent_notice_version="TEST-PDPA-1", prefiller=_EnrichingPrefiller()
    )
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")
    assert turn is not None and turn.prompt is not None
    # The enrichment moves the flow to its location question, but an ambiguous
    # spoken answer must still leave the extracted location in session state.
    while turn.prompt.prompt_id != "voc_sub_issue":
        turn = await flow.advance(conversation_id, "ข้อมูล", turn.prompt.prompt_id, "ข้อมูล")
        assert turn is not None and turn.prompt is not None
    clarified = await flow.advance(conversation_id, "ไม่แน่ใจ", None, None)
    assert clarified is not None and clarified.prompt is not None
    assert clarified.prompt.prompt_id == "voc_sub_issue"
    assert flow._states[conversation_id].answers[STEP_LOCATION_TEXT] == "กรุงเทพมหานคร"


async def test_value_outside_the_catalog_is_refused() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")

    next_turn = await _answer(flow, conversation_id, turn, "ข้อมูลรายละเอียด")
    assert next_turn is not None and next_turn.prompt is not None
    refused = await _answer(flow, conversation_id, next_turn, "NOT_A_REAL_CODE")

    assert refused is not None and refused.prompt is not None
    assert refused.prompt.prompt_id == next_turn.prompt.prompt_id
    assert not refused.has_tool_call


async def test_declining_consent_ends_the_flow_without_preparing_a_case() -> None:
    """ไม่ยินยอม = ไม่เตรียมเรื่อง และต้องไม่ทิ้ง session ค้างไว้"""
    flow, tool = _flow()
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        if turn.prompt is None or turn.prompt.prompt_id == STEP_CONSENT:
            break
        value = (
            turn.prompt.options[0].value
            if turn.prompt.options
            else "ข้อความทดสอบสำหรับการกรอกข้อมูล"
        )
        turn = await _answer(flow, conversation_id, turn, value)

    declined = await _answer(flow, conversation_id, turn, CONSENT_DECLINE)

    assert declined.finished is True
    assert not declined.has_tool_call
    assert flow.is_active(conversation_id) is False


async def test_cancel_words_end_the_session() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    await flow.start(conversation_id, "ร้องเรียนบริการ")

    cancelled = await flow.advance(conversation_id, "ยกเลิก", None, None)

    assert cancelled is not None and cancelled.finished is True
    assert flow.is_active(conversation_id) is False


async def test_completed_flow_emits_a_prepare_call_with_external_payload() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        if turn.has_tool_call:
            break
        value = (
            turn.prompt.options[0].value
            if turn.prompt.options
            else "ข้อความทดสอบสำหรับการกรอกข้อมูล"
        )
        turn = await _answer(flow, conversation_id, turn, value)

    assert turn.has_tool_call
    assert turn.tool_name is ToolName.VOC
    assert turn.tool_action is ToolAction.VOC_PREPARE_CASE
    assert turn.tool_input["externalPayload"]["consent"]["accepted"] is True
    # session ต้องถูกปิดหลังส่งต่อให้ขั้นยืนยัน เพื่อไม่ให้เทิร์นถัดไปถูกกลืนโดย flow
    assert flow.is_active(conversation_id) is False


async def test_unavailable_catalog_does_not_open_a_dangling_session() -> None:
    """อ่าน catalog ไม่ได้ ต้องบอกตรง ๆ ไม่ใช่เปิด session แล้วเดารหัสเอง"""
    flow, _ = _flow(FakeVocTool(error=BackendError(ToolErrorCode.UNAVAILABLE, "ระบบ VOC ล่ม")))
    conversation_id = uuid4()

    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")

    assert turn is not None and turn.finished is True
    assert turn.prompt is None and not turn.has_tool_call
    assert flow.is_active(conversation_id) is False


async def test_typed_label_answers_work_without_button_clicks() -> None:
    """โหมดเสียงกดปุ่มไม่ได้ จึงต้องตอบด้วยข้อความหรือลำดับข้อได้"""
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = await flow.start(conversation_id, "ร้องเรียนหน่อย")
    label = turn.prompt.options[1].label

    typed = await flow.advance(conversation_id, label, None, None)

    assert typed is not None
    assert typed.prompt is None or typed.prompt.prompt_id != turn.prompt.prompt_id


async def _walk_to_ca(flow: VocGuidedFlow, conversation_id):
    turn = await flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        if turn.prompt is None or turn.prompt.prompt_id == STEP_CA_NUMBER:
            return turn
        value = (
            turn.prompt.options[0].value
            if turn.prompt.options
            else "ข้อความทดสอบสำหรับการกรอกข้อมูล"
        )
        turn = await _answer(flow, conversation_id, turn, value)
    raise AssertionError("ไม่ถึงขั้นถามหมายเลขผู้ใช้ไฟ")


async def test_spoken_no_answer_skips_the_optional_ca_step() -> None:
    """Regression: ตอบว่า "ไม่มีครับ" เคยวนถามหมายเลขผู้ใช้ไฟไม่จบ"""
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = await _walk_to_ca(flow, conversation_id)

    answered = await flow.advance(conversation_id, "ไม่มีครับ", None, None)

    assert answered.prompt is None or answered.prompt.prompt_id != STEP_CA_NUMBER


async def test_repeated_invalid_answers_do_not_trap_the_user() -> None:
    """ตอบผิดซ้ำ ๆ ในขั้นที่ข้ามได้ ต้องเดินหน้าต่อ ไม่ใช่ติดอยู่ขั้นเดิมตลอด"""
    flow, _ = _flow()
    conversation_id = uuid4()
    await _walk_to_ca(flow, conversation_id)

    last = None
    for _ in range(_MAX_STEP_RETRIES):
        last = await flow.advance(conversation_id, "อะไรนะ", None, None)

    assert last is not None
    assert last.prompt is None or last.prompt.prompt_id != STEP_CA_NUMBER
