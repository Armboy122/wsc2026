"""``Tool`` ตัวเดียวที่รับผิดชอบทุก operation ของ declarative tool หนึ่งตัวจาก DB — D2.6

นี่คือจุดที่ประกอบทุกชิ้นของ D2.1–D2.5 เข้าด้วยกันเป็นตัวพิสูจน์ว่า contract ใช้ได้จริง:
``ToolShape`` (D2.3, source="db") + schema instance validation (D1.2/D2.6) +
``build_declarative_http_request`` (D2.6) + ``DeclarativeToolExecutor`` (D2.4, ผ่านนโยบาย
เครือข่ายขาออกของ D1.3 ทุกครั้งไม่มีทางลัด) ประกอบเป็น ``Tool`` ตัวเดียวที่
``ToolRegistry`` เรียกได้เหมือน Python plugin ทุกประการ — agent ไม่รู้ว่านี่มาจาก DB
(ARCHITECTURE-V2.md §3.4)

ข้อผิดพลาดทุกจุด (schema ไม่ตรง, urlTemplate ผิด, นโยบายเครือข่ายบล็อก, ปลายทางล่ม)
แปลเป็นข้อความภาษาไทยทั่วไปที่ไม่รั่ว URL/schema/เหตุผลนโยบายให้ LLM หรือผู้ใช้เห็น
(CONTRACTS-V2.md §4.2/§8.6 error รูปเดียว)
"""

from __future__ import annotations

from typing import Any

from app.agent.tool_shape import ToolShape
from app.contracts import ToolCall, ToolError, ToolErrorCode, ToolResult, ToolResultStatus
from app.tools.declarative_executor import (
    DeclarativeToolAuth,
    DeclarativeToolError,
    DeclarativeToolExecutor,
)
from app.tools.declarative_request import UrlTemplateError, build_declarative_http_request
from app.tools.network_policy import NetworkPolicyError
from app.tools.schema_instance import SchemaInstanceError, validate_schema_instance


class DeclarativeTool:
    """Tool ตัวเดียวต่อ declarative tool หนึ่งแถวใน DB — จัดการทุก operation ของมัน"""

    def __init__(
        self,
        shape: ToolShape,
        executor: DeclarativeToolExecutor,
        *,
        auth: DeclarativeToolAuth | None = None,
    ) -> None:
        if shape.source != "db":
            raise ValueError("DeclarativeTool รับเฉพาะ ToolShape ที่มาจาก DB เท่านั้น")
        self.name = shape.slug
        self._shape = shape
        self._executor = executor
        self._auth = auth

    @property
    def actions(self) -> frozenset[str]:
        """action ทั้งหมดที่ LLM เรียกได้ — ``ToolRegistry`` ใช้แทน ``TOOL_ACTIONS`` เดิม
        สำหรับ tool ที่ไม่ได้อยู่ใน dict กลางนั้น (CONTRACTS-V2.md §3.5)"""
        return frozenset(op.action for op in self._shape.operations if op.exposure == "llm")

    def reset(self) -> None:
        """declarative tool ไม่มีสถานะภายใน process ให้รีเซ็ต (ยิงจริงทุกครั้ง ไม่มี fixture ค้าง)"""

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        del context
        operation = self._shape.operation(call.action)
        if operation is None or operation.http_method is None or operation.url_template is None:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ไม่รู้จัก action นี้")

        try:
            validate_schema_instance(operation.input_schema, call.input)
        except SchemaInstanceError:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ข้อมูลนำเข้าไม่ตรงกับ schema ของ action นี้")

        try:
            request = build_declarative_http_request(
                http_method=operation.http_method,
                url_template=operation.url_template,
                input=call.input,
                auth=self._auth,
            )
        except UrlTemplateError:
            return self._error(call, ToolErrorCode.INTERNAL, "การตั้งค่า tool นี้มีปัญหา กรุณาติดต่อผู้ดูแลระบบ")

        try:
            response = await self._executor.execute(request)
        except (DeclarativeToolError, NetworkPolicyError):
            # ไม่แยกข้อความตามเหตุผล (SSRF บล็อก vs. ปลายทางล่ม) ตั้งใจ — ทั้งสองไม่ใช่สิ่งที่
            # ผู้ใช้/LLM แก้ได้ และการบอกเหตุผลนโยบายออกไปเป็นการรั่วข้อมูลที่ไม่จำเป็น
            return self._error(call, ToolErrorCode.UNAVAILABLE, "บริการที่ร้องขอไม่พร้อมใช้งานชั่วคราว")

        if response.status_code >= 400 or not isinstance(response.json_body, dict):
            return self._error(call, ToolErrorCode.UNAVAILABLE, "บริการที่ร้องขอไม่พร้อมใช้งานชั่วคราว")

        if operation.output_schema is not None:
            try:
                validate_schema_instance(operation.output_schema, response.json_body)
            except SchemaInstanceError:
                return self._error(call, ToolErrorCode.INTERNAL, "บริการส่งข้อมูลที่ไม่ตรงกับ schema ที่ประกาศไว้")

        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data=response.json_body,
            simulation=True,
        )

    @staticmethod
    def _error(call: ToolCall, code: ToolErrorCode, message: str) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            error=ToolError(code=code, message=message),
            simulation=True,
        )
