"""Application entry point: static Voice UI, `GET /health`, and `WS /ws/live`.

Dependency graph: settings → deterministic Knowledge catalog → Knowledge service →
ADK Knowledge tool/Gemini Live runtime (constructed per `/ws/live` connection).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.api.live import router as live_router
from app.api.routes import router
from app.core.config import load_settings
from app.core.di import set_knowledge_service
from app.core.startup import create_platform_app
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.service import KnowledgeDocumentService

settings = load_settings()
knowledge_catalog = KnowledgeCatalog(settings.knowledge_source_root)
knowledge_service = KnowledgeDocumentService(knowledge_catalog)
set_knowledge_service(knowledge_service)

app = create_platform_app(settings)
app.include_router(router)
app.include_router(live_router)

_web_root = Path(__file__).resolve().parents[1] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="web")
