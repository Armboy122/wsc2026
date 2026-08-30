"""Tests for scripts/sync_knowledge.py (manifest diff, CLI, provider seam)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sync_knowledge.py"

_spec = importlib.util.spec_from_file_location("sync_knowledge", SCRIPT_PATH)
sync_mod = importlib.util.module_from_spec(_spec)
# Register the module before exec so dataclasses can resolve its __module__.
sys.modules.setdefault("sync_knowledge", sync_mod)
assert _spec.loader is not None
_spec.loader.exec_module(sync_mod)


class FakeProvider:
    def __init__(self):
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self._counter = 0

    def upload(self, local_path: Path, rel_path: str) -> str:
        assert local_path.is_file()
        self.uploaded.append(rel_path)
        self._counter += 1
        return f"fileSearchStores/test/documents/doc{self._counter}"

    def delete_document(self, document_name: str) -> None:
        self.deleted.append(document_name)


def make_corpus(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def args_for(corpus: Path, *extra: str):
    return sync_mod.parse_args(["--root", str(corpus), *extra])


# --- discovery ---------------------------------------------------------------

def test_discover_skips_hidden_manifest_readme_and_bad_suffix(tmp_path) -> None:
    make_corpus(
        tmp_path,
        {
            "docs/a.md": "a",
            "docs/b.txt": "b",
            "docs/skip.bin": "x",
            ".hidden/c.md": "h",
            "docs/.secret.md": "s",
            "manifest.json": "{}",
            "README.md": "readme",
        },
    )
    found = {source.rel_path for source in sync_mod.discover_sources(tmp_path)}
    assert found == {"docs/a.md", "docs/b.txt"}


def test_discover_file_scope_validates_paths(tmp_path) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a", "docs/b.md": "b"})
    found = {source.rel_path for source in sync_mod.discover_sources(tmp_path, ("docs/b.md",))}
    assert found == {"docs/b.md"}
    try:
        sync_mod.discover_sources(tmp_path, ("docs/missing.md",))
    except sync_mod.UsageError as exc:
        assert "docs/missing.md" in str(exc)
    else:
        raise AssertionError("expected UsageError")


# --- planning ----------------------------------------------------------------

def _manifest_entry(sha: str, doc: str) -> dict:
    return {"sha256": sha, "sizeBytes": 1, "documentName": doc, "uploadedAt": "2026-01-01T00:00:00Z"}


def test_build_plan_new_changed_unchanged_forced(tmp_path) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a", "docs/b.md": "changed", "docs/c.md": "c"})
    local = sync_mod.discover_sources(tmp_path)
    manifest_files = {
        "docs/a.md": _manifest_entry(local[0].sha256, "doc-a"),
        "docs/b.md": _manifest_entry("stale-hash", "doc-b"),
    }
    plan = sync_mod.build_plan(local, manifest_files)
    assert [item.kind for item in plan.uploads] == ["changed", "new"]
    assert [item.rel_path for item in plan.uploads] == ["docs/b.md", "docs/c.md"]
    assert plan.unchanged == ("docs/a.md",)
    assert plan.prune == ()

    forced = sync_mod.build_plan(local, manifest_files, force=True)
    # --force re-uploads everything tracked in the manifest; kind is "forced".
    assert {item.kind for item in forced.uploads} == {"forced", "new"}


def test_build_plan_prune_candidates(tmp_path) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    local = sync_mod.discover_sources(tmp_path)
    manifest_files = {
        "docs/a.md": _manifest_entry(local[0].sha256, "doc-a"),
        "docs/gone.md": _manifest_entry("x", "doc-gone"),
    }
    plan = sync_mod.build_plan(local, manifest_files)
    assert plan.prune == (sync_mod.PruneItem("docs/gone.md", "doc-gone"),)
    # scoped runs never produce prune candidates
    scoped = sync_mod.build_plan(local, manifest_files, scope=("docs/a.md",))
    assert scoped.prune == ()


# --- run_sync ----------------------------------------------------------------

def test_dry_run_has_no_side_effects(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    provider = FakeProvider()
    code = sync_mod.run_sync(args_for(tmp_path, "--dry-run"), provider=provider)
    out = capsys.readouterr().out
    assert code == 0
    assert "[dry-run]" in out
    assert "upload new: docs/a.md" in out
    assert provider.uploaded == []
    assert not (tmp_path / "manifest.json").exists()


def test_up_to_date_does_nothing_and_needs_no_provider(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    manifest_path = tmp_path / "manifest.json"
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {"docs/a.md": _manifest_entry(sync_mod.compute_sha256(tmp_path / "docs/a.md"), "doc-a")},
    )
    before = manifest_path.read_text()
    code = sync_mod.run_sync(args_for(tmp_path), provider=None)  # no SDK needed
    out = capsys.readouterr().out
    assert code == 0
    assert "up to date" in out
    assert manifest_path.read_text() == before


def test_full_sync_uploads_only_new_and_changed(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a", "docs/b.md": "changed", "docs/c.md": "c"})
    provider = FakeProvider()
    manifest_path = tmp_path / "manifest.json"
    a_sha = sync_mod.compute_sha256(tmp_path / "docs/a.md")
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {
            "docs/a.md": _manifest_entry(a_sha, "doc-a-old"),
            "docs/b.md": _manifest_entry("stale", "doc-b-old"),
        },
    )
    code = sync_mod.run_sync(args_for(tmp_path), provider=provider)
    assert code == 0
    assert provider.uploaded == ["docs/b.md", "docs/c.md"]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["storeName"] == "fileSearchStores/test"
    assert manifest["files"]["docs/a.md"]["documentName"] == "doc-a-old"  # untouched
    assert manifest["files"]["docs/b.md"]["documentName"] == "fileSearchStores/test/documents/doc1"
    assert manifest["files"]["docs/c.md"]["documentName"] == "fileSearchStores/test/documents/doc2"
    assert set(manifest["files"]["docs/b.md"]) == {"sha256", "sizeBytes", "documentName", "uploadedAt"}


def test_prune_requires_both_flags(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    provider = FakeProvider()
    manifest_path = tmp_path / "manifest.json"
    a_sha = sync_mod.compute_sha256(tmp_path / "docs/a.md")
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {
            "docs/a.md": _manifest_entry(a_sha, "doc-a"),
            "docs/gone.md": _manifest_entry("x", "doc-gone"),
        },
    )
    # --prune without --yes: nothing is deleted
    code = sync_mod.run_sync(args_for(tmp_path, "--prune"), provider=provider)
    out = capsys.readouterr().out
    assert code == 0
    assert provider.deleted == []
    assert "--yes" in out
    assert "docs/gone.md" in json.loads(manifest_path.read_text())["files"]

    # --prune --yes: the stale remote document is deleted and the entry removed
    code = sync_mod.run_sync(args_for(tmp_path, "--prune", "--yes"), provider=provider)
    assert code == 0
    assert provider.deleted == ["doc-gone"]
    assert "docs/gone.md" not in json.loads(manifest_path.read_text())["files"]


def test_verbose_reports_per_file_progress(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    provider = FakeProvider()
    sync_mod.run_sync(args_for(tmp_path, "--verbose"), provider=provider)
    out = capsys.readouterr().out
    assert "uploading docs/a.md" in out
    assert "uploaded docs/a.md" in out


def test_main_returns_exit_codes(tmp_path, capsys) -> None:
    make_corpus(tmp_path, {"docs/a.md": "a"})
    assert sync_mod.main(["--root", str(tmp_path), "--dry-run"]) == 0
    # missing --file target -> usage error (exit 2)
    assert sync_mod.main(["--root", str(tmp_path), "--file", "docs/nope.md"]) == 2
    # nothing to do but provider required would be a mistake: up-to-date is exit 0
    assert sync_mod.main(["--root", str(tmp_path), "--file", "docs/a.md", "--dry-run"]) == 0
