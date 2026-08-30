"""Tests for scripts/sync_knowledge.py (authoritative-source policy, manifest diff, CLI, provider seam).

The fail-closed source policy under test: only files under
``<corpus root>/source/**`` are ever syncable. Default corpus root is
``<repo>/knowledge`` so the default run covers exactly ``knowledge/source/**``
with the manifest at ``knowledge/manifest.json``. README/metadata files,
sample docs, hidden files, and the manifest are never uploaded, at any depth.
The repository intentionally ships no PEA content in ``source/``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync_knowledge.py"

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


def make_source_corpus(root: Path, files: dict[str, str]) -> None:
    """Write syncable sources into the corpus's source/ subtree."""
    make_corpus(root, {f"source/{rel}": content for rel, content in files.items()})


def args_for(corpus: Path, *extra: str):
    return sync_mod.parse_args(["--root", str(corpus), *extra])


# --- default layout constants ------------------------------------------------

def test_default_root_and_manifest_point_at_knowledge_tree() -> None:
    # Default corpus root is <repo>/knowledge; default manifest stays at
    # knowledge/manifest.json; the syncable subtree is knowledge/source/**.
    assert sync_mod.DEFAULT_CORPUS_ROOT == REPO_ROOT / "knowledge"
    assert sync_mod.DEFAULT_CORPUS_ROOT / sync_mod.MANIFEST_NAME == REPO_ROOT / "knowledge" / "manifest.json"
    assert (sync_mod.DEFAULT_CORPUS_ROOT / sync_mod.SOURCE_DIR_NAME).is_dir()
    # The shipped corpus carries no uploadable sources (placeholder only).
    assert sync_mod.discover_sources(sync_mod.DEFAULT_CORPUS_ROOT) == []


# --- discovery ---------------------------------------------------------------

def test_discover_only_source_subtree_is_syncable(tmp_path) -> None:
    make_corpus(
        tmp_path,
        {
            "source/a.md": "a",
            "source/sub/b.txt": "b",
            # sample docs / documentation / metadata: never uploadable
            "docs/pea-electricity-rates.md": "sample",
            "README.md": "readme",
            "source/README.md": "placeholder",
            "manifest.json": "{}",
            "source/manifest.json": "{}",
            "tests/test_x.py": "code",
            # hidden files and non-document suffixes: never uploadable
            ".hidden/c.md": "h",
            "source/.secret.md": "s",
            "source/.gitkeep": "",
            "source/skip.bin": "x",
        },
    )
    found = {source.rel_path for source in sync_mod.discover_sources(tmp_path)}
    assert found == {"source/a.md", "source/sub/b.txt"}


def test_discover_excludes_readme_in_any_case(tmp_path) -> None:
    make_corpus(
        tmp_path,
        {
            "source/a.md": "a",
            "source/README.md": "upper",
            "source/readme.md": "lower",
            "source/ReadMe.MD": "mixed",
        },
    )
    found = {source.rel_path for source in sync_mod.discover_sources(tmp_path)}
    assert found == {"source/a.md"}


def test_discover_missing_source_dir_fails_closed(tmp_path) -> None:
    # A corpus root without source/ must error, never silently sync nothing.
    make_corpus(tmp_path, {"README.md": "readme", "docs/a.md": "sample"})
    try:
        sync_mod.discover_sources(tmp_path)
    except sync_mod.UsageError as exc:
        assert "source" in str(exc)
    else:
        raise AssertionError("expected UsageError")


def test_discover_file_scope_uses_exact_source_paths(tmp_path) -> None:
    make_source_corpus(tmp_path, {"a.md": "a", "b.md": "b"})
    found = {source.rel_path for source in sync_mod.discover_sources(tmp_path, ("source/b.md",))}
    assert found == {"source/b.md"}
    # sample-doc style paths and prefix-less paths are not syncable
    for bad in ("docs/b.md", "b.md", "source/missing.md"):
        try:
            sync_mod.discover_sources(tmp_path, (bad,))
        except sync_mod.UsageError as exc:
            assert bad in str(exc)
        else:
            raise AssertionError(f"expected UsageError for {bad}")


# --- planning ----------------------------------------------------------------

def _manifest_entry(sha: str, doc: str) -> dict:
    return {"sha256": sha, "sizeBytes": 1, "documentName": doc, "uploadedAt": "2026-01-01T00:00:00Z"}


def test_build_plan_new_changed_unchanged_forced(tmp_path) -> None:
    make_source_corpus(tmp_path, {"a.md": "a", "b.md": "changed", "c.md": "c"})
    local = sync_mod.discover_sources(tmp_path)
    manifest_files = {
        "source/a.md": _manifest_entry(local[0].sha256, "doc-a"),
        "source/b.md": _manifest_entry("stale-hash", "doc-b"),
    }
    plan = sync_mod.build_plan(local, manifest_files)
    assert [item.kind for item in plan.uploads] == ["changed", "new"]
    assert [item.rel_path for item in plan.uploads] == ["source/b.md", "source/c.md"]
    assert plan.unchanged == ("source/a.md",)
    assert plan.prune == ()

    forced = sync_mod.build_plan(local, manifest_files, force=True)
    # --force re-uploads everything tracked in the manifest; kind is "forced".
    assert {item.kind for item in forced.uploads} == {"forced", "new"}


def test_build_plan_prune_candidates(tmp_path) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    local = sync_mod.discover_sources(tmp_path)
    manifest_files = {
        "source/a.md": _manifest_entry(local[0].sha256, "doc-a"),
        "source/gone.md": _manifest_entry("x", "doc-gone"),
    }
    plan = sync_mod.build_plan(local, manifest_files)
    assert plan.prune == (sync_mod.PruneItem("source/gone.md", "doc-gone"),)
    # scoped runs never produce prune candidates
    scoped = sync_mod.build_plan(local, manifest_files, scope=("source/a.md",))
    assert scoped.prune == ()


def test_stale_pre_repair_manifest_entries_become_prune_candidates(tmp_path) -> None:
    # Pre-repair manifests tracked unsourced docs/ uploads; under the new
    # source-only discovery those entries are stale and can be pruned, so
    # previously uploaded fabricated documents can be removed from the store.
    make_source_corpus(tmp_path, {"a.md": "a"})
    local = sync_mod.discover_sources(tmp_path)
    manifest_files = {
        "source/a.md": _manifest_entry(local[0].sha256, "doc-a"),
        "docs/pea-electricity-rates.md": _manifest_entry("x", "doc-fabricated"),
    }
    plan = sync_mod.build_plan(local, manifest_files)
    assert plan.prune == (sync_mod.PruneItem("docs/pea-electricity-rates.md", "doc-fabricated"),)


# --- run_sync ----------------------------------------------------------------

def test_dry_run_has_no_side_effects(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    provider = FakeProvider()
    code = sync_mod.run_sync(args_for(tmp_path, "--dry-run"), provider=provider)
    out = capsys.readouterr().out
    assert code == 0
    assert "[dry-run]" in out
    assert "upload new: source/a.md" in out
    assert provider.uploaded == []
    assert not (tmp_path / "manifest.json").exists()


def test_up_to_date_does_nothing_and_needs_no_provider(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    manifest_path = tmp_path / "manifest.json"
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {"source/a.md": _manifest_entry(sync_mod.compute_sha256(tmp_path / "source/a.md"), "doc-a")},
    )
    before = manifest_path.read_text()
    code = sync_mod.run_sync(args_for(tmp_path), provider=None)  # no SDK needed
    out = capsys.readouterr().out
    assert code == 0
    assert "up to date" in out
    assert manifest_path.read_text() == before


def test_default_repo_run_uploads_nothing(capsys) -> None:
    # The shipped repository carries no approved exports: a default run
    # (no --root) must upload nothing and write no manifest.
    manifest_path = sync_mod.DEFAULT_CORPUS_ROOT / sync_mod.MANIFEST_NAME
    assert not manifest_path.exists()
    provider = FakeProvider()
    code = sync_mod.run_sync(sync_mod.parse_args([]), provider=provider)
    out = capsys.readouterr().out
    assert code == 0
    assert "up to date" in out
    assert provider.uploaded == []
    assert not manifest_path.exists()


def test_full_sync_uploads_only_new_and_changed(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a", "b.md": "changed", "c.md": "c"})
    provider = FakeProvider()
    manifest_path = tmp_path / "manifest.json"
    a_sha = sync_mod.compute_sha256(tmp_path / "source/a.md")
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {
            "source/a.md": _manifest_entry(a_sha, "doc-a-old"),
            "source/b.md": _manifest_entry("stale", "doc-b-old"),
        },
    )
    code = sync_mod.run_sync(args_for(tmp_path), provider=provider)
    assert code == 0
    assert provider.uploaded == ["source/b.md", "source/c.md"]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["storeName"] == "fileSearchStores/test"
    assert manifest["files"]["source/a.md"]["documentName"] == "doc-a-old"  # untouched
    assert manifest["files"]["source/b.md"]["documentName"] == "fileSearchStores/test/documents/doc1"
    assert manifest["files"]["source/c.md"]["documentName"] == "fileSearchStores/test/documents/doc2"
    assert set(manifest["files"]["source/b.md"]) == {"sha256", "sizeBytes", "documentName", "uploadedAt"}


def test_prune_requires_both_flags(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    provider = FakeProvider()
    manifest_path = tmp_path / "manifest.json"
    a_sha = sync_mod.compute_sha256(tmp_path / "source/a.md")
    sync_mod.write_manifest(
        manifest_path,
        "fileSearchStores/test",
        {
            "source/a.md": _manifest_entry(a_sha, "doc-a"),
            "source/gone.md": _manifest_entry("x", "doc-gone"),
        },
    )
    # --prune without --yes: nothing is deleted
    code = sync_mod.run_sync(args_for(tmp_path, "--prune"), provider=provider)
    out = capsys.readouterr().out
    assert code == 0
    assert provider.deleted == []
    assert "--yes" in out
    assert "source/gone.md" in json.loads(manifest_path.read_text())["files"]

    # --prune --yes: the stale remote document is deleted and the entry removed
    code = sync_mod.run_sync(args_for(tmp_path, "--prune", "--yes"), provider=provider)
    assert code == 0
    assert provider.deleted == ["doc-gone"]
    assert "source/gone.md" not in json.loads(manifest_path.read_text())["files"]


def test_root_without_source_dir_is_usage_error(tmp_path) -> None:
    make_corpus(tmp_path, {"README.md": "readme", "docs/a.md": "sample"})
    code = sync_mod.main(["--root", str(tmp_path), "--dry-run"])
    assert code == 2


def test_verbose_reports_per_file_progress(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    provider = FakeProvider()
    sync_mod.run_sync(args_for(tmp_path, "--verbose"), provider=provider)
    out = capsys.readouterr().out
    assert "uploading source/a.md" in out
    assert "uploaded source/a.md" in out


def test_main_returns_exit_codes(tmp_path, capsys) -> None:
    make_source_corpus(tmp_path, {"a.md": "a"})
    assert sync_mod.main(["--root", str(tmp_path), "--dry-run"]) == 0
    # missing --file target -> usage error (exit 2)
    assert sync_mod.main(["--root", str(tmp_path), "--file", "source/nope.md"]) == 2
    # prefix-less / sample-doc paths are not syncable sources (exit 2)
    assert sync_mod.main(["--root", str(tmp_path), "--file", "docs/a.md"]) == 2
    # nothing to do but provider required would be a mistake: up-to-date is exit 0
    assert sync_mod.main(["--root", str(tmp_path), "--file", "source/a.md", "--dry-run"]) == 0
