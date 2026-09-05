"""เส้นทาง admin แบบบางที่สุด (D3.1, TASKS-3DAYS.md)

นโยบาย auth ทั้งหมดอยู่ที่ ``app/core/admin_auth.py`` — router นี้เรียกใช้เท่านั้น
ทุก endpoint ใต้ /api/v1/admin ต้อง ``Depends(require_admin)`` ห้ามมี endpoint admin ที่ข้าม auth

นโยบายการจัดการ tool (list/save/enable/try) อยู่ที่ ``app/core/tool_admin.py`` —
handler ที่นี่แปลง request/response เท่านั้น ตามข้อตกลง "keep HTTP routes thin"
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.contracts import (
    AdminLoginRequest,
    AdminOperationInput,
    AdminPromptInput,
    AdminToolDefinitionInput,
    AdminToolEnabledInput,
    AdminTryOperationInput,
)
from app.core import admin_auth
from app.core.admin_auth import ADMIN_SESSION_COOKIE, require_admin
from app.core.config import Settings
from app.core.errors import ConflictException
from app.core.logging import get_logger, log_extra
from app.core.prompt_admin import PromptAdminService, PromptValidationError
from app.core.tool_admin import ToolAdminService
from app.tools.declarative_validator import DeclarativeValidationError

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = get_logger(__name__)


@router.post("/login")
async def login(request: Request, body: AdminLoginRequest) -> JSONResponse:
    settings: Settings = request.app.state.settings
    if not settings.admin_password:
        logger.warning("admin_login_disabled", extra=log_extra(reason="not_configured"))
        # แยก 503 (admin ปิด) ออกจาก 401 (รหัสผ่านผิด) เพื่อไม่ให้เดาได้ว่ารหัสผ่านเป็นอะไร
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ปิดใช้งานหน้า admin: ยังไม่ได้ตั้งค่า ADMIN_PASSWORD",
        )
    if not admin_auth.verify_admin_password(settings.admin_password, body.password):
        logger.warning("admin_login_failed", extra=log_extra(reason="invalid_password"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสผ่าน admin ไม่ถูกต้อง",
        )
    logger.info("admin_login_succeeded", extra=log_extra())
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        admin_auth.admin_session_store.create(),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    # ไม่บังคับ auth — จุดประสงค์คือทำลาย session ของผู้เรียกเอง
    admin_auth.admin_session_store.revoke(request.cookies.get(ADMIN_SESSION_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return response


@router.get("/session")
async def session_status(_: Annotated[None, Depends(require_admin)]) -> dict[str, bool]:
    return {"authenticated": True}


# ---------------------------------------------------------------- D3.3/D3.4/D3.5 --


def _tool_admin(request: Request) -> ToolAdminService:
    return request.app.state.tool_admin


def _prompt_admin(request: Request) -> PromptAdminService:
    return request.app.state.prompt_admin


# ---------------------------------------------------------------------- D3.6 --


@router.get("/prompt")
async def get_prompt(
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[PromptAdminService, Depends(_prompt_admin)],
) -> JSONResponse:
    return JSONResponse(await service.get_prompt())


@router.put("/prompt")
async def save_prompt(
    body: AdminPromptInput,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[PromptAdminService, Depends(_prompt_admin)],
) -> JSONResponse:
    try:
        result = await service.save_prompt(body.content)
        logger.info("admin_prompt_saved", extra=log_extra(content_length=len(body.content)))
        return JSONResponse(result)
    except PromptValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/tools")
async def list_tools(
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    return JSONResponse(await service.list_tools())


@router.get("/tools/{slug}")
async def get_tool(
    slug: str,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    return JSONResponse(await service.get_tool(slug))


@router.post("/tools", status_code=status.HTTP_201_CREATED)
async def create_tool(
    body: AdminToolDefinitionInput,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    saved = await _save(service, body, update=False)
    return JSONResponse(saved, status_code=status.HTTP_201_CREATED)


@router.put("/tools/{slug}")
async def update_tool(
    slug: str,
    body: AdminToolDefinitionInput,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    if body.slug != slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slug ใน URL กับ slug ในเนื้อความต้องตรงกัน",
        )
    saved = await _save(service, body, update=True)
    return JSONResponse(saved)


@router.patch("/tools/{slug}/enabled")
async def set_tool_enabled(
    slug: str,
    body: AdminToolEnabledInput,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    await service.set_enabled(slug, body.enabled)
    return JSONResponse({"slug": slug, "enabled": body.enabled})


@router.post("/tools/try")
async def try_tool_operation(
    body: AdminTryOperationInput,
    _: Annotated[None, Depends(require_admin)],
    service: Annotated[ToolAdminService, Depends(_tool_admin)],
) -> JSONResponse:
    # ผลเป็น {ok: false, reason, error} เสมอเมื่อถูกปฏิเสธ — ไม่ใช่ HTTP error เพราะ
    # ฝั่ง UI ต้องแสดงเหตุผล (เช่น SSRF บล็อก) ตรงจุด ไม่ใช่ฟ้องว่า request พัง
    result = await service.try_operation(
        http_method=body.http_method,
        url_template=body.url_template,
        input=body.input,
        input_schema=body.input_schema,
        auth_env_var=body.auth_env_var,
        auth_header_name=body.auth_header_name,
        auth_scheme=body.auth_scheme,
    )
    logger.info(
        "admin_external_tool_try",
        extra=log_extra(ok=bool(result.get("ok")), reason=result.get("reason")),
    )
    return JSONResponse(result)


async def _save(
    service: ToolAdminService,
    body: AdminToolDefinitionInput,
    *,
    update: bool,
) -> dict[str, Any]:
    try:
        return await service.save_tool(
            body.model_dump(by_alias=True, exclude_unset=True),
            update=update,
            auth_env_var_provided="auth_env_var" in body.model_fields_set,
        )
    except DeclarativeValidationError as error:
        # ผิดตรงไหนบอกชัดตรงนั้น (D3.4) — ข้อความภาษาไทยจาก validator จุดเดียวกับ loader
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ConflictException as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail) from error
