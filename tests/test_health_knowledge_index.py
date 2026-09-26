"""``GET /health`` reports the knowledge index lifecycle with counts only."""

from __future__ import annotations

import builtins
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.config import Settings
from app.core.di import get_knowledge_service, set_knowledge_service
from app.core.startup import create_knowledge_index_manager, create_platform_app
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import FakeEmbedder
from app.knowledge.index.embedder import Embedder
from app.knowledge.index.manager import IndexManager, IndexState
from app.knowledge.service import KnowledgeDocumentService

DOC = "# เอกสาร\n\n## บริการ\n\n" + "ค่าไฟฟ้า " * 60 + "\n"


class FailingEmbedder(FakeEmbedder):
    """Deterministic fake embedder whose ``fail`` switch forces rebuild failures."""

    def __init__(self, dim: int = 64) -> None:
        super().__init__(dim)
        self.fail = False

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if self.fail:
            raise RuntimeError("embedder unavailable")
        return super().embed_documents(texts)


@pytest.fixture
def restore_knowledge_service():
    from app import main  # noqa: F401 - ensure the app graph exists before swapping

    original = get_knowledge_service()
    yield
    set_knowledge_service(original)


def _build(
    tmp_path: Path, embedder: Embedder | None = None
) -> tuple[TestClient, IndexManager, Path]:
    source = tmp_path / "source"
    aliases = tmp_path / "aliases"
    source.mkdir(parents=True, exist_ok=True)
    aliases.mkdir(parents=True, exist_ok=True)
    (source / "doc.md").write_text(DOC, encoding="utf-8")

    set_knowledge_service(
        KnowledgeDocumentService(KnowledgeCatalog(source, alias_root=aliases))
    )
    manager = IndexManager(
        source_root=source,
        alias_root=aliases,
        index_dir=tmp_path / "index",
        embedder=embedder if embedder is not None else FakeEmbedder(64),
        watch=False,
    )
    app = create_platform_app(Settings(gemini_api_key="test-key"), index_manager=manager)
    app.include_router(router)
    return TestClient(app), manager, source


def _wait_for(predicate: Callable[[], bool], *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before the timeout")


def test_health_reports_ready_with_counts_only(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    client, manager, _source = _build(tmp_path)

    with client:
        _wait_for(lambda: manager.health().status is IndexState.READY)
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledgeIndex"]["status"] == "ready"
    assert payload["knowledgeIndex"]["documents"] == 1
    assert payload["knowledgeIndex"]["chunks"] >= 1
    assert set(payload["knowledgeIndex"]) == {"status", "documents", "chunks"}
    # No paths, content, or error text may leak through health.
    assert str(tmp_path) not in response.text
    assert "ค่าไฟฟ้า" not in response.text


def test_health_reports_building_before_the_first_build(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    client, _manager, _source = _build(tmp_path)

    payload = client.get("/health").json()

    assert payload["knowledgeIndex"] == {"status": "building", "documents": 0, "chunks": 0}


def test_health_reports_error_without_a_manager(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "doc.md").write_text(DOC, encoding="utf-8")
    set_knowledge_service(
        KnowledgeDocumentService(KnowledgeCatalog(source, alias_root=tmp_path / "none"))
    )
    app = create_platform_app(Settings(gemini_api_key=None))
    app.include_router(router)

    payload = TestClient(app).get("/health").json()

    assert payload["knowledgeIndex"] == {"status": "error", "documents": 0, "chunks": 0}
    assert payload["liveVoice"] == "not_configured"


def test_health_reports_error_after_a_failed_initial_build(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    embedder = FailingEmbedder()
    embedder.fail = True
    client, manager, _source = _build(tmp_path, embedder=embedder)

    with client:
        _wait_for(lambda: manager.health().status is IndexState.ERROR)
        payload = client.get("/health").json()

    assert payload["knowledgeIndex"] == {"status": "error", "documents": 0, "chunks": 0}
    # Voice keeps serving even when the index cannot build.
    assert payload["liveVoice"] == "configured"
    assert payload["status"] == "ok"


def test_health_reports_stale_when_a_rebuild_fails(
    tmp_path: Path, restore_knowledge_service: None
) -> None:
    embedder = FailingEmbedder()
    client, manager, source = _build(tmp_path, embedder=embedder)

    with client:
        _wait_for(lambda: manager.health().status is IndexState.READY)
        embedder.fail = True
        (source / "doc.md").write_text("# เอกสาร\n\n## บริการ\n\nเนื้อหาใหม่\n", encoding="utf-8")
        manager.refresh_if_stale()
        payload = client.get("/health").json()

    assert payload["knowledgeIndex"]["status"] == "stale"
    assert payload["knowledgeIndex"]["documents"] == 1


def test_missing_index_extra_yields_no_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "app.knowledge.index.manager":
            raise ImportError("the optional index extra is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert create_knowledge_index_manager(Settings()) is None


def test_configured_embedder_builds_a_manager() -> None:
    manager = create_knowledge_index_manager(Settings(knowledge_embedder="fake"))

    assert isinstance(manager, IndexManager)
    assert isinstance(manager.embedder, FakeEmbedder)


def test_real_app_lifespan_builds_the_index(restore_knowledge_service: None) -> None:
    from app.main import app, knowledge_index_manager

    assert isinstance(knowledge_index_manager, IndexManager)
    with TestClient(app) as client:
        _wait_for(lambda: knowledge_index_manager.health().status is IndexState.READY)
        payload = client.get("/health").json()

    assert payload["knowledgeIndex"]["status"] == "ready"
    assert payload["knowledgeIndex"]["documents"] >= 45
    assert payload["knowledgeIndex"]["chunks"] > 0
