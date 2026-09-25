from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest
from google.adk.tools.tool_context import ToolContext
from google.genai import Client

from app.agent.adk_agent import AdkKnowledgeTool, create_adk_agent
from app.contracts import (
    Citation,
    ToolAction,
    ToolCall,
    ToolErrorCode,
    ToolError,
    ToolName,
    ToolResult,
    ToolResultStatus,
)
from app.tools.knowledge_tool import KnowledgeTool


class Knowledge:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        self.calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"answerContext": "ข้อมูลจากเอกสารที่อนุมัติ"},
            citations=(Citation(
                source_id="service.md",
                title="คู่มือบริการ",
                uri="knowledge://source/service.md",
                snippet="ข้อมูลจากเอกสารที่อนุมัติ",
            ),),
            simulation=False,
        )


@pytest.mark.asyncio
async def test_adk_knowledge_tool_calls_only_knowledge_and_returns_provenance() -> None:
    knowledge = Knowledge()
    tool = AdkKnowledgeTool(cast(KnowledgeTool, knowledge))

    assert tool.name == "search_knowledge"
    assert tool._get_declaration().name == "search_knowledge"
    result = await tool.run_async(
        args={"query": "ขอใช้ไฟฟ้า", "maxResults": 2},
        tool_context=cast(ToolContext, object()),
    )

    assert result["data"]["answerContext"] == "ข้อมูลจากเอกสารที่อนุมัติ"
    assert result["citations"][0]["sourceId"] == "service.md"
    assert len(knowledge.calls) == 1
    assert knowledge.calls[0].name is ToolName.KNOWLEDGE
    assert knowledge.calls[0].action is ToolAction.KNOWLEDGE_SEARCH
    assert knowledge.calls[0].input == {"query": "ขอใช้ไฟฟ้า", "maxResults": 2}


def test_adk_agent_exposes_only_knowledge_and_voice_runtime_has_no_main_agent_import() -> None:
    knowledge_tool = AdkKnowledgeTool(cast(KnowledgeTool, Knowledge()))
    client = Client(api_key="test")
    try:
        agent = create_adk_agent(
            model="gemini-live-test", client=client, knowledge_tool=knowledge_tool
        )
        assert len(agent.tools) == 1
        assert agent.tools[0] is knowledge_tool
    finally:
        client.close()

    for filename in ("app/agent/adk_agent.py", "app/runtime/adk_live.py"):
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "app.agent.main_agent" not in imported_modules


@pytest.mark.asyncio
async def test_adk_knowledge_tool_returns_safe_typed_error() -> None:
    class Unavailable(Knowledge):
        async def execute(self, call: ToolCall, context: object) -> ToolResult:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                action=call.action,
                status=ToolResultStatus.ERROR,
                error=ToolError(code=ToolErrorCode.UNAVAILABLE, message="ไม่พร้อมใช้งาน"),
                simulation=False,
            )

    tool = AdkKnowledgeTool(cast(KnowledgeTool, Unavailable()))
    result = await tool.run_async(
        args={"query": "คำถาม"}, tool_context=cast(ToolContext, object())
    )

    assert result["error"]["message"] == "ไม่พร้อมใช้งาน"
