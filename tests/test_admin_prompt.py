"""ทดสอบหน้าแก้ SYSTEM_PROMPT — D3.6 (TASKS-3DAYS.md)

ความเสี่ยงที่เทสนี้กันไว้:

- ทุก endpoint ใหม่ fail closed เมื่อไม่ผ่าน admin auth (เดียวกับ D3.1)
- save แล้วต้องมีผลเทิร์นถัดไปจริง — agent อ่านผ่าน ``DbSystemPromptProvider`` ต่อเทิร์น
  เทสจึงยืนยันผ่าน provider เดียวกับที่ runtime ใช้ ไม่ใช่แค่อ่านตารางตรง ๆ
- บันทึกค่าว่าง/เว้นวรรคล้วน = reject — provider ถือว่าค่าว่างเสียแล้ว fallback เงียบ ๆ
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.admin import router as admin_router
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.prompt_admin import PromptAdminService
from app.core.startup import create_platform_app
from app.db import Database
from app.db.bootstrap_prompt import DbSystemPromptProvider, seed_system_prompt
from app.llm.prompting import SYSTEM_PROMPT


def _settings() -> Settings:
    return Settings.from_env({"APP_ENV": "development", "ADMIN_PASSWORD": "pw"})


def _make_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Database]:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    asyncio.run(seed_system_prompt(db))
    app = create_platform_app(_settings())
    app.state.prompt_admin = PromptAdminService(db)
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client, db


def test_prompt_endpoints_fail_closed_without_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    app = create_platform_app(_settings())
    app.state.prompt_admin = PromptAdminService(db)
    app.include_router(admin_router)
    client = TestClient(app)

    assert client.get("/api/v1/admin/prompt").status_code == 401
    assert client.put("/api/v1/admin/prompt", json={"content": "x"}).status_code == 401


def test_get_prompt_returns_seeded_default(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(monkeypatch)
    response = client.get("/api/v1/admin/prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "system_prompt"
    assert body["content"] == SYSTEM_PROMPT
    assert body["isModified"] is False
    assert body["updatedAt"]


def test_save_prompt_takes_effect_next_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = _make_client(monkeypatch)
    new_prompt = SYSTEM_PROMPT + "\nทดสอบ: ตอบกลับด้วยคำว่า พร้อมใช้งาน เสมอ"

    response = client.put("/api/v1/admin/prompt", json={"content": new_prompt})
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == new_prompt
    assert body["isModified"] is True

    # runtime อ่านต่อเทิร์นผ่าน provider นี้ — เทียบกับสิ่งที่ agent เห็นจริง
    assert asyncio.run(DbSystemPromptProvider(db).get()) == new_prompt


def test_save_prompt_rejects_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = _make_client(monkeypatch)

    response = client.put("/api/v1/admin/prompt", json={"content": "   \n  "})
    assert response.status_code == 400
    assert "ต้องไม่ว่าง" in response.json()["detail"]

    # ค่าเดิมต้องยังอยู่ไม่ถูกแตะ
    assert asyncio.run(DbSystemPromptProvider(db).get()) == SYSTEM_PROMPT


def test_save_prompt_accepts_non_ascii(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(monkeypatch)
    content = "คุณคือผู้ช่วยไฟฟ้า ตอบสั้นและมีหลักฐานเสมอ"

    response = client.put("/api/v1/admin/prompt", json={"content": content})
    assert response.status_code == 200
    assert response.json()["content"] == content
