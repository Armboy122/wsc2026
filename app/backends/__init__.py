"""backend adapter ของ PEA แบบจำลอง: กำหนดผลลัพธ์ได้ อยู่ในหน่วยความจำ และรีเซ็ตได้

อะแดปเตอร์เหล่านี้ไม่เก็บสถานะ PEA ระบบจริงและไม่ก่อให้เกิดผลกระทบในโลกจริง
ผลลัพธ์ปฏิบัติการแต่ละรายการที่ส่งกลับผ่านเครื่องมือจะมีค่า ``simulation: true``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.contracts import ToolErrorCode

_MOCK_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"


class BackendError(Exception):
    """ข้อผิดพลาดแบบมีชนิดและปลอดภัยสำหรับผู้ใช้ ซึ่งเกิดจาก backend จำลอง

    ``code`` เป็นหนึ่งในค่า :class:`ToolErrorCode` ตามสัญญา ส่วน ``message`` ต้องไม่มี
    ข้อมูลรับรองหรือตัวระบุภายในนอกเหนือจากข้อมูลที่ปลอดภัยสำหรับผู้ใช้
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_mock_json(name: str) -> Any:
    """โหลดไฟล์ fixture แบบกำหนดผลลัพธ์ได้จากโครงสร้าง ``data/mock`` ของ repository"""
    with (_MOCK_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)
