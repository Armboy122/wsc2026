"""ข้อผิดพลาด HTTP ที่ปลอดภัยสำหรับผู้ใช้และตัวจัดการข้อยกเว้นที่รองรับ Pydantic"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)


class SafeError(BaseModel):
    """เนื้อหาข้อผิดพลาดที่ปลอดภัยสำหรับผู้ใช้ซึ่งส่งกลับจากเส้นทางแพลตฟอร์ม"""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1)
    detail: str | None = None
    request_id: str | None = Field(default=None, serialization_alias="requestId")


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    from app.core.middleware import get_request_id

    logger.warning("validation_failed", extra=log_extra(errors=exc.errors()))
    body = SafeError(
        error="invalid_request",
        detail="คำขอไม่ผ่านการตรวจสอบตามสัญญา",
        request_id=get_request_id(),
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump(by_alias=True))


async def catchall_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.core.middleware import get_request_id

    logger.exception("unexpected_error", extra=log_extra(path=request.url.path))
    body = SafeError(
        error="internal_error",
        detail="เกิดข้อผิดพลาดที่ไม่คาดคิด กรุณาลองใหม่อีกครั้ง",
        request_id=get_request_id(),
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump(by_alias=True))


def register_exception_handlers(app: Any) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, catchall_exception_handler)
