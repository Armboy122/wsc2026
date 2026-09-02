"""OMS presentation policy, loaded only when the OMS plugin is enabled."""

from __future__ import annotations

from app.agent.response_policy import ErrorPresentation
from app.contracts import ToolAction, ToolErrorCode, ToolName, ToolResult, ToolResultStatus


class OmsResponsePolicy:
    """Turn trusted OMS outcomes and planner labels into user-facing text."""

    planner_instructions = """สำหรับ OMS ใช้ directResponse ได้เฉพาะ [oms_ca_number, oms_outage_start, oms_with_ca_inputs, oms_anonymous_inputs]
การแจ้งเหตุ OMS ที่มี caNumber ต้องเรียก oms_tool.get_outage_by_ca ก่อนเสมอ ห้ามเรียก prepare_outage_with_ca ในรอบเดียวกัน หลังผลตรวจมี activeEvent ให้สรุปเหตุเดิม; เมื่อ activeEvent เป็น null และ recommendedAction เป็น CREATE_METER_EVENT จึงเรียก prepare_outage_with_ca และหากขาด description ให้ใช้ oms_with_ca_inputs
การแจ้งเหตุแบบไม่ทราบ CA ใช้ prepare_anonymous_outage ได้เมื่อมี description, location และ contactPhone ครบ; หากยังไม่ทราบว่าผู้ใช้มี CA หรือไม่ ให้ใช้ oms_outage_start"""

    _direct_messages = {
        "oms_ca_number": "ได้ครับ กรุณาแจ้งหมายเลขผู้ใช้ไฟ 12 หลัก (ดูได้จากบิลค่าไฟ) เพื่อตรวจสอบเหตุไฟฟ้าขัดข้องครับ",
        "oms_outage_start": "ได้ครับ กรุณาแจ้งก่อนว่าคุณมีหมายเลขผู้ใช้ไฟ (CA) 12 หลัก หรือไม่ครับ\n- ถ้ามี: กรุณาแจ้งหมายเลข 12 หลักพร้อมอาการที่เกิดขึ้นครับ\n- ถ้าไม่มี: กรุณาแจ้ง 3 อย่างนี้ครับ: อาการ สถานที่หรือที่อยู่คร่าว ๆ และเบอร์โทรที่ติดต่อกลับได้",
        "oms_with_ca_inputs": "ได้ครับ กรุณาแจ้งหมายเลขผู้ใช้ไฟ 12 หลักและอาการที่เกิดขึ้นครับ ถ้าสะดวก แนบเบอร์โทรติดต่อกลับหรือที่อยู่เพิ่มเติมได้ครับ",
        "oms_anonymous_inputs": "ได้ครับ กรุณาแจ้งอาการที่เกิดขึ้น สถานที่หรือที่อยู่คร่าว ๆ และเบอร์โทรที่ติดต่อกลับได้ครับ",
    }

    def direct_message(self, kind: str, followup_text: str, allow_grounded_followup: bool) -> str | None:
        if kind not in self._direct_messages:
            return None
        if kind == "oms_ca_number" and allow_grounded_followup and followup_text:
            return followup_text
        return self._direct_messages[kind]

    def result_fact(self, result: ToolResult) -> str | None:
        if result.name is not ToolName.OMS or result.status is not ToolResultStatus.SUCCESS:
            return None
        data = result.data or {}
        safety = data.get("safetyMessage")
        if result.action is ToolAction.OMS_GET_OUTAGE_BY_CA:
            active_event = data.get("activeEvent")
            if isinstance(active_event, dict) and isinstance(active_event.get("message"), str):
                status = active_event.get("status")
                message = f"สถานะ {status}: {active_event['message']}" if isinstance(status, str) else active_event["message"]
                return f"{safety}\n\n{message}" if isinstance(safety, str) else message
            return "ไม่พบเหตุไฟฟ้าขัดข้องที่เกี่ยวข้องในขณะนี้ครับ"
        if result.action in {ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE}:
            summary = data.get("summary")
            return summary if isinstance(summary, str) else "เตรียมแจ้งเหตุไฟฟ้าขัดข้องแล้วครับ"
        if result.action in {ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE}:
            message, status = data.get("message"), data.get("status")
            reference = data.get("eventId") or data.get("reportId")
            prefix = f"สถานะ {status}: " if isinstance(status, str) else ""
            if isinstance(message, str) and isinstance(reference, str):
                return f"{prefix}{message} (เลขอ้างอิง {reference})"
            return f"{prefix}{message}" if isinstance(message, str) else "ดำเนินการกับ OMS เรียบร้อยแล้วครับ"
        return None

    def error_presentation(self, result: ToolResult) -> ErrorPresentation | None:
        if result.name is not ToolName.OMS:
            return None
        code = result.error.code if result.error else None
        if result.action is ToolAction.OMS_GET_OUTAGE_BY_CA and code is ToolErrorCode.NOT_FOUND:
            return ErrorPresentation(
                code=code,
                explanation="ไม่พบหมายเลขผู้ใช้ไฟนี้ในระบบครับ",
                next_step="กรุณาตรวจสอบหมายเลขอีกครั้ง หรือแจ้งอาการ สถานที่ และเบอร์โทรเพื่อแจ้งเหตุแทนได้ครับ",
                retryable=True,
            )
        if result.action in {ToolAction.OMS_GET_OUTAGE_BY_CA, ToolAction.OMS_PREPARE_OUTAGE_WITH_CA} and code is ToolErrorCode.INVALID_INPUT:
            return ErrorPresentation(
                code=code,
                explanation="หมายเลขผู้ใช้ไฟต้องเป็นตัวเลข 12 หลักเท่านั้นครับ",
                next_step="กรุณาตรวจสอบหมายเลขแล้วส่งใหม่ หรือถ้าไม่ทราบหมายเลข ให้แจ้งอาการที่เกิดขึ้น สถานที่ และเบอร์โทรแทนได้ครับ",
                retryable=True,
            )
        if code is ToolErrorCode.CONFLICT:
            return ErrorPresentation(
                code=code,
                explanation="OMS พบเหตุการณ์ที่เกี่ยวข้องอยู่แล้ว จึงไม่สามารถสร้างเหตุซ้ำได้ครับ",
                next_step="กรุณาตรวจสอบและติดตามเหตุการณ์เดิมแทนการสร้างรายการใหม่ครับ",
                retryable=False,
            )
        return None

    def grounds_followup(self, result: ToolResult) -> bool:
        return (
            result.name is ToolName.OMS
            and result.action is ToolAction.OMS_GET_OUTAGE_BY_CA
            and result.status is ToolResultStatus.SUCCESS
        )
