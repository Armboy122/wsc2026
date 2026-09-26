"""PEA Voice Agent and its single ADK-facing Knowledge capability.

Gemini Live receives a compact voice prompt and calls ``search_knowledge(query)``. The tool
runs the deterministic local hybrid index off the event loop and returns approved Q&A first,
then source-attributed document chunks; the same Live session reads them and answers.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import Client, types

from app.contracts import ToolErrorCode
from app.core.logging import get_logger
from app.knowledge.index import (
    IndexManager,
    IndexUnavailableError,
    InvalidQueryError,
    SearchResult,
)

logger = get_logger(__name__)

KNOWLEDGE_TOOL_NAME = "search_knowledge"
MAX_QUERY_CHARS = 500
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "adk_voice.md"

_USER_SAFE_INVALID_QUERY = "คำถามที่ส่งมาไม่ถูกต้อง กรุณาถามใหม่เป็นข้อความสั้น ๆ"
_USER_SAFE_UNAVAILABLE = "ระบบค้นหาความรู้ยังไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"
_USER_SAFE_INTERNAL = "ค้นหาความรู้ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"


class AdkKnowledgeTool(BaseTool):
    """Search approved local Knowledge for one Thai query; never answers or generates text."""

    def __init__(self, manager: IndexManager) -> None:
        super().__init__(
            name=KNOWLEDGE_TOOL_NAME,
            description=(
                "ค้นเอกสารความรู้ PEA ที่ได้รับอนุมัติแบบ deterministic จากคำถามภาษาไทย "
                "แล้วคืนคำตอบที่อนุมัติและเนื้อหาที่เกี่ยวข้องพร้อมแหล่งอ้างอิง "
                "เครื่องมือนี้ไม่สร้างคำตอบเองและไม่ใช้ความจำของโมเดล"
            ),
        )
        self._manager = manager
        self._schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "คำถามภาษาไทยสั้น ๆ ที่ต้องการค้นจากเอกสาร PEA ที่อนุมัติแล้ว",
                    "minLength": 1,
                    "maxLength": MAX_QUERY_CHARS,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    @property
    def manager(self) -> IndexManager:
        return self._manager

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._schema,
        )

    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, Any]:
        query = _validated_query(args)
        if query is None:
            return _error_payload(ToolErrorCode.INVALID_INPUT, _USER_SAFE_INVALID_QUERY)

        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(self._manager.search, query)
        except InvalidQueryError:
            return _error_payload(ToolErrorCode.INVALID_INPUT, _USER_SAFE_INVALID_QUERY)
        except IndexUnavailableError:
            logger.warning("knowledge_search_unavailable")
            return _error_payload(ToolErrorCode.UNAVAILABLE, _USER_SAFE_UNAVAILABLE)
        except Exception:  # noqa: BLE001 - any unexpected failure maps to a safe wire error
            logger.error("knowledge_search_failed")
            return _error_payload(ToolErrorCode.INTERNAL, _USER_SAFE_INTERNAL)

        payload = search_result_payload(result)
        logger.info(
            "knowledge_search status=%s approved_qa=%d chunks=%d latency_ms=%.1f",
            payload["status"],
            len(payload["approvedQa"]),
            len(payload["chunks"]),
            (time.perf_counter() - started) * 1000.0,
        )
        return payload


def _validated_query(args: Any) -> str | None:
    """Accept only ``{"query": <non-empty string of at most 500 chars>}``."""
    if not isinstance(args, dict) or set(args) != {"query"}:
        return None
    query = args["query"]
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        return None
    return query.strip()


def search_result_payload(result: SearchResult) -> dict[str, Any]:
    """Model-facing tool result: approved Q&A first, then chunks, then flat sources."""
    approved_qa = [
        {
            "sourceId": hit.source_id,
            "title": hit.title,
            "uri": hit.uri,
            "content": hit.text,
        }
        for hit in result.qa
    ]
    chunks = [
        {
            "sourceId": hit.source_id,
            "title": hit.title,
            "uri": hit.uri,
            "heading": " > ".join(hit.heading_path),
            "content": hit.text,
        }
        for hit in result.chunks
    ]
    metadata: dict[str, dict[str, str]] = {}
    for hit in (*result.qa, *result.chunks):
        metadata.setdefault(
            hit.source_id,
            {"sourceId": hit.source_id, "title": hit.title, "uri": hit.uri},
        )
    sources = [metadata[source_id] for source_id in result.sources]
    return {
        "status": "success",
        "approvedQa": approved_qa,
        "chunks": chunks,
        "sources": sources,
    }


def _error_payload(code: ToolErrorCode, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code.value, "message": message}}


def create_adk_agent(
    *, model: str, client: Client, knowledge_tool: AdkKnowledgeTool
) -> Agent:
    """Build the one conversational agent; its instruction is the prompt file verbatim.

    The prompt is passed as-is so it contains no ``{...}`` ADK template variables.
    """
    instruction = _PROMPT_PATH.read_text(encoding="utf-8").rstrip()
    return Agent(
        name="pea_one_agent",
        model=Gemini(model=model, client=client),
        instruction=instruction,
        tools=[knowledge_tool],
    )
