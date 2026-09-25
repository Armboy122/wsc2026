"""PEA Voice Agent and its single ADK-facing Knowledge capability."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import Client, types

from app.contracts import KnowledgeSearchInput, ToolAction, ToolCall, ToolName
from app.tools.knowledge_tool import KnowledgeTool


class AdkKnowledgeTool(BaseTool):
    """Adapt the validated Knowledge capability to ADK's tool interface."""

    def __init__(self, knowledge_tool: KnowledgeTool) -> None:
        super().__init__(
            name="search_knowledge",
            description="ค้นเอกสารความรู้ PEA ที่ได้รับอนุมัติ เพื่อใช้ตอบคำถามจากหลักฐาน",
        )
        self._knowledge_tool = knowledge_tool
        self._schema = KnowledgeSearchInput.model_json_schema(by_alias=True)

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._schema,
        )

    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, Any]:
        call = ToolCall(
            call_id=uuid4(),
            name=ToolName.KNOWLEDGE,
            action=ToolAction.KNOWLEDGE_SEARCH,
            input=args,
        )
        execute_knowledge = self._knowledge_tool.execute
        result = await execute_knowledge(call, context=None)
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)


def create_adk_agent(
    *, model: str, client: Client, knowledge_tool: AdkKnowledgeTool
) -> Agent:
    return Agent(
        name="pea_one_agent",
        model=Gemini(model=model, client=client),
        instruction=Path(__file__).resolve().parents[1].joinpath(
            "prompts/adk_voice.md"
        ).read_text(encoding="utf-8"),
        tools=[knowledge_tool],
    )
