"""เครื่องมือ VOC (เสียงของลูกค้า) แบบจำลอง (``voc_tool``)

เปิดเผยการกระทำตามสัญญา ``list_categories``, ``prepare_case`` และการกระทำภายใน
``submit_case`` โดยผลลัพธ์ทั้งหมดเป็นข้อมูลจำลอง
"""

from __future__ import annotations

from typing import Any

from app.backends.simulated_voc import SimulatedVocBackend, default_backend
from app.contracts import ToolAction, ToolName
from app.tools._base import SimulatedTool


class VocTool(SimulatedTool):
    """เครื่องมือ VOC ระดับบนสุด ซึ่งเป็นเจ้าของเฉพาะการกระทำ VOC ตามสัญญาสามรายการ"""

    name = ToolName.VOC

    def __init__(self, backend: SimulatedVocBackend | None = None) -> None:
        self.backend = backend if backend is not None else default_backend

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.VOC_LIST_CATEGORIES:
            return self.backend.list_categories()
        if action is ToolAction.VOC_PREPARE_CASE:
            return self.backend.prepare_case(
                input_model.category,
                input_model.subject,
                input_model.detail,
                input_model.contact_channel,
                input_model.idempotency_key,
            )
        if action is ToolAction.VOC_SUBMIT_CASE:
            return self.backend.submit_case(
                input_model.pending_action_id,
                input_model.idempotency_key,
            )
        raise ValueError(f"ไม่มีการจัดการการกระทำ {action.value}")
