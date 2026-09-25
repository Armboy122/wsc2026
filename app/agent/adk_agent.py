"""PEA Voice Agent and its single ADK-facing Knowledge capability.

Gemini Live receives a compact deterministic catalog in its instruction, chooses source IDs,
and calls ``get_knowledge_documents``. The tool only validates those IDs and returns the
complete approved Markdown with provenance; the same Live session reads it and answers.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import Client, types

from app.contracts import ToolErrorCode
from app.core.logging import get_logger
from app.knowledge.service import (
    USER_SAFE_DOCUMENT_UNAVAILABLE,
    KnowledgeDocumentService,
    SelectionResult,
)

logger = get_logger(__name__)

KNOWLEDGE_TOOL_NAME = "get_knowledge_documents"
_MAX_SOURCE_ID_CHARS = 300
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "adk_voice.md"


class AdkKnowledgeTool(BaseTool):
    """Return complete approved documents for catalog source IDs chosen by Gemini Live."""

    def __init__(self, service: KnowledgeDocumentService) -> None:
        super().__init__(
            name=KNOWLEDGE_TOOL_NAME,
            description=(
                "ดึงเอกสารความรู้ PEA ที่ได้รับอนุมัติฉบับเต็มตาม sourceId ที่เลือกจาก catalog "
                "ในคำสั่งระบบ เครื่องมือนี้ไม่ตอบคำถามและไม่ค้นหาจากคำถาม"
            ),
        )
        self._service = service
        self._schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "source_ids": {
                    "type": "array",
                    "description": "sourceId จาก catalog เท่านั้น เลือกเฉพาะเอกสารที่จำเป็น",
                    "items": {"type": "string", "maxLength": _MAX_SOURCE_ID_CHARS},
                    "minItems": 1,
                    "maxItems": service.max_documents,
                },
            },
            "required": ["source_ids"],
            "additionalProperties": False,
        }

    @property
    def service(self) -> KnowledgeDocumentService:
        return self._service

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._schema,
        )

    def catalog_instruction(self) -> str:
        """Deterministic compact catalog text appended to the Live agent instruction."""
        catalog = json.dumps(
            list(self._service.catalog_entries()), ensure_ascii=False, separators=(",", ":")
        )
        return (
            "## Knowledge catalog\n"
            f"เลือก sourceId จากรายการนี้เท่านั้น แล้วเรียก {KNOWLEDGE_TOOL_NAME} "
            f"(สูงสุด {self._service.max_documents} เอกสารต่อครั้ง):\n{catalog}"
        )

    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, Any]:
        source_ids = args.get("source_ids") if isinstance(args, dict) else None
        if set(args or {}) != {"source_ids"} or not isinstance(source_ids, list):
            # An empty selection is rejected by the service as an invalid selection.
            source_ids = []
        try:
            result = await asyncio.to_thread(self._service.select, source_ids)
        except Exception:
            logger.error("knowledge_documents_failed")
            return _error_payload(ToolErrorCode.INTERNAL, USER_SAFE_DOCUMENT_UNAVAILABLE)
        payload = selection_payload(result)
        logger.info(
            "knowledge_documents_returned",
            extra={"status": payload["status"], "documents": len(result.documents)},
        )
        return payload


def selection_payload(result: SelectionResult) -> dict[str, Any]:
    """Model-facing tool result: complete documents and provenance, or one safe failure."""
    if result.failure is not None:
        return _error_payload(result.failure.code, result.failure.message)
    return {
        "status": "success",
        "documents": [
            {
                "sourceId": document.source_id,
                "title": document.title,
                "uri": document.uri,
                "content": document.content,
            }
            for document in result.documents
        ],
        "sources": [
            {"sourceId": document.source_id, "title": document.title, "uri": document.uri}
            for document in result.documents
        ],
    }


def _error_payload(code: ToolErrorCode, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code.value, "message": message}}


def create_adk_agent(
    *, model: str, client: Client, knowledge_tool: AdkKnowledgeTool
) -> Agent:
    instruction = (
        _PROMPT_PATH.read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + knowledge_tool.catalog_instruction()
    )
    return Agent(
        name="pea_one_agent",
        model=Gemini(model=model, client=client),
        instruction=instruction,
        tools=[knowledge_tool],
    )
