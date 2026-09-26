"""Public application surface: static Voice UI, `GET /health`, and `WS /ws/live` only."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.config import Settings
from app.core.di import get_knowledge_service, set_knowledge_service
from app.core.startup import create_platform_app
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index.manager import IndexManager
from app.knowledge.service import KnowledgeDocumentService


@pytest.fixture
def restore_knowledge_service():
    from app import main  # noqa: F401 - ensure the app graph exists before swapping

    original = get_knowledge_service()
    yield
    set_knowledge_service(original)


def _health_app(
    api_key: str | None, source_root: Path, index_manager: IndexManager | None = None
) -> TestClient:
    set_knowledge_service(
        KnowledgeDocumentService(KnowledgeCatalog(source_root, alias_root=source_root / "none"))
    )
    app = create_platform_app(Settings(gemini_api_key=api_key), index_manager=index_manager)
    app.include_router(router)
    return TestClient(app)


def test_only_health_and_live_routes_are_registered() -> None:
    from app.main import app

    routes = []
    for route in app.routes:
        # FastAPI wraps included routers; inspect the routers this app actually includes.
        original = getattr(route, "original_router", None)
        routes.extend(original.routes if original is not None else [route])
    http = {route.path for route in routes if isinstance(route, APIRoute)}
    websockets = {route.path for route in routes if isinstance(route, APIWebSocketRoute)}
    assert http == {"/health"}
    assert websockets == {"/ws/live"}
    assert set(app.openapi()["paths"]) == {"/health"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/chat"),
        ("post", "/api/v1/actions/00000000-0000-0000-0000-000000000000/confirm"),
        ("post", "/api/v1/actions/00000000-0000-0000-0000-000000000000/reject"),
        ("get", "/api/v1/traces/00000000-0000-0000-0000-000000000000"),
        ("post", "/api/v1/reset"),
        ("post", "/api/v1/line/webhook"),
        ("post", "/webhook/line"),
        ("get", "/docs"),
        ("get", "/redoc"),
        ("get", "/openapi.json"),
    ],
)
def test_obsolete_routes_are_absent(method: str, path: str) -> None:
    from app.main import app

    client = TestClient(app)
    response = client.get(path) if method == "get" else client.post(path, json={})
    assert response.status_code in {404, 405}


def test_static_voice_ui_is_served() -> None:
    from app.main import app

    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_health_ok_when_catalog_and_live_key_present(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    (tmp_path / "doc.md").write_text("# เอกสาร\n", encoding="utf-8")
    response = _health_app("test-key", tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "knowledgeBackend": "ready",
        "liveVoice": "configured",
        "knowledgeIndex": {"status": "error", "documents": 0, "chunks": 0},
    }
    assert "test-key" not in response.text


def test_health_degraded_without_documents_or_live_key(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    response = _health_app(None, tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "knowledgeBackend": "unavailable",
        "liveVoice": "not_configured",
        "knowledgeIndex": {"status": "error", "documents": 0, "chunks": 0},
    }
