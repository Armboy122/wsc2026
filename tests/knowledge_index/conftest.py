"""Shared fixtures for knowledge index tests.

All tests are offline: they use the deterministic ``FakeEmbedder`` and the real approved
corpus under ``knowledge/source`` (read-only).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import FakeEmbedder, KnowledgeIndex

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "knowledge" / "source"
ALIAS_ROOT = ROOT / "knowledge" / "aliases"


@pytest.fixture(scope="session")
def real_catalog() -> KnowledgeCatalog:
    return KnowledgeCatalog(SOURCE_ROOT, alias_root=ALIAS_ROOT)


@pytest.fixture(scope="session")
def real_index(real_catalog: KnowledgeCatalog) -> KnowledgeIndex:
    return KnowledgeIndex(real_catalog, embedder=FakeEmbedder())


@pytest.fixture
def temp_catalog(tmp_path: Path) -> Callable[..., KnowledgeCatalog]:
    """Build a throwaway catalog under ``tmp_path`` from ``{relative_path: text}``."""

    def _build(
        files: dict[str, str],
        aliases: dict[str, str] | None = None,
        *,
        source_root: Path | None = None,
        alias_root: Path | None = None,
    ) -> KnowledgeCatalog:
        root = source_root if source_root is not None else tmp_path / "source"
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        rules_root = alias_root if alias_root is not None else tmp_path / "aliases"
        rules_root.mkdir(parents=True, exist_ok=True)
        for name, content in (aliases or {}).items():
            (rules_root / name).write_text(content, encoding="utf-8")
        return KnowledgeCatalog(root, alias_root=rules_root)

    return _build
