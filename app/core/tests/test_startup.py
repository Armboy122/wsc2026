"""Application startup builds only the minimal Voice + deterministic Knowledge graph."""

from __future__ import annotations

import ast
from pathlib import Path


def test_runtime_wires_minimal_voice_graph() -> None:
    from app import main
    from app.core.di import get_knowledge_service
    from app.knowledge.service import KnowledgeDocumentService

    assert isinstance(main.knowledge_service, KnowledgeDocumentService)
    assert get_knowledge_service() is main.knowledge_service
    assert main.knowledge_service.catalog is main.knowledge_catalog
    assert len(main.knowledge_catalog) > 0
    for removed in (
        "main_agent", "tool_registry", "plugins", "llm_adapter", "judge_llm_client",
        "knowledge_backend", "knowledge_tool", "guided_flows",
    ):
        assert not hasattr(main, removed)


def test_entry_point_imports_no_platform_modules() -> None:
    tree = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= {
        "__future__",
        "pathlib",
        "fastapi.staticfiles",
        "app.api.live",
        "app.api.routes",
        "app.core.config",
        "app.core.di",
        "app.core.startup",
        "app.knowledge.catalog",
        "app.knowledge.service",
    }
