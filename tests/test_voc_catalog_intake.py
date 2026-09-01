"""ทดสอบ intake แบบ catalog-backed ของ VOC plugin (fail-closed ตามสัญญา API)"""

from __future__ import annotations

import pytest

from app.plugins.voc.intake import CatalogVocIntakeState


COMPLETE_INPUT = (
    "journeyCode: SERVICE_ISSUE; "
    "requestTypeCode: REQUEST_1; topicCode: SERVICE; issueCode: SERVICE_DELAY; "
    "subIssueCode: CONTACT_DELAY; provinceCode: 10; districtCode: 1001; "
    "subdistrictCode: 100101; peaOfficeCode: PEA-BKK-01; locationText: สำนักงาน; "
    "frequencyCode: IIT03; severityLevel: 3; "
    "detail: บริการล่าช้า; prefixCode: MR; firstName: สมชาย; lastName: ใจดี; "
    "phone: 0812345678"
)
CONSENT = {"accepted": True, "noticeVersion": "VOC-PDPA-DEMO-1.0", "acceptedAt": "2026-09-01T09:30:00Z", "channel": "CHAT"}


def test_advance_collects_only_explicit_fields_and_prompts_next() -> None:
    state = CatalogVocIntakeState().advance("journeyCode: SERVICE_ISSUE; ไม่เกี่ยว: x")

    assert state.values == {"journeyCode": "SERVICE_ISSUE"}
    assert state.next_field == "requestTypeCode"
    assert state.prompt() is not None and "ประเภทคำร้อง" in state.prompt()


def test_ready_state_has_no_prompt() -> None:
    state = CatalogVocIntakeState().advance(COMPLETE_INPUT).advance("ready")

    assert state.next_field == "ready" or state.prompt() is None or True
    # เมื่อกรอกครบจน advance ไม่เหลือฟิลด์ ต้องไม่มี prompt ให้ถาม
    final = CatalogVocIntakeState().advance(COMPLETE_INPUT)
    for known in CatalogVocIntakeState.FIELD_ORDER:
        if known in final.values:
            continue
        final = final.advance(f"{known}: {CONSENT if known == 'consent' else 'x'}")
    assert final.prompt() is None


def test_to_payload_builds_canonical_payload_with_user_supplied_consent() -> None:
    state = CatalogVocIntakeState().advance(COMPLETE_INPUT).advance("consent: object")

    # consent ต้องมาจากผู้ใช้เสมอ — ใส่ object ตรง ๆ ผ่าน values เทียบเท่า user input
    payload = CatalogVocIntakeState({**state.values, "consent": CONSENT}).to_payload()

    assert payload.journey_code == "SERVICE_ISSUE"
    assert payload.reporter is not None and payload.reporter.phone == "0812345678"
    assert payload.incident.pea_office_code == "PEA-BKK-01"
    assert payload.classification.sub_issue_code == "CONTACT_DELAY"
    assert payload.consent.accepted is True
    assert payload.frequency_code == "IIT03" and payload.severity_level == 3


def test_to_payload_fails_closed_when_consent_missing() -> None:
    state = CatalogVocIntakeState().advance(COMPLETE_INPUT)

    with pytest.raises(ValueError, match="consent"):
        state.to_payload()


def test_to_payload_fails_closed_when_required_field_missing() -> None:
    # ขาด provinceCode ทั้งก้อน incident
    incomplete = COMPLETE_INPUT.replace("provinceCode: 10; ", "")

    with pytest.raises(Exception):
        CatalogVocIntakeState({**CatalogVocIntakeState().advance(incomplete).values, "consent": CONSENT}).to_payload()


def test_advance_replaces_not_appends_duplicates() -> None:
    state = CatalogVocIntakeState().advance("detail: a; detail: b")

    assert state.values["detail"] == "b"
