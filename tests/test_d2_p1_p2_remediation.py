"""การทดสอบปิด P1/P2/P3 ที่พบจาก D2.7 (docs/v2/TASKS-3DAYS.md):

1. Fresh DB ต้องมี ``oms_tool`` โดยอัตโนมัติ — bootstrap ที่ repeatable/idempotent
   (``app/db/bootstrap_oms.py``) seed จากต้นฉบับเดียวกับ ``scripts/seed_oms_tool.py``
   แล้ว declarative loader และ ``ToolRegistry`` ต้องเห็น OMS ครบ: catalogue มีเฉพาะ
   3 LLM actions, submit ยังเป็น internal เสมอ
2. Legacy Pydantic validation ใน ``ToolRegistry`` ต้องผูกกับคู่ (tool_slug, action)
   ที่เป็น legacy จริง — declarative tool ที่ชื่อ action ชนกับ legacy (เช่น ``search``)
   ต้อง execute ด้วย schema ของตัวเอง ไม่ถูกบังคับด้วย schema/output ของ legacy tool
   ส่วน declarative ``oms_tool`` (slug ตรงกับ ``ToolName.OMS`` เดิม, D2.7) ต้องยังได้
   validation/output behavior ตาม contracts เหมือนเดิม
3. การสร้าง PendingAction ใน Main Agent ต้องเลือก legacy coercion ด้วย (tool, action)
   เช่นกัน — declarative prepare operation ที่ action ชนชื่อ legacy ต้องสร้าง
   PendingAction ได้จาก raw JSON input ของตัวเอง
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.agent.declarative_tools import load_declarative_tools
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolContext, ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import (
    ChatRequest,
    Citation,
    PendingActionStatus,
    ToolCall,
    ToolErrorCode,
    ToolResult,
    ToolResultStatus,
)
from app.db import Database
from app.db.bootstrap_oms import OMS_TOOL_SLUG, seed_oms_tool
from app.llm import LLMClient, LLMResponse
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.declarative_tool import DeclarativeTool


class _FakeKnowledgeBackend:
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        citation = Citation(
            source_id="doc-1",
            title="เอกสารทดสอบ",
            uri="knowledge://doc-1.docx",
            snippet="ข้อมูลสำหรับทดสอบ",
        )
        return GroundedEvidence("ข้อความเนื้อหา", 1, (citation,))


class _ScriptedLLMAdapter:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)

    async def complete(self, request: Any) -> LLMResponse:
        if not self._responses:
            return LLMResponse(text="เรียบร้อยครับ")
        return self._responses.pop(0)


async def _create_test_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test_pea.db")
    db.migrate()
    return db


# ---------------------------------------------------------------------------
# 1) bootstrap: fresh DB ต้องมี oms_tool ครบใน loader/catalogue/registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_seeds_oms_tool_into_empty_db_end_to_end(tmp_path: Path) -> None:
    db = await _create_test_db(tmp_path)
    try:
        tool_id = await seed_oms_tool(db, oms_base_url="http://oms.test")
        assert tool_id is not None

        allowlist_rows = await db.fetch_all("SELECT domain FROM domain_allowlist WHERE enabled = 1")
        bundle = await load_declarative_tools(
            db,
            app_env="development",
            allowlist=tuple(row["domain"] for row in allowlist_rows),
        )

        # declarative loader ได้ oms_tool ตัวเดียวจาก DB ว่าง
        assert [tool.name for tool in bundle.tools] == [OMS_TOOL_SLUG]

        # catalogue มีเฉพาะ 3 LLM actions — submit ยัง internal ไม่ปรากฏแก่ LLM
        assert len(bundle.catalogue) == 1
        catalogue_def = bundle.catalogue[0]
        assert catalogue_def.name == OMS_TOOL_SLUG
        assert sorted(catalogue_def.actions) == sorted(
            ("get_outage_by_ca", "prepare_outage_with_ca", "prepare_anonymous_outage")
        )
        assert "submit_outage_with_ca" not in catalogue_def.actions
        assert "submit_anonymous_outage" not in catalogue_def.actions

        # submit operations ยัง internal ตามสัญญา write_confirm
        for submit_action in ("submit_outage_with_ca", "submit_anonymous_outage"):
            spec = bundle.operation_specs[(OMS_TOOL_SLUG, submit_action)]
            assert spec.mode == "submit"
            assert spec.exposure == "internal"

        # end-to-end: registry ที่ประกอบจาก bundle ต้อง dispatch oms_tool ได้จริง
        registry = ToolRegistry(
            [KnowledgeTool(_FakeKnowledgeBackend()), *bundle.tools],
            catalogue=bundle.catalogue,
            operation_specs=bundle.operation_specs,
        )
        assert OMS_TOOL_SLUG in registry.names
        registry_catalogue = {definition.name: definition for definition in registry.llm_catalogue}
        assert sorted(registry_catalogue[OMS_TOOL_SLUG].actions) == sorted(
            ("get_outage_by_ca", "prepare_outage_with_ca", "prepare_anonymous_outage")
        )

        # dispatch จริงผ่าน HTTP executor จำลอง — พิสูจน์เส้นทางครบตั้งแต่ DB ถึงผลลัพธ์
        valid_output = {
            "caNumber": "112233445566",
            "customerFound": True,
            "network": {"meterId": "M-1", "transformerId": "T-1", "feederId": "F-1"},
            "activeEvent": None,
            "recommendedAction": "CREATE_METER_EVENT",
        }

        def mock_handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/outages/by-ca/112233445566")
            return httpx.Response(200, json=valid_output)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
        with patch("app.tools.declarative_executor.httpx.AsyncClient", return_value=mock_client):
            result = await registry.execute(
                ToolCall(
                    call_id=uuid.uuid4(),
                    name=OMS_TOOL_SLUG,
                    action="get_outage_by_ca",
                    input={"caNumber": "112233445566"},
                ),
                ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4()),
            )
        assert result.status is ToolResultStatus.SUCCESS
        assert result.data["caNumber"] == "112233445566"
        await mock_client.aclose()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_never_overwrites_user_config(tmp_path: Path) -> None:
    db = await _create_test_db(tmp_path)
    try:
        first_id = await seed_oms_tool(db, oms_base_url="http://oms.test")
        assert first_id is not None

        # ผู้ใช้แก้ config ของตัวเองหลัง seed
        await db.execute(
            "UPDATE tool SET description = ? WHERE slug = ?",
            ("คำอธิบายที่ผู้ใช้แก้เอง", OMS_TOOL_SLUG),
        )
        row_count_before = len(await db.fetch_all("SELECT id FROM tool_operation"))

        # seed ซ้ำต้องไม่ทำอะไรเลย
        second_id = await seed_oms_tool(db, oms_base_url="http://other-host.test")
        assert second_id is None

        tool_row = await db.fetch_one("SELECT * FROM tool WHERE slug = ?", (OMS_TOOL_SLUG,))
        assert tool_row["description"] == "คำอธิบายที่ผู้ใช้แก้เอง"
        assert tool_row["id"] == first_id
        assert len(await db.fetch_all("SELECT id FROM tool_operation")) == row_count_before

        # url_template ของ operation เดิมต้องไม่ถูกเปลี่ยนเป็น host ใหม่
        op_row = await db.fetch_one(
            "SELECT url_template FROM tool_operation WHERE tool_id = ? AND action = ?",
            (first_id, "get_outage_by_ca"),
        )
        assert op_row["url_template"] == "http://oms.test/outages/by-ca/{caNumber}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2) legacy validation ใน ToolRegistry ผูกกับ (tool_slug, action) ที่เป็น legacy จริง
# ---------------------------------------------------------------------------


class _ClashSearchTool:
    """declarative-style tool ที่ action ``search`` ชนกับ knowledge legacy แต่ schema เป็นของตัวเอง"""

    name = "clash_search_tool"
    actions = frozenset({"search"})

    def __init__(self) -> None:
        self.last_input: dict[str, Any] | None = None

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        self.last_input = dict(call.input)
        # ผลลัพธ์ตั้งใจไม่ตรงกับ KnowledgeSearchOutput (answerContext/resultCount) —
        # ถ้า registry บังคับ output ของ legacy tool ผิดตัว จะกลายเป็น error INTERNAL
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"topic": call.input["topic"], "hits": 7},
            simulation=True,
        )

    def reset(self) -> None:
        pass


@pytest.mark.asyncio
async def test_declarative_tool_with_legacy_colliding_action_uses_own_schema() -> None:
    registry = ToolRegistry([KnowledgeTool(_FakeKnowledgeBackend()), _ClashSearchTool()])

    # input ตาม schema ของตัวเอง (ไม่มี "query" ที่ KnowledgeSearchInput บังคับ) ต้องผ่าน
    call = ToolCall(
        call_id=uuid.uuid4(),
        name="clash_search_tool",
        action="search",
        input={"topic": "ไฟดับ"},
    )
    result = await registry.execute(
        call, ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4())
    )
    assert result.status is ToolResultStatus.SUCCESS
    assert result.data == {"topic": "ไฟดับ", "hits": 7}

    # legacy knowledge ยังถูก validate ด้วยสัญญาของตัวเองอยู่ครบ
    legacy_call = ToolCall(
        call_id=uuid.uuid4(),
        name="knowledge_tool",
        action="search",
        input={"query": "ไฟดับ"},
    )
    legacy_result = await registry.execute(
        legacy_call, ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4())
    )
    assert legacy_result.status is ToolResultStatus.SUCCESS

    bad_legacy_call = ToolCall(
        call_id=uuid.uuid4(),
        name="knowledge_tool",
        action="search",
        input={"topic": "ไฟดับ"},
    )
    bad_legacy_result = await registry.execute(
        bad_legacy_call, ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4())
    )
    assert bad_legacy_result.status is ToolResultStatus.ERROR
    assert bad_legacy_result.error is not None
    assert bad_legacy_result.error.code is ToolErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_declarative_oms_tool_keeps_legacy_contract_validation() -> None:
    """declarative oms_tool (slug ตรงกับ ToolName.OMS เดิม) ต้องยังได้ validation ตาม contracts

    - input ไม่ผ่าน OmsGetOutageByCaInput (pattern 12 หลัก) → invalid_input ที่ชั้น registry
    - output ที่ไม่ตรง OmsGetOutageByCaOutput → internal ที่ชั้น registry
      (outputSchema ใน DB ปล่อยว่างโดยตั้งใจ พึ่ง OUTPUT_MODELS ที่ชั้นนี้)
    """
    from app.plugins.oms.declarative_shape import oms_declarative_tool

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    with patch("app.tools.declarative_executor.httpx.AsyncClient", return_value=mock_client):
        oms_tool: DeclarativeTool = oms_declarative_tool("http://oms.test")
        registry = ToolRegistry([KnowledgeTool(_FakeKnowledgeBackend()), oms_tool])
        context = ToolContext(conversation_id=uuid.uuid4(), trace_id=uuid.uuid4())

        bad_input = await registry.execute(
            ToolCall(
                call_id=uuid.uuid4(),
                name=OMS_TOOL_SLUG,
                action="get_outage_by_ca",
                input={"caNumber": "12"},
            ),
            context,
        )
        assert bad_input.status is ToolResultStatus.ERROR
        assert bad_input.error is not None
        assert bad_input.error.code is ToolErrorCode.INVALID_INPUT

        bad_output = await registry.execute(
            ToolCall(
                call_id=uuid.uuid4(),
                name=OMS_TOOL_SLUG,
                action="get_outage_by_ca",
                input={"caNumber": "112233445566"},
            ),
            context,
        )
        assert bad_output.status is ToolResultStatus.ERROR
        assert bad_output.error is not None
        assert bad_output.error.code is ToolErrorCode.INTERNAL
    await mock_client.aclose()


# ---------------------------------------------------------------------------
# 3) PendingAction จาก declarative prepare ที่ action ชนชื่อ legacy
# ---------------------------------------------------------------------------


_CLASH_PREPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "note": {"type": "string", "description": "รายละเอียดของ tool ตัวเอง"},
        "idempotencyKey": {"type": "string"},
    },
    "required": ["note", "idempotencyKey"],
    "additionalProperties": False,
}

_CLASH_SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "pendingActionId": {"type": "string"},
        "idempotencyKey": {"type": "string"},
    },
    "required": ["pendingActionId", "idempotencyKey"],
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_pending_action_from_declarative_prepare_with_colliding_action(tmp_path: Path) -> None:
    """prepare_case ของ declarative tool (ชนกับ VOC legacy) ต้องสร้าง PendingAction

    จาก raw JSON input ของตัวเอง — เดิม registry/main agent เลือก INPUT_MODELS ด้วย
    action อย่างเดียว ทำให้ถูก coerce ด้วย VocPrepareCaseInput แล้ว ValidationError
    จนสร้าง pending action ไม่ได้เลย
    """
    db = await _create_test_db(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("clash_ops", "Clash Ops", "Declarative tool with legacy-colliding action names", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "prepare_case",
                "write_confirm",
                json.dumps(_CLASH_PREPARE_SCHEMA),
                "{}",
                "llm",
                "prepare",
                "submit_case",
                None,
                None,
            ),
        )
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "submit_case",
                "write_confirm",
                json.dumps(_CLASH_SUBMIT_SCHEMA),
                "{}",
                "internal",
                "submit",
                None,
                "POST",
                "http://clash.test/cases",
            ),
        )

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ticket": "T-1", "status": "RECEIVED"})

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
        with patch("app.tools.declarative_executor.httpx.AsyncClient", return_value=mock_client):
            bundle = await load_declarative_tools(db, app_env="development", allowlist=())
            assert len(bundle.tools) == 1

            prepare_call = ToolCall(
                call_id=uuid.uuid4(),
                name="clash_ops",
                action="prepare_case",
                input={"note": "โคมไฟดับทั้งถนน", "idempotencyKey": "KEY-CLASH-001"},
            )
            adapter = _ScriptedLLMAdapter([
                LLMResponse(tool_calls=(prepare_call,)),
                LLMResponse(text="เตรียมรายการเรียบร้อยครับ กรุณายืนยัน"),
            ])
            registry = ToolRegistry(
                [KnowledgeTool(_FakeKnowledgeBackend()), *bundle.tools],
                catalogue=bundle.catalogue,
                operation_specs=bundle.operation_specs,
            )
            agent = MainAgent(LLMClient(adapter), registry)

            response = await agent.handle_chat(ChatRequest(message="ช่วยแจ้งเหตุหน่อย"))

            # เดิมพังตรงนี้: ไม่มี pending action เพราะถูก coerce ด้วย VocPrepareCaseInput
            assert response.pending_action is not None
            pending = response.pending_action
            assert pending.tool_slug == "clash_ops"
            assert pending.prepare_action == "prepare_case"
            assert pending.submit_action == "submit_case"
            assert pending.idempotency_key == "KEY-CLASH-001"
            assert pending.status is PendingActionStatus.PENDING_CONFIRMATION
            # prepared_input มาจาก raw JSON ของตัวเอง — ฟิลด์ที่ไม่อยู่ในชุด preview ที่ระบบรู้จัก
            # ถูกปกปิดตามสัญญา redaction เดิม (_SAFE_PREVIEW_FIELDS) และ idempotencyKey ถูกปกปิดเสมอ
            assert pending.prepared_input == {"note": "[redacted]", "idempotencyKey": "[redacted]"}

            # ยืนยันได้จน submitted — state machine ยังครบกับ action ชื่อชน legacy
            confirm = await agent.confirm_pending_action(pending.pending_action_id)
            assert confirm.pending_action.status is PendingActionStatus.SUBMITTED
            assert confirm.tool_result is not None
            assert confirm.tool_result.status is ToolResultStatus.SUCCESS
            assert confirm.tool_result.data == {"ticket": "T-1", "status": "RECEIVED"}
        await mock_client.aclose()
    finally:
        db.close()
