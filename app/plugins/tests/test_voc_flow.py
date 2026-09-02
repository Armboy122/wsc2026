"""VOC guided flow: session routing, stale answers, consent, and cancellation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.backends import BackendError
from app.contracts import ToolAction, ToolErrorCode, ToolName
from app.plugins.tests.test_voc_intake import _catalog
from app.plugins.voc.flow import VocGuidedFlow
from app.plugins.voc.intake import CONSENT_DECLINE, STEP_CONSENT


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


def _answer(flow: VocGuidedFlow, conversation_id, turn, value: str):
    return flow.advance(conversation_id, "", turn.prompt.prompt_id, value)


def test_flow_starts_only_for_case_intent() -> None:
    flow, _ = _flow()

    assert flow.start(uuid4(), "ร้องเรียนบริการหน่อย") is not None
    assert flow.start(uuid4(), "อัตราค่าไฟคิดยังไง") is None
    # การติดตามเรื่องเป็นคนละงาน ต้องปล่อยให้เส้นทางปกติจัดการ
    assert flow.start(uuid4(), "ติดตามเรื่องร้องเรียน") is None
    # คำถามขอข้อมูลต้องได้คำตอบ ไม่ใช่ถูกลากเข้าโฟลว์เปิดเรื่อง
    assert flow.start(uuid4(), "มีประเภทเรื่องร้องเรียนอะไรบ้าง") is None
    assert flow.start(uuid4(), "ขอดูประเภทเรื่องร้องเรียน") is None


def test_unambiguous_opening_message_preselects_the_journey() -> None:
    """ข้อความที่ระบุประเภทชัดเจนต้องไม่ถูกถามซ้ำอีกรอบ"""
    flow, _ = _flow()

    turn = flow.start(uuid4(), "อยากร้องเรียน แจ้งปัญหาด้านบริการ")

    assert turn is not None and turn.prompt is not None
    assert turn.prompt.prompt_id != "voc_journey"


def test_answer_for_a_previous_question_is_not_accepted() -> None:
    """กดปุ่มของคำถามเก่าต้องได้คำถามปัจจุบันกลับ ไม่ใช่ถูกบันทึกผิดขั้น"""
    flow, _ = _flow()
    conversation_id = uuid4()
    first = flow.start(conversation_id, "ร้องเรียนบริการ")
    second = _answer(flow, conversation_id, first, first.prompt.options[0].value)

    replayed = flow.advance(conversation_id, "", first.prompt.prompt_id, first.prompt.options[0].value)

    assert replayed is not None
    assert replayed.prompt is not None
    assert replayed.prompt.prompt_id == second.prompt.prompt_id


def test_value_outside_the_catalog_is_refused() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = flow.start(conversation_id, "ร้องเรียนบริการ")

    refused = _answer(flow, conversation_id, turn, "NOT_A_REAL_CODE")

    assert refused is not None and refused.prompt is not None
    assert refused.prompt.prompt_id == turn.prompt.prompt_id
    assert not refused.has_tool_call


def test_declining_consent_ends_the_flow_without_preparing_a_case() -> None:
    """ไม่ยินยอม = ไม่เตรียมเรื่อง และต้องไม่ทิ้ง session ค้างไว้"""
    flow, tool = _flow()
    conversation_id = uuid4()
    turn = flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        if turn.prompt is None or turn.prompt.prompt_id == STEP_CONSENT:
            break
        value = (
            turn.prompt.options[0].value
            if turn.prompt.options
            else "ข้อความทดสอบสำหรับการกรอกข้อมูล"
        )
        turn = _answer(flow, conversation_id, turn, value)

    declined = _answer(flow, conversation_id, turn, CONSENT_DECLINE)

    assert declined.finished is True
    assert not declined.has_tool_call
    assert flow.is_active(conversation_id) is False


def test_cancel_words_end_the_session() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    flow.start(conversation_id, "ร้องเรียนบริการ")

    cancelled = flow.advance(conversation_id, "ยกเลิก", None, None)

    assert cancelled is not None and cancelled.finished is True
    assert flow.is_active(conversation_id) is False


def test_completed_flow_emits_a_prepare_call_with_external_payload() -> None:
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = flow.start(conversation_id, "ร้องเรียนบริการ")
    for _ in range(40):
        if turn.has_tool_call:
            break
        value = (
            turn.prompt.options[0].value
            if turn.prompt.options
            else "ข้อความทดสอบสำหรับการกรอกข้อมูล"
        )
        turn = _answer(flow, conversation_id, turn, value)

    assert turn.has_tool_call
    assert turn.tool_name is ToolName.VOC
    assert turn.tool_action is ToolAction.VOC_PREPARE_CASE
    assert turn.tool_input["externalPayload"]["consent"]["accepted"] is True
    # session ต้องถูกปิดหลังส่งต่อให้ขั้นยืนยัน เพื่อไม่ให้เทิร์นถัดไปถูกกลืนโดย flow
    assert flow.is_active(conversation_id) is False


def test_unavailable_catalog_does_not_open_a_dangling_session() -> None:
    """อ่าน catalog ไม่ได้ ต้องบอกตรง ๆ ไม่ใช่เปิด session แล้วเดารหัสเอง"""
    flow, _ = _flow(FakeVocTool(error=BackendError(ToolErrorCode.UNAVAILABLE, "ระบบ VOC ล่ม")))
    conversation_id = uuid4()

    turn = flow.start(conversation_id, "ร้องเรียนบริการ")

    assert turn is not None and turn.finished is True
    assert turn.prompt is None and not turn.has_tool_call
    assert flow.is_active(conversation_id) is False


def test_typed_label_answers_work_without_button_clicks() -> None:
    """โหมดเสียงกดปุ่มไม่ได้ จึงต้องตอบด้วยข้อความหรือลำดับข้อได้"""
    flow, _ = _flow()
    conversation_id = uuid4()
    turn = flow.start(conversation_id, "ร้องเรียนหน่อย")
    label = turn.prompt.options[1].label

    typed = flow.advance(conversation_id, label, None, None)

    assert typed is not None
    assert typed.prompt is None or typed.prompt.prompt_id != turn.prompt.prompt_id
