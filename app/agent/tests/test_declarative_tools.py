"""ทดสอบการโหลด declarative tool จาก DB เป็นสิ่งที่ ToolRegistry ใช้ได้จริง — D2.6

พิสูจน์เส้นทางเต็ม: แถวใน SQLite → ToolShape → Tool ที่เรียกได้ → ToolDefinition ที่ LLM
เห็น → OperationSpec ที่ Main Agent ถาม policy ได้ → ToolRegistry.execute() dispatch ถูกตัว
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from app.agent.declarative_tools import load_declarative_tools
from app.agent.operation_policy import OperationPolicy
from app.agent.registry import ToolContext, ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import Citation, ToolCall, ToolResultStatus
from app.db import Database
from app.tools.knowledge_tool import KnowledgeTool

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"maxLength": {"type": "integer"}},
    "required": [],
    "additionalProperties": False,
}


class _StubKnowledgeBackend:
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        citation = Citation(
            sourceId="doc", title="เอกสารตัวอย่าง", uri="knowledge://source/doc.docx", snippet="เนื้อหาตัวอย่าง"
        )
        return GroundedEvidence("เนื้อหาตัวอย่าง", 1, (citation,))


async def _seeded_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "pea.db")
    db.migrate()
    tool_id = await db.execute(
        "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
        ("cat_fact_tool", "สุ่มข้อเท็จจริงเกี่ยวกับแมว", "ดึงข้อเท็จจริงเกี่ยวกับแมวแบบสุ่ม", "db"),
    )
    await db.execute(
        "INSERT INTO tool_operation "
        "(tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tool_id,
            "get_random_fact",
            "plain_read",
            json.dumps(_INPUT_SCHEMA),
            "{}",
            "llm",
            "read",
            "GET",
            "https://catfact.ninja/fact",
        ),
    )
    return db


async def test_load_declarative_tools_produces_a_callable_tool_and_catalogue_entry(tmp_path: Path) -> None:
    db = await _seeded_db(tmp_path)
    try:
        bundle = await load_declarative_tools(db, app_env="development", allowlist=())

        assert len(bundle.tools) == 1
        assert bundle.tools[0].name == "cat_fact_tool"
        definition = bundle.catalogue[0]
        assert definition.name == "cat_fact_tool"
        assert definition.actions == ("get_random_fact",)
        assert definition.input_schemas == {"get_random_fact": _INPUT_SCHEMA}
        assert bundle.operation_specs[("cat_fact_tool", "get_random_fact")].policy is OperationPolicy.PLAIN_READ
    finally:
        db.close()


@pytest.mark.asyncio
async def test_registry_dispatches_a_declarative_tool_end_to_end(tmp_path: Path) -> None:
    db = await _seeded_db(tmp_path)
    try:
        handler = lambda request: httpx.Response(  # noqa: E731
            200, json={"fact": "Cats sleep 70% of their lives.", "length": 27}
        )
        bundle = await load_declarative_tools(
            db, app_env="development", allowlist=(), transport=httpx.MockTransport(handler)
        )
        registry = ToolRegistry(
            [KnowledgeTool(backend=_StubKnowledgeBackend()), *bundle.tools],
            catalogue=bundle.catalogue,
            operation_specs=bundle.operation_specs,
        )

        call = ToolCall(call_id=uuid.uuid4(), name="cat_fact_tool", action="get_random_fact", input={})
        result = await registry.execute(call, ToolContext(uuid.uuid4(), uuid.uuid4()))

        assert result.status is ToolResultStatus.SUCCESS
        assert result.data == {"fact": "Cats sleep 70% of their lives.", "length": 27}
        assert "cat_fact_tool" in {definition.name for definition in registry.llm_catalogue}
    finally:
        db.close()
