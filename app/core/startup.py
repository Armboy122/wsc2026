"""FastAPI app construction for the Voice agent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware

if TYPE_CHECKING:
    from app.knowledge.index.manager import IndexManager

logger = logging.getLogger(__name__)


def create_knowledge_index_manager(settings: Settings) -> IndexManager | None:
    """Build the knowledge index manager, or ``None`` when the optional extra is missing.

    Importing the index pulls in NumPy, which lives in the optional ``index`` extra. The
    manager only starts a background build later, so constructing it never blocks the app
    and never loads a model.
    """
    try:
        from app.knowledge.index.manager import IndexManager, build_embedder
    except ImportError:
        logger.warning(
            "knowledge index disabled: optional 'index' dependencies are not installed"
        )
        return None
    return IndexManager(
        source_root=settings.knowledge_source_root,
        index_dir=settings.knowledge_index_dir,
        embedder=build_embedder(settings.knowledge_embedder),
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the index build without blocking startup, and stop it on shutdown."""
    manager = getattr(app.state, "knowledge_index_manager", None)
    if manager is not None:
        manager.start()
    try:
        yield
    finally:
        if manager is not None:
            await asyncio.to_thread(manager.stop)


def create_platform_app(
    settings: Settings, *, index_manager: IndexManager | None = None
) -> FastAPI:
    """Create the FastAPI app with request-id logging and safe exception handlers."""
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PEA Knowledge Voice Agent",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.state.settings = settings
    app.state.knowledge_index_manager = index_manager
    return app
