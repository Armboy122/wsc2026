"""ทดสอบรายการ tool ในหน้า admin ให้ครบทุก code tool ใน registry จริง — T6 (D3.3)

ความเสี่ยงที่เทสนี้กันไว้:

- T6: ToolAdminService วนแค่ plugin shapes เดิม → KnowledgeTool (built-in) หายจาก
  หน้ารายการ tool — รายการต้องอ่านจาก ToolRegistry ที่ runtime ใช้จริง
- T6: get_tool/set_enabled ต้องกัน code tool ทุกตัวรวม KnowledgeTool ไม่ใช่แค่ปลั๊กอิน
- D3.3 (regression): declarative tool ยังแสดง enabled / editable / selfDisabledReason ถูกต้อง

ประกอบ registry แบบเดียวกับ production: ``KnowledgeTool`` จริงกับ backend ปลอมขั้นต่ำ
(ทำตาม protocol ``search`` คืน ``GroundedEvidence`` จริง) ไม่ใช่ mock ทั้งก้อน
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.registry import ToolRegistry
from app.api.admin import router as admin_router
from app.backends.full_document_knowledge import GroundedEvidence
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database
from app.tools.knowledge_tool import KnowledgeTool

_KNOWLEDGE_DESCRIPTION = "ตอบความรู้ PEA จากข้อความฉบับเต็มของไฟล์ที่เลือก"

_VALID_DEFINITION: dict[str, Any] = {
    "slug": "cat_fact_tool",
    "displayName": "สุ่มข้อเท็จจริงเกี่ยวกับแมว",
    "description": "ดึงข้อเท็จจริงเกี่ยวกับแมวจากบริการสาธารณะ",
    "enabled": True,
    "operations": [
        {
            "action": "get_random_fact",
            "policy": "plain_read",
            "exposure": "llm",
            "mode": "read",
            "httpMethod": "GET",
            "urlTemplate": "https://catfact.ninja/fact",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "outputSchema": None,
        }
    ],
}


class _MinimalKnowledgeBackend:
    """backend ปลอมขั้นต่ำ — KnowledgeTool จริงเรียก ``search`` ตาม protocol"""

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        return GroundedEvidence(
            answer_context="ข้อความฉบับเต็มของเอกสารที่เลือก (ข้อมูลทดสอบ)",
            result_count=1,
            citations=(),
        )


def _settings() -> Settings:
    return Settings.from_env({"APP_ENV": "development", "ADMIN_PASSWORD": "pw"})


def _make_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, ToolRegistry, Database]:
    """ประกอบแอปแบบเดียวกับ production: registry มี KnowledgeTool จริง + ไม่มีปลั๊กอิน"""
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    registry = ToolRegistry([KnowledgeTool(_MinimalKnowledgeBackend())])
    service = ToolAdminService(
        db,
        settings=_settings(),
        registry=registry,
        plugins=(),
    )
    app = create_platform_app(_settings())
    app.state.tool_admin = service
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client, registry, db


def _db_write(db: Database, sql: str, params: tuple = ()) -> None:
    db._conn.execute(sql, params)  # noqa: SLF001 — เทสเขียนแถวที่ผิดตรง ๆ โดยตั้งใจ
    db._conn.commit()


def _tools_by_slug(client: TestClient) -> dict[str, dict[str, Any]]:
    body = client.get("/api/v1/admin/tools").json()
    return {tool["slug"]: tool for tool in body["tools"]}


# ----------------------------------------------------- T6: code tool ครบในรายการ --


def test_knowledge_tool_appears_as_non_editable_code_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _make_client(monkeypatch)
    knowledge = _tools_by_slug(client)["knowledge_tool"]

    # ปรากฏในรายการในฐานะ code tool — แก้ไข/เปิด-ปิดจากหน้าเว็บไม่ได้
    assert knowledge["source"] == "code"
    assert knowledge["editable"] is False
    assert knowledge["enabled"] is True
    assert knowledge["hasAuth"] is False
    assert knowledge["selfDisabledReason"] is None
    # description มาจากแค็ตตาล็อกจริงของ registry (BUILT_IN_CATALOGUE)
    assert knowledge["description"] == _KNOWLEDGE_DESCRIPTION

    # operation สะท้อนสิ่งที่ registry รู้จริง: action จาก catalogue, policy จาก operation_specs
    assert [op["action"] for op in knowledge["operations"]] == ["search"]
    operation = knowledge["operations"][0]
    assert operation["policy"] == "grounded_answer"
    assert operation["mode"] == "read"
    assert operation["exposure"] == "llm"
    # limits จริงจาก BUILT_IN_OPERATION_SPECS (dedupe ไม่ได้ประกาศ = None ตามจริง)
    assert operation["limits"] == {"maxCallsPerTurn": 2, "dedupeIdenticalInput": None}
    # inputSchema derive จากสัญญาจริง (KnowledgeSearchInput) ไม่ใช่ค่ากุมา
    assert operation["inputSchema"]["properties"]["query"]["type"] == "string"
    assert operation["inputSchema"]["properties"]["maxResults"]["type"] == "integer"


def test_code_tool_not_duplicated_when_plugins_cover_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ปลั๊กอินที่ shape มาจาก plugins ต้องไม่ถูกประกอบซ้ำจาก registry"""
    client, _, _ = _make_client(monkeypatch)
    slugs = [tool["slug"] for tool in client.get("/api/v1/admin/tools").json()["tools"]]
    assert slugs.count("knowledge_tool") == 1


# ----------------------------------------- D3.3 regression: declarative tool เหมือนเดิม --


def test_declarative_tool_still_lists_enabled_editable_and_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, registry, db = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201

    # tool ที่ definition ผิด fail closed — ยังต้องแสดงพร้อมเหตุผล กันหายเงียบ
    _db_write(
        db,
        "INSERT INTO tool (slug, display_name, description, source) "
        "VALUES ('broken_tool', 'เสีย', '', 'db')",
    )
    _db_write(
        db,
        "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, "
        "exposure, mode, http_method, url_template) "
        "SELECT id, 'do', 'plain_read', ?, 'null', 'llm', 'read', 'GET', 'https://ok.test/x' "
        "FROM tool WHERE slug = 'broken_tool'",
        (
            json.dumps(
                {"type": "object", "oneOf": [{"type": "object"}], "additionalProperties": False}
            ),
        ),
    )
    asyncio.run(client.app.state.tool_admin.reload())
    assert "broken_tool" not in registry.names

    by_slug = _tools_by_slug(client)
    # knowledge (code) และ declarative ทั้งปกติและเสีย อยู่รายการเดียวกัน
    assert {"knowledge_tool", "cat_fact_tool", "broken_tool"} <= set(by_slug)

    declarative = by_slug["cat_fact_tool"]
    assert declarative["enabled"] is True
    assert declarative["editable"] is True
    assert declarative["selfDisabledReason"] is None
    assert declarative["source"] == "db"

    broken = by_slug["broken_tool"]
    assert broken["enabled"] is True  # DB บอกเปิด แต่...
    assert broken["selfDisabledReason"]  # ...มีเหตุผลที่แสดงให้ admin เห็น
    assert "oneOf" in broken["selfDisabledReason"]
    assert broken["editable"] is True


# ------------------------------------------------- T6: code tool ถูกปฏิเสธถูกต้อง --


def test_get_tool_of_code_tool_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _make_client(monkeypatch)
    response = client.get("/api/v1/admin/tools/knowledge_tool")
    assert response.status_code == 404
    assert "โค้ด" in response.json()["detail"]


def test_set_enabled_of_code_tool_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, registry, _ = _make_client(monkeypatch)
    response = client.patch(
        "/api/v1/admin/tools/knowledge_tool/enabled", json={"enabled": False}
    )
    assert response.status_code == 404
    assert "โค้ด" in response.json()["detail"]
    # ถูกปฏิเสธแล้ว knowledge ยังอยู่ใน registry และยังแสดงว่าเปิดอยู่
    assert "knowledge_tool" in registry.names
    knowledge = _tools_by_slug(client)["knowledge_tool"]
    assert knowledge["enabled"] is True


def test_declarative_tool_edit_and_toggle_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """regression: ขอบเขตการกัน code tool ห้ามบัง declarative tool"""
    client, registry, _ = _make_client(monkeypatch)
    assert client.post("/api/v1/admin/tools", json=_VALID_DEFINITION).status_code == 201

    edited = copy.deepcopy(_VALID_DEFINITION)
    edited["description"] = "คำอธิบายใหม่"
    assert client.put("/api/v1/admin/tools/cat_fact_tool", json=edited).status_code == 200
    assert client.patch(
        "/api/v1/admin/tools/cat_fact_tool/enabled", json={"enabled": False}
    ).status_code == 200
    assert "cat_fact_tool" not in registry.names
