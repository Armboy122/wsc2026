"""เครื่องมือ OMS (จัดการไฟฟ้าขัดข้อง) แบบจำลอง (``oms_tool``)

เปิดเผยการกระทำตามสัญญา ``get_outage_status``, ``prepare_outage_report`` และการกระทำภายใน
``submit_outage_report`` ผลลัพธ์ทั้งหมดเป็นข้อมูลจำลอง และผลลัพธ์การอ่านหรือเตรียม
ข้อมูลไฟฟ้าขัดข้องมี ``safetyMessage`` เสมอ
"""

from __future__ import annotations

from typing import Any

from app.backends.simulated_oms import SimulatedOmsBackend, default_backend
from app.contracts import ToolAction, ToolName
from app.tools._base import SimulatedTool


class OmsTool(SimulatedTool):
    """เครื่องมือ OMS ระดับบนสุด ซึ่งเป็นเจ้าของเฉพาะการกระทำ OMS ตามสัญญาสามรายการ"""

    name = ToolName.OMS

    def __init__(self, backend: SimulatedOmsBackend | None = None) -> None:
        self.backend = backend if backend is not None else default_backend

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.OMS_OUTAGE_STATUS:
            return self.backend.get_outage_status(input_model.area_code)
        if action is ToolAction.OMS_PREPARE_OUTAGE_REPORT:
            return self.backend.prepare_outage_report(
                input_model.area_code,
                input_model.location_note,
                input_model.symptoms,
                input_model.idempotency_key,
            )
        if action is ToolAction.OMS_SUBMIT_OUTAGE_REPORT:
            return self.backend.submit_outage_report(
                input_model.pending_action_id,
                input_model.idempotency_key,
            )
        raise ValueError(f"ไม่มีการจัดการการกระทำ {action.value}")
