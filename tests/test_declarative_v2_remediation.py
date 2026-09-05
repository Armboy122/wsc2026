"""การทดสอบสำหรับ Pre-D2.7 Remediation สำหรับ V2:
1. การห้าม DB tool หรือ LLM ข้าม human confirmation (exposure: internal, rejection at catalogue and runtime)
2. Generic write_confirm lifecycle สำหรับ declarative tool (prepare -> confirm -> submit, idempotency, rejection)
3. ป้องกัน policy collision โดยการ key OperationSpec ด้วย (tool_slug, action)
4. Fail-closed declarative validation สำหรับแถว DB ที่ผิดพลาด (ไม่ crash startup, ไม่รั่วข้อมูล, ข้ามแถวที่เสีย)
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
from app.agent.main_agent import InvalidActionStateError, MainAgent
from app.agent.operation_policy import OperationPolicy, OperationSpec
from app.agent.registry import ToolContext, ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import (
    ChatRequest,
    Citation,
    PendingAction,
    PendingActionStatus,
    ToolAction,
    ToolCall,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    TraceEventKind,
)
from app.db import Database
from app.llm import LLMClient, LLMResponse, ToolDefinition
from app.tools.declarative_validator import (
    sanitize_validation_error_message,
    validate_declarative_tool_shape,
)
from app.tools.knowledge_tool import KnowledgeTool


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
        self.requests: list[Any] = []

    async def complete(self, request: Any) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            return LLMResponse(text="เรียบร้อยครับ")
        return self._responses.pop(0)


_GENERIC_PREPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "idempotencyKey": {"type": "string"},
    },
    "required": ["description", "idempotencyKey"],
    "additionalProperties": False,
}

_GENERIC_SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "pendingActionId": {"type": "string"},
        "idempotencyKey": {"type": "string"},
    },
    "required": ["pendingActionId", "idempotencyKey"],
    "additionalProperties": False,
}


async def _create_test_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test_pea.db")
    db.migrate()
    return db


@pytest.mark.asyncio
async def test_submit_mode_with_llm_exposure_fails_validation_and_is_excluded(tmp_path: Path) -> None:
    """1) mode: submit ต้องมี exposure: internal เสมอ

    ถ้าแถวใน DB กำหนด mode: submit แต่ exposure: llm:
    - ต้องไม่ crash startup
    - tool นั้นต้องถูกข้ามไป (fail-closed)
    - ไม่อยู่ใน bundle.tools และ catalogue
    """
    db = await _create_test_db(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("bad_tool", "Bad Tool", "Tool with invalid submit exposure", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "bad_submit",
                "plain_read",
                json.dumps(_GENERIC_SUBMIT_SCHEMA),
                "{}",
                "llm",  # ผิดกฎ: submit ต้องเป็น internal
                "submit",
                None,
                "POST",
                "https://api.example.com/submit",
            ),
        )

        bundle = await load_declarative_tools(db, app_env="development", allowlist=())
        # fail-closed: bad_tool ต้องไม่ถูกโหลด
        assert len(bundle.tools) == 0
        assert len(bundle.catalogue) == 0
        assert ("bad_tool", "bad_submit") not in bundle.operation_specs
    finally:
        db.close()


@pytest.mark.asyncio
async def test_chat_call_to_submit_or_internal_action_is_rejected_at_runtime(tmp_path: Path) -> None:
    """1b) LLM หรือ chat พยายามยิง submit/internal action ตรง ๆ

    ต้องถูก reject ด้วย CONFIRMATION_REQUIRED และบันทึก trace error stage: chat_policy
    """
    # จำลอง tool ที่มี internal submit action
    spec = OperationSpec(
        policy=OperationPolicy.WRITE_CONFIRM,
        mode="submit",
        exposure="internal",
    )
    call = ToolCall(
        call_id=uuid.uuid4(),
        name="custom_tool",
        action="execute_something",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "KEY-123"},
    )
    adapter = _ScriptedLLMAdapter([LLMResponse(tool_calls=(call,))])

    class _MockCustomTool:
        name = "custom_tool"
        actions = frozenset({"execute_something"})

        async def execute(self, c: ToolCall, ctx: Any) -> ToolResult:
            return ToolResult(
                call_id=c.call_id,
                name=c.name,
                action=c.action,
                status=ToolResultStatus.SUCCESS,
                data={"result": "ok"},
            )

        def reset(self) -> None:
            pass

    registry = ToolRegistry(
        [KnowledgeTool(_FakeKnowledgeBackend()), _MockCustomTool()],
        operation_specs={("custom_tool", "execute_something"): spec},
    )
    agent = MainAgent(LLMClient(adapter), registry)

    response = await agent.handle_chat(ChatRequest(message="ยิง submit เลย"))

    # ต้องมี tool_result ที่บอกว่าต้องการ confirmation
    assert len(response.tool_results) == 1
    result = response.tool_results[0]
    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code is ToolErrorCode.CONFIRMATION_REQUIRED
    assert "ยืนยัน" in result.error.message

    # ตรวจสอบ trace event stage: chat_policy
    trace = agent.get_trace(response.trace_id)
    chat_policy_events = [
        event for event in trace.events
        if event.kind is TraceEventKind.ERROR and event.data.get("stage") == "chat_policy"
    ]
    assert len(chat_policy_events) == 1
    assert chat_policy_events[0].data["action"] == "execute_something"


@pytest.mark.asyncio
async def test_generic_declarative_write_confirm_lifecycle_end_to_end(tmp_path: Path) -> None:
    """2) Generic write_confirm lifecycle สำหรับ declarative DB tool:

    - prepare สร้าง PendingAction
    - confirm endpoint สั่ง execute submit (internal) ผ่าน ToolRegistry
    - สำเร็จ -> submitted
    - confirm ซ้ำ -> คืนผลลัพธ์เดิม (idempotent)
    """
    db = await _create_test_db(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("declarative_ops", "Ops Tool", "Generic declarative tool with write_confirm", "db"),
        )
        # Prepare operation
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "prepare_task",
                "write_confirm",
                json.dumps(_GENERIC_PREPARE_SCHEMA),
                "{}",
                "llm",
                "prepare",
                "submit_task",
                None,
                None,
            ),
        )
        # Submit operation
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "submit_task",
                "write_confirm",
                json.dumps(_GENERIC_SUBMIT_SCHEMA),
                "{}",
                "internal",
                "submit",
                None,
                "POST",
                "https://api.example.com/tasks",
            ),
        )

        submitted_payloads: list[dict[str, Any]] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            submitted_payloads.append(body)
            return httpx.Response(200, json={"taskId": "TASK-999", "status": "CREATED"})

        mock_transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=mock_transport)

        with patch("app.tools.declarative_executor.httpx.AsyncClient", return_value=mock_client):
            bundle = await load_declarative_tools(db, app_env="development", allowlist=("https://api.example.com/tasks",))

            assert len(bundle.tools) == 1
            declarative_tool = bundle.tools[0]
            # catalogue ต้องมีเฉพาะ prepare_task เท่านั้น (submit_task ต้องไม่หลุดไป LLM)
            assert bundle.catalogue[0].actions == ("prepare_task",)

            # Tool.actions ต้องมีทั้งสอง actions เพื่อให้ ToolRegistry.execute อนุญาต submit_task
            assert "prepare_task" in declarative_tool.actions
            assert "submit_task" in declarative_tool.actions

            # Setup MainAgent with Scripted LLM calling prepare_task
            prepare_call = ToolCall(
                call_id=uuid.uuid4(),
                name="declarative_ops",
                action="prepare_task",
                input={"description": "Fix light outage", "idempotencyKey": "KEY-IDEMP-001"},
            )
            adapter = _ScriptedLLMAdapter([
                LLMResponse(tool_calls=(prepare_call,)),
                LLMResponse(text="เตรียมการแจ้งเหตุเรียบร้อยครับ กรุณายืนยัน"),
            ])
            registry = ToolRegistry(
                [KnowledgeTool(_FakeKnowledgeBackend()), declarative_tool],
                catalogue=bundle.catalogue,
                operation_specs=bundle.operation_specs,
            )
            agent = MainAgent(LLMClient(adapter), registry)

            chat_response = await agent.handle_chat(ChatRequest(message="ช่วยแจ้งเหตุหน่อย"))

            assert chat_response.pending_action is not None
            pa = chat_response.pending_action
            assert pa.tool_name == "declarative_ops"
            assert pa.tool_slug == "declarative_ops"
            assert pa.prepare_action == "prepare_task"
            assert pa.submit_action == "submit_task"
            assert pa.idempotency_key == "KEY-IDEMP-001"
            assert pa.status is PendingActionStatus.PENDING_CONFIRMATION

            # ยืนยันรายการผ่าน confirm_pending_action
            confirm_res = await agent.confirm_pending_action(pa.pending_action_id)
            assert confirm_res.pending_action.status is PendingActionStatus.SUBMITTED
            assert confirm_res.tool_result is not None
            assert confirm_res.tool_result.status is ToolResultStatus.SUCCESS
            assert confirm_res.tool_result.data == {"taskId": "TASK-999", "status": "CREATED"}
            # verify HTTP was invoked once with prepared payload
            assert len(submitted_payloads) == 1
            assert submitted_payloads[0]["description"] == "Fix light outage"

            # ยืนยันซ้ำ: ต้องได้ idempotent result โดยไม่ยิง HTTP ซ้ำ
            confirm_res2 = await agent.confirm_pending_action(pa.pending_action_id)
            assert confirm_res2.pending_action.status is PendingActionStatus.SUBMITTED
            assert len(submitted_payloads) == 1  # ยังคงเป็น 1 ครั้ง ไม่ยิงเพิ่ม

    finally:
        db.close()


@pytest.mark.asyncio
async def test_generic_declarative_rejection_is_terminal(tmp_path: Path) -> None:
    """2b) Reject pending action เป็น terminal state ห้าม confirm ต่อได้"""
    db = await _create_test_db(tmp_path)
    try:
        tool_id = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("sample_ops", "Sample Ops", "Test tool", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation "
            "(tool_id, action, policy, input_schema, output_schema, exposure, mode, submit_action, http_method, url_template) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tool_id,
                "prepare_item",
                "write_confirm",
                json.dumps(_GENERIC_PREPARE_SCHEMA),
                "{}",
                "llm",
                "prepare",
                "submit_item",
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
                "submit_item",
                "write_confirm",
                json.dumps(_GENERIC_SUBMIT_SCHEMA),
                "{}",
                "internal",
                "submit",
                None,
                "POST",
                "https://api.example.com/items",
            ),
        )

        bundle = await load_declarative_tools(db, app_env="development", allowlist=("https://api.example.com/items",))
        call = ToolCall(
            call_id=uuid.uuid4(),
            name="sample_ops",
            action="prepare_item",
            input={"description": "Test item", "idempotencyKey": "KEY-REJECT-001"},
        )
        adapter = _ScriptedLLMAdapter([
            LLMResponse(tool_calls=(call,)),
            LLMResponse(text="เตรียมแล้ว"),
        ])
        registry = ToolRegistry(
            [KnowledgeTool(_FakeKnowledgeBackend()), bundle.tools[0]],
            catalogue=bundle.catalogue,
            operation_specs=bundle.operation_specs,
        )
        agent = MainAgent(LLMClient(adapter), registry)
        chat_resp = await agent.handle_chat(ChatRequest(message="เตรียมรายการ"))
        pa = chat_resp.pending_action
        assert pa is not None

        # ปฏิเสธรายการ
        reject_res = await agent.reject_pending_action(pa.pending_action_id, reason="ผู้ใช้ยกเลิก")
        assert reject_res.pending_action.status is PendingActionStatus.REJECTED

        # พยายามกดยืนยันหลังจากปฏิเสธแล้ว -> ต้องโยน InvalidActionStateError
        with pytest.raises(InvalidActionStateError, match="ไม่สามารถยืนยันรายการที่ถูกปฏิเสธแล้วได้"):
            await agent.confirm_pending_action(pa.pending_action_id)

    finally:
        db.close()


@pytest.mark.asyncio
async def test_policy_collision_regression_same_action_name_different_tools() -> None:
    """3) Policy collision & keying:

    declarative tool ที่มี action 'search' (plain_read)
    ต้องไม่ชนหรือทับ 'knowledge_tool/search' (grounded_answer)
    """
    class _CustomSearchTool:
        name = "custom_search_tool"
        actions = frozenset({"search"})

        async def execute(self, call: ToolCall, context: Any) -> ToolResult:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                action=call.action,
                status=ToolResultStatus.SUCCESS,
                data={"results": ["custom_data"]},
            )

        def reset(self) -> None:
            pass

    registry = ToolRegistry(
        [KnowledgeTool(_FakeKnowledgeBackend()), _CustomSearchTool()],
        operation_specs={
            ("custom_search_tool", "search"): OperationSpec(
                policy=OperationPolicy.PLAIN_READ,
                mode="read",
                exposure="llm",
            ),
        },
    )

    # operation_spec_for_call สำหรับ knowledge_tool search
    k_call = ToolCall(call_id=uuid.uuid4(), name=ToolName.KNOWLEDGE, action="search", input={"query": "test"})
    k_spec = registry.operation_spec_for_call(k_call)
    assert k_spec.policy is OperationPolicy.GROUNDED_ANSWER

    # operation_spec_for_call สำหรับ custom_search_tool search
    c_call = ToolCall(call_id=uuid.uuid4(), name="custom_search_tool", action="search", input={"query": "test"})
    c_spec = registry.operation_spec_for_call(c_call)
    assert c_spec.policy is OperationPolicy.PLAIN_READ

    # ตรวจสอบว่า key ใน registry.operation_specs แยกกันชัดเจน
    assert registry.operation_spec("knowledge_tool", "search").policy is OperationPolicy.GROUNDED_ANSWER
    assert registry.operation_spec("custom_search_tool", "search").policy is OperationPolicy.PLAIN_READ


@pytest.mark.asyncio
async def test_fail_closed_on_corrupt_db_rows_does_not_crash_startup(tmp_path: Path) -> None:
    """4) Fail-closed declarative validation:

    แถวใน DB ข้อมูลผิดพลาด (invalid slug, missing submit_action, missing http method, invalid schema)
    ต้องไม่ทำให้ startup พัง (crash) และข้ามเฉพาะแถวที่เสีย
    แถวที่ถูกต้องใน DB เดียวกันต้องยังทำงานได้ปกติ
    """
    db = await _create_test_db(tmp_path)
    try:
        # Tool 1: Corrupt slug
        t1 = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("INVALID SLUG WITH SPACES!", "Invalid", "bad slug", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t1, "read", "plain_read", "{}", "{}", "llm", "read", "GET", "https://api.example.com/ok"),
        )

        # Tool 2: Prepare without submit_action
        t2 = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("unpaired_prep", "Unpaired", "prepare without submit", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t2, "prepare_alone", "write_confirm", "{}", "{}", "llm", "prepare", None, None),
        )

        # Tool 3: Missing http_method for read DB tool
        t3 = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("no_http_tool", "No HTTP", "read without http", "db"),
        )
        await db.execute(
            "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t3, "read_something", "plain_read", "{}", "{}", "llm", "read", None, None),
        )

        # Tool 4: Valid Tool
        t4 = await db.execute(
            "INSERT INTO tool (slug, display_name, description, source) VALUES (?, ?, ?, ?)",
            ("good_tool", "Good Tool", "valid tool", "db"),
        )
        valid_schema = json.dumps({
            "type": "object",
            "properties": {"info_id": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        })
        await db.execute(
            "INSERT INTO tool_operation (tool_id, action, policy, input_schema, output_schema, exposure, mode, http_method, url_template) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t4, "get_info", "plain_read", valid_schema, "{}", "llm", "read", "GET", "https://api.example.com/info"),
        )

        # load_declarative_tools ต้องไม่ crash และข้าม t1, t2, t3 โหลดเฉพาะ t4
        bundle = await load_declarative_tools(db, app_env="development", allowlist=("https://api.example.com/info",))
        assert len(bundle.tools) == 1
        assert bundle.tools[0].name == "good_tool"
        assert len(bundle.catalogue) == 1
        assert bundle.catalogue[0].name == "good_tool"
        assert ("good_tool", "get_info") in bundle.operation_specs
    finally:
        db.close()


def test_sanitize_validation_error_message_does_not_leak_secrets_or_urls() -> None:
    """4b) การ sanitize ข้อความ error ต้องไม่เปิดเผย secret tokens หรือ full URLs"""
    msg_with_url = "Failed connecting to https://internal-service.pea.co.th/secret-api/v1?token=xyz12345: bad gateway"
    sanitized = sanitize_validation_error_message(msg_with_url)
    assert "https://" not in sanitized
    assert "xyz12345" not in sanitized
    assert "[url_redacted]" in sanitized

    msg_with_token = "authorization token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 was rejected"
    sanitized_token = sanitize_validation_error_message(msg_with_token)
    assert "[redacted_jwt]" in sanitized_token
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized_token
