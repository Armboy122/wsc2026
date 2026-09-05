"""ทดสอบ ToolRegistry.execute — D2.5 regression

🔒 การกระทำ/tool ที่ไม่รู้จักต้องถูกปฏิเสธแบบ fail-safe (INVALID_INPUT) เสมอ ไม่ใช่ raise
KeyError แม้ว่า ``call.name``/``call.action`` จะเป็น slug/action ใหม่ที่ไม่มีอยู่ใน
``TOOL_ACTIONS`` เดิมเลยก็ตาม (CONTRACTS-V2 §3.5) — ครอบคลุมทั้งกรณี tool ไม่รู้จักเลย
และกรณี tool รู้จักแต่ action ไม่รู้จัก
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.registry import ToolContext, ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import Citation, ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.knowledge_tool import KnowledgeTool


class _StubKnowledgeBackend:
    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        citation = Citation(
            sourceId="doc",
            title="เอกสารตัวอย่าง",
            uri="knowledge://source/doc.docx",
            snippet="เนื้อหาตัวอย่าง",
        )
        return GroundedEvidence("เนื้อหาตัวอย่าง", 1, (citation,))


def _registry() -> ToolRegistry:
    return ToolRegistry((KnowledgeTool(backend=_StubKnowledgeBackend()),))


def _context() -> ToolContext:
    return ToolContext(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_unregistered_tool_name_is_rejected_not_a_keyerror():
    registry = _registry()
    call = ToolCall(call_id=uuid4(), name="a_brand_new_declarative_tool", action="do_thing", input={})

    result = await registry.execute(call, _context())

    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_unknown_action_on_a_registered_tool_is_rejected_not_a_keyerror():
    registry = _registry()
    call = ToolCall(call_id=uuid4(), name=ToolName.KNOWLEDGE, action="no_such_action", input={})

    result = await registry.execute(call, _context())

    assert result.status is ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_known_tool_and_action_still_dispatch_normally():
    registry = _registry()
    call = ToolCall(
        call_id=uuid4(),
        name=ToolName.KNOWLEDGE,
        action=ToolAction.KNOWLEDGE_SEARCH,
        input={"query": "billing due date", "maxResults": 1},
    )

    result = await registry.execute(call, _context())

    assert result.status is ToolResultStatus.SUCCESS
