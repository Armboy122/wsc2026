"""backend VOC (เสียงของลูกค้า) ในหน่วยความจำแบบกำหนดผลลัพธ์ได้

อ่านหมวดหมู่คงที่จาก ``data/mock/voc_categories.json`` และบันทึกเคสจำลอง
ไว้ในสถานะภายใน process โดยไม่มีการเรียก CRM หรือ contact centre ระบบจริง
เคสที่ส่งแล้วจะได้ ``vocId`` (เลขติดตาม) พร้อม ``trackingKey`` (คีย์ยืนยัน)
ซึ่งผู้ใช้ต้องใช้คู่กันเพื่อติดตามสถานะเรื่องร้องเรียน
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
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
        contact_name: str,
        contact_phone: str,
        location: str,
        contact_channel: ContactChannel,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """ตรวจสอบและจัดเตรียมฉบับร่างเคส โดยยังไม่สร้างเคสจำลอง"""
        self._prepared[idempotency_key] = {
            "category": category.value,
            "subject": subject,
            "detail": detail,
            "contactName": contact_name,
            "contactPhone": contact_phone,
            "location": location,
            "contactChannel": contact_channel.value,
        }
        summary = f"เตรียมเคสหมวดหมู่ {category.value}"
        return {
            "category": category.value,
            "subject": subject,
            "summary": summary,
        }

    def submit_case(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """สร้างเคสที่จัดเตรียมไว้เพียงหนึ่งครั้ง โดยตัดรายการซ้ำด้วย idempotency key

        เคสที่สร้างแล้วจะได้ ``vocId`` (เลขติดตาม) และ ``trackingKey`` (คีย์ยืนยัน)
        ซึ่งผู้ใช้ต้องเก็บไว้เพื่อใช้ติดตามสถานะเรื่องร้องเรียนภายหลัง
        """
        existing = self._cases.get(idempotency_key)
        if existing is not None:
            return {
                "caseId": existing["caseId"],
                "vocId": existing["vocId"],
                "trackingKey": existing["trackingKey"],
                "status": existing["status"],
                "category": existing["category"],
            }
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "ไม่มีเคสที่จัดเตรียมไว้สำหรับ idempotency key นี้",
            )
        self._seq += 1
        now = datetime.now(UTC)
        voc_id = f"SIM-CASE-{self._seq:06d}"
        tracking_key = secrets.token_urlsafe(6)
        case = {
            "caseId": voc_id,
            "vocId": voc_id,
            "trackingKey": tracking_key,
            "status": "submitted",
            "category": prepared["category"],
            "createdAt": now,
            "updatedAt": now,
        }
        self._cases[idempotency_key] = case
        return {
            "caseId": case["caseId"],
            "vocId": case["vocId"],
            "trackingKey": case["trackingKey"],
            "status": case["status"],
            "category": case["category"],
        }

    def get_case(self, voc_id: str, tracking_key: str) -> dict[str, Any]:
        """ค้นหาเคสด้วย ``vocId`` + ``trackingKey`` ที่ต้องตรงกันทั้งคู่

        หากคีย์ไม่ตรงหรือไม่พบเคส ให้ล้มเหลวแบบ fail-closed โดยไม่เปิดเผยว่า
        ``vocId`` มีอยู่จริงหรือไม่
        """
        match = next(
            (
                case
                for case in self._cases.values()
                if case["vocId"] == voc_id and case["trackingKey"] == tracking_key
            ),
            None,
        )
        if match is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "ไม่พบเคสสำหรับ vocId และ trackingKey ที่ระบุ",
            )
        return {
            "vocId": match["vocId"],
            "status": match["status"],
            "category": match["category"],
            "createdAt": match["createdAt"],
            "updatedAt": match["updatedAt"],
        }


default_backend = SimulatedVocBackend()
