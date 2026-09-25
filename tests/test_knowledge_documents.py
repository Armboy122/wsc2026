"""Selected-document Knowledge service: validation, completeness, and fail-closed limits."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.contracts import ToolErrorCode
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.service import (
    KNOWLEDGE_URI_PREFIX,
    USER_SAFE_CONTEXT_EXCEEDED,
    USER_SAFE_INVALID_SELECTION,
    USER_SAFE_TOO_MANY_DOCUMENTS,
    KnowledgeDocumentService,
)

LONG_BODY = "รายละเอียดบริการ\n" * 40


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    _write(root / "alpha.md", f"# บริการอัลฟ่า\n\n## หัวข้อ\n\n{LONG_BODY}")
    _write(root / "beta.md", "# บริการบีต้า\n\n## หัวข้อ\n\nเนื้อหาบีต้า\n")
    _write(root / "nested" / "gamma.md", "# บริการแกมม่า\n\nเนื้อหาแกมม่า\n")
    return root


@pytest.fixture
def service(source_root: Path) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(KnowledgeCatalog(source_root, alias_root=None))


def test_select_returns_complete_document_with_provenance(service: KnowledgeDocumentService) -> None:
    result = service.select(["alpha.md"])

    assert result.ok and result.failure is None
    document = result.documents[0]
    assert document.source_id == "alpha.md"
    assert document.title == "บริการอัลฟ่า"
    assert document.uri == f"{KNOWLEDGE_URI_PREFIX}alpha.md"
    assert document.content == (
        service.catalog.get("alpha.md").path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    )
    assert len(document.content) > len(LONG_BODY)


def test_select_returns_multiple_approved_documents_in_order(
    service: KnowledgeDocumentService,
) -> None:
    result = service.select(["nested/gamma.md", "beta.md"])

    assert result.ok
    assert [document.source_id for document in result.documents] == [
        "nested/gamma.md",
        "beta.md",
    ]
    assert all(document.content.strip() for document in result.documents)


def test_catalog_entries_expose_selection_metadata_only(
    service: KnowledgeDocumentService,
) -> None:
    entries = service.catalog_entries()

    assert [entry["sourceId"] for entry in entries] == [
        "alpha.md",
        "beta.md",
        "nested/gamma.md",
    ]
    assert all("content" not in entry for entry in entries)


def test_unknown_source_id_fails_closed(service: KnowledgeDocumentService) -> None:
    result = service.select(["does-not-exist.md"])

    assert not result.ok
    assert result.documents == ()
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.INVALID_INPUT
    assert result.failure.message == USER_SAFE_INVALID_SELECTION


def test_duplicate_source_ids_fail_closed(service: KnowledgeDocumentService) -> None:
    result = service.select(["alpha.md", "alpha.md"])

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    "unsafe",
    [
        "/etc/passwd",
        "../source/alpha.md",
        "nested/../../alpha.md",
        "C:/windows/alpha.md",
        "alpha.md\\",
        "nested\\alpha.md",
        ".hidden.md",
        "",
        " alpha.md",
        "alpha.md ",
        ".",
        "..",
    ],
)
def test_unsafe_source_ids_fail_closed(
    service: KnowledgeDocumentService, unsafe: str
) -> None:
    result = service.select([unsafe])

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.INVALID_INPUT
    assert result.failure.message == USER_SAFE_INVALID_SELECTION


def test_empty_and_non_sequence_selection_fails_closed() -> None:
    class Weird:
        def __iter__(self):  # pragma: no cover - never iterated
            return iter(())

    catalog = KnowledgeCatalog(Path("knowledge/source"))
    service = KnowledgeDocumentService(catalog)

    for candidate in ([], "alpha.md", Weird()):
        result = service.select(candidate)  # type: ignore[arg-type]
        assert not result.ok
        assert result.failure is not None
        assert result.failure.code is ToolErrorCode.INVALID_INPUT


def test_document_count_limit_fails_closed(source_root: Path) -> None:
    service = KnowledgeDocumentService(
        KnowledgeCatalog(source_root, alias_root=None), max_documents=1
    )

    result = service.select(["alpha.md", "beta.md"])

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.INVALID_INPUT
    assert result.failure.message == USER_SAFE_TOO_MANY_DOCUMENTS


def test_context_budget_overflow_fails_without_truncation(source_root: Path) -> None:
    catalog = KnowledgeCatalog(source_root, alias_root=None)
    full_length = len(
        catalog.get("alpha.md").path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    )
    service = KnowledgeDocumentService(catalog, max_total_chars=full_length - 1)

    result = service.select(["alpha.md"])

    assert not result.ok
    assert result.documents == ()
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.INVALID_INPUT
    assert result.failure.message == USER_SAFE_CONTEXT_EXCEEDED


def test_context_budget_allows_exact_boundary(source_root: Path) -> None:
    catalog = KnowledgeCatalog(source_root, alias_root=None)
    full_length = len(
        catalog.get("alpha.md").path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    )
    service = KnowledgeDocumentService(catalog, max_total_chars=full_length)

    result = service.select(["alpha.md"])

    assert result.ok
    assert len(result.documents[0].content) == full_length


def test_missing_document_file_fails_closed(source_root: Path) -> None:
    service = KnowledgeDocumentService(KnowledgeCatalog(source_root, alias_root=None))
    service.catalog.get("beta.md").path.unlink()  # type: ignore[union-attr]

    result = service.select(["beta.md"])

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code is ToolErrorCode.UNAVAILABLE


def test_document_selection_is_deterministic(source_root: Path) -> None:
    service = KnowledgeDocumentService(KnowledgeCatalog(source_root, alias_root=None))

    first = service.select(["alpha.md", "beta.md"])
    second = service.select(["alpha.md", "beta.md"])

    assert first == second


def test_knowledge_modules_never_import_or_call_a_generative_provider() -> None:
    modules = sorted(Path("app/knowledge").glob("*.py"))
    assert modules, "expected deterministic Knowledge modules"

    forbidden_prefixes = ("google", "openai", "anthropic")
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.split(".")[0] in forbidden_prefixes for alias in node.names
                ), f"{module} imports a generative provider"
            if isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden_prefixes, (
                    f"{module} imports a generative provider"
                )
            if isinstance(node, ast.Attribute):
                assert node.attr != "generate_content", (
                    f"{module} calls a generative provider"
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"generate_content", "generate_content_async"}
