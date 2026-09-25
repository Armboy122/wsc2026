"""Architecture guards for the Voice + deterministic Knowledge scope (Story 3 Ticket 002)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

DELETED_PATHS = (
    "app/backends",
    "app/line",
    "app/live",
    "app/llm",
    "app/plugins",
    "app/tools",
    "app/agent/main_agent.py",
    "app/agent/registry.py",
    "app/agent/guided_flow.py",
    "app/agent/response_policy.py",
    "app/agent/stores.py",
    "app/api/line.py",
    "data/mock",
    "evaluation",
    "scripts/evaluate",
    "scripts/add-plugin",
    "web/linkify.js",
)

DELETED_MODULE_PREFIXES = (
    "app.backends",
    "app.line",
    "app.live",
    "app.llm",
    "app.plugins",
    "app.tools",
    "app.agent.main_agent",
    "app.agent.registry",
    "app.agent.guided_flow",
    "app.agent.response_policy",
    "app.agent.stores",
    "yaml",
)


@pytest.mark.parametrize("relative", DELETED_PATHS)
def test_obsolete_platform_paths_are_deleted(relative: str) -> None:
    assert not (ROOT / relative).exists(), relative


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_no_python_module_imports_deleted_platform_code() -> None:
    offenders = []
    for path in [*ROOT.joinpath("app").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py")]:
        for module in _imported_modules(path):
            if any(module == prefix or module.startswith(prefix + ".") for prefix in DELETED_MODULE_PREFIXES):
                offenders.append((str(path.relative_to(ROOT)), module))
    assert offenders == []


def test_contracts_module_holds_only_shared_primitives() -> None:
    import app.contracts as contracts

    for removed in ("BillCalculationRequest", "ChatRequest", "PendingAction", "Citation", "ToolName", "TraceEvent"):
        assert not hasattr(contracts, removed), removed
    assert {code.name for code in contracts.ToolErrorCode} == {"INVALID_INPUT", "UNAVAILABLE", "INTERNAL"}


def test_web_client_has_no_chat_or_rest_api_surface() -> None:
    for path in ROOT.joinpath("web").glob("*.js"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("/api/v1", "agent.response", "navigator.geolocation", "pendingAction"):
            assert forbidden not in source, (path.name, forbidden)
    for page in ("index.html", "phone.html"):
        html = ROOT.joinpath("web", page).read_text(encoding="utf-8")
        assert "linkify.js" not in html
        assert "/api/v1" not in html
    assert 'id="voice-toggle"' in ROOT.joinpath("web", "index.html").read_text(encoding="utf-8")


def test_pyyaml_is_not_a_direct_dependency() -> None:
    pyproject = ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8").lower()
    assert "pyyaml" not in pyproject


def test_all_knowledge_documents_are_retained() -> None:
    """The owner requires every knowledge document to be kept."""
    from app.knowledge.catalog import KnowledgeCatalog

    source_root = ROOT / "knowledge" / "source"
    catalog = KnowledgeCatalog(source_root, alias_root=ROOT / "knowledge" / "aliases")
    assert len(catalog.entries()) >= 45
    assert len(list(source_root.glob("PEA_*.md"))) >= 34
    assert len(list(source_root.joinpath("qa").glob("qa_*.md"))) >= 10
    assert len(list(ROOT.joinpath("knowledge", "aliases").glob("*.md"))) >= 4
    assert ROOT.joinpath("docs", "research", "electricity-tariff-sep-2569.md").is_file()
