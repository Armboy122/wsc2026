"""bootstrap ที่ทำให้ SYSTEM_PROMPT มีอยู่ในตาราง prompt เสมอ (D3.2, TASKS-3DAYS.md)

ครั้งแรกต่อ DB: insert ค่าเริ่มต้นจาก ``app.llm.prompting.SYSTEM_PROMPT``
มีแถวอยู่แล้ว: **ไม่แตะอะไรเลย** (idempotent — เคารพค่าที่ admin แก้ผ่าน DB/หน้าเว็บไว้)

``DbSystemPromptProvider`` อ่านค่าจาก DB ทุกครั้งที่ถูกเรียก (ต่อเทิร์น) เพื่อให้
"แก้ prompt จาก DB แล้วมีผลในเทิร์นถัดไป" โดยไม่ต้อง restart
"""

from __future__ import annotations

from app.db import Database
from app.llm.prompting import SYSTEM_PROMPT

SYSTEM_PROMPT_KEY = "system_prompt"


async def seed_system_prompt(db: Database) -> bool:
    """seed SYSTEM_PROMPT ลง DB ถ้ายังไม่มี — คืน ``True`` เมื่อสร้างแถวใหม่"""
    existing = await db.fetch_one(
        "SELECT key FROM prompt WHERE key = ?", (SYSTEM_PROMPT_KEY,)
    )
    if existing is not None:
        return False
    await db.execute(
        "INSERT INTO prompt (key, content) VALUES (?, ?)",
        (SYSTEM_PROMPT_KEY, SYSTEM_PROMPT),
    )
    return True


class DbSystemPromptProvider:
    """แหล่ง SYSTEM_PROMPT จากตาราง prompt — อ่านสดจาก DB ทุกเทิร์น"""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self) -> str:
        row = await self._db.fetch_one(
            "SELECT content FROM prompt WHERE key = ?", (SYSTEM_PROMPT_KEY,)
        )
        raw = row["content"] if row is not None and row["content"] else ""
        # prompt ว่างทำให้ JSON contract ของ agent พังทันที — ถือว่าค่าเสีย ใช้ค่าเริ่มต้นแทน
        return raw if raw.strip() else SYSTEM_PROMPT
