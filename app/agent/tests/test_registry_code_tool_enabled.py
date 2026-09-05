"""ทดสอบการเปิด/ปิด code tool จากหน้า admin ให้มีผลจริงที่ ToolRegistry — P4

ความเสี่ยงที่เทสนี้กันไว้ (TASKS P4):

- ปิด code tool แล้ว tool นั้นต้องหายจากแค็ตตาล็อกที่ส่งให้ LLM จริง
- ปิดแล้วเรียกใช้ต้องถูกปฏิเสธอย่างชัดเจน (UNAVAILABLE) ไม่ใช่ dispatch เงียบ ๆ
- เปิดกลับแล้วใช้งานได้เหมือนเดิม
- knowledge เป็นเส้นทางหลักที่ registry บังคับว่าต้องมีเสมอ — ห้ามปิดจากที่ใดก็ได้
- แค็ตตาล็อกเต็ม (full_catalogue) ยังเห็น tool ที่ถูกปิด เพื่อหน้า admin แสดงรายการครบ

ประกอบ registry แบบเดียวกับ production: KnowledgeTool จริงกับ backend ปลอมขั้นต่ำ
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolContext, ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import ToolCall, ToolErrorCode, ToolResult, ToolResultStatus
from app.llm.models import ToolDefinition
from app.tools.knowledge_tool import KnowledgeTool


class _StubKnowledgeBackend:
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        return GroundedEvidence("เนื้อหาตัวอย่าง", 1, ())


class _StubCodeTool:
    """tool จากโค้ด (Python) แบบเดียวกับปลั๊กอิน: มี actions + reset + execute"""

    def __init__(self, name: str = "custom_code_tool") -> None:
        self.name = name
        self.actions = frozenset({"do_thing"})
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        self.calls += 1
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={},
            simulation=True,
        )


class _ResetFailingFlow:
    def __init__(self, owner: str = "custom_code_tool") -> None:
        self._tool = _StubCodeTool(owner)
        self.reset_calls = 0

    def is_active(self, conversation_id) -> bool:
        return True

    def reset(self) -> None:
        self.reset_calls += 1
        raise RuntimeError("reset failure must not escape")


class _ResetTrackingFlow:
    def __init__(self, owner: str = "custom_code_tool") -> None:
        self._tool = _StubCodeTool(owner)
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1


def _registry(
    *tools: Any, disabled_code_tools: tuple[str, ...] | frozenset[str] = ()
) -> ToolRegistry:
    code_tools = tuple(tool for tool in tools if isinstance(tool, _StubCodeTool))
    catalogue = tuple(
        ToolDefinition(
            name=tool.name,
            description="stub code tool",
            actions=tuple(tool.actions),
        )
        for tool in code_tools
    )
    return ToolRegistry(
        [KnowledgeTool(backend=_StubKnowledgeBackend()), *tools],
        catalogue=catalogue,
        disabled_code_tools=disabled_code_tools,
    )


def _code_registry() -> tuple[ToolRegistry, _StubCodeTool]:
    tool = _StubCodeTool()
    return _registry(tool), tool


def _call(name: str = "custom_code_tool", action: str = "do_thing") -> ToolCall:
    return ToolCall(call_id=uuid4(), name=name, action=action, input={})


def _context() -> ToolContext:
    return ToolContext(uuid4(), uuid4())


def test_disabled_code_tool_is_hidden_from_llm_catalogue() -> None:
    registry, _ = _code_registry()

    assert any(d.name == "custom_code_tool" for d in registry.llm_catalogue)
    registry.set_code_tool_enabled("custom_code_tool", False)

    assert all(d.name != "custom_code_tool" for d in registry.llm_catalogue)
    # knowledge (built-in) ยังอยู่ครบ
    assert any(d.name == "knowledge_tool" for d in registry.llm_catalogue)


@pytest.mark.asyncio
async def test_disabled_code_tool_dispatch_is_rejected_clearly() -> None:
    registry, tool = _code_registry()
    registry.set_code_tool_enabled("custom_code_tool", False)

    result = await registry.execute(_call(), _context())

    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code is ToolErrorCode.UNAVAILABLE
    assert result.error.message
    # ต้องไม่ dispatch ลง tool จริง
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_re_enabled_code_tool_returns_to_catalogue_and_dispatch() -> None:
    registry, tool = _code_registry()
    registry.set_code_tool_enabled("custom_code_tool", False)
    registry.set_code_tool_enabled("custom_code_tool", True)

    assert any(d.name == "custom_code_tool" for d in registry.llm_catalogue)
    result = await registry.execute(_call(), _context())

    assert result.status is ToolResultStatus.SUCCESS
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_disabled_code_tool_can_be_declared_at_construction() -> None:
    """เส้นทาง boot: main.py โหลดสถานะจาก DB แล้วส่งเข้า constructor"""
    tool = _StubCodeTool()
    registry = _registry(tool, disabled_code_tools=("custom_code_tool",))

    assert all(d.name != "custom_code_tool" for d in registry.llm_catalogue)
    result = await registry.execute(_call(), _context())
    assert result.error is not None
    assert result.error.code is ToolErrorCode.UNAVAILABLE


def test_knowledge_cannot_be_disabled() -> None:
    registry, _ = _code_registry()

    with pytest.raises(ValueError):
        registry.set_code_tool_enabled("knowledge_tool", False)

    # knowledge ยังอยู่ในแค็ตตาล็อกครบและ dispatch ได้เหมือนเดิม
    assert any(d.name == "knowledge_tool" for d in registry.llm_catalogue)


def test_knowledge_is_dropped_from_disabled_set_at_construction() -> None:
    """กันพลาดระดับข้อมูล: ถ้า DB มีแถวปิด knowledge ค้างไว้ registry ต้องไม่ปิดมัน"""
    registry = _registry(disabled_code_tools=("knowledge_tool",))

    assert any(d.name == "knowledge_tool" for d in registry.llm_catalogue)


def test_full_catalogue_keeps_disabled_tool_for_admin_list() -> None:
    """หน้า admin ต้องยังเห็น tool ที่ถูกปิด — ใช้ full_catalogue ไม่ใช่ llm_catalogue"""
    registry, _ = _code_registry()
    registry.set_code_tool_enabled("custom_code_tool", False)

    assert any(d.name == "custom_code_tool" for d in registry.full_catalogue)


def test_code_tool_enabled_reflects_state() -> None:
    registry, _ = _code_registry()

    assert registry.code_tool_enabled("custom_code_tool") is True
    registry.set_code_tool_enabled("custom_code_tool", False)
    assert registry.code_tool_enabled("custom_code_tool") is False
    registry.set_code_tool_enabled("custom_code_tool", True)
    assert registry.code_tool_enabled("custom_code_tool") is True


def test_state_listener_failure_is_isolated_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    registry, _ = _code_registry()
    events: list[tuple[str, bool]] = []

    def failing_listener(slug: str, enabled: bool) -> None:
        raise RuntimeError("secret listener detail")

    registry.add_code_tool_state_listener(failing_listener)
    registry.add_code_tool_state_listener(lambda slug, enabled: events.append((slug, enabled)))

    registry.set_code_tool_enabled("custom_code_tool", False)

    assert registry.code_tool_enabled("custom_code_tool") is False
    assert events == [("custom_code_tool", False)]
    assert "secret listener detail" not in caplog.text
    assert "code_tool_state_listener_failed" in caplog.text
    assert any(
        getattr(record, "error_type", None) == "RuntimeError"
        for record in caplog.records
    )


def test_failing_guided_flow_reset_stays_quarantined_after_reenable() -> None:
    registry, _ = _code_registry()
    flow = _ResetFailingFlow()
    flows = GuidedFlows((flow,))
    flows.bind_tool_enabled(registry.code_tool_enabled)
    registry.add_code_tool_state_listener(flows.code_tool_state_changed)
    events: list[tuple[str, bool]] = []
    registry.add_code_tool_state_listener(lambda slug, enabled: events.append((slug, enabled)))

    registry.set_code_tool_enabled("custom_code_tool", False)
    registry.set_code_tool_enabled("custom_code_tool", True)

    assert registry.code_tool_enabled("custom_code_tool") is True
    assert events == [("custom_code_tool", False), ("custom_code_tool", True)]
    assert flow.reset_calls == 2
    assert flows.active_flow(uuid4()) is None


@pytest.mark.asyncio
async def test_demo_reset_reports_flow_failure_after_attempting_all_flows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry, _ = _code_registry()
    failing = _ResetFailingFlow()
    succeeding = _ResetTrackingFlow()
    flows = GuidedFlows((failing, succeeding))
    agent = MainAgent(object(), registry, guided_flows=flows)

    with pytest.raises(RuntimeError, match="guided flow reset failed"):
        await agent.reset_demo()

    assert failing.reset_calls == 1
    assert succeeding.reset_calls == 1
    assert "reset failure must not escape" not in caplog.text


@pytest.mark.asyncio
async def test_declarative_and_other_code_tools_unaffected() -> None:
    """ปิด tool หนึ่งตัวต้องไม่กระทบ tool อื่นใน registry"""
    voc = _StubCodeTool("custom_code_tool")
    other = _StubCodeTool("other_tool")
    registry = _registry(voc, other)
    registry.set_code_tool_enabled("custom_code_tool", False)

    assert all(d.name != "custom_code_tool" for d in registry.llm_catalogue)
    assert any(d.name == "other_tool" for d in registry.llm_catalogue)
    result = await registry.execute(_call("other_tool"), _context())
    assert result.status is ToolResultStatus.SUCCESS
    assert other.calls == 1
