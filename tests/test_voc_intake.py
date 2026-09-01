from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.voc_intake import (
    VocIntakeCoordinator,
    VocStep,
    VocWorkflowStore,
    category_choices,
)
from app.contracts import VocCategory, VocCategoryItem


CATEGORIES = tuple(
    VocCategoryItem(code=code, label=label)
    for code, label in (
        (VocCategory.POWER_QUALITY, "แจ้งปัญหาคุณภาพไฟฟ้า"),
        (VocCategory.SERVICE, "แจ้งปัญหาด้านบริการ"),
        (VocCategory.COMPLIMENT, "ชื่นชม"),
        (VocCategory.TIP_OFF, "แจ้งเบาะแส"),
        (VocCategory.OPERATIONS, "แจ้งปัญหาการดำเนินงาน"),
        (VocCategory.STAKEHOLDER_FEEDBACK, "ชื่นชม เสนอแนะ ข้อคิดเห็น"),
    )
)


def test_explicit_power_quality_intent_skips_category_choices() -> None:
    decision = VocIntakeCoordinator().start(
        "อยากร้องเรียนเรื่องคุณภาพของไฟฟ้า",
        CATEGORIES,
    )

    assert decision.state.category is VocCategory.POWER_QUALITY
    assert decision.state.step is VocStep.SUBJECT
    assert decision.needs_categories is False
    assert decision.prompt is not None and "หัวข้อ" in decision.prompt
    assert "เลือกประเภท" not in decision.prompt


def test_ambiguous_complaint_requests_authoritative_category_choices() -> None:
    coordinator = VocIntakeCoordinator()
    decision = coordinator.start("อยากร้องเรียนครับ", CATEGORIES)

    assert decision.state.step is VocStep.CATEGORY
    assert decision.needs_categories is True
    choices = category_choices(CATEGORIES)
    assert "1. แจ้งปัญหาคุณภาพไฟฟ้า" in choices
    assert "6. ชื่นชม เสนอแนะ ข้อคิดเห็น" in choices
    assert "power_quality" not in choices


@pytest.mark.parametrize(
    "selection",
    ["1", "1. แจ้งปัญหาคุณภาพไฟฟ้า", "power_quality", "แจ้งปัญหาคุณภาพไฟฟ้า"],
)
def test_category_selection_advances_to_subject(selection: str) -> None:
    coordinator = VocIntakeCoordinator()
    initial = coordinator.start("อยากร้องเรียนครับ", CATEGORIES)

    decision = coordinator.advance(initial.state, selection, CATEGORIES)

    assert decision.state.category is VocCategory.POWER_QUALITY
    assert decision.state.step is VocStep.SUBJECT
    assert decision.prompt is not None and "หัวข้อ" in decision.prompt
    assert decision.needs_categories is False


def test_labelled_fields_can_complete_intake_without_guessing() -> None:
    coordinator = VocIntakeCoordinator()
    initial = coordinator.start("อยากร้องเรียนเรื่องคุณภาพไฟฟ้า", CATEGORIES)

    decision = coordinator.advance(
        initial.state,
        (
            "subject: ไฟตกทุกคืน; detail: แรงดันไม่คงที่; "
            "contactName: สมชาย ใจดี; contactPhone: 0812345678; "
            "location: เชียงใหม่"
        ),
        CATEGORIES,
    )

    assert decision.state.ready
    assert decision.prompt is None
    payload = decision.state.prepare_input("voc-test-key")
    assert payload["category"] == "power_quality"
    assert payload["subject"] == "ไฟตกทุกคืน"
    assert payload["contactName"] == "สมชาย ใจดี"


def test_unlabelled_reply_fills_only_the_requested_slot() -> None:
    coordinator = VocIntakeCoordinator()
    state = coordinator.start("อยากร้องเรียนเรื่องคุณภาพไฟฟ้า", CATEGORIES).state

    subject = coordinator.advance(state, "ไฟตกทุกคืน", CATEGORIES)
    detail = coordinator.advance(subject.state, "เกิดประมาณสองทุ่มทุกวัน", CATEGORIES)

    assert subject.state.subject == "ไฟตกทุกคืน"
    assert subject.state.detail is None
    assert subject.state.step is VocStep.DETAIL
    assert detail.state.detail == "เกิดประมาณสองทุ่มทุกวัน"
    assert detail.state.step is VocStep.CONTACT_NAME


def test_prepare_input_rejects_incomplete_state() -> None:
    state = VocIntakeCoordinator().start(
        "อยากร้องเรียนเรื่องคุณภาพไฟฟ้า",
        CATEGORIES,
    ).state

    with pytest.raises(ValueError, match="ยังไม่ครบ"):
        state.prepare_input("voc-test-key")


def test_workflow_store_is_scoped_by_conversation_and_resettable() -> None:
    store = VocWorkflowStore()
    conversation_id = uuid4()
    state = VocIntakeCoordinator().start(
        "อยากร้องเรียนเรื่องคุณภาพไฟฟ้า",
        CATEGORIES,
    ).state

    store.put(conversation_id, state)
    assert store.get(conversation_id) == state
    assert store.get(uuid4()) is None

    store.clear()
    assert store.get(conversation_id) is None
