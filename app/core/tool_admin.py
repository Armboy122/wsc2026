"""บริการจัดการ tool จากหน้า admin — D3.3/D3.4/D3.5 (TASKS-3DAYS.md)

นโยบายทั้งหมดของการสร้าง/แก้/ทดสอบ tool อยู่ที่นี่ route handler (``app/api/admin.py``)
เรียกใช้เท่านั้น จุดสำคัญที่ตรึงไว้:

- **validation จุดเดียวกับ loader** — definition ที่ save ผ่าน
  ``validate_declarative_tool_shape`` (app/tools/declarative_validator.py) เสมอ รวม
  schema subset (D1.2) และ network policy ตอน save (check_url, CONTRACTS-V2 §7.3) ผิด =
  ไม่ persist
- **hot reload** — save/เปิด-ปิดสำเร็จแล้วโหลด declarative tool ทั้งชุดใหม่จาก DB แล้ว
  แทนที่ใน ``ToolRegistry`` ทันที (D3.4 "save แล้วมีผลเลย") โดย tool ที่ definition ผิด
  fail closed เหมือนตอน startup (ไม่ dispatch ไม่เห็นในแค็ตตาล็อก)
- **ปุ่ม "ลองยิงดู" ไม่มีทางลัด** (D3.5) — ยิงผ่าน ``DeclarativeToolExecutor`` (D2.4) ตัวเดียว
  กับที่ declarative tool จริงใช้ นโยบายเครือข่ายขาออกทำงานครบทุกขั้น (resolve DNS เทียบ
  blocklist ก่อนยิง) เหตุผลการถูกบล็อกแสดงให้ admin เห็นได้เพราะ admin เป็นผู้ตั้งค่าเอง
  (ข้อห้ามรั่วของ CONTRACTS-V2 §9.4 ใช้กับผู้ใช้/LLM ไม่ใช่หน้า admin)
- **secret ปลอดภัย** — รับเฉพาะ *ชื่อ* environment variable ค่าจริงถูกอ่านตอน execute เท่านั้น
  และไม่เคยส่งกลับไปแสดงใน response ใด ๆ — response ของปุ่ม "ลองยิงดู" (D3.5) ถูก redact
  ค่า secret ทุกตำแหน่ง (รวม object/list/string ซ้อนกัน) ก่อนคืนเสมอ กันปลายทาง echo
  Authorization header กลับมา
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import httpx

from app.agent.declarative_tools import DeclarativeToolBundle, load_declarative_tools
from app.agent.operation_policy import OperationLimits, OperationSpec
from app.agent.registry import ToolRegistry
from app.agent.tool_shape import ToolOperationShape, ToolShape, from_plugin
from app.contracts import INPUT_MODELS, ToolAction, ToolName
from app.core.config import Settings
from app.core.errors import ConflictException, NotFoundException
from app.core.logging import get_logger, log_extra
from app.db import Database
from app.db import tool_repository
from app.plugins.loader import LoadedPlugin
from app.tools.declarative_executor import (
    DeclarativeToolAuth,
    DeclarativeToolError,
    DeclarativeToolExecutor,
)
from app.tools.declarative_request import UrlTemplateError, build_declarative_http_request
from app.tools.declarative_validator import (
    DeclarativeValidationError,
    validate_declarative_tool_shape,
)
from app.tools.network_policy import NetworkPolicyError, check_url
from app.tools.schema_instance import SchemaInstanceError, validate_schema_instance
from app.tools.schema_subset import SchemaSubsetError, validate_schema_subset

# slug ปลอมของ "ลองยิงดู" — ไม่ลง registry ไม่ถูก dispatch เป็น tool จริง
_TRY_TOOL_SLUG = "admin_try"

# token แทนที่ตำแหน่งของ secret ใน response ของปุ่ม "ลองยิงดู" (D3.5 hardening)
_REDACTED = "[REDACTED]"
logger = get_logger(__name__)

# P1: header name และ scheme ต้องเป็น HTTP token เท่านั้น (RFC 9110) — กัน header
# injection ผ่านช่องตั้งค่า (เช่น CRLF หรือช่องว่าง) ก่อนค่าไปถึง executor
_HTTP_TOKEN_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")


def _validate_auth_header(header_name: str | None, scheme: str | None) -> None:
    """ตรวจรูปแบบ header name/scheme — ผิด = DeclarativeValidationError (400 ที่ route)"""
    if header_name is not None and not _HTTP_TOKEN_RE.fullmatch(header_name):
        raise DeclarativeValidationError(
            "ชื่อ header ไม่ถูกต้อง — ต้องเป็นชื่อ HTTP header เช่น Authorization หรือ X-API-Key"
        )
    if scheme is not None and scheme != "" and not _HTTP_TOKEN_RE.fullmatch(scheme):
        raise DeclarativeValidationError(
            'scheme ไม่ถูกต้อง — ใช้คำเดียวเช่น Bearer หรือเว้นว่างเพื่อส่งค่าตรง ๆ'
        )


class ToolAdminService:
    """สถานะ + นโยบายของหน้า admin: รายการ tool · save · เปิด-ปิด · ลองยิง"""

    def __init__(
        self,
        db: Database,
        *,
        settings: Settings,
        registry: ToolRegistry,
        plugins: Iterable[LoadedPlugin] = (),
        extra_code_shapes: Iterable[ToolShape] = (),
        transport: httpx.BaseTransport | None = None,
        initial_bundle: DeclarativeToolBundle | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._registry = registry
        self._plugin_shapes = (
            *(from_plugin(loaded) for loaded in plugins),
            *extra_code_shapes,
        )
        # T6: รายการต้องครบทุก code tool ที่อยู่ใน registry จริง — ตัวที่ไม่ได้มาจาก
        # ``plugins`` (เช่น KnowledgeTool built-in) ประกอบ shape จากข้อมูลจริงของ registry
        # (``full_catalogue`` + ``operation_specs``) โดยไม่สร้าง source of truth ซ้ำ
        # ใช้ full_catalogue เพราะ llm_catalogue กรอง tool ที่ถูกปิดออกแล้ว (P4)
        self._registry_code_shapes = _code_shapes_from_registry(
            registry, exclude=frozenset(shape.slug for shape in self._plugin_shapes)
        )
        # ขอบเขต "tool จากโค้ด" สำหรับกัน get_tool (แก้ definition) และกำหนดกลุ่มที่
        # เปิด/ปิดผ่านสถานะ code ได้ (P4): ทุก code tool ใน registry รวม KnowledgeTool +
        # ทุก shape ที่มาจาก plugins/extra (กัน slug ที่ยังไม่ลง registry)
        self._code_tool_slugs = (
            frozenset(registry.code_tool_names)
            | frozenset(shape.slug for shape in self._plugin_shapes)
            | frozenset(shape.slug for shape in self._registry_code_shapes)
        )
        self._transport = transport
        # main.py โหลด bundle แรกมาแล้วตอน startup — รับมาเก็บเพื่อไม่ต้องโหลดซ้ำ
        self._bundle = initial_bundle or DeclarativeToolBundle(
            tools=(), catalogue=(), operation_specs={}
        )

    async def list_tools(self) -> dict[str, Any]:
        """รายการ tool ทั้งสองชั้นในหน้าเดียว (D3.3)

        - code tool ทุกตัวที่อยู่ใน registry จริง (ปลั๊กอิน Python + built-in เช่น
          KnowledgeTool) — อยู่รายการเดียวกันแต่ **แก้ไม่ได้** เปิด/ปิดได้ยกเว้น
          knowledge ที่เป็น guard ของระบบ (P4)
        - declarative tool (source: db) ทุกแถวรวมที่ปิดอยู่
        - tool ที่ปิดตัวเอง (definition ผิด fail closed) แสดงพร้อมเหตุผล กัน "หายเงียบ"
        """
        disabled_reasons = {item.slug: item.reason for item in self._bundle.disabled}
        tools: list[dict[str, Any]] = []
        for shape in (*self._plugin_shapes, *self._registry_code_shapes):
            tools.append(
                {
                    **_shape_to_definition(shape),
                    "enabled": self._registry.code_tool_enabled(shape.slug),
                    "hasAuth": False,
                    "editable": False,
                    "toggleDisabledReason": _toggle_disabled_reason(shape.slug),
                    "selfDisabledReason": None,
                }
            )
        for definition in await tool_repository.list_tool_definitions(self._db):
            tools.append(
                {
                    **definition,
                    "editable": True,
                    "toggleDisabledReason": None,
                    "selfDisabledReason": disabled_reasons.get(definition["slug"]),
                }
            )
        return {"appEnv": self._settings.app_env, "tools": tools}

    async def get_tool(self, slug: str) -> dict[str, Any]:
        """definition ของ declarative tool หนึ่งตัวสำหรับฟอร์มแก้ไข (D3.4)

        ไม่คืน ``authEnvVar`` ย้อนกลับ — เขียนได้อย่างเดียว (CONTRACTS-V2 §10.2:
        secret_ref ห้ามปรากฏใน response)
        """
        if slug in self._code_tool_slugs:
            raise NotFoundException(
                detail="tool จากโค้ด (Python) แก้ไขจากหน้าเว็บไม่ได้ — แก้ที่โค้ดแล้ว deploy แทน"
            )
        definition = await tool_repository.get_tool_definition(self._db, slug)
        if definition is None:
            raise NotFoundException(detail="ไม่พบ tool ที่ร้องขอ")
        return definition

    async def save_tool(
        self,
        definition: dict[str, Any],
        *,
        update: bool,
        auth_env_var_provided: bool | None = None,
    ) -> dict[str, Any]:
        """validate → persist → hot reload (D3.4) — คืน definition ที่บันทึกแล้ว

        ``update=True`` ต้องมี tool เดิมอยู่ก่อน (แก้ไข) · ``update=False`` ต้องไม่มี
        (สร้างใหม่) — ทั้งสองกรณี slug ที่ชนกับปลั๊กอิน Python = conflict
        """
        shape, enabled, auth_env_var = _shape_from_definition(definition)
        auth_header_name = definition.get("authHeaderName")
        auth_scheme = definition.get("authScheme")
        auth_header_provided = "authHeaderName" in definition or "authScheme" in definition
        _validate_auth_header(auth_header_name, auth_scheme)
        if auth_env_var_provided is None:
            auth_env_var_provided = "authEnvVar" in definition
        if update:
            existing = await tool_repository.get_tool_definition(self._db, shape.slug)
            if existing is None:
                raise NotFoundException(detail="ไม่พบ tool ที่ร้องขอ")
        elif shape.slug in self._registry.names or await tool_repository.get_tool_definition(
            self._db, shape.slug
        ):
            raise ConflictException(detail=f"มี tool ชื่อ '{shape.slug}' อยู่แล้ว")

        # validation ก่อน persist เสมอ — ผิด = ไม่แตะ DB (CONTRACTS-V2 §2.3)
        validate_declarative_tool_shape(
            shape,
            app_env=self._settings.app_env,
            allowlist=await self._allowlist(),
        )
        await tool_repository.save_tool(
            self._db,
            shape,
            enabled=enabled,
            auth_env_var=auth_env_var,
            preserve_auth=update and not auth_env_var_provided,
            auth_header_name=auth_header_name,
            auth_scheme=auth_scheme,
            auth_header_provided=auth_header_provided,
        )
        await self.reload()
        saved = await tool_repository.get_tool_definition(self._db, shape.slug)
        assert saved is not None  # เขียนสำเร็จแล้วต้องอ่านกลับได้
        logger.info(
            "admin_tool_saved",
            extra=log_extra(
                slug=shape.slug,
                operation_count=len(shape.operations),
                update=update,
                enabled=enabled,
                has_auth=bool(saved.get("hasAuth")),
            ),
        )
        return saved

    async def set_enabled(self, slug: str, enabled: bool) -> None:
        if slug in self._code_tool_slugs:
            # P4: code tool เปิด/ปิดจากหน้าเว็บได้แล้ว — แต่ registry ต้อง validate
            # ก่อนแตะ DB เสมอ (guard ของ knowledge + สถานะ in-memory ต้องตรงกับ DB)
            try:
                self._registry.validate_code_tool_enabled(slug, enabled)
            except ValueError as error:
                raise ConflictException(detail=str(error)) from error
            try:
                await tool_repository.set_code_tool_enabled(self._db, slug, enabled)
            except ValueError as error:
                raise ConflictException(detail=str(error)) from error
            # Persist first so a DB failure cannot leave the running registry ahead of
            # durable state. The validation above makes this final in-memory update
            # non-throwing for the current single-process registry.
            self._registry.set_code_tool_enabled(slug, enabled)
            logger.info(
                "admin_tool_enabled_changed", extra=log_extra(slug=slug, enabled=enabled, source="code")
            )
            return
        if not await tool_repository.set_tool_enabled(self._db, slug, enabled):
            raise NotFoundException(detail="ไม่พบ tool ที่ร้องขอ")
        await self.reload()
        logger.info("admin_tool_enabled_changed", extra=log_extra(slug=slug, enabled=enabled))

    async def reload(self) -> None:
        """โหลด declarative tool จาก DB ทั้งชุดใหม่แล้วแทนที่ใน registry ทันที

        tool ที่ definition ผิด fail closed เหมือนตอน startup (ถูกข้าม + บันทึกเหตุผลไว้
        แสดงในหน้ารายการ) เพื่อไม่ให้แถวที่เสียทำให้ระบบทั้งระบบล้ม
        """
        bundle = await load_declarative_tools(
            self._db,
            app_env=self._settings.app_env,
            allowlist=await self._allowlist(),
            transport=self._transport,
        )
        self._registry.replace_declarative_tools(
            bundle.tools, bundle.catalogue, bundle.operation_specs
        )
        self._bundle = bundle

    async def try_operation(
        self,
        *,
        http_method: str,
        url_template: str,
        input: dict[str, Any],
        input_schema: dict[str, Any] | None = None,
        tool_slug: str | None = None,
        auth_env_var: str | None = None,
        auth_env_var_provided: bool | None = None,
        auth_header_name: str | None = None,
        auth_scheme: str | None = None,
    ) -> dict[str, Any]:
        """ปุ่ม "ลองยิงดู" (D3.5) — ยิงจริงผ่าน executor กลาง (D2.4) ไม่มีทางลัด

        ผ่านชั้นเดียวกับ declarative tool จริงทุกขั้น: validate URL/นโยบาย → resolve DNS
        เทียบ blocklist → ยิง → เพดาน timeout/ขนาด response ผลรวมถึงตัวเหตุผลการบล็อก
        (เช่น ``169.254.169.254``) แสดงให้ admin เห็นพร้อมเหตุผล

        A1: รองรับการใช้ credential ที่บันทึกไว้ใน DB สำหรับ tool เดิม:
        - tool_slug ระบุ + auth_env_var ไม่ส่ง = preserve credential เดิมฝั่ง server
        - tool_slug ระบุ + auth_env_var เป็น string = replace ด้วยตัวแปรใหม่สำหรับการลอง
        - tool_slug ระบุ + auth_env_var เป็น None (ส่งมาจริง) = remove credential (ลองโดยไม่ส่ง auth)
        - เปลี่ยน header/scheme แต่คง credential = ใช้ค่าที่แก้ในฟอร์มคู่กับ secret เดิม
        - unknown tool_slug = คืน not_found ปลอดภัย ไม่ fallback
        - การลองยิงไม่ persist การแก้ลง DB

        D3.5 (hardening): ก่อนคืนผลทุกเส้นทาง (response สำเร็จหรือ error) ค่าจริงของ secret
        ที่อ่านจาก effective auth_env_var จะถูกแทนที่ด้วย ``[REDACTED]`` ทุกตำแหน่งที่พบ — รวม
        object/list/string ซ้อนกันและรูปแบบ ``Bearer <secret>`` — เพราะปลายทางอาจ echo
        Authorization header กลับมาใน body ทำให้ secret ปรากฏในหน้า admin ได้

        response ที่ไม่ใช่ JSON แสดงเป็นข้อความแบบจำกัดขนาด (truncate ที่ 2000 อักขระ
        พร้อม flag ``textTruncated``) — **truncate หลัง redact เสมอ** เพราะถ้าตัดก่อน
        secret ที่อยู่คร่อมจุดตัดจะเหลือเฉพาะบางส่วนจน redaction จับไม่เจอ
        """
        if auth_env_var_provided is None:
            auth_env_var_provided = auth_env_var is not None

        effective_auth_env_var: str | None = None
        effective_header_name: str | None = auth_header_name
        effective_scheme: str | None = auth_scheme

        if tool_slug is not None:
            saved_auth = await tool_repository.get_tool_auth(self._db, tool_slug)
            if saved_auth is None:
                return _try_error("not_found", "ไม่พบ tool ที่ร้องขอ")
            if auth_env_var_provided and auth_env_var is None:
                # เลือกลบ credential -> ลองโดยไม่ส่ง auth
                effective_auth_env_var = None
                effective_header_name = None
                effective_scheme = None
            elif auth_env_var:
                # ระบุชื่อ env var ใหม่ -> ใช้ credential ใหม่สำหรับการลอง
                effective_auth_env_var = auth_env_var
                effective_header_name = auth_header_name if auth_header_name else "Authorization"
                effective_scheme = auth_scheme if auth_scheme is not None else "Bearer"
            elif saved_auth["hasAuth"]:
                # ไม่เปลี่ยน credential -> ใช้ credential เดิมฝั่ง server
                effective_auth_env_var = saved_auth["secretRef"]
                effective_header_name = (
                    auth_header_name
                    if auth_header_name
                    else (saved_auth["headerName"] or "Authorization")
                )
                effective_scheme = (
                    auth_scheme
                    if auth_scheme is not None
                    else (
                        saved_auth["scheme"]
                        if saved_auth["scheme"] is not None
                        else "Bearer"
                    )
                )
            else:
                effective_auth_env_var = None
                effective_header_name = None
                effective_scheme = None
        else:
            if auth_env_var:
                effective_auth_env_var = auth_env_var
                effective_header_name = auth_header_name if auth_header_name else "Authorization"
                effective_scheme = auth_scheme if auth_scheme is not None else "Bearer"
            else:
                effective_auth_env_var = None
                effective_header_name = None
                effective_scheme = None

        secret_variants = _secret_variants(
            effective_auth_env_var,
            scheme=effective_scheme if effective_scheme is not None else "Bearer",
        )
        # P1: ตรวจรูปแบบ header/scheme ที่นี่ (ขั้นนอก) เพื่อคืน ok:false แทน HTTP 500
        if effective_auth_env_var:
            try:
                _validate_auth_header(
                    effective_header_name if effective_header_name else "Authorization",
                    effective_scheme if effective_scheme is not None else "Bearer",
                )
            except DeclarativeValidationError as error:
                return _try_error("invalid_input", str(error))
        result = await self._try_operation_raw(
            http_method=http_method,
            url_template=url_template,
            input=input,
            input_schema=input_schema,
            auth_env_var=effective_auth_env_var,
            auth_header_name=effective_header_name,
            auth_scheme=effective_scheme,
        )
        if secret_variants:
            result = _redact_secrets(result, secret_variants)
        if result.get("ok"):
            response = result.get("response") or {}
            text = response.get("text")
            if isinstance(text, str) and len(text) > 2000:
                response["text"] = text[:2000]
                response["textTruncated"] = True
        return result

    async def _try_operation_raw(
        self,
        *,
        http_method: str,
        url_template: str,
        input: dict[str, Any],
        input_schema: dict[str, Any] | None,
        auth_env_var: str | None,
        auth_header_name: str | None = None,
        auth_scheme: str | None = None,
    ) -> dict[str, Any]:
        """ยิงจริงโดยไม่แตะ response — เรียกจาก ``try_operation`` เท่านั้น (redaction อยู่ที่นั่น)"""
        allowlist = await self._allowlist()
        if input_schema is not None:
            # inputSchema ที่ยังไม่เคย save = untrusted — ตรวจ allowlist ก่อนใช้เทียบ input
            try:
                validate_schema_subset(input_schema)
            except SchemaSubsetError as error:
                return _try_error("invalid_schema", str(error))
            try:
                validate_schema_instance(input_schema, input)
            except SchemaInstanceError as error:
                return _try_error("invalid_input", str(error))

        # ตรวจ URL ก่อนแบบเปิดเหตุผล (check_url คือขั้นเดียวกับที่ executor ทำภายใน) —
        # validator ที่เรียกต่อด้านล่างห่อ NetworkPolicyError เป็นข้อความรวม ทำให้ reason หาย
        try:
            check_url(url_template, app_env=self._settings.app_env, allowlist=allowlist)
        except NetworkPolicyError as error:
            return _try_error(error.reason, error.message)

        operation = ToolOperationShape(
            action="try",
            description="",
            input_schema=input_schema
            if input_schema is not None
            else {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            output_schema=None,
            exposure="internal",
            mode="read",
            submit_action=None,
            policy="plain_read",
            limits=None,
            client_context=None,
            http_method=http_method,
            url_template=url_template,
        )
        shape = ToolShape(
            slug=_TRY_TOOL_SLUG,
            display_name="ลองยิงดู",
            description="",
            operations=(operation,),
            executor=None,
            source="db",
        )
        try:
            # ตรวจ URL/HTTPS/allowlist เหมือนตอน save และเหมือนตอน executor ยิงจริง
            validate_declarative_tool_shape(
                shape, app_env=self._settings.app_env, allowlist=allowlist
            )
        except DeclarativeValidationError as error:
            return _try_error("policy_rejected", str(error))

        if auth_env_var:
            auth = DeclarativeToolAuth(
                env_var=auth_env_var,
                header_name=auth_header_name if auth_header_name else "Authorization",
                scheme=auth_scheme if auth_scheme is not None else "Bearer",
            )
        else:
            auth = None
        try:
            request = build_declarative_http_request(
                http_method=http_method,
                url_template=url_template,
                input=input,
                auth=auth,
            )
        except UrlTemplateError as error:
            return _try_error("invalid_input", str(error))

        executor = DeclarativeToolExecutor(
            app_env=self._settings.app_env,
            allowlist=allowlist,
            transport=self._transport,
        )
        try:
            response = await executor.execute(request)
        except NetworkPolicyError as error:
            # admin เป็นผู้ตั้งค่า URL เอง จึงแสดงเหตุผลนโยบายให้แก้ได้ (D3.5/D1.3)
            return _try_error(error.reason, error.message)
        except DeclarativeToolError as error:
            return _try_error(error.reason, error.message)

        return {
            "ok": True,
            "request": {
                "method": request.method,
                "url": request.url,
                "query": dict(request.query),
                # JSON request body เฉพาะ method ที่มี body (POST/PUT/PATCH) — GET/DELETE เป็น None
                # แสดงให้ admin เห็นว่ายิงอะไรไปจริง (redact ที่ try_operation ก่อนคืนเสมอ)
                "body": request.json_body,
            },
            "response": {
                "statusCode": response.status_code,
                "elapsedMs": round(response.elapsed_seconds * 1000, 1),
                # แสดงเฉพาะ JSON — response รูปแบบอื่นคืน null พร้อม flag
                "body": response.json_body,
                "isJson": response.json_body is not None,
                # response ที่ไม่ใช่ JSON: ข้อความดิบจาก executor (truncate ที่ try_operation
                # หลัง redact เสมอ — ดู docstring ของ try_operation)
                "text": response.text_body,
            },
        }

    async def _allowlist(self) -> tuple[str, ...]:
        rows = await self._db.fetch_all(
            "SELECT domain FROM domain_allowlist WHERE enabled = 1"
        )
        return tuple(row["domain"] for row in rows)


def _try_error(reason: str, message: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "error": message}


def _toggle_disabled_reason(slug: str) -> str | None:
    """เหตุผลที่ห้ามเปิด/ปิด code tool ตัวนี้จากหน้าเว็บ — None = เปิด/ปิดได้ (P4)

    knowledge เป็น built-in ที่ระบบบังคับว่าต้องมีเสมอ (ToolRegistry ยอมรับ registry
    ที่ไม่มีอย่างอื่น แต่ห้ามไม่มี knowledge) การปิดจึงทำให้เส้นทางหลักใช้งานไม่ได้
    จึงกันไว้ที่ server ตั้งแต่ registry.set_code_tool_enabled ไม่ให้แค่เตือนบน UI
    """
    if slug == ToolName.KNOWLEDGE.value:
        return (
            "ปิดเครื่องมือความรู้ (knowledge) ไม่ได้ — เป็นเส้นทางหลัก"
            "ที่ระบบต้องใช้เสมอ"
        )
    return None


def _secret_variants(auth_env_var: str | None, *, scheme: str = "Bearer") -> tuple[str, ...]:
    """ค่าจริงของ secret ทุกรูปแบบที่อาจปรากฏใน response — เพื่อนำไปแทนที่ด้วย [REDACTED]

    อ่านค่าจาก environment variable ตัวเดียวกับที่ executor ใช้ตอนยิงจริง (D2.4 ฉีด header
    ``<scheme> <secret>``) ครอบคลุมค่าดิบ (scheme ว่าง = ส่งค่าตรง ๆ กรณี X-API-Key),
    รูปแบบ ``<scheme> <secret>`` และรูปแบบ URL-encoded — เก็บไว้ใช้แทนที่ในหน่วยความจำ
    เท่านั้น ห้าม log หรือส่งกลับใน response/error
    """
    if not auth_env_var:
        return ()
    secret = os.environ.get(auth_env_var, "")
    if not secret:
        return ()
    variants = (
        secret,
        f"{scheme} {secret}".strip(),
        quote(secret, safe=""),
    )
    return tuple(dict.fromkeys(variant for variant in variants if variant))


def _redact_secrets(value: Any, secrets: tuple[str, ...]) -> Any:
    """แทนที่ค่า secret ทุกตำแหน่งในโครงสร้างข้อมูล (object/list/string ซ้อนกัน) ด้วย [REDACTED]"""
    if not secrets:
        return value
    if isinstance(value, dict):
        return {key: _redact_secrets(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secrets(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        # แทนที่รูปแบบที่ยาวที่สุดก่อน (เช่น "Bearer <secret>") กันการแยกส่วนที่ไม่จำเป็น
        for variant in sorted(set(secrets), key=len, reverse=True):
            redacted = redacted.replace(variant, _REDACTED)
        return redacted
    return value


def _code_shapes_from_registry(
    registry: ToolRegistry, *, exclude: frozenset[str]
) -> tuple[ToolShape, ...]:
    """ประกอบ shape ของ code tool ที่อยู่ใน registry จริงแต่ไม่มาจาก ``plugins`` (T6)

    ใช้เฉพาะข้อมูลที่ registry รู้จริง: ``full_catalogue`` (slug/description/action) และ
    ``operation_specs`` (policy/mode/exposure/limits/clientContext) ส่วนที่ registry ไม่มี
    จะสะท้อนความจริงตรง ๆ (คำอธิบายต่อ operation เป็นค่าว่างเหมือน ``from_db_row``)
    ไม่กุข้อมูลปลอมขึ้นมาแทน
    """
    shapes: list[ToolShape] = []
    excluded: set[str] = set(exclude)
    for definition in registry.full_catalogue:
        slug = definition.name
        if slug in excluded or slug not in registry.code_tool_names:
            continue
        excluded.add(slug)
        shapes.append(
            ToolShape(
                slug=slug,
                # registry ไม่มี display name แยกต่างหาก — ใช้ slug ตามความจริง
                display_name=slug,
                description=definition.description,
                operations=tuple(
                    _code_operation_shape(slug, action, registry.operation_specs)
                    for action in definition.actions
                ),
                executor=None,
                source="code",
            )
        )
    return tuple(shapes)


def _code_operation_shape(
    slug: str,
    action: str,
    operation_specs: Mapping[tuple[str, str], OperationSpec],
) -> ToolOperationShape:
    """หนึ่ง operation ของ code tool จากข้อมูลจริงของ registry

    policy ที่ไม่ได้ประกาศ = ค่าเริ่มต้น plain_read ตาม ``OperationSpec`` (fail safe
    เหมือนที่ dispatch ใช้) — inputSchema derive จากสัญญากลาง INPUT_MODELS เมื่อมี
    (เช่น knowledge.search) ไม่มี = None ตามจริง
    """
    spec = operation_specs.get((slug, action)) or OperationSpec()
    return ToolOperationShape(
        action=action,
        # registry ไม่เก็บคำอธิบายต่อ operation — แสดงเป็นค่าว่างตามจริง
        description="",
        input_schema=_code_input_schema(action),
        output_schema=None,
        exposure=spec.exposure,
        mode=spec.mode,
        submit_action=spec.submit_action,
        policy=spec.policy.value,
        limits=_operation_limits_to_dict(spec.limits),
        client_context=dict(spec.client_context) if spec.client_context else None,
        http_method=None,
        url_template=None,
    )


def _code_input_schema(action: str) -> dict[str, Any] | None:
    """schema ขาเข้าจริงของ action — derive จากสัญญากลาง INPUT_MODELS เช่นเดียวกับ
    ``tool_catalogue`` (app/llm/prompting.py); action ที่ไม่มีสัญญา Pydantic คืน None"""
    tool_action = next((item for item in ToolAction if item.value == action), None)
    if tool_action is None or tool_action not in INPUT_MODELS:
        return None
    return INPUT_MODELS[tool_action].model_json_schema(by_alias=True, mode="validation")


def _operation_limits_to_dict(limits: OperationLimits | None) -> dict[str, Any] | None:
    """รูปเดียวกับที่ ``from_plugin`` ใช้กับ limits ของปลั๊กอิน"""
    if limits is None:
        return None
    return {
        "maxCallsPerTurn": limits.max_calls_per_turn,
        "dedupeIdenticalInput": limits.dedupe_identical_input,
    }


def _shape_to_definition(shape: ToolShape) -> dict[str, Any]:
    """ToolShape (ปลั๊กอิน Python) → definition รูปเดียวกับที่ repository คืน"""
    return {
        "slug": shape.slug,
        "displayName": shape.display_name,
        "description": shape.description,
        "source": shape.source,
        "operations": [
            {
                "action": op.action,
                "description": op.description,
                "policy": op.policy,
                "exposure": op.exposure,
                "mode": op.mode,
                "submitAction": op.submit_action,
                "httpMethod": op.http_method,
                "urlTemplate": op.url_template,
                "inputSchema": op.input_schema,
                "outputSchema": op.output_schema,
                "limits": op.limits,
                "clientContext": op.client_context,
            }
            for op in shape.operations
        ],
    }


def _shape_from_definition(
    definition: dict[str, Any],
) -> tuple[ToolShape, bool, str | None]:
    """definition จาก request → (ToolShape, enabled, authEnvVar)

    รับ dict ที่ผ่าน Pydantic model ของ admin API มาแล้ว (รูป camelCase)
    """
    operations = tuple(
        ToolOperationShape(
            action=op["action"],
            description=op.get("description") or "",
            input_schema=op["inputSchema"],
            output_schema=op.get("outputSchema"),
            exposure=op.get("exposure") or "llm",
            mode=op.get("mode") or "read",
            submit_action=op.get("submitAction"),
            policy=op.get("policy") or "plain_read",
            limits=op.get("limits"),
            client_context=op.get("clientContext"),
            http_method=op.get("httpMethod"),
            url_template=op.get("urlTemplate"),
        )
        for op in definition["operations"]
    )
    shape = ToolShape(
        slug=definition["slug"],
        display_name=definition["displayName"],
        description=definition.get("description") or "",
        operations=operations,
        executor=None,
        source="db",
    )
    return shape, bool(definition.get("enabled", True)), definition.get("authEnvVar")
