"""PEA One Agent application composition root.

This module only wires the frozen platform, one Main Agent, four top-level tools,
and the static competition UI. Business policy remains in the Main Agent and
tool modules.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent.main_agent import InvalidActionStateError, MainAgent, NotFoundError
from app.agent.registry import ToolRegistry
from app.api.routes import router
from app.backends.gemini_file_search import GeminiFileSearchKnowledgeBackend
from app.core.di import adapter_service, agent_service
from app.core.errors import ConflictException, NotFoundException, platform_exception_handler
from app.core.startup import create_platform_app, startup_event
from app.llm import DemoLLMAdapter, LLMClient
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool
from app.tools.sabuy_tool import SabuyTool
from app.tools.voc_tool import VocTool


class _KnowledgeReadiness:
    """Expose a credential-free readiness probe to the health route."""

    def __init__(self, backend: GeminiFileSearchKnowledgeBackend) -> None:
        self._backend = backend

    async def ready(self) -> bool:
        return self._backend.is_configured()


async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return await platform_exception_handler(
        request,
        NotFoundException(detail=str(exc)),
    )


async def _conflict_handler(
    request: Request,
    exc: InvalidActionStateError,
) -> JSONResponse:
    return await platform_exception_handler(
        request,
        ConflictException(detail=str(exc)),
    )


knowledge_backend = GeminiFileSearchKnowledgeBackend()
llm_adapter = DemoLLMAdapter()
tool_registry = ToolRegistry(
    [
        KnowledgeTool(knowledge_backend),
        SabuyTool(),
        VocTool(),
        OmsTool(),
    ]
)
main_agent = MainAgent(LLMClient(llm_adapter), tool_registry)

agent_service.set_agent(main_agent)
adapter_service.set_llm(llm_adapter)
adapter_service.set_knowledge(_KnowledgeReadiness(knowledge_backend))

app = create_platform_app()
app.include_router(router)
app.add_exception_handler(NotFoundError, _not_found_handler)
app.add_exception_handler(InvalidActionStateError, _conflict_handler)
startup_event(app, tool_registry)

_web_root = Path(__file__).resolve().parents[1] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="web")
