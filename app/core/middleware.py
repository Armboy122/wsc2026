"""Request ID generation, structured logging context, and local demo CORS."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger, log_extra, set_request_id
from app.core.logging import get_request_id as get_request_id_from_context

logger = get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach or propagate a request id and emit structured access logs."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id:
            request_id = str(uuid.uuid4())
        set_request_id(request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "http_access",
            extra=log_extra(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 3),
            ),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id() -> str | None:
    """Return the request id bound by RequestIdMiddleware, if any."""
    return get_request_id_from_context()


def add_cors_middleware(app: Any, origins: tuple[str, ...]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
