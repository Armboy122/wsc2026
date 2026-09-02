"""Catalog-driven VOC intake: every branch must come from the catalog, not a guess."""

from __future__ import annotations

import pytest

from app.contracts import VocExternalCasePayload
from app.plugins.voc.intake import (
    CA_SKIP,
    CONSENT_ACCEPT,
    STEP_CA_NUMBER,
    STEP_CONSENT,
    STEP_JOURNEY,
    STEP_SUB_ISSUE,
    IntakeError,
    VocIntakeFlow,
    VocIntakeState,
)

_TEXT_ANSWERS = {
    "voc_subject": "พนักงานพูดจาไม่สุภาพ",
    "voc_detail": "ไปติดต่อที่สำนักงานแล้วพนักงานพูดไม่สุภาพ",
    "voc_reporter_name": "สมชาย ใจดี",
    "voc_reporter_phone": "0812345678",
    "voc_location_text": "หน้าสำนักงานการไฟฟ้า",
}


def _catalog() -> dict:
    """Catalog ย่อที่มีโครงครบเหมือน gateway จริง แต่คุมค่าได้ในเทสต์"""
    return {
        "catalogVersion": "TEST-1",
        "journeys": [
            {
                "code": "SERVICE_ISSUE", "label": "แจ้งปัญหาด้านบริการ", "reporterMode": "REQUIRED",
                "classificationRootCodes": ["REQUEST_1"], "requiresFrequency": True,
                "requiresSeverity": True, "requiresSubIssue": True, "requiresIncidentLocation": True,
                "supportsCaNumber": True,
            },
            {
                "code": "TIP_OFF", "label": "แจ้งเบาะแส", "reporterMode": "OPTIONAL",
                "classificationRootCodes": ["REQUEST_4"], "requiresFrequency": False,
                "requiresSeverity": False, "requiresSubIssue": False, "requiresIncidentLocation": True,
                "supportsCaNumber": False,
            },
        ],
        "requestTypes": [
            {
                "code": "REQUEST_1", "name": "ร้องเรียน",
                "topics": [{
                    "code": "SERVICE", "name": "การให้บริการ",
                    "issues": [{
                        "code": "SERVICE_DELAY", "name": "บริการล่าช้า",
                        "subIssues": [
                            {"code": "CONTACT_DELAY", "name": "ติดต่อกลับล่าช้า"},
                            {"code": "QUEUE_DELAY", "name": "รอคิวนาน"},
                        ],
                    }],
                }],
            },
            {
                "code": "REQUEST_4", "name": "แจ้งเบาะแส",
                "topics": [{
                    "code": "SAFETY", "name": "ความปลอดภัย",
                    "issues": [{"code": "SUSPICIOUS_ACTIVITY", "name": "พบความผิดปกติ", "subIssues": []}],
                }],
            },
        ],
        "incidentFrequencies": [{"code": "IIT01", "name": "ครั้งแรก", "rank": 1}],
        "severityLevels": [{"level": 3, "name": "ผลกระทบปานกลาง"}],
        "titlePrefixes": [{"code": "MR", "label": "นาย"}],
        "serviceAreas": [{
            "provinceCode": "10", "provinceName": "กรุงเทพมหานคร",
            "districtCode": "1001", "districtName": "เขตพระนคร",
            "subdistrictCode": "100101", "subdistrictName": "พระบรมมหาราชวัง",
            "peaOfficeCode": "PEA-BKK-01", "peaOfficeName": "สำนักงานตัวอย่าง",
        }],
    }


def _flow() -> VocIntakeFlow:
    return VocIntakeFlow(_catalog(), consent_notice_version="TEST-PDPA-1")


def _walk(flow: VocIntakeFlow, journey: str) -> VocIntakeState:
    """เดินจนจบโดยเลือกตัวเลือกแรกเสมอ เพื่อทดสอบว่า flow ยุติได้จริง"""
    state = VocIntakeState()
    for _ in range(40):
        state, prompt = flow.resolve(state)
        if prompt is None:
            return state
        if prompt.prompt_id == STEP_JOURNEY:
            answer = journey
        elif prompt.prompt_id == STEP_CONSENT:
            answer = CONSENT_ACCEPT
        elif prompt.options:
            answer = prompt.options[0].value
        else:
            answer = _TEXT_ANSWERS.get(prompt.prompt_id, "ข้อมูลทดสอบ")
        state = flow.apply(state, prompt, answer)
    raise AssertionError("flow ไม่ยุติภายในจำนวนขั้นที่กำหนด")


@pytest.mark.parametrize("journey", ["SERVICE_ISSUE", "TIP_OFF"])
def test_completed_flow_builds_a_contract_valid_payload(journey: str) -> None:
    """ทุก journey ต้องได้ payload ที่ผ่านสัญญาของ gateway โดยไม่ต้องเดารหัส"""
    flow = _flow()
    state = _walk(flow, journey)

    payload = flow.build_external_payload(state)

    VocExternalCasePayload.model_validate(payload)
    assert payload["journeyCode"] == journey
    assert payload["consent"]["noticeVersion"] == "TEST-PDPA-1"


def test_journey_requirement_flags_decide_which_questions_are_asked() -> None:
    """คำถามความถี่/ความรุนแรง/ประเด็นย่อยต้องมาจาก flag ของ journey ไม่ใช่ค่าคงที่ในโค้ด"""
    flow = _flow()

    service = flow.build_external_payload(_walk(flow, "SERVICE_ISSUE"))
    tip_off = flow.build_external_payload(_walk(flow, "TIP_OFF"))

    assert service["frequencyCode"] == "IIT01"
    assert service["severityLevel"] == 3
    assert service["classification"]["subIssueCode"] == "CONTACT_DELAY"
    # TIP_OFF ไม่ประกาศ requiresFrequency/Severity/SubIssue จึงต้องไม่ถูกถามและไม่มีในpayload
    assert "frequencyCode" not in tip_off
    assert "severityLevel" not in tip_off
    assert tip_off["classification"].get("subIssueCode") is None


def test_optional_reporter_journey_stays_anonymous() -> None:
    """reporterMode=OPTIONAL ต้องไม่บังคับเก็บตัวตนผู้แจ้ง"""
    flow = _flow()

    payload = flow.build_external_payload(_walk(flow, "TIP_OFF"))

    assert "reporter" not in payload


def test_required_reporter_journey_collects_identity() -> None:
    flow = _flow()

    payload = flow.build_external_payload(_walk(flow, "SERVICE_ISSUE"))

    assert payload["reporter"]["prefixCode"] == "MR"
    assert payload["reporter"]["phone"] == "0812345678"


def test_answer_outside_the_catalog_is_rejected() -> None:
    """ค่าที่ไม่ได้มาจาก catalog ต้องถูกปฏิเสธ ไม่ว่ามาจากทางใด"""
    flow = _flow()
    _, prompt = flow.resolve(VocIntakeState())

    with pytest.raises(IntakeError):
        flow.apply(VocIntakeState(), prompt, "JOURNEY_THAT_DOES_NOT_EXIST")


def test_payload_requires_explicit_consent() -> None:
    """ห้ามประกอบ payload เมื่อผู้ใช้ยังไม่ได้กดยินยอมจริง"""
    flow = _flow()
    state = _walk(flow, "SERVICE_ISSUE")
    without_consent = VocIntakeState(
        {key: value for key, value in state.answers.items() if key != STEP_CONSENT}
    )

    with pytest.raises(IntakeError):
        flow.build_external_payload(without_consent)


def test_changing_an_upstream_answer_clears_dependent_codes() -> None:
    """ย้อนไปเปลี่ยนประเภทเรื่องแล้ว รหัสปลายทางเดิมต้องไม่ค้างจนสร้าง payload ที่ขัดกันเอง"""
    flow = _flow()
    state = _walk(flow, "SERVICE_ISSUE")
    assert state.answers[STEP_SUB_ISSUE] == "CONTACT_DELAY"

    switched = state.with_answer(STEP_JOURNEY, "TIP_OFF")

    assert STEP_SUB_ISSUE not in switched.answers
    assert "voc_request_type" not in switched.answers


def test_single_option_steps_are_not_asked() -> None:
    """ขั้นที่มีทางเลือกเดียวต้องถูกเติมให้เอง เพื่อไม่ถามคำถามที่ไม่มีทางเลือกจริง"""
    flow = _flow()
    state = VocIntakeState().with_answer(STEP_JOURNEY, "SERVICE_ISSUE")

    resolved, prompt = flow.resolve(state)

    # REQUEST_1 เป็น root เดียวของ journey นี้ และมี topic/issue อย่างละหนึ่ง
    assert resolved.answers["voc_request_type"] == "REQUEST_1"
    assert resolved.answers["voc_topic"] == "SERVICE"
    assert resolved.answers["voc_issue"] == "SERVICE_DELAY"
    assert prompt is not None and prompt.prompt_id == STEP_SUB_ISSUE


def test_out_of_catalog_location_is_accepted_as_free_text() -> None:
    """จังหวัดนอกข้อมูลตัวอย่างต้องแจ้งเรื่องได้ ไม่ใช่ถูกกันออกจากบริการ

    catalog สาธิตมี serviceAreas เพียงแถวเดียว การบังคับเลือกจากรายการ
    จึงทำให้ผู้ใช้ต่างจังหวัดใช้งานไม่ได้เลย
    """
    flow = _flow()
    state = VocIntakeState()
    for _ in range(40):
        state, prompt = flow.resolve(state)
        if prompt is None:
            break
        if prompt.prompt_id == STEP_JOURNEY:
            answer = "SERVICE_ISSUE"
        elif prompt.prompt_id == STEP_CONSENT:
            answer = CONSENT_ACCEPT
        elif prompt.prompt_id == "voc_location_text":
            answer = "บ้านเลขที่ 45 ต.เขารูปช้าง อ.เมือง จ.สงขลา"
        elif prompt.prompt_id == STEP_CA_NUMBER:
            answer = CA_SKIP
        elif prompt.options:
            answer = prompt.options[0].value
        else:
            answer = _TEXT_ANSWERS.get(prompt.prompt_id, "ข้อมูลทดสอบ")
        state = flow.apply(state, prompt, answer)

    payload = flow.build_external_payload(state)

    VocExternalCasePayload.model_validate(payload)
    assert payload["incident"]["locationText"].endswith("สงขลา")
    # ส่ง locationText ให้ VOC map เอง แทนการยัดรหัสพื้นที่ที่ไม่ตรงความจริง
    assert payload["incident"]["provinceCode"] == "UNSPECIFIED"


def test_location_matching_the_catalog_still_resolves_real_codes() -> None:
    flow = _flow()
    state = VocIntakeState().with_answer(STEP_JOURNEY, "SERVICE_ISSUE")
    state, prompt = flow.resolve(state)
    while prompt is not None and prompt.prompt_id != "voc_location_text":
        answer = CONSENT_ACCEPT if prompt.prompt_id == STEP_CONSENT else prompt.options[0].value
        state = flow.apply(state, prompt, answer)
        state, prompt = flow.resolve(state)

    state = flow.apply(state, prompt, "แถวพระบรมมหาราชวัง เขตพระนคร กรุงเทพมหานคร")
    state, _ = flow.resolve(state)

    assert state.answers["voc_province"] == "10"
    assert state.answers["voc_office"] == "PEA-BKK-01"


def test_ca_number_is_optional_and_validated_when_given() -> None:
    """CA ช่วยระบุจุดใช้ไฟ แต่ catalog บอกว่า supports ไม่ใช่ required"""
    flow = _flow()
    state = VocIntakeState().with_answer(STEP_JOURNEY, "SERVICE_ISSUE")
    state, prompt = flow.resolve(state)
    while prompt is not None and prompt.prompt_id != STEP_CA_NUMBER:
        if prompt.options:
            answer = CONSENT_ACCEPT if prompt.prompt_id == STEP_CONSENT else prompt.options[0].value
        else:
            answer = _TEXT_ANSWERS.get(prompt.prompt_id, "ข้อมูลทดสอบ")
        state = flow.apply(state, prompt, answer)
        state, prompt = flow.resolve(state)

    assert prompt is not None and prompt.allow_free_text is True
    with pytest.raises(IntakeError):
        flow.apply(state, prompt, "12345")  # สั้นเกินไป
    assert flow.apply(state, prompt, CA_SKIP).answers[STEP_CA_NUMBER] == CA_SKIP
    assert flow.apply(state, prompt, "100000000003").answers[STEP_CA_NUMBER] == "100000000003"


def test_skipped_ca_is_not_sent_to_the_gateway() -> None:
    flow = _flow()
    state = _walk(flow, "SERVICE_ISSUE")

    payload = flow.build_external_payload(state)

    assert "caNumber" not in payload.get("reporter", {})
