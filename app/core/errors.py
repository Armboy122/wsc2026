"""Safe, user-facing HTTP errors and Pydantic-friendly exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, log_extra

logger = get_logger(__name__)


class SafeError(BaseModel):
    """User-safe error body returned by platform routes."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1)
    detail: str | None = None
    request_id: str | None = Field(default=None, serialization_alias="requestId")


class PlatformException(Exception):
    """Base for intentional HTTP errors raised inside handlers."""

    def __init__(
        self,
        status_code: int,
        error: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.detail = detail


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

    return _build_safe_response(exc, get_request_id())


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    from app.core.middleware import get_request_id

    logger.warning("validation_failed", extra=log_extra(errors=exc.errors()))
    body = SafeError(
        error="invalid_request",
        detail="Request failed contract validation.",
        request_id=get_request_id(),
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump(by_alias=True))


async def catchall_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.core.middleware import get_request_id

    logger.exception("unexpected_error", extra=log_extra(path=request.url.path))
    body = SafeError(
        error="internal_error",
        detail="An unexpected error occurred. Please try again.",
        request_id=get_request_id(),
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump(by_alias=True))


def register_exception_handlers(app: Any) -> None:
    app.add_exception_handler(PlatformException, platform_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, catchall_exception_handler)
