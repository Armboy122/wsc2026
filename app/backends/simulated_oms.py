"""backend OMS (จัดการไฟฟ้าขัดข้อง) ในหน่วยความจำแบบกำหนดผลลัพธ์ได้

อ่านพื้นที่ไฟฟ้าขัดข้องคงที่จาก ``data/mock/oms_outages.json`` และบันทึกรายงานจำลอง
ไว้ในสถานะภายใน process โดยไม่มีการเรียก OMS ระบบจริง ผลลัพธ์การอ่านหรือเตรียม
ข้อมูลไฟฟ้าขัดข้องทุกรายการมี ``safetyMessage``
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import ToolErrorCode


class SimulatedOmsBackend:
    """backend สถานะและรายงานไฟฟ้าขัดข้อง OMS แบบจำลองที่มีสถานะภายใน process ซึ่งรีเซ็ตได้"""

    def __init__(self) -> None:
        rows = load_mock_json("oms_outages.json")
        self._areas: dict[str, dict[str, Any]] = {row["areaCode"]: row for row in rows}
        self._prepared: dict[str, dict[str, Any]] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """ล้างฉบับร่างที่เตรียมไว้และรายงานที่ส่งแล้ว เพื่อคืนสถานะเริ่มต้น"""
        self._prepared.clear()
        self._reports.clear()
        self._seq = 0

    def get_outage_status(self, area_code: str) -> dict[str, Any]:
        """ส่งคืนสถานะไฟฟ้าขัดข้อง fixture สำหรับ ``area_code`` (อ่านอย่างเดียว)"""
        area = self._areas.get(area_code)
        if area is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบพื้นที่")
        return {
            "areaCode": area["areaCode"],
            "status": area["status"],
            "updatedAt": area["updatedAt"],
            "estimatedRestoreAt": area["estimatedRestoreAt"],
            "safetyMessage": area["safetyMessage"],
        }

    def prepare_outage_report(
        self,
        area_code: str,
        location_note: str,
        symptoms: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """ตรวจสอบและจัดเตรียมฉบับร่างรายงานไฟฟ้าขัดข้อง โดยยังไม่ส่งรายงานจำลอง"""
        area = self._areas.get(area_code)
        if area is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบพื้นที่")
        self._prepared[idempotency_key] = {
            "areaCode": area_code,
            "locationNote": location_note,
            "symptoms": symptoms,
        }
        summary = f"เตรียมรายงานไฟฟ้าขัดข้องสำหรับพื้นที่ {area_code}"
        return {
            "areaCode": area_code,
            "summary": summary,
            "safetyMessage": area["safetyMessage"],
        }

    def submit_outage_report(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """ส่งรายงานที่จัดเตรียมไว้เพียงหนึ่งครั้ง โดยตัดรายการซ้ำด้วย idempotency key"""
        existing = self._reports.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "ไม่มีรายงานไฟฟ้าขัดข้องที่จัดเตรียมไว้สำหรับ idempotency key นี้",
            )
        self._seq += 1
        report = {
            "reportId": f"SIM-RPT-{self._seq:06d}",
            "status": "submitted",
            "areaCode": prepared["areaCode"],
        }
        self._reports[idempotency_key] = report
        return dict(report)


default_backend = SimulatedOmsBackend()
