"""จุดประกอบหลักของแอปพลิเคชัน PEA One Agent

โมดูลนี้ทำหน้าที่เชื่อมแพลตฟอร์มตามสัญญา, Main Agent หนึ่งตัว, เครื่องมือระดับบนสุดสองตัว
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
from app.api.live import router as live_router
from app.api.routes import router
from app.backends.full_document_knowledge import (
    SUPPORTED_PROVIDERS,
    FullDocumentKnowledgeBackend,
)
from app.core.config import LLMRuntimeSettings, load_settings
from app.core.di import adapter_service, agent_service
from app.core.errors import ConflictException, NotFoundException, platform_exception_handler
from app.core.startup import create_platform_app, startup_event
from app.llm import JudgeLLMClient, LLMClient, LLMProviderConfig, create_llm_adapter
from app.plugins import load_plugins
from app.tools.knowledge_tool import KnowledgeTool


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


def _provider_config(config: LLMRuntimeSettings) -> LLMProviderConfig:
    return LLMProviderConfig(
        provider=config.provider,
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url,
    )


settings = load_settings()
if settings.knowledge_backend_name != "full_document":
    raise RuntimeError(
        f"ไม่รองรับ backend ความรู้: {settings.knowledge_backend_name}"
    )
if settings.knowledge_provider not in SUPPORTED_PROVIDERS:
    raise RuntimeError(f"ไม่รองรับ Knowledge provider: {settings.knowledge_provider}")

knowledge_backend = FullDocumentKnowledgeBackend(
    api_key=settings.knowledge_llm.api_key,
    source_root=settings.knowledge_source_root,
    model=settings.knowledge_llm.model,
    provider=settings.knowledge_llm.provider,
    base_url=settings.knowledge_llm.base_url,
)
llm_adapter = create_llm_adapter(_provider_config(settings.main_llm))
judge_llm_adapter = create_llm_adapter(_provider_config(settings.judge_llm))
judge_llm_client = JudgeLLMClient(judge_llm_adapter)
# Knowledge เป็น built-in ส่วนเครื่องมือปฏิบัติการมาจาก manifest ของปลั๊กอินตอน startup
plugins = load_plugins(settings)
tool_registry = ToolRegistry(
    [KnowledgeTool(knowledge_backend), *(plugin.tool for plugin in plugins)],
    catalogue=tuple(plugin.tool_definition for plugin in plugins),
)
main_agent = MainAgent(LLMClient(llm_adapter), tool_registry)

agent_service.set_agent(main_agent)
adapter_service.set_llm(llm_adapter)
adapter_service.set_knowledge(_KnowledgeReadiness(knowledge_backend))

app = create_platform_app(settings)
app.include_router(router)
app.include_router(live_router)
app.add_exception_handler(NotFoundError, _not_found_handler)
app.add_exception_handler(InvalidActionStateError, _conflict_handler)
startup_event(app, tool_registry)

# ช่องทาง LINE เปิดเฉพาะเมื่อกรอก credential ครบ (เว้นว่าง = ปิดทั้ง route และบริการ)
if settings.line_channel_secret and settings.line_channel_access_token:
    from app.api.line import configure_line_webhook, router as line_router
    from app.line.api_client import LineApiClient
    from app.line.bridge import LineBridge
    from app.line.service import LineWebhookService

    configure_line_webhook(
        LineWebhookService(
            secret=settings.line_channel_secret,
            client=LineApiClient(settings.line_channel_access_token),
            bridge=LineBridge(main_agent),
        )
    )
    app.include_router(line_router)

_web_root = Path(__file__).resolve().parents[1] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="web")
