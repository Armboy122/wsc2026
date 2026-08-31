"""backend VOC (เสียงของลูกค้า) ในหน่วยความจำแบบกำหนดผลลัพธ์ได้

อ่านหมวดหมู่คงที่จาก ``data/mock/voc_categories.json`` และบันทึกเคสจำลอง
ไว้ในสถานะภายใน process โดยไม่มีการเรียก CRM หรือ contact centre ระบบจริง
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import ContactChannel, ToolErrorCode, VocCategory


class SimulatedVocBackend:
    """backend หมวดหมู่และเคส VOC แบบจำลองที่มีสถานะภายใน process ซึ่งรีเซ็ตได้"""

    def __init__(self) -> None:
        self._categories: list[dict[str, Any]] = load_mock_json("voc_categories.json")
        self._prepared: dict[str, dict[str, Any]] = {}
        self._cases: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """ล้างฉบับร่างที่เตรียมไว้และเคสที่ส่งแล้ว เพื่อคืนสถานะเริ่มต้น"""
        self._prepared.clear()
        self._cases.clear()
        self._seq = 0

    def list_categories(self) -> dict[str, Any]:
        """ส่งคืนรายการหมวดหมู่คงที่ (อ่านอย่างเดียว)"""
        return {
            "categories": [
                {"code": item["code"], "label": item["label"]} for item in self._categories
            ]
        }

    def prepare_case(
        self,
        category: VocCategory,
        subject: str,
        detail: str,
        contact_channel: ContactChannel,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """ตรวจสอบและจัดเตรียมฉบับร่างเคส โดยยังไม่สร้างเคสจำลอง"""
        self._prepared[idempotency_key] = {
            "category": category.value,
            "subject": subject,
            "detail": detail,
            "contactChannel": contact_channel.value,
        }
        summary = f"เตรียมเคสหมวดหมู่ {category.value}"
        return {
            "category": category.value,
            "subject": subject,
            "summary": summary,
        }

    def submit_case(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """สร้างเคสที่จัดเตรียมไว้เพียงหนึ่งครั้ง โดยตัดรายการซ้ำด้วย idempotency key"""
        existing = self._cases.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "ไม่มีเคสที่จัดเตรียมไว้สำหรับ idempotency key นี้",
            )
        self._seq += 1
        case = {
            "caseId": f"SIM-CASE-{self._seq:06d}",
            "status": "submitted",
            "category": prepared["category"],
        }
        self._cases[idempotency_key] = case
        return dict(case)


default_backend = SimulatedVocBackend()
