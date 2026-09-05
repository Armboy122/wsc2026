"""จุดประกอบหลักของแอปพลิเคชัน PEA One Agent

โมดูลนี้ทำหน้าที่เชื่อมแพลตฟอร์มตามสัญญา, Main Agent หนึ่งตัว, เครื่องมือระดับบนสุดสองตัว
และ UI แบบ static สำหรับการแข่งขันเท่านั้น นโยบายธุรกิจยังคงอยู่ใน Main Agent
และโมดูลเครื่องมือ
"""

from __future__ import annotations

import asyncio
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
from app.backends.full_document_knowledge import (
    SUPPORTED_PROVIDERS,
    FullDocumentKnowledgeBackend,
)
from app.contracts import ToolAction, ToolName
from app.core.config import LLMRuntimeSettings, load_settings
from app.core.di import adapter_service, agent_service
from app.core.errors import ConflictException, NotFoundException, platform_exception_handler
from app.core.startup import create_platform_app, startup_event
from app.db import Database
from app.db.bootstrap_oms import seed_oms_tool
from app.llm import JudgeLLMClient, LLMClient, LLMProviderConfig, create_llm_adapter
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

# D2.6: declarative tool ที่มาจาก DB (source='db') — ต้อง migrate ก่อนอ่าน แล้วรวม catalogue/
# operation_specs เข้ากับของปลั๊กอิน Python เหมือนเป็นชั้นเดียวกัน (ARCHITECTURE-V2.md §3.4:
# agent ไม่รู้ว่า executor เป็น HTTP หรือโค้ด) asyncio.run ปลอดภัยตรงนี้เพราะยังไม่มี event loop
# ทำงานอยู่ตอน import โมดูลนี้
db = Database()
db.migrate()


async def _load_declarative_catalogue():
    # P1 ของ D2: DB ใหม่ (data/pea.db ถูก ignore) ต้องได้ oms_tool โดยอัตโนมัติ — bootstrap
    # นี้ idempotent (มี tool อยู่แล้ว = ไม่แตะ config ของผู้ใช้) และ seed จากต้นฉบับเดียวกับ
    # scripts/seed_oms_tool.py (app/db/bootstrap_oms.py) ปลั๊กอิน Python ของ OMS ยังคง
    # disabled ตามเดิม (app/plugins/oms/plugin.yaml enabled: false)
    await seed_oms_tool(db, oms_base_url=settings.oms_base_url)
    allowlist_rows = await db.fetch_all("SELECT domain FROM domain_allowlist WHERE enabled = 1")
    return await load_declarative_tools(
        db,
        app_env=settings.app_env,
        allowlist=tuple(row["domain"] for row in allowlist_rows),
    )


declarative_bundle = asyncio.run(_load_declarative_catalogue())

tool_registry = ToolRegistry(
    [
        KnowledgeTool(knowledge_backend),
        *(plugin.tool for plugin in plugins),
        *declarative_bundle.tools,
    ],
    catalogue=tuple(plugin.tool_definition for plugin in plugins) + declarative_bundle.catalogue,
    response_policies=(
        OmsResponsePolicy(),
        *(policy for plugin in plugins if (policy := plugin.response_policy) is not None),
    ),
    operation_specs={
        **{
            key: spec
            for plugin in plugins
            for key, spec in plugin.operation_specs.items()
        },
        **declarative_bundle.operation_specs,
    },
)
main_llm_client = LLMClient(llm_adapter)
guided_flows = GuidedFlows(
    tuple(flow for plugin in plugins if (flow := plugin.guided_flow) is not None)
)
# flow ใช้ LLM เพื่อเลือกจากตัวเลือกที่ catalog ให้มาเท่านั้น ไม่ใช่เพื่อสร้างรหัสเอง
guided_flows.attach_llm(main_llm_client)
main_agent = MainAgent(main_llm_client, tool_registry, guided_flows=guided_flows)

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
