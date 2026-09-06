"""จุดประกอบหลักของแอปพลิเคชัน PEA One Agent

โมดูลนี้ทำหน้าที่เชื่อมแพลตฟอร์มตามสัญญา, Main Agent หนึ่งตัว, เครื่องมือระดับบนสุดสองตัว
และ UI แบบ static สำหรับการแข่งขันเท่านั้น นโยบายธุรกิจยังคงอยู่ใน Main Agent
และโมดูลเครื่องมือ
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent.declarative_tools import load_declarative_tools
from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import InvalidActionStateError, MainAgent, NotFoundError
from app.agent.registry import ToolRegistry
from app.api.live import router as live_router
from app.api.routes import router
from app.api.admin import router as admin_router
from app.backends.full_document_knowledge import (
    SUPPORTED_PROVIDERS,
    FullDocumentKnowledgeBackend,
)
from app.contracts import ToolAction, ToolName
from app.core.config import LLMRuntimeSettings, load_settings
from app.core.di import adapter_service, agent_service
from app.core.errors import ConflictException, NotFoundException, platform_exception_handler
from app.core.prompt_admin import PromptAdminService
from app.core.public_api import ApiKeyStore, ConversationOwnership, InMemoryRateLimiter
from app.core.startup import create_platform_app, startup_event
from app.core.tool_admin import ToolAdminService
from app.db import Database
from app.agent.stores import PendingActionStore, TraceStore
from app.db import tool_repository
from app.db.bootstrap_oms import seed_oms_tool
from app.db.bootstrap_prompt import DbSystemPromptProvider, seed_system_prompt
from app.llm import JudgeLLMClient, LLMClient, LLMProviderConfig, create_llm_adapter
from app.llm.prompting import set_system_prompt_provider
from app.plugins import load_plugins
from app.plugins.oms.declarative_shape import OMS_OPERATIONS
from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.oms.response import OmsResponsePolicy
from app.plugins.runtime import BoundDemoBehavior
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
        thinking=config.thinking,
        effort=config.effort,
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
# โหลด plugin contributions ก่อนประกอบ demo adapter; provider จริงรับเฉพาะข้อความคำสั่ง
plugins = load_plugins(settings)
# D2.7: oms_tool ย้ายขึ้น declarative tool contract (DB) แล้ว plugin.yaml ของมันถูกปิดไว้
# (soft delete) จึงไม่อยู่ใน `plugins` อีกต่อไป แต่ OmsResponsePolicy/OmsDemoBehavior เป็นแค่ชั้น
# presentation/demo ที่ไม่ผูกกับว่า tool ตัวจริงมาจาก DB หรือโค้ด จึงยังผูกตรงที่นี่ได้ — ดึง
# action ที่ LLM เรียกได้จาก OMS_OPERATIONS (ต้นฉบับเดียวกับที่ scripts/seed_oms_tool.py ใช้)
# แทนการพิมพ์ ToolAction.OMS_* ซ้ำมือ กันไม่ให้หลุดตามหลังถ้า operations ของ OMS เปลี่ยน
_oms_llm_actions = frozenset(
    ToolAction(op.action) for op in OMS_OPERATIONS if op.exposure == "llm"
)
oms_demo_behavior = BoundDemoBehavior(
    behavior=OmsDemoBehavior(), tool_name=ToolName.OMS, allowed_actions=_oms_llm_actions
)
llm_adapter = create_llm_adapter(
    _provider_config(settings.main_llm),
    demo_behaviors=(
        oms_demo_behavior,
        *(behavior for plugin in plugins if (behavior := plugin.demo_behavior) is not None),
    ),
)
judge_llm_adapter = create_llm_adapter(_provider_config(settings.judge_llm))
judge_llm_client = JudgeLLMClient(judge_llm_adapter)

# D2.6 / P9: ย้ายการโหลด async ทั้งหมดออกจากระดับ module เพื่อให้ uvicorn --reload ทำงานได้
# registry ถูกสร้างด้วย code tools ก่อน แล้ว declarative tools + สถานะเปิด/ปิดของ code tool
# จะถูกโหลดผ่าน bootstrap ใน FastAPI lifespan (หรือเมื่อมี request/connection แรกเข้า)
db = Database(settings.db_path, state_key=settings.state_key)
db.migrate()
pending_action_store = PendingActionStore(db)
trace_store = TraceStore(db)

tool_registry = ToolRegistry(
    [
        KnowledgeTool(knowledge_backend),
        *(plugin.tool for plugin in plugins),
    ],
    catalogue=tuple(plugin.tool_definition for plugin in plugins),
    response_policies=(
        OmsResponsePolicy(),
        *(policy for plugin in plugins if (policy := plugin.response_policy) is not None),
    ),
    operation_specs={
        key: spec
        for plugin in plugins
        for key, spec in plugin.operation_specs.items()
    },
)

main_llm_client = LLMClient(llm_adapter)
guided_flows = GuidedFlows(
    tuple(flow for plugin in plugins if (flow := plugin.guided_flow) is not None),
)
# flow ใช้ LLM เพื่อเลือกจากตัวเลือกที่ catalog ให้มาเท่านั้น ไม่ใช่เพื่อสร้างรหัสเอง
guided_flows.attach_llm(main_llm_client)
main_agent = MainAgent(
    main_llm_client,
    tool_registry,
    pending_actions=pending_action_store,
    traces=trace_store,
    guided_flows=guided_flows,
)

agent_service.set_agent(main_agent)
adapter_service.set_llm(llm_adapter)
adapter_service.set_knowledge(_KnowledgeReadiness(knowledge_backend))

_bootstrap_lock = asyncio.Lock()
_bootstrapped = False


async def bootstrap(target_app: FastAPI | None = None) -> None:
    """โหลด prompt, สถานะ code tool, seed OMS และ declarative tools ใน event loop"""
    global _bootstrapped
    if _bootstrapped:
        return
    async with _bootstrap_lock:
        if _bootstrapped:
            return

        # D3.2: SYSTEM_PROMPT อยู่ใน DB แล้ว — seed ครั้งเดียว (idempotent) และอ่านจาก DB ต่อเทิร์น
        await seed_system_prompt(db)
        set_system_prompt_provider(DbSystemPromptProvider(db))

        # P4: สถานะเปิด/ปิดของ code tool persist ในตาราง tool (แถว source='code')
        disabled_slugs = await tool_repository.disabled_code_tool_slugs(db)
        for slug in disabled_slugs:
            try:
                tool_registry.set_code_tool_enabled(slug, False)
            except ValueError:
                pass

        # P1 ของ D2: DB ใหม่ ต้องได้ oms_tool โดยอัตโนมัติ
        await seed_oms_tool(db, oms_base_url=settings.oms_base_url)

        resolved_app = target_app or globals().get("app")
        tool_admin: ToolAdminService | None = (
            getattr(resolved_app.state, "tool_admin", None) if resolved_app else None
        )
        if tool_admin is not None:
            await tool_admin.reload()
        else:
            allowlist_rows = await db.fetch_all(
                "SELECT domain FROM domain_allowlist WHERE enabled = 1"
            )
            bundle = await load_declarative_tools(
                db,
                app_env=settings.app_env,
                allowlist=tuple(row["domain"] for row in allowlist_rows),
            )
            tool_registry.replace_declarative_tools(
                bundle.tools, bundle.catalogue, bundle.operation_specs
            )

        startup_event(resolved_app or app, tool_registry)
        _bootstrapped = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap(app)
    yield


app = create_platform_app(settings, lifespan=lifespan)
app.state.api_key_store = ApiKeyStore(db)
app.state.conversation_ownership = ConversationOwnership(db)
app.state.public_api_rate_limiter = InMemoryRateLimiter(settings.public_api_rate_limit_per_minute)
app.include_router(router)
app.include_router(live_router)
app.include_router(admin_router)
# D3.3/D3.4/D3.5: บริการหลังบ้านของหน้า admin — initial_bundle จะถูกเติมผ่าน reload() ใน lifespan
app.state.tool_admin = ToolAdminService(
    db,
    settings=settings,
    registry=tool_registry,
    plugins=plugins,
)
# D3.6: หน้าแก้ prompt — แชร์ connection เดียวกับ tool admin แก้แล้วมีผลเทิร์นถัดไป
# เพราะ runtime อ่านผ่าน DbSystemPromptProvider (ด้านบน) ต่อเทิร์นอยู่แล้ว
app.state.prompt_admin = PromptAdminService(db)
app.add_exception_handler(NotFoundError, _not_found_handler)
app.add_exception_handler(InvalidActionStateError, _conflict_handler)


class EnsureBootstrappedMiddleware:
    """ประกันว่า bootstrap ทำงานเสมอแม้ไคลเอนต์ไม่ได้เข้าผ่าน lifespan (เช่น TestClient โดยตรง)"""

    def __init__(self, asgi_app: Any) -> None:
        self._asgi_app = asgi_app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket") and not _bootstrapped:
            await bootstrap(app)
        await self._asgi_app(scope, receive, send)


app.add_middleware(EnsureBootstrappedMiddleware)

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

# ช่องทาง Telegram เปิดเฉพาะเมื่อกรอก credential ครบ (เว้นว่าง = ปิดทั้ง route และบริการแบบ fail closed)
if settings.telegram_bot_token and settings.telegram_bot_secret:
    from app.api.telegram import configure_telegram_webhook, router as telegram_router
    from app.telegram.api_client import TelegramApiClient
    from app.telegram.bridge import TelegramBridge
    from app.telegram.service import TelegramWebhookService

    configure_telegram_webhook(
        TelegramWebhookService(
            secret=settings.telegram_bot_secret,
            client=TelegramApiClient(settings.telegram_bot_token),
            bridge=TelegramBridge(main_agent),
        )
    )
    app.include_router(telegram_router)

_web_root = Path(__file__).resolve().parents[1] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="web")
