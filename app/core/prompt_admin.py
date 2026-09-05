"""บริการจัดการ SYSTEM_PROMPT จากหน้า admin — D3.6 (TASKS-3DAYS.md)

นโยบายทั้งหมดของการอ่าน/แก้ prompt อยู่ที่นี่ route handler (``app/api/admin.py``)
เรียกใช้เท่านั้น จุดสำคัญที่ตรึงไว้:

- **แก้แล้วมีผลเทิร์นถัดไปทันที** — เพราะ runtime อ่านผ่าน ``DbSystemPromptProvider``
  (app/db/bootstrap_prompt.py) ต่อเทิร์นอยู่แล้ว (D3.2) ที่นี่เขียน DB จุดเดียวเท่านั้น
- **ห้ามบันทึกค่าว่าง/เว้นวรรคล้วน** — provider ถือว่าค่าว่างเสียและจะ fallback ไป
  SYSTEM_PROMPT เงียบ ๆ ทำให้ "แก้แล้วเหมือนไม่มีผล" ปัญหานั้นต้องจับที่ปุ่ม save แทน
- ตาราง ``prompt`` มี key เดียวตาม D2.1/D3.2 — บริการนี้ยังไม่รองรับ key อื่น
"""

from __future__ import annotations

from typing import Any

from app.db import Database
from app.db.bootstrap_prompt import SYSTEM_PROMPT_KEY
from app.llm.prompting import SYSTEM_PROMPT

# เพดานกันพิมพ์หลุด — SYSTEM_PROMPT เริ่มต้นยาว ~1.5k ตัวอักษร ตัวนี้เหลือให้แก้ได้อิสระ
MAX_PROMPT_LENGTH = 20_000


class PromptValidationError(ValueError):
    """ข้อมูลที่ส่งมาแก้ prompt ไม่ผ่าน — ข้อความภาษาไทยอ่านรู้เรื่องสำหรับหน้าเว็บ"""


class PromptAdminService:
    """อ่าน/เขียน SYSTEM_PROMPT ในตาราง prompt — หน้าแก้ prompt (D3.6)"""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_prompt(self) -> dict[str, Any]:
        """ค่า prompt ปัจจุบันพร้อม metadata สำหรับแสดงบนหน้าเว็บ"""
        row = await self._db.fetch_one(
            "SELECT content, updated_at FROM prompt WHERE key = ?", (SYSTEM_PROMPT_KEY,)
        )
        content = row["content"] if row is not None and row["content"] else SYSTEM_PROMPT
        return {
            "key": SYSTEM_PROMPT_KEY,
            "content": content,
            "updatedAt": row["updated_at"] if row is not None else None,
            "isModified": content != SYSTEM_PROMPT,
        }

    async def save_prompt(self, content: str) -> dict[str, Any]:
        """บันทึก SYSTEM_PROMPT — มีผลตั้งแต่เทิร์นถัดไปโดยไม่ต้อง restart (D3.6)"""
        if not isinstance(content, str) or not content.strip():
            raise PromptValidationError(
                "เนื้อหา prompt ต้องไม่ว่าง — ถ้าบันทึกค่าว่างระบบจะกลับไปใช้ค่าเริ่มต้นเงียบ ๆ "
                "ทำให้การแก้ไขหายไปโดยไม่มีใครรู้"
            )
        if len(content) > MAX_PROMPT_LENGTH:
            raise PromptValidationError(
                f"prompt ยาวเกิน {MAX_PROMPT_LENGTH} ตัวอักษร (ปัจจุบัน {len(content)} ตัวอักษร)"
            )
        await self._db.execute(
            "INSERT INTO prompt (key, content, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET content = excluded.content, "
            "updated_at = excluded.updated_at",
            (SYSTEM_PROMPT_KEY, content),
        )
        return await self.get_prompt()
