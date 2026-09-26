"""Architecture guards for the Voice + deterministic Knowledge scope (Story 3 Ticket 002)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
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
    # Story 4 ticket 004 re-introduced ``evaluation/rag`` as an offline regression harness;
    # the removed platform evaluator must stay gone.
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
    from app import contracts

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
    assert len(catalog.documents) >= 45
    assert len(list(source_root.glob("PEA_*.md"))) >= 34
    assert len(list(source_root.joinpath("qa").glob("qa_*.md"))) >= 10
    assert len(list(ROOT.joinpath("knowledge", "aliases").glob("*.md"))) >= 4
    assert ROOT.joinpath("docs", "research", "electricity-tariff-sep-2569.md").is_file()


def test_obsolete_catalog_tool_is_absent_from_app_code() -> None:
    """Story 4 replaced the catalog tool; the string must not survive in app code."""
    obsolete = "get_knowledge" + "_documents"
    offenders = [
        str(path.relative_to(ROOT))
        for path in ROOT.joinpath("app").rglob("*.py")
        if obsolete in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_adk_agent_exposes_only_the_search_knowledge_tool() -> None:
    from app.agent.adk_agent import KNOWLEDGE_TOOL_NAME

    assert KNOWLEDGE_TOOL_NAME == "search_knowledge"
    source = ROOT.joinpath("app", "agent", "adk_agent.py").read_text(encoding="utf-8")
    assert "catalog_instruction" not in source
    assert "get_knowledge" + "_documents" not in source


def test_knowledge_index_package_has_no_generative_or_adk_imports() -> None:
    """The local index is deterministic: no generative client and no ADK dependency."""
    modules = sorted(ROOT.joinpath("app", "knowledge", "index").glob("*.py"))
    assert modules, "expected the deterministic knowledge index modules"

    forbidden_roots = ("google", "adk", "genai", "openai", "anthropic")
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in forbidden_roots, f"{module.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden_roots, f"{module.name} imports {node.module}"
            elif isinstance(node, ast.Attribute):
                assert node.attr != "generate_content", (
                    f"{module.name} calls a generative provider"
                )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"generate_content", "generate_content_async"}


def test_importing_knowledge_index_keeps_torch_and_sentence_transformers_lazy() -> None:
    """Importing the index must not pull in torch or sentence-transformers."""
    code = (
        "import sys; import app.knowledge.index; "
        "assert 'torch' not in sys.modules, 'torch must stay lazy'; "
        "assert 'sentence_transformers' not in sys.modules, "
        "'sentence-transformers must stay lazy'"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
