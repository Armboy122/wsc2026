"""ทดสอบแบ็กเอนด์ VOC จำลองที่ให้ผลลัพธ์แบบกำหนดแน่นอน"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.backends import BackendError
from app.backends.simulated_voc import SimulatedVocBackend
from app.contracts import ContactChannel, ToolErrorCode, VocCategory


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
    out = backend.prepare_case(
        VocCategory.SERVICE,
        subject,
        detail,
        ContactChannel.EMAIL,
        "k1",
    )
    assert out["category"] == "service"
    assert out["subject"] == subject
    # สรุปสำหรับการยืนยันต้องปลอดภัยจาก PII และระบุเฉพาะหมวดหมู่
    # โดยต้องไม่เปิดเผยหัวข้อหรือรายละเอียดที่ผู้ใช้ระบุ
    assert out["summary"] == "เตรียมเคสหมวดหมู่ service"
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
    backend.prepare_case(
        VocCategory.TIP_OFF,
        "สายไฟตก",
        "มีสายไฟตกอยู่บนถนนของฉัน",
        ContactChannel.PHONE,
        "k1",
    )
    first = backend.submit_case(uuid4(), "k1")
    second = backend.submit_case(uuid4(), "k1")
    assert first == second
    assert first["status"] == "submitted"
    assert first["category"] == "tip_off"
    assert len(backend._cases) == 1


def test_reset_clears_state():
    backend = SimulatedVocBackend()
    backend.prepare_case(
        VocCategory.SERVICE,
        "คำถาม",
        "คำถามทั่วไป",
        ContactChannel.NONE,
        "k1",
    )
    backend.submit_case(uuid4(), "k1")
    backend.reset()
    assert backend._prepared == {}
    assert backend._cases == {}
    assert backend._seq == 0
