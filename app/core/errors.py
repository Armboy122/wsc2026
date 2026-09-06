"""ข้อผิดพลาด HTTP ที่ปลอดภัยสำหรับผู้ใช้และตัวจัดการข้อยกเว้นที่รองรับ Pydantic"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request, status
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)


class SafeError(BaseModel):
    """เนื้อหาข้อผิดพลาดที่ปลอดภัยสำหรับผู้ใช้ซึ่งส่งกลับจากเส้นทางแพลตฟอร์ม"""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1)
    detail: str | None = None
    request_id: str | None = Field(default=None, serialization_alias="requestId")


class PublicErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INTERNAL = "internal"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"


class PublicError(BaseModel):
    """Closed public API error envelope; never contains internal diagnostics."""

    model_config = ConfigDict(extra="forbid")

    code: PublicErrorCode
    message: str = Field(min_length=1, max_length=500)
    trace_id: UUID = Field(serialization_alias="traceId")


class PublicErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: PublicError


class PlatformException(Exception):
    """คลาสพื้นฐานสำหรับข้อผิดพลาด HTTP ที่ตั้งใจให้เกิดภายในตัวจัดการ"""

    def __init__(
        self,
        status_code: int,
        error: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.detail = detail


class PublicApiException(PlatformException):
    """An intentionally safe error raised at the public API boundary."""

    def __init__(
        self,
        status_code: int,
        code: PublicErrorCode | str,
        message: str,
        trace_id: UUID | None = None,
    ) -> None:
        closed_code = PublicErrorCode(code)
        super().__init__(status_code, closed_code.value, message)
        self.code = closed_code
        self.message = message
        self.trace_id = trace_id or uuid4()


class NotFoundException(PlatformException):
    def __init__(self, error: str = "not_found", detail: str | None = None) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, error, detail)


class ConflictException(PlatformException):
    def __init__(self, error: str = "conflict", detail: str | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, error, detail)


class BadGatewayException(PlatformException):
    def __init__(self, error: str = "bad_gateway", detail: str | None = None) -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, error, detail)


def _build_safe_response(exc: PlatformException, request_id: str | None) -> JSONResponse:
    body = SafeError(error=exc.error, detail=exc.detail, request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(by_alias=True))


async def platform_exception_handler(request: Request, exc: PlatformException) -> JSONResponse:
    from app.core.middleware import get_request_id

    if isinstance(exc, PublicApiException) or _is_public_api_request(request):
        trace_id = exc.trace_id if isinstance(exc, PublicApiException) else uuid4()
        logger.warning(
            "public_api_request_failed",
            extra=log_extra(trace_id=str(trace_id), status_code=exc.status_code),
        )
        return _public_error_response(
            status_code=exc.status_code,
            code=(
                exc.code
                if isinstance(exc, PublicApiException)
                else _public_code(exc.status_code)
            ),
            message=(
                exc.message
                if isinstance(exc, PublicApiException)
                else _public_message(exc.status_code)
            ),
            trace_id=trace_id,
        )
    return _build_safe_response(exc, get_request_id())


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    from app.core.middleware import get_request_id

    safe_errors = [{"type": item.get("type")} for item in exc.errors()]
    if _is_public_api_request(request):
        trace_id = uuid4()
        logger.warning(
            "validation_failed",
            extra=log_extra(errors=safe_errors, trace_id=str(trace_id)),
        )
        return _public_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=PublicErrorCode.INVALID_INPUT,
            message="คำขอไม่ผ่านการตรวจสอบตามสัญญา",
            trace_id=trace_id,
        )
    logger.warning("validation_failed", extra=log_extra(errors=safe_errors))
    body = SafeError(
        error="invalid_request",
        detail="คำขอไม่ผ่านการตรวจสอบตามสัญญา",
        request_id=get_request_id(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body.model_dump(by_alias=True),
    )


async def catchall_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.core.middleware import get_request_id

    is_public_api = _is_public_api_request(request)
    if is_public_api or _is_web_operational_request(request):
        trace_id = uuid4()
        # Do not attach exc_info: provider exceptions can contain credentials or URLs.
        logger.error(
            "unexpected_operational_api_error",
            extra=log_extra(
                path=request.url.path,
                trace_id=str(trace_id),
                exception_type=type(exc).__name__,
            ),
        )
    else:
        logger.exception("unexpected_error", extra=log_extra(path=request.url.path))
    if is_public_api:
        return _public_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=PublicErrorCode.INTERNAL,
            message="เกิดข้อผิดพลาดที่ไม่คาดคิด กรุณาลองใหม่อีกครั้ง",
            trace_id=trace_id,
        )
    body = SafeError(
        error="internal_error",
        detail="เกิดข้อผิดพลาดที่ไม่คาดคิด กรุณาลองใหม่อีกครั้ง",
        request_id=get_request_id(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(by_alias=True),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if not _is_public_api_request(request):
        return await fastapi_http_exception_handler(request, exc)
    trace_id = uuid4()
    logger.warning(
        "public_api_http_error",
        extra=log_extra(trace_id=str(trace_id), status_code=exc.status_code),
    )
    return _public_error_response(
        status_code=exc.status_code,
        code=_public_code(exc.status_code),
        message=_public_message(exc.status_code),
        trace_id=trace_id,
    )


def register_exception_handlers(app: Any) -> None:
    app.add_exception_handler(PlatformException, platform_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, catchall_exception_handler)


def _public_error_response(
    *,
    status_code: int,
    code: PublicErrorCode,
    message: str,
    trace_id: UUID,
) -> JSONResponse:
    body = PublicErrorResponse(
        error=PublicError(code=code, message=message, trace_id=trace_id)
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", by_alias=True),
    )


def _public_code(status_code: int) -> PublicErrorCode:
    if status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    }:
        return PublicErrorCode.INVALID_INPUT
    if status_code == status.HTTP_404_NOT_FOUND:
        return PublicErrorCode.NOT_FOUND
    if status_code == status.HTTP_409_CONFLICT:
        return PublicErrorCode.CONFLICT
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return PublicErrorCode.RATE_LIMITED
    if status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        return PublicErrorCode.UNAUTHORIZED
    return (
        PublicErrorCode.UNAVAILABLE
        if status_code >= 500
        else PublicErrorCode.INTERNAL
    )


def _is_public_api_request(request: Request) -> bool:
    """Limit the V2 envelope to external chat/actions, not web/admin routes."""
    return request.url.path == "/api/v1/chat" or request.url.path.startswith(
        "/api/v1/actions/"
    )


def _is_web_operational_request(request: Request) -> bool:
    """Provider-backed web routes must not log raw exception details."""
    return request.url.path == "/api/v1/web/chat" or request.url.path.startswith(
        "/api/v1/web/actions/"
    )


def _public_message(status_code: int) -> str:
    if status_code == status.HTTP_404_NOT_FOUND:
        return "ไม่พบทรัพยากร"
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return "เกินจำนวนคำขอที่อนุญาต"
    if status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        return "ไม่สามารถยืนยันตัวตนได้"
    if status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    }:
        return "คำขอไม่ถูกต้อง"
    if status_code == status.HTTP_409_CONFLICT:
        return "สถานะของทรัพยากรขัดแย้งกับคำขอ"
    return "ไม่สามารถให้บริการได้ในขณะนี้"
