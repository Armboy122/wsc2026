"""FastAPI app construction for the Voice agent."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware


def create_platform_app(settings: Settings) -> FastAPI:
    """Create the FastAPI app with request-id logging and safe exception handlers."""
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PEA Knowledge Voice Agent",
        version="0.1.0",
        docs_url="/docs" if settings.app_env == "development" else None,
        redoc_url="/redoc" if settings.app_env == "development" else None,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.state.settings = settings
    return app
