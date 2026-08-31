"""``knowledge_tool`` — เครื่องมือเดียวในเดโม PEA One Agent ที่ไม่ใช่เครื่องมือจำลอง

ทำงานตามการกระทำที่กำหนดไว้ในสัญญา ``knowledge_tool.search`` (CONTRACTS.md)
โดยส่งคำค้นให้ backend เอกสารที่เลือกไฟล์ DOCX ที่เกี่ยวข้อง แล้วใช้ข้อความฉบับเต็มของ
แต่ละไฟล์สร้างหลักฐาน ผลลัพธ์จะมีค่า ``simulation=false`` และมีค่า ``Citation``
ตามสัญญาเมื่อมีหลักฐาน เครื่องมือนี้ไม่มีการค้นคืนภายในเครื่องหรือใช้ความจำของโมเดล
เป็นทางเลือกสำรอง

โมดูลนี้ทำตามโครงสร้างของโปรโตคอล Tool ใน ARCHITECTURE.md:

    class Tool(Protocol):
        name: ToolName
        async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError

from app import contracts
from app.backends.full_document_knowledge import (
    FullDocumentKnowledgeBackend,
    GroundedEvidence,
    KnowledgeBackendError,
)

logger = logging.getLogger("pea_one_agent.knowledge_tool")

# ข้อความเมื่อเครื่องมือทำงานล้มเหลว ต้องปลอดภัยต่อผู้ใช้และไม่มีข้อมูลรับรอง
USER_SAFE_INVALID_INPUT = (
    "คำขอค้นหาความรู้ไม่ถูกต้อง กรุณาตรวจสอบช่อง query และ maxResults"
)
USER_SAFE_INTERNAL = (
    "เกิดข้อผิดพลาดขณะค้นหาฐานความรู้ กรุณาลองใหม่อีกครั้ง"
)


@dataclass(frozen=True)
class ToolContext:
    """บริบทประจำการเรียกที่ Tool Registry ส่งให้

    ปัจจุบันเครื่องมือความรู้ไม่ต้องใช้ฟิลด์บริบทใด แต่ registry อาจส่งออบเจ็กต์
    ที่มีข้อมูลมากกว่าได้ และ ``execute`` รองรับด้วยการตรวจโครงสร้างแบบ duck typing
    ดังนั้นรูปแบบภายในเครื่องนี้จึงเป็นเพียงเอกสารของข้อมูลขั้นต่ำที่เครื่องมือรองรับ
    """

    conversation_id: UUID | None = None
    trace_id: UUID | None = None


class KnowledgeSearchBackend(Protocol):
    """ขอบเขตขั้นต่ำที่ ``KnowledgeTool`` ต้องใช้จาก backend ความรู้"""

    async def search(self, query: str, max_results: int) -> GroundedEvidence: ...


class KnowledgeTool:
    """การใช้งาน ``Tool`` แบบกำหนดตายตัวสำหรับ :class:`~app.contracts.ToolName.KNOWLEDGE`

    เครื่องมือนี้เป็นเจ้าของเฉพาะการกระทำ ``search`` (กำหนดไว้ใน
    ``app.contracts.TOOL_ACTIONS``) การกระทำอื่นจะถูกปฏิเสธแบบปิดเมื่อเกิดข้อผิดพลาด
    ก่อนเรียกใช้ backend
    """

    name: contracts.ToolName = contracts.ToolName.KNOWLEDGE

    def __init__(self, backend: KnowledgeSearchBackend | None = None) -> None:
        self._backend: KnowledgeSearchBackend = (
            backend if backend is not None else FullDocumentKnowledgeBackend()
        )

    async def execute(
        self, call: contracts.ToolCall, context: ToolContext | Any
    ) -> contracts.ToolResult:
        """ตรวจสอบข้อมูลนำเข้าตามสัญญา เรียกการค้นคืนจากบริการโฮสต์ และห่อเป็นผลลัพธ์ตามสัญญา"""
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
            logger.exception("knowledge_tool.search ล้มเหลวโดยไม่คาดคิด")
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
