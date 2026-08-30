"""``knowledge_tool`` — the only non-simulated tool in the PEA One Agent demo.

Implements the frozen ``knowledge_tool.search`` action (CONTRACTS.md) against
the Gemini File Search Hosted RAG backend. Results carry ``simulation=false``
and, when the provider returns evidence, frozen ``Citation`` values. The tool
forwards the retrieval query to the hosted service and never substitutes local
retrieval (no embeddings, no local index, no model-memory fallback).

The module satisfies the Tool protocol from ARCHITECTURE.md structurally:

    class Tool(Protocol):
        name: ToolName
        async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app import contracts
from app.backends.gemini_file_search import (
    GeminiFileSearchKnowledgeBackend,
    GroundedEvidence,
    KnowledgeBackendError,
)

logger = logging.getLogger("pea_one_agent.knowledge_tool")

# User-safe, credential-free messages for the tool's own failure surface.
USER_SAFE_INVALID_INPUT = (
    "The knowledge search request is invalid. Check the query and maxResults fields."
)
USER_SAFE_INTERNAL = (
    "Something went wrong while searching the knowledge base. Please try again."
)


@dataclass(frozen=True)
class ToolContext:
    """Per-call context handed by the Tool Registry.

    The knowledge tool needs no context field today; the registry may pass a
    richer object and ``execute`` is duck-typed over it, so this local shape
    is only documentation of the minimum the tool tolerates.
    """

    conversation_id: UUID | None = None
    trace_id: UUID | None = None


class KnowledgeTool:
    """Frozen ``Tool`` implementation for :class:`~app.contracts.ToolName.KNOWLEDGE`.

    Only the ``search`` action is owned by this tool (frozen in
    ``app.contracts.TOOL_ACTIONS``); anything else is rejected fail-closed
    before a backend call.
    """

    name: contracts.ToolName = contracts.ToolName.KNOWLEDGE

    def __init__(self, backend: GeminiFileSearchKnowledgeBackend | None = None) -> None:
        self._backend = backend if backend is not None else GeminiFileSearchKnowledgeBackend()

    async def execute(
        self, call: contracts.ToolCall, context: ToolContext | Any
    ) -> contracts.ToolResult:
        """Validate the frozen input, run hosted retrieval, wrap a frozen result."""
        if (
            call.name is not contracts.ToolName.KNOWLEDGE
            or call.action is not contracts.ToolAction.KNOWLEDGE_SEARCH
        ):
            return self._error(
                call, contracts.ToolErrorCode.INVALID_INPUT, USER_SAFE_INVALID_INPUT
            )
        try:
            payload = contracts.validate_tool_input(call)
        except ValidationError:
            return self._error(
                call, contracts.ToolErrorCode.INVALID_INPUT, USER_SAFE_INVALID_INPUT
            )
        try:
            evidence = await self._backend.search(payload.query, payload.max_results)
        except KnowledgeBackendError as exc:
            return self._error(call, exc.code, exc.message)
        except Exception:
            logger.exception("knowledge_tool.search failed unexpectedly")
            return self._error(call, contracts.ToolErrorCode.INTERNAL, USER_SAFE_INTERNAL)
        return self._success(call, evidence)

    def _success(self, call: contracts.ToolCall, evidence: GroundedEvidence) -> contracts.ToolResult:
        output = contracts.KnowledgeSearchOutput(
            answer_context=evidence.answer_context,
            result_count=evidence.result_count,
        )
        return contracts.ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=contracts.ToolResultStatus.SUCCESS,
            data=output.model_dump(by_alias=True, mode="json"),
            citations=evidence.citations,
            simulation=False,
        )

    def _error(
        self, call: contracts.ToolCall, code: contracts.ToolErrorCode, message: str
    ) -> contracts.ToolResult:
        return contracts.ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=contracts.ToolResultStatus.ERROR,
            error=contracts.ToolError(code=code, message=message),
            simulation=False,
        )
