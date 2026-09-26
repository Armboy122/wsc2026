"""Deterministic catalog behavior for approved local Markdown documents."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.knowledge.catalog import KnowledgeCatalog


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    _write(
        root / "b-service.md",
        "# บริการขอใช้ไฟฟ้าใหม่\n\n## เอกสารที่ต้องใช้\n\n- สำเนาบัตรประชาชน\n\n## ขั้นตอน\n",
    )
    _write(
        root / "a-service.md",
        "# บริการคืนเงินประกัน\n\n## เงื่อนไข\n\nรายละเอียด\n",
    )
    _write(root / "qa" / "qa-one.md", "# ถาม: ค่าไฟ\n\n## ตอบ\n\nคำตอบ\n")
    return root


def test_catalog_is_ordered_and_derives_metadata_from_markdown(source_root: Path) -> None:
    catalog = KnowledgeCatalog(source_root, alias_root=source_root.parent / "aliases")

    assert [document.source_id for document in catalog.documents] == [
        "a-service.md",
        "b-service.md",
        "qa/qa-one.md",
    ]
    first = catalog.documents[0]
    assert first.title == "บริการคืนเงินประกัน"
    assert len(catalog) == 3
    assert "qa/qa-one.md" in catalog
    assert catalog.get("missing.md") is None


def test_catalog_rebuild_is_deterministic(source_root: Path) -> None:
    alias_root = source_root.parent / "aliases"
    first = KnowledgeCatalog(source_root, alias_root=alias_root)
    second = KnowledgeCatalog(source_root, alias_root=alias_root)

    assert first.documents == second.documents


def test_catalog_excludes_readme_dotfiles_non_markdown_and_symlinks(
    source_root: Path, tmp_path: Path
) -> None:
    _write(source_root / "README.md", "# Readme\n")
    _write(source_root / "qa" / "README.md", "# Readme\n")
    _write(source_root / ".hidden.md", "# ซ่อน\n")
    _write(source_root / ".private" / "secret.md", "# ลับ\n")
    _write(source_root / "notes.txt", "not markdown\n")
    outside = _write(tmp_path / "outside.md", "# ไฟล์นอกราก\n")
    symlink = source_root / "linked.md"
    try:
        os.symlink(outside, symlink)
    except (OSError, NotImplementedError):
        symlink = None  # type: ignore[assignment]

    catalog = KnowledgeCatalog(source_root, alias_root=source_root.parent / "aliases")
    source_ids = {document.source_id for document in catalog.documents}

    assert source_ids == {"a-service.md", "b-service.md", "qa/qa-one.md"}
    assert "README.md" not in source_ids
    assert ".hidden.md" not in source_ids
    assert "notes.txt" not in source_ids
    if symlink is not None:
        assert "linked.md" not in source_ids


def test_catalog_missing_root_is_empty(tmp_path: Path) -> None:
    catalog = KnowledgeCatalog(tmp_path / "absent")

    assert len(catalog) == 0
    assert catalog.documents == ()


def test_catalog_accepts_alias_rules_for_known_source_ids(
    source_root: Path, tmp_path: Path
) -> None:
    alias_root = tmp_path / "aliases"
    _write(
        alias_root / "connection.md",
        "---\n"
        "id: connection\n"
        "aliases:\n"
        "  - ขอไฟใหม่\n"
        "  - ขอใช้ไฟฟ้าใหม่\n"
        "sourceIds:\n"
        "  - b-service.md\n"
        "---\n\n# ขอใช้ไฟฟ้าใหม่\n",
    )

    catalog = KnowledgeCatalog(source_root, alias_root=alias_root)

    assert "b-service.md" in catalog


def test_catalog_rejects_alias_rules_for_unknown_source_ids(
    source_root: Path, tmp_path: Path
) -> None:
    alias_root = tmp_path / "aliases"
    _write(
        alias_root / "broken.md",
        "---\n"
        "id: broken\n"
        "aliases:\n"
        "  - ขอไฟใหม่\n"
        "sourceIds:\n"
        "  - does-not-exist.md\n"
        "---\n",
    )

    with pytest.raises(ValueError):
        KnowledgeCatalog(source_root, alias_root=alias_root)


def test_real_corpus_catalog_contains_only_approved_markdown() -> None:
    root = Path("knowledge/source")
    if not root.is_dir():
        pytest.skip("knowledge corpus is unavailable in this checkout")

    catalog = KnowledgeCatalog(root)

    assert len(catalog) > 0
    for document in catalog.documents:
        assert document.source_id.endswith(".md")
        assert not document.source_id.startswith("/")
        assert ".." not in document.source_id.split("/")
        assert document.path.is_relative_to(root)
        assert document.title.strip() != ""
