"""ทดสอบแบ็กเอนด์ VOC จำลองที่ให้ผลลัพธ์แบบกำหนดแน่นอน"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.backends import BackendError
from app.backends.simulated_voc import SimulatedVocBackend
from app.contracts import ContactChannel, ToolErrorCode, VocCategory


def _prepare(
    backend: SimulatedVocBackend,
    *,
    category: VocCategory = VocCategory.SERVICE,
    subject: str = "ยอดค่าไฟไม่ถูกต้อง",
    detail: str = "ค่าไฟล่าสุดดูสูงเกินไป",
    contact_name: str = "สมชาย ใจดี",
    contact_phone: str = "0812345678",
    location: str = "ถนนสุขุมวิท กรุงเทพฯ",
    contact_channel: ContactChannel = ContactChannel.EMAIL,
    key: str = "k1",
) -> dict:
    return backend.prepare_case(
        category,
        subject,
        detail,
        contact_name,
        contact_phone,
        location,
        contact_channel,
        key,
    )


def test_list_categories_returns_fixture_categories():
    backend = SimulatedVocBackend()
    out = backend.list_categories()
    codes = [item["code"] for item in out["categories"]]
    assert codes == ["power_quality", "service", "compliment", "tip_off", "operations", "stakeholder_feedback"]
    assert all(item["label"] for item in out["categories"])


def test_prepare_case_has_no_side_effect():
    backend = SimulatedVocBackend()
    subject = "ยอดค่าไฟไม่ถูกต้อง"
    detail = "ค่าไฟล่าสุดดูสูงเกินไป"
    out = _prepare(backend, subject=subject, detail=detail)
    assert out["category"] == "service"
    assert out["subject"] == subject
    # สรุปสำหรับการยืนยันต้องปลอดภัยจาก PII และระบุเฉพาะหมวดหมู่
    # โดยต้องไม่เปิดเผยหัวข้อ รายละเอียด ชื่อ หรือเบอร์โทรที่ผู้ใช้ระบุ
    assert out["summary"] == "เตรียมเรื่องร้องเรียนประเภท แจ้งปัญหาด้านบริการ"
    assert "service" not in out["summary"]
    assert subject not in out["summary"]
    assert detail not in out["summary"]
    # การเตรียมข้อมูลต้องยังไม่สร้างเคส
    assert backend._cases == {}


def test_submit_case_without_prepare_raises_not_found():
    backend = SimulatedVocBackend()
    with pytest.raises(BackendError) as exc:
        backend.submit_case(uuid4(), "missing")
    assert exc.value.code is ToolErrorCode.NOT_FOUND


def test_submit_case_deduplicates_by_idempotency_key():
    backend = SimulatedVocBackend()
    _prepare(backend, category=VocCategory.TIP_OFF, subject="สายไฟตก", detail="มีสายไฟตกอยู่บนถนนของฉัน", contact_channel=ContactChannel.PHONE)
    first = backend.submit_case(uuid4(), "k1")
    second = backend.submit_case(uuid4(), "k1")
    assert first == second
    assert first["status"] == "submitted"
    assert first["category"] == "tip_off"
    assert first["vocId"] == first["caseId"]
    assert first["trackingKey"]
    assert len(backend._cases) == 1


def test_submit_case_returns_voc_id_and_tracking_key():
    backend = SimulatedVocBackend()
    _prepare(backend, key="k1")
    out = backend.submit_case(uuid4(), "k1")
    assert out["vocId"] == "SIM-CASE-000001"
    assert len(out["trackingKey"]) >= 8


def test_get_case_returns_status_with_matching_key():
    backend = SimulatedVocBackend()
    _prepare(backend, category=VocCategory.SERVICE, key="k1")
    submitted = backend.submit_case(uuid4(), "k1")
    out = backend.get_case(submitted["vocId"], submitted["trackingKey"])
    assert out["vocId"] == submitted["vocId"]
    assert out["status"] == "submitted"
    assert out["category"] == "service"
    assert out["createdAt"] == out["updatedAt"]


def test_get_case_wrong_key_fails_closed():
    backend = SimulatedVocBackend()
    _prepare(backend, key="k1")
    submitted = backend.submit_case(uuid4(), "k1")
    with pytest.raises(BackendError) as exc:
        backend.get_case(submitted["vocId"], "wrong-key")
    assert exc.value.code is ToolErrorCode.NOT_FOUND
    # คีย์ผิดและ vocId ไม่มีอยู่ต้องล้มเหลวเหมือนกัน (ไม่รั่วไหลว่า vocId มีจริง)
    with pytest.raises(BackendError) as missing:
        backend.get_case("SIM-CASE-999999", "wrong-key")
    assert missing.value.code is ToolErrorCode.NOT_FOUND


def test_reset_clears_drafts_but_keeps_submitted_cases_trackable():
    """ผู้ใช้ถือคีย์ติดตามไว้แล้ว จึงต้องติดตามเคสที่ส่งแล้วได้ต่อหลังรีเซ็ต"""
    backend = SimulatedVocBackend()
    _prepare(backend, key="k1")
    submitted = backend.submit_case(uuid4(), "k1")
    _prepare(backend, key="draft-only")

    backend.reset()

    assert backend._prepared == {}
    tracked = backend.get_case(submitted["vocId"], submitted["trackingKey"])
    assert tracked["status"] == "submitted"


def test_reset_does_not_recycle_voc_ids():
    """ตัวนับต้องไม่ย้อนกลับ มิฉะนั้นเคสใหม่จะได้ ``vocId`` ซ้ำกับเคสที่ยังติดตามอยู่"""
    backend = SimulatedVocBackend()
    _prepare(backend, key="k1")
    first = backend.submit_case(uuid4(), "k1")

    backend.reset()
    _prepare(backend, key="k2")
    second = backend.submit_case(uuid4(), "k2")

    assert first["vocId"] != second["vocId"]
