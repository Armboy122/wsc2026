"""VOC presentation policy, loaded only when the VOC plugin is enabled."""

from __future__ import annotations

from app.contracts import ToolAction, ToolErrorCode, ToolName, ToolResult, ToolResultStatus


class VocResponsePolicy:
    """Own VOC-specific planner guidance and trusted result presentation."""

    planner_instructions = """สำหรับ VOC ใช้ voc_tool.list_categories เพื่อโหลด taxonomy ล่าสุดก่อนเตรียมเรื่อง
voc_tool.prepare_case ต้องส่งข้อมูลตาม input schema ให้ครบ และเมื่อเชื่อม REST gateway ต้องมี externalPayload ที่ผู้ใช้ให้จริง รวม taxonomy, location และ consent; ห้ามเดารหัสหรือการยินยอม
ใช้ voc_tool.get_case เมื่อติดตามเรื่องด้วย vocId และ trackingKey ครบเท่านั้น
ใช้ directResponse ได้เฉพาะ [voc_details, voc_contact_name, voc_contact_phone, voc_location, voc_tracking_inputs] เมื่อจำเป็นต้องถามข้อมูลเพิ่ม"""

    _direct_messages = {
        "voc_details": "กรุณาระบุหัวข้อและรายละเอียดของเรื่องที่ต้องการแจ้งครับ",
        "voc_contact_name": "กรุณาระบุชื่อผู้ร้องเรียนเพื่อเตรียมเรื่องครับ",
        "voc_contact_phone": "กรุณาระบุเบอร์โทรที่สะดวกให้เจ้าหน้าที่ติดต่อกลับครับ",
        "voc_location": "กรุณาระบุสถานที่เกิดเหตุหรือพื้นที่ที่เกี่ยวข้องครับ",
        "voc_tracking_inputs": "กรุณาระบุเลขเรื่อง VOC และคีย์ติดตามที่ได้รับตอนส่งเรื่องให้ครบครับ",
        "voc_demo_prepare_unavailable": "โหมดออฟไลน์รองรับการดูประเภทเรื่องและติดตามเคส VOC เท่านั้น การเปิดเคสใหม่ต้องใช้ตัวช่วยที่เชื่อม provider เพื่อรวบรวม taxonomy สถานที่ และ consent โดยไม่เดาข้อมูลครับ",
    }

    def direct_message(self, kind: str, followup_text: str, allow_grounded_followup: bool) -> str | None:
        del followup_text, allow_grounded_followup
        return self._direct_messages.get(kind)

    def result_fact(self, result: ToolResult) -> str | None:
        if result.name is not ToolName.VOC or result.status is not ToolResultStatus.SUCCESS:
            return None
        data = result.data or {}
        if result.action is ToolAction.VOC_LIST_CATEGORIES:
            categories = data.get("categories")
            if isinstance(categories, list):
                labels = [item.get("label") for item in categories if isinstance(item, dict) and isinstance(item.get("label"), str)]
                if labels:
                    choices = "\n".join(f"{index}. {label}" for index, label in enumerate(labels, start=1))
                    return f"ประเภทเรื่องที่เลือกได้มีดังนี้:\n{choices}"
        if result.action is ToolAction.VOC_GET_CASE:
            voc_id, status = data.get("vocId"), data.get("status")
            if isinstance(voc_id, str) and isinstance(status, str):
                return f"เรื่องร้องเรียนเลขที่ {voc_id} มีสถานะ {status} ครับ"
        summary = data.get("summary")
        if isinstance(summary, str):
            return summary
        if result.action is ToolAction.VOC_SUBMIT_CASE:
            voc_id, tracking_key = data.get("vocId"), data.get("trackingKey")
            prefix = "ผลจำลอง: " if result.simulation else ""
            if isinstance(voc_id, str) and isinstance(tracking_key, str):
                return f"{prefix}ส่งเรื่องร้องเรียนแล้ว เลขเรื่อง {voc_id} และคีย์ติดตาม {tracking_key} ครับ"
            return f"{prefix}ส่งเรื่องร้องเรียนแล้วครับ"
        return None

    def error_message(self, result: ToolResult) -> str | None:
        if result.name is not ToolName.VOC:
            return None
        code = result.error.code if result.error else None
        if result.action is ToolAction.VOC_GET_CASE and code is ToolErrorCode.NOT_FOUND:
            return "ไม่พบเรื่องร้องเรียนที่ตรงกับเลขเรื่องและคีย์ติดตาม กรุณาตรวจสอบทั้งสองค่าอีกครั้งครับ"
        if code is ToolErrorCode.INVALID_INPUT:
            return "ข้อมูลเรื่องร้องเรียนยังไม่ครบหรือไม่ตรงกับ catalog กรุณาตรวจสอบข้อมูลแล้วลองใหม่ครับ"
        if code is ToolErrorCode.CONFLICT:
            return "รายการ VOC นี้ขัดแย้งกับข้อมูลที่ส่งไว้ก่อนหน้า กรุณาเริ่มเตรียมรายการใหม่ครับ"
        return None

    def grounds_followup(self, result: ToolResult) -> bool:
        return (
            result.name is ToolName.VOC
            and result.action is ToolAction.VOC_GET_CASE
            and result.status is ToolResultStatus.SUCCESS
        )
