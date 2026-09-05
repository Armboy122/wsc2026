"""เส้นทาง admin แบบบางที่สุด (D3.1, TASKS-3DAYS.md)

นโยบาย auth ทั้งหมดอยู่ที่ ``app/core/admin_auth.py`` — router นี้เรียกใช้เท่านั้น
D3.1 สร้างเฉพาะตัว auth; endpoint จัดการ tool/prompt (D3.3/D3.4/D3.6) ต้องใส่
``Depends(require_admin)`` ทุกตัว ห้ามมี endpoint admin ที่ข้าม auth
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core import admin_auth
from app.core.admin_auth import ADMIN_SESSION_COOKIE, require_admin
from app.core.config import Settings

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(request: Request, body: AdminLoginRequest) -> JSONResponse:
    settings: Settings = request.app.state.settings
    if not settings.admin_password:
        # แยก 503 (admin ปิด) ออกจาก 401 (รหัสผ่านผิด) เพื่อไม่ให้เดาได้ว่ารหัสผ่านเป็นอะไร
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ปิดใช้งานหน้า admin: ยังไม่ได้ตั้งค่า ADMIN_PASSWORD",
        )
    if not admin_auth.verify_admin_password(settings.admin_password, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสผ่าน admin ไม่ถูกต้อง",
        )
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
