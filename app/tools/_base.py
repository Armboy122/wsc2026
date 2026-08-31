"""โครงสร้างพื้นฐานร่วมสำหรับเครื่องมือปฏิบัติการจำลองสามตัว

เครื่องมือแต่ละตัวตรวจสอบข้อมูลนำเข้าของการกระทำและข้อมูลผลลัพธ์สำเร็จกับโมเดล
``app.contracts`` ตามสัญญาก่อนส่งคืน ``ToolResult`` ผลลัพธ์ทุกค่าที่สร้างที่นี่
เป็นข้อมูลปฏิบัติการ จึงมีค่า ``simulation: true``
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.backends import BackendError
from app.contracts import (
    ToolCall,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    validate_tool_input,
    validate_tool_success_data,
)


class SimulatedTool:
    """คลาสพื้นฐานที่ทำงานตาม ``execute`` seam แบบแคบสำหรับเครื่องมือจำลอง"""

    name: ToolName
    backend: Any

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        """ตรวจสอบการเรียก ส่งงานไปยัง backend และส่งคืนผลลัพธ์แบบมีชนิด"""
        if call.name != self.name:
            return self._error(
                call,
                ToolErrorCode.INVALID_INPUT,
                f"เครื่องมือ {call.name.value} ไม่รองรับการเรียกนี้",
            )
        try:
            input_model = validate_tool_input(call)
        except ValidationError:
            return self._error(
                call,
                ToolErrorCode.INVALID_INPUT,
                f"ข้อมูลนำเข้าสำหรับ {call.action.value} ไม่ถูกต้อง",
            )
        try:
            data = self._run(call.action, input_model)
        except BackendError as exc:
            return self._error(call, exc.code, exc.message)
        except Exception:  # noqa: BLE001 - ปิดอย่างปลอดภัยเมื่อเกิดข้อผิดพลาดที่ไม่คาดคิดจาก backend
            return self._error(call, ToolErrorCode.INTERNAL, "เกิดข้อผิดพลาดภายในที่ไม่คาดคิด")
        try:
            output_model = validate_tool_success_data(call.action, data)
        except ValidationError:
            return self._error(call, ToolErrorCode.INTERNAL, "เครื่องมือส่งผลลัพธ์ที่ไม่ถูกต้อง")
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data=output_model.model_dump(by_alias=True, mode="json"),
            error=None,
            citations=(),
            simulation=True,
        )

    def reset(self) -> None:
        """รีเซ็ตสถานะ backend ของเครื่องมือนี้ โดยมอบหมายให้ backend ดำเนินการ"""
        self.backend.reset()

    def _run(self, action: Any, input_model: Any) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _error(call: ToolCall, code: ToolErrorCode, message: str) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            data=None,
            error=ToolError(code=code, message=message),
            citations=(),
            simulation=True,
        )
