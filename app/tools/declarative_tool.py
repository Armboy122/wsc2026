"""``Tool`` ตัวเดียวที่รับผิดชอบทุก operation ของ declarative tool หนึ่งตัวจาก DB — D2.6/D2.7

นี่คือจุดที่ประกอบทุกชิ้นของ D2.1–D2.5 เข้าด้วยกันเป็นตัวพิสูจน์ว่า contract ใช้ได้จริง:
``ToolShape`` (D2.3, source="db") + schema instance validation (D1.2/D2.6) +
``build_declarative_http_request`` (D2.6) + ``DeclarativeToolExecutor`` (D2.4, ผ่านนโยบาย
เครือข่ายขาออกของ D1.3 ทุกครั้งไม่มีทางลัด) ประกอบเป็น ``Tool`` ตัวเดียวที่
``ToolRegistry`` เรียกได้เหมือน Python plugin ทุกประการ — agent ไม่รู้ว่านี่มาจาก DB
(ARCHITECTURE-V2.md §3.4)

ข้อผิดพลาดทุกจุด (schema ไม่ตรง, urlTemplate ผิด, นโยบายเครือข่ายบล็อก, ปลายทางล่ม)
แปลเป็นข้อความภาษาไทยทั่วไปที่ไม่รั่ว URL/schema/เหตุผลนโยบายให้ LLM หรือผู้ใช้เห็น
(CONTRACTS-V2.md §4.2/§8.6 error รูปเดียว)

D2.7 เติม 2 เรื่องที่ D2.6 ยังไม่ต้องพิสูจน์ (ตัวพิสูจน์ตอนนั้นมีแค่ ``plain_read``):

1. **``write_confirm`` สองจังหวะ** — ``mode: prepare`` ไม่มี side effect จริงตามสัญญา
   (CONTRACTS-V2.md §3.1) จึง**ไม่ยิง HTTP เลย** เก็บ payload ไว้ในหน่วยความจำของ tool
   นี้เองโดยผูกกับ ``idempotencyKey`` ก่อน (เหมือนที่ ``OmsTool`` เดิมทำกับ ``_drafts``)
   ``mode: submit`` เท่านั้นที่ยิงจริง โดยดึง payload ที่เก็บไว้กลับมาใช้ ไม่ใช่ input ของ
   ``submit`` เอง (ซึ่งมีแค่ ``pendingActionId``/``idempotencyKey`` ตามสัญญากลาง)
2. **แปล HTTP status code เป็น ``ToolErrorCode`` ที่จำเพาะขึ้น** — ตัวพิสูจน์ของ D2.6 ยุบทุก
   4xx/5xx เป็น ``unavailable`` เพราะพอสำหรับ ``plain_read``เท่านั้น แต่ ``write_confirm`` ของ
   OMS ต้องแยก 404 (ไม่พบหมายเลขผู้ใช้ไฟ) กับ 409 (มีเหตุการณ์ซ้ำ) ออกจากกันเพื่อให้
   response policy ของแต่ละ tool แสดงข้อความที่ถูกต้อง — ธรรมเนียมนี้ทั่วไปสำหรับ REST
   ไม่ผูกกับ tool ใดตัวหนึ่ง (ดู CONTRACTS-V2.md §4.2)
"""

from __future__ import annotations

from typing import Any

from app.agent.tool_shape import ToolOperationShape, ToolShape
from app.contracts import ToolCall, ToolError, ToolErrorCode, ToolResult, ToolResultStatus
from app.tools.declarative_executor import (
    DeclarativeToolAuth,
    DeclarativeToolError,
    DeclarativeToolExecutor,
)
from app.tools.declarative_request import UrlTemplateError, build_declarative_http_request
from app.tools.network_policy import NetworkPolicyError
from app.tools.schema_instance import SchemaInstanceError, validate_schema_instance

# D2.7: ธรรมเนียม REST ทั่วไป ไม่ผูกกับ tool ใดตัวหนึ่ง — status code อื่นที่ไม่อยู่ในนี้
# (รวม 5xx และเครือข่ายล่ม) ยังคงยุบเป็น unavailable เหมือนเดิมเสมอ
_STATUS_ERROR_MAP: dict[int, tuple[ToolErrorCode, str]] = {
    400: (ToolErrorCode.INVALID_INPUT, "ข้อมูลนำเข้าไม่ถูกต้อง"),
    404: (ToolErrorCode.NOT_FOUND, "ไม่พบข้อมูลที่ร้องขอ"),
    409: (ToolErrorCode.CONFLICT, "มีข้อมูลที่ขัดแย้งกันอยู่แล้ว"),
}
_DEFAULT_UPSTREAM_ERROR = (ToolErrorCode.UNAVAILABLE, "บริการที่ร้องขอไม่พร้อมใช้งานชั่วคราว")
_GENERIC_PREPARED_SUMMARY = "เตรียมรายการที่ร้องขอไว้แล้ว กรุณายืนยันเพื่อดำเนินการต่อ"


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
        # D2.7: ฉบับร่างของ operation ที่ mode=prepare รอ submit — คีย์ด้วย idempotencyKey
        # เหมือน SimulatedTool เดิม (เช่น OmsTool._drafts) อยู่ในหน่วยความจำของ process นี้เท่านั้น
        self._drafts: dict[str, tuple[str, dict[str, Any]]] = {}

    @property
    def actions(self) -> frozenset[str]:
        """action ทั้งหมดที่ tool นี้รองรับ — ``ToolRegistry`` ใช้ตรวจสอบว่า call.action ถูกต้อง
        สำหรับ tool นอก TOOL_ACTIONS เดิม (รวม internal submit actions ด้วย)"""
        return frozenset(op.action for op in self._shape.operations)

    def reset(self) -> None:
        """ล้างฉบับร่างที่ยังไม่ submit เพื่อคืนสถานะเริ่มต้นสำหรับการรันเดโมใหม่"""
        self._drafts.clear()

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        del context
        operation = self._shape.operation(call.action)
        if operation is None:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ไม่รู้จัก action นี้")

        try:
            validate_schema_instance(operation.input_schema, call.input)
        except SchemaInstanceError:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ข้อมูลนำเข้าไม่ตรงกับ schema ของ action นี้")

        if operation.mode == "prepare":
            return self._prepare(call, operation)
        if operation.mode == "submit":
            return await self._submit(call, operation)
        return await self._call_http(call, operation, input=call.input)

    def _prepare(self, call: ToolCall, operation: ToolOperationShape) -> ToolResult:
        """เก็บ payload ไว้รอ submit โดยไม่ยิง HTTP เลย — ``write_confirm`` ต้องไม่มี side
        effect จริงก่อนผู้ใช้ยืนยัน (CONTRACTS-V2.md §3.1) เหมือน ``OmsTool`` เดิมทำ"""
        payload = dict(call.input)
        idempotency_key = payload.pop("idempotencyKey", None)
        if not isinstance(idempotency_key, str) or not idempotency_key:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ข้อมูลนำเข้าของ action เตรียมรายการต้องมี idempotencyKey")
        self._drafts[idempotency_key] = (call.action, payload)
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"summary": _GENERIC_PREPARED_SUMMARY},
            simulation=True,
        )

    async def _submit(self, call: ToolCall, operation: ToolOperationShape) -> ToolResult:
        """ยิง HTTP จริงครั้งเดียวโดยใช้ payload ที่ ``_prepare`` เก็บไว้ ไม่ใช่ input ของ
        submit เอง (มีแค่ ``pendingActionId``/``idempotencyKey`` ตามสัญญากลาง)"""
        prepare_operation = next(
            (op for op in self._shape.operations if op.submit_action == call.action), None
        )
        if prepare_operation is None or operation.http_method is None or operation.url_template is None:
            return self._error(call, ToolErrorCode.INTERNAL, "การตั้งค่า tool นี้มีปัญหา กรุณาติดต่อผู้ดูแลระบบ")

        idempotency_key = call.input.get("idempotencyKey")
        draft = self._drafts.get(idempotency_key) if isinstance(idempotency_key, str) else None
        if draft is None:
            return self._error(call, ToolErrorCode.NOT_FOUND, "ไม่พบรายการที่เตรียมไว้")
        draft_action, payload = draft
        if draft_action != prepare_operation.action:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ประเภทรายการไม่ตรงกัน")

        result = await self._call_http(call, operation, input=payload)
        if result.status is ToolResultStatus.SUCCESS:
            del self._drafts[idempotency_key]
        return result

    async def _call_http(self, call: ToolCall, operation: ToolOperationShape, *, input: dict[str, Any]) -> ToolResult:
        if operation.http_method is None or operation.url_template is None:
            return self._error(call, ToolErrorCode.INVALID_INPUT, "ไม่รู้จัก action นี้")

        try:
            request = build_declarative_http_request(
                http_method=operation.http_method,
                url_template=operation.url_template,
                input=input,
                auth=self._auth,
            )
        except UrlTemplateError:
            return self._error(call, ToolErrorCode.INTERNAL, "การตั้งค่า tool นี้มีปัญหา กรุณาติดต่อผู้ดูแลระบบ")

        try:
            response = await self._executor.execute(request)
        except (DeclarativeToolError, NetworkPolicyError):
            # ไม่แยกข้อความตามเหตุผล (SSRF บล็อก vs. ปลายทางล่ม) ตั้งใจ — ทั้งสองไม่ใช่สิ่งที่
            # ผู้ใช้/LLM แก้ได้ และการบอกเหตุผลนโยบายออกไปเป็นการรั่วข้อมูลที่ไม่จำเป็น
            code, message = _DEFAULT_UPSTREAM_ERROR
            return self._error(call, code, message)

        # ตรวจ status code ก่อนรูปร่าง body เสมอ — ปลายทางที่ตอบ error เป็น text/html หรือ
        # body ที่ไม่ใช่ JSON object (เช่น 404 ตัวเปล่า) ต้องยังแปลเป็น ToolErrorCode ที่ถูกต้อง
        # ไม่ใช่ถูกกลืนเป็น unavailable เพราะเช็ค dict ก่อน (จะทำให้ D2.7 ไม่มีผลกับปลายทางจริง
        # ที่ไม่ส่ง JSON กลับตอน error ซึ่งเป็นกรณีทั่วไป)
        if response.status_code >= 400:
            code, message = _STATUS_ERROR_MAP.get(response.status_code, _DEFAULT_UPSTREAM_ERROR)
            return self._error(call, code, message)
        if not isinstance(response.json_body, dict):
            code, message = _DEFAULT_UPSTREAM_ERROR
            return self._error(call, code, message)

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
