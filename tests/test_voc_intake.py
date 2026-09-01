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


def test_spoken_answers_are_cleaned_without_losing_real_values() -> None:
    """ผู้ใช้เสียงตอบเป็นประโยคเต็ม ระบบต้องเก็บเฉพาะสาระ แต่ห้ามตัดข้อมูลจริงทิ้ง"""
    from app.agent.voc_intake import VocStep, _spoken_value

    # ตัดคำทวนชื่อฟิลด์และคำลงท้ายออก
    assert _spoken_value("ชื่อผู้ร้องเรียน นายอาร์ม ครับ", VocStep.CONTACT_NAME) == "นายอาร์ม"
    assert _spoken_value("เบอร์โทรศัพท์ 0626509444 ครับ", VocStep.CONTACT_PHONE) == "0626509444"
    assert _spoken_value("หมู่บ้านศุภาลัย ครับ", VocStep.LOCATION) == "หมู่บ้านศุภาลัย"
    assert _spoken_value("088-123-4567", VocStep.CONTACT_PHONE) == "0881234567"

    # ค่าจริงที่บังเอิญขึ้นต้นคล้ายคำนำหน้าต้องไม่ถูกตัด
    assert _spoken_value("ชื่นกมล ดีงาม", VocStep.CONTACT_NAME) == "ชื่นกมล ดีงาม"
    assert _spoken_value("ที่ว่าการอำเภอเมือง", VocStep.LOCATION) == "ที่ว่าการอำเภอเมือง"

    # ข้อความอิสระต้องคงเดิม ไม่ตีความเกินจริง
    assert _spoken_value("ไฟตกบ่อยครับที่บ้าน", VocStep.SUBJECT) == "ไฟตกบ่อยครับที่บ้าน"


def test_opening_sentence_supplies_both_category_and_subject() -> None:
    """ประโยคเปิดที่บอกทั้งประเภทและเรื่อง ต้องไม่ถามหัวข้อซ้ำอีก"""
    from app.agent.voc_intake import _subject_from_opening

    categories = CATEGORIES
    assert _subject_from_opening("ร้องเรียนการบริการของเจ้าหน้าที่หน่อยครับ", categories) == "บริการของเจ้าหน้าที่"
    assert _subject_from_opening("อยากร้องเรียนเรื่องไฟตกบ่อยที่บ้านครับ", categories) == "ไฟตกบ่อยที่บ้าน"

    # บอกแค่ประเภทต้องคืน None เพื่อให้ระบบถามหัวข้อตามปกติ ไม่เดาแทนผู้ใช้
    for opening in ("ร้องเรียนบริการครับ", "ขอร้องเรียนครับ", "แจ้งปัญหาด้านบริการ", "ชื่นชม"):
        assert _subject_from_opening(opening, categories) is None


def test_rejected_case_reopens_form_for_the_wrong_field_only() -> None:
    """ปฏิเสธเพราะกรอกผิด ต้องแก้เฉพาะฟิลด์สุดท้าย ไม่ต้องกรอกใหม่ทั้งหมด"""
    from app.agent.voc_intake import VocIntakeState, VocStep
    from app.contracts import VocCategory

    ready = VocIntakeState(
        category=VocCategory.SERVICE,
        subject="บริการล่าช้า",
        detail="รอนานมาก",
        contact_name="นายอาร์ม",
        contact_phone="0626509444",
        location="พิมพ์ผิด",
        step=VocStep.READY,
    )
    reopened = ready.reopen()

    assert reopened.location is None
    assert reopened.step is VocStep.LOCATION
    assert not reopened.ready
    assert (reopened.subject, reopened.contact_name, reopened.contact_phone) == (
        "บริการล่าช้า",
        "นายอาร์ม",
        "0626509444",
    )
