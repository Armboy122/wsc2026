"""ทดสอบ bootstrap และ provider ของ SYSTEM_PROMPT ใน DB (D3.2, TASKS-3DAYS.md)"""

from __future__ import annotations

import pytest

from app.db import Database
from app.db.bootstrap_prompt import DbSystemPromptProvider, seed_system_prompt
from app.llm.prompting import SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_seed_inserts_default_prompt_and_is_idempotent() -> None:
    db = Database(":memory:")
    db.migrate()

    assert await seed_system_prompt(db) is True
    row = await db.fetch_one(
        "SELECT content FROM prompt WHERE key = 'system_prompt'"
    )
    assert row is not None and row["content"] == SYSTEM_PROMPT

    # idempotent: ค่าที่ admin แก้ไว้ใน DB ต้องไม่ถูก overwrite ด้วยค่าเริ่มต้น
    await db.execute(
        "UPDATE prompt SET content = ? WHERE key = 'system_prompt'", ("แก้เอง",)
    )
    assert await seed_system_prompt(db) is False
    row = await db.fetch_one(
        "SELECT content FROM prompt WHERE key = 'system_prompt'"
    )
    assert row is not None and row["content"] == "แก้เอง"


@pytest.mark.asyncio
async def test_db_provider_returns_current_db_value_every_call() -> None:
    """อ่านจาก DB ทุกเทิร์น — แก้ prompt แล้วมีผลเทิร์นถัดไปโดยไม่ต้อง restart"""
    db = Database(":memory:")
    db.migrate()
    await seed_system_prompt(db)
    provider = DbSystemPromptProvider(db)

    assert await provider.get() == SYSTEM_PROMPT

    await db.execute(
        "UPDATE prompt SET content = ? WHERE key = 'system_prompt'",
        ("โปรมต์เวอร์ชันใหม่จาก DB",),
    )
    assert await provider.get() == "โปรมต์เวอร์ชันใหม่จาก DB"


@pytest.mark.asyncio
async def test_db_provider_falls_back_when_missing_or_blank() -> None:
    """prompt ว่างทำให้ JSON contract ของ agent พัง — ค่าเสียต้อง fallback เป็นค่าเริ่มต้น"""
    db = Database(":memory:")
    db.migrate()
    provider = DbSystemPromptProvider(db)

    # ยังไม่ seed เลย
    assert await provider.get() == SYSTEM_PROMPT

    # seed แล้วแต่เนื้อหาว่าง/ช่องว่างเท่านั้น
    await seed_system_prompt(db)
    await db.execute(
        "UPDATE prompt SET content = ? WHERE key = 'system_prompt'", ("   ",)
    )
    assert await provider.get() == SYSTEM_PROMPT
