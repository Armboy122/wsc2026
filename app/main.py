"""จุดประกอบหลักของแอปพลิเคชัน PEA One Agent

โมดูลนี้ทำหน้าที่เชื่อมแพลตฟอร์มตามสัญญา, Main Agent หนึ่งตัว, เครื่องมือระดับบนสุดสี่ตัว
และ UI แบบ static สำหรับการแข่งขันเท่านั้น นโยบายธุรกิจยังคงอยู่ใน Main Agent
และโมดูลเครื่องมือ
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent.main_agent import InvalidActionStateError, MainAgent, NotFoundError
from app.agent.registry import ToolRegistry
from app.api.routes import router
from app.backends.full_document_knowledge import (
    SUPPORTED_PROVIDERS,
    FullDocumentKnowledgeBackend,
)
from app.core.config import load_settings
from app.core.di import adapter_service, agent_service
from app.core.errors import ConflictException, NotFoundException, platform_exception_handler
from app.core.startup import create_platform_app, startup_event
from app.llm import DemoLLMAdapter, LLMClient, MaxPlusDeepSeekAdapter
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool
from app.tools.sabuy_tool import SabuyTool
from app.tools.voc_tool import VocTool


class _KnowledgeReadiness:
    """เปิดเผยตัวตรวจสอบความพร้อมที่ไม่มีข้อมูลรับรองให้เส้นทาง health"""

    def __init__(self, backend: FullDocumentKnowledgeBackend) -> None:
        self._backend = backend

    async def ready(self) -> bool:
        return await self._backend.is_ready()


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


settings = load_settings()
if settings.llm_adapter_name not in {"demo", "maxplus_openai"}:
    raise RuntimeError(f"ไม่รองรับ LLM adapter: {settings.llm_adapter_name}")
if settings.knowledge_backend_name != "full_document":
    raise RuntimeError(
        f"ไม่รองรับ backend ความรู้: {settings.knowledge_backend_name}"
    )
if settings.knowledge_provider not in SUPPORTED_PROVIDERS:
    raise RuntimeError(f"ไม่รองรับ Knowledge provider: {settings.knowledge_provider}")

_using_maxplus = settings.knowledge_provider == "maxplus_openai"
knowledge_backend = FullDocumentKnowledgeBackend(
    api_key=(settings.maxplus_api_key if _using_maxplus else settings.gemini_api_key),
    source_root=settings.knowledge_source_root,
    model=(settings.maxplus_model if _using_maxplus else settings.gemini_long_context_model),
    provider=settings.knowledge_provider,
    base_url=(settings.maxplus_base_url if _using_maxplus else None),
)
llm_adapter = (
    MaxPlusDeepSeekAdapter(
        api_key=settings.maxplus_api_key,
        base_url=settings.maxplus_base_url,
        model=settings.maxplus_model,
    )
    if settings.llm_adapter_name == "maxplus_openai"
    else DemoLLMAdapter()
)
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

app = create_platform_app(settings)
app.include_router(router)
app.add_exception_handler(NotFoundError, _not_found_handler)
app.add_exception_handler(InvalidActionStateError, _conflict_handler)
startup_event(app, tool_registry)

_web_root = Path(__file__).resolve().parents[1] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="web")
