"""Index lifecycle tests: build, atomic swap, disk cache, incremental rebuild, watcher.

All tests are offline and deterministic: they use :class:`FakeEmbedder` (never torch) and a
throwaway corpus under ``tmp_path``, with a short debounce/poll interval for the watcher.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import FakeEmbedder
from app.knowledge.index.embedder import BgeM3Embedder, Embedder
from app.knowledge.index.manager import (
    CACHE_FORMAT_VERSION,
    CACHE_HEADER_NAME,
    CACHE_VECTORS_NAME,
    IndexManager,
    IndexState,
    IndexUnavailableError,
    build_embedder,
    corpus_fingerprint,
)
from app.knowledge.index.models import CHUNKER_VERSION

DOC_A_TEXT = "# เอกสาร ก\n\n## ส่วนบริการ\n\n" + "ค่าไฟฟ้าและการชำระเงิน " * 30 + "\n"
DOC_B_TEXT = "# เอกสาร ข\n\n## ส่วนบริการ\n\n" + "การติดตั้งมิเตอร์ใหม่ " * 30 + "\n"
DOC_C_TEXT = "# เอกสาร ค\n\n## ส่วนบริการ\n\n" + "คำค้นเฉพาะทางพิเศษสำหรับทดสอบ " * 20 + "\n"
QA_FILE = (
    "# ถาม: การขอใช้ไฟฟ้าใหม่ต้องทำอย่างไร | คำถามใกล้เคียง: ขอไฟใหม่ทำอย่างไร\n\n"
    "## สถานะหลักฐาน\n\nตรง\n\n"
    "## ตอบ\n\nยื่นคำขอที่สำนักงานการไฟฟ้าในพื้นที่พร้อมเอกสารประกอบ\n\n"
    "## แหล่งอ้างอิงทางการ\n\nhttps://www.pea.co.th/faqs\n"
)
DOC_A_MARKER = "ค่าไฟฟ้าและการชำระเงิน"


class CountingEmbedder:
    """``FakeEmbedder`` wrapper recording every document batch it is asked to embed."""

    def __init__(self, *, dim: int = 64, model_id: str | None = None) -> None:
        self._inner = FakeEmbedder(dim)
        self._model_id = model_id or self._inner.model_id
        self.calls: list[list[str]] = []
        self.query_count = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._inner.dim

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        batch = list(texts)
        self.calls.append(batch)
        return self._inner.embed_documents(batch)

    def embed_query(self, text: str) -> np.ndarray:
        self.query_count += 1
        return self._inner.embed_query(text)

    @property
    def embedded_texts(self) -> list[str]:
        return [text for batch in self.calls for text in batch]

    def reset(self) -> None:
        self.calls.clear()
        self.query_count = 0


class ToggleFailingEmbedder(CountingEmbedder):
    """Counting embedder that can be switched to fail, to exercise rebuild failures."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fail = False

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if self.fail:
            raise RuntimeError("embedder unavailable")
        return super().embed_documents(texts)


_MANAGERS: list[IndexManager] = []


@pytest.fixture(autouse=True)
def _stop_managers_after_each_test():
    """Never leak watcher/build threads when a test fails before calling stop()."""
    yield
    while _MANAGERS:
        _MANAGERS.pop().stop()


def _write_files(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def make_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Create a throwaway source root and matching alias root."""
    source = tmp_path / "source"
    aliases = tmp_path / "aliases"
    _write_files(
        source,
        {"PEA_ก.md": DOC_A_TEXT, "PEA_ข.md": DOC_B_TEXT, "qa/qa_ทดสอบ.md": QA_FILE},
    )
    aliases.mkdir(parents=True, exist_ok=True)
    return source, aliases


def make_manager(
    tmp_path: Path,
    *,
    source_root: Path | None = None,
    alias_root: Path | None = None,
    embedder: Embedder | None = None,
    watch: bool = False,
    debounce_ms: int = 30,
    poll_interval_s: float = 0.02,
    **kwargs: Any,
) -> IndexManager:
    source = source_root if source_root is not None else make_corpus(tmp_path)[0]
    manager = IndexManager(
        source_root=source,
        alias_root=alias_root,
        index_dir=tmp_path / "index",
        embedder=embedder if embedder is not None else CountingEmbedder(),
        watch=watch,
        debounce_ms=debounce_ms,
        poll_interval_s=poll_interval_s,
        **kwargs,
    )
    _MANAGERS.append(manager)
    return manager


def wait_for(predicate: Callable[[], bool], *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before the timeout")


def wait_ready(manager: IndexManager) -> None:
    manager.start()
    wait_for(lambda: manager.health().status is IndexState.READY)


def test_manager_reports_building_then_ready(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    assert manager.health().status is IndexState.BUILDING
    assert manager.health().documents == 0
    assert manager.searcher is None

    wait_ready(manager)

    health = manager.health()
    assert health.status is IndexState.READY
    assert health.documents == 3
    assert health.chunks > 0
    assert manager.searcher is not None
    manager.stop()


def test_search_before_ready_raises_unavailable(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    with pytest.raises(IndexUnavailableError) as info:
        manager.search("ค่าไฟฟ้า")

    assert info.value.code == "unavailable"
    assert manager.health().status is IndexState.BUILDING
    assert manager.searcher is None


def test_search_after_ready_returns_approved_results(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    wait_ready(manager)

    result = manager.search("การขอใช้ไฟฟ้าใหม่ต้องทำอย่างไร")

    assert result.qa
    assert result.qa[0].source_id == "qa/qa_ทดสอบ.md"
    manager.stop()


def test_second_start_loads_from_cache_without_re_embedding(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    first = CountingEmbedder()
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=first)
    wait_ready(manager)
    manager.stop()
    assert first.embedded_texts, "the first build must embed the corpus"

    second = CountingEmbedder()
    manager2 = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=second)
    wait_ready(manager2)

    assert second.embedded_texts == [], "an unchanged corpus must be served from cache"
    manager2.stop()


def test_chunker_version_change_invalidates_the_cache(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    first = CountingEmbedder()
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, embedder=first, chunker_version="v1"
    )
    wait_ready(manager)
    manager.stop()
    assert first.embedded_texts

    second = CountingEmbedder()
    manager2 = make_manager(
        tmp_path, source_root=source, alias_root=aliases, embedder=second, chunker_version="v2"
    )
    wait_ready(manager2)

    assert len(second.embedded_texts) == len(first.embedded_texts)
    manager2.stop()


def test_embedder_model_id_change_invalidates_the_cache(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    first = CountingEmbedder(model_id="fake-hash-v1-64")
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=first)
    wait_ready(manager)
    manager.stop()

    second = CountingEmbedder(model_id="fake-hash-v2-64")
    manager2 = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=second)
    wait_ready(manager2)

    assert len(second.embedded_texts) == len(first.embedded_texts)
    manager2.stop()


def test_incremental_rebuild_embeds_only_changed_chunks(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    embedder = CountingEmbedder()
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=embedder)
    wait_ready(manager)
    total_texts = len(embedder.embedded_texts)
    assert total_texts > 0

    embedder.reset()
    (source / "PEA_ข.md").write_text(
        "# เอกสาร ข\n\n## ส่วนบริการ\n\n" + "การติดตั้งมิเตอร์ใหม่และค่าใช้จ่าย " * 30 + "\n",
        encoding="utf-8",
    )

    assert manager.refresh_if_stale() is True
    assert manager.health().status is IndexState.READY

    reembedded = embedder.embedded_texts
    assert reembedded, "the edited document must be re-embedded"
    assert len(reembedded) < total_texts, "unchanged chunks must come from the cache"
    assert all(DOC_A_MARKER not in text for text in reembedded)
    manager.stop()


@pytest.mark.parametrize("damage", ["header", "vectors"])
def test_corrupt_cache_is_ignored_and_rebuilt(tmp_path: Path, damage: str) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases)
    wait_ready(manager)
    manager.stop()

    cache_dir = tmp_path / "index"
    assert (cache_dir / CACHE_HEADER_NAME).is_file()
    assert (cache_dir / CACHE_VECTORS_NAME).is_file()
    if damage == "header":
        (cache_dir / CACHE_HEADER_NAME).write_text("not json", encoding="utf-8")
    else:
        (cache_dir / CACHE_VECTORS_NAME).write_bytes(b"definitely not an npy matrix")

    embedder = CountingEmbedder()
    manager2 = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=embedder)
    wait_ready(manager2)

    assert embedder.embedded_texts, "a corrupt cache must trigger a full rebuild"
    header = json.loads((cache_dir / CACHE_HEADER_NAME).read_text(encoding="utf-8"))
    assert header["cacheVersion"] == CACHE_FORMAT_VERSION
    manager2.stop()


def test_cache_directory_holds_only_safe_formats(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    wait_ready(manager)
    manager.stop()

    names = {path.name for path in (tmp_path / "index").iterdir()}
    assert names == {CACHE_HEADER_NAME, CACHE_VECTORS_NAME}
    assert not any(path.suffix in {".pkl", ".pickle"} for path in (tmp_path / "index").iterdir())


def test_failed_rebuild_keeps_last_good_index_and_reports_stale(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    embedder = ToggleFailingEmbedder()
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=embedder)
    wait_ready(manager)
    good_health = manager.health()
    good_sources = [chunk.source_id for chunk in manager.search(DOC_A_MARKER).chunks]

    embedder.fail = True
    (source / "PEA_ก.md").write_text(
        "# เอกสาร ก\n\n## ส่วนบริการ\n\n" + "เนื้อหาใหม่ที่ต้องฝัง " * 30 + "\n",
        encoding="utf-8",
    )

    assert manager.refresh_if_stale() is False
    assert manager.health().status is IndexState.STALE
    assert manager.health().documents == good_health.documents
    assert manager.health().chunks == good_health.chunks
    assert [chunk.source_id for chunk in manager.search(DOC_A_MARKER).chunks] == good_sources
    manager.stop()


def test_failed_initial_build_reports_error_and_recovers(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    embedder = ToggleFailingEmbedder()
    embedder.fail = True
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases, embedder=embedder)
    manager.start()
    wait_for(lambda: manager.health().status is IndexState.ERROR)

    assert manager.health().documents == 0
    with pytest.raises(IndexUnavailableError):
        manager.search(DOC_A_MARKER)

    embedder.fail = False
    assert manager.refresh_if_stale() is True
    assert manager.health().status is IndexState.READY
    manager.stop()


def test_added_file_is_indexed_after_debounce(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, watch=True, poll_interval_s=0.02
    )
    wait_ready(manager)

    (source / "PEA_ค.md").write_text(DOC_C_TEXT, encoding="utf-8")

    wait_for(lambda: manager.health().documents == 4)
    result = manager.search("คำค้นเฉพาะทางพิเศษสำหรับทดสอบ")
    assert any(hit.source_id == "PEA_ค.md" for hit in result.chunks)
    manager.stop()


def test_edited_file_is_indexed_after_debounce(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, watch=True, poll_interval_s=0.02
    )
    wait_ready(manager)
    previous = manager.searcher

    marker = "รหัสทดสอบแก้ไขพิเศษ"
    (source / "PEA_ก.md").write_text(
        f"# เอกสาร ก\n\n## ส่วนบริการ\n\n{marker} " + "ค่าไฟฟ้า " * 30 + "\n",
        encoding="utf-8",
    )

    wait_for(lambda: manager.searcher is not previous)
    assert manager.searcher is not None
    assert any(marker in chunk.text for chunk in manager.searcher.chunks)
    manager.stop()


def test_deleted_file_is_removed_after_debounce(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, watch=True, poll_interval_s=0.02
    )
    wait_ready(manager)
    previous = manager.searcher

    (source / "PEA_ข.md").unlink()

    wait_for(lambda: manager.searcher is not previous)
    assert manager.health().documents == 2
    assert manager.searcher is not None
    assert all(chunk.source_id != "PEA_ข.md" for chunk in manager.searcher.chunks)
    manager.stop()


def test_alias_file_change_triggers_rebuild(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, watch=True, poll_interval_s=0.02
    )
    wait_ready(manager)
    previous = manager.searcher

    (aliases / "rule.md").write_text(
        "---\nid: kho-fai\naliases:\n  - ขอไฟ\n  - ขอใช้ไฟฟ้าใหม่\n"
        "sourceIds:\n  - PEA_ก.md\n---\n",
        encoding="utf-8",
    )

    wait_for(lambda: manager.searcher is not previous)
    assert manager.health().documents == 3
    manager.stop()


def test_fingerprint_check_ignores_non_knowledge_changes(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases)
    wait_ready(manager)

    (source / "notes.txt").write_text("not knowledge", encoding="utf-8")
    assert manager.refresh_if_stale() is False

    doc = source / "PEA_ก.md"
    stat = doc.stat()
    os.utime(doc, (stat.st_atime, stat.st_mtime + 100))
    assert manager.refresh_if_stale() is False, "mtime-only changes must not rebuild"
    manager.stop()


def test_watcher_stops_cleanly(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    manager = make_manager(
        tmp_path, source_root=source, alias_root=aliases, watch=True, poll_interval_s=0.02
    )
    wait_ready(manager)

    manager.stop()

    assert not manager._started
    assert not any(
        thread.name.startswith("knowledge-index") for thread in threading.enumerate()
    )


def test_build_writes_only_inside_the_index_directory(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in source.rglob("*"))
    manager = make_manager(tmp_path, source_root=source, alias_root=aliases)
    wait_ready(manager)
    manager.stop()

    assert sorted(path.relative_to(tmp_path) for path in source.rglob("*")) == before
    assert (tmp_path / "index").is_dir()


def test_corpus_fingerprint_tracks_content_and_aliases(tmp_path: Path) -> None:
    source, aliases = make_corpus(tmp_path)
    catalog = KnowledgeCatalog(source, alias_root=aliases)
    base = corpus_fingerprint(
        catalog, aliases, chunker_version=CHUNKER_VERSION, model_id="fake-hash-v1-64"
    )

    (aliases / "rule.md").write_text(
        "---\nid: r\naliases:\n  - ก\nsourceIds:\n  - PEA_ก.md\n---\n", encoding="utf-8"
    )
    with_alias = corpus_fingerprint(
        KnowledgeCatalog(source, alias_root=aliases),
        aliases,
        chunker_version=CHUNKER_VERSION,
        model_id="fake-hash-v1-64",
    )
    assert with_alias != base

    (source / "PEA_ก.md").write_text(DOC_A_TEXT.replace("ค่าไฟฟ้า", "ไฟฟ้าใหม่"), encoding="utf-8")
    edited = corpus_fingerprint(
        KnowledgeCatalog(source, alias_root=aliases),
        aliases,
        chunker_version=CHUNKER_VERSION,
        model_id="fake-hash-v1-64",
    )
    assert edited != with_alias


def test_build_embedder_defaults_to_bge_m3_and_supports_fake() -> None:
    assert isinstance(build_embedder("fake"), FakeEmbedder)
    real = build_embedder("bge-m3")
    assert isinstance(real, BgeM3Embedder)
    assert real.model_id == "BAAI/bge-m3"
    assert real.dim == 1024
    with pytest.raises(ValueError):
        build_embedder("gemini-embedding")


def test_test_suite_forces_the_offline_embedder() -> None:
    """Guard: the suite must never load torch or write the cache into the repository."""
    import sys

    from app import main

    assert isinstance(main.knowledge_index_manager, IndexManager)
    assert isinstance(main.knowledge_index_manager.embedder, FakeEmbedder)
    assert "torch" not in sys.modules
    root = Path(__file__).resolve().parents[2]
    assert not main.settings.knowledge_index_dir.is_relative_to(root)
