"""Tests for scripts/sync_knowledge.py (authoritative-source policy, manifest diff, CLI, provider seam).

The fail-closed source policy under test: only files under
``<corpus root>/source/**`` are ever syncable. Default corpus root is
``<repo>/knowledge`` so the default run covers exactly ``knowledge/source/**``
with the manifest at ``knowledge/manifest.json``. README/metadata files,
sample docs, hidden files, and the manifest are never uploaded, at any depth.
Tests must not depend on the shipped corpus contents: empty-corpus behavior is
exercised against tmp_path corpora, never against ``DEFAULT_CORPUS_ROOT``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

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
    # Corpus-state independent: the shipped source/ may hold approved exports
    # or only placeholders; discovery must never reach outside source/**.
    for source in sync_mod.discover_sources(sync_mod.DEFAULT_CORPUS_ROOT):
        assert source.rel_path.startswith(sync_mod.SOURCE_DIR_NAME + "/")


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


def test_empty_source_corpus_uploads_nothing_and_writes_no_manifest(tmp_path, capsys) -> None:
    # A corpus whose source/ holds only the excluded placeholder README has no
    # syncable files: the run must upload nothing and write no manifest. This
    # uses tmp_path instead of DEFAULT_CORPUS_ROOT so the result is independent
    # of whatever approved exports the repository currently ships in source/.
    make_corpus(tmp_path, {"source/README.md": "placeholder"})
    manifest_path = tmp_path / sync_mod.MANIFEST_NAME
    assert not manifest_path.exists()
    provider = FakeProvider()
    code = sync_mod.run_sync(args_for(tmp_path), provider=provider)
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


# --- provider upload seam: Unicode-safe display names + MIME-safe upload -----
#
# Live repro 1 (google-genai 1.x and 2.19.0): syncing a Thai-named source
# such as ``source/01_PEA_SabuyService_ขอใช้ไฟฟ้าใหม่.docx`` crashed with
# httpx UnicodeEncodeError while ASCII-encoding request headers: the SDK
# copies the local file's basename into the ASCII-only
# ``X-Goog-Upload-File-Name`` header when ``file=`` is a path, and the sync
# passed the raw corpus-relative path as ``display_name``.
# Live repro 2: the first repair streamed a binary handle with an explicit
# ``config.mime_type``; the header leak was gone but Gemini answered
# 400 INVALID_ARGUMENT: UploadToFileSearchStoreRequest.mime_type invalid
# for ``application/vnd.openxmlformats-officedocument.wordprocessingml.document``,
# because the SDK copies ``config.mime_type`` into the request body, which
# the API rejects for that value.
# Final contract pinned below: the provider uploads an ASCII-named temporary
# copy of the source (same suffix, same bytes) and never sets
# ``config.mime_type`` — the SDK infers the MIME type from the ASCII path
# for the upload header only. The temp file is removed on success and on
# every failure path. ASCII display names and UTF-8 custom_metadata survive.

THAI_REL = "source/01_PEA_SabuyService_ขอใช้ไฟฟ้าใหม่.docx"


def install_fake_genai(monkeypatch, *, fail: BaseException | None = None, error: dict | None = None) -> dict:
    """Replace the lazy SDK import with a capture-only fake client.

    Returns the dict that records the kwargs of the single
    ``upload_to_file_search_store`` call (``file`` and ``config``; the fake
    config/metadata constructors are plain dicts so the captured values are
    directly assertable). When ``file=`` is a path, the fake also records
    whether the file existed at call time and its exact bytes, so tests can
    verify the temporary-copy contract. ``fail`` makes the SDK call raise
    (simulating a transport/SDK error); ``error`` makes the returned
    operation carry a provider error (simulating a 400 LRO response).
    """
    captured: dict = {}

    class FakeStores:
        def upload_to_file_search_store(self, **kwargs):
            captured.update(kwargs)
            file_arg = kwargs.get("file")
            if isinstance(file_arg, (str, Path)):
                sent = Path(file_arg)
                captured["file_existed_at_call"] = sent.is_file()
                if sent.is_file():
                    captured["file_bytes_at_call"] = sent.read_bytes()
            if fail is not None:
                raise fail
            return types.SimpleNamespace(
                done=True,
                error=error,
                response=types.SimpleNamespace(
                    document_name="fileSearchStores/test/documents/doc-live"
                ),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.file_search_stores = FakeStores()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = types.SimpleNamespace(
        UploadToFileSearchStoreConfig=lambda **kw: dict(kw),
        CustomMetadata=lambda **kw: dict(kw),
    )
    monkeypatch.setattr(sync_mod, "_import_genai", lambda: fake_genai)
    return captured


def make_doc(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PK fake docx bytes")
    return path


def test_upload_thai_path_sends_ascii_display_name(monkeypatch, tmp_path) -> None:
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    doc = make_doc(tmp_path, THAI_REL)
    document_name = provider.upload(doc, THAI_REL)
    assert document_name == "fileSearchStores/test/documents/doc-live"
    display = captured["config"]["display_name"]
    display.encode("ascii")  # must never raise: headers must stay ASCII-safe
    assert "01_PEA_SabuyService" in display  # recognizable ASCII part kept
    assert display.endswith(".docx")  # ASCII suffix kept where possible
    assert "ขอ" not in display
    # deterministic: the same path always yields the same display name
    provider.upload(doc, THAI_REL)
    assert captured["config"]["display_name"] == display


def test_upload_two_same_skeleton_paths_cannot_collide(monkeypatch, tmp_path) -> None:
    # Both Thai file names reduce to the same ASCII skeleton; the path-hash
    # suffix must keep the remote display names distinct.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    rel_a = "source/ไฟฟ้า.md"
    rel_b = "source/สายดิน.md"
    provider.upload(make_doc(tmp_path, rel_a), rel_a)
    name_a = captured["config"]["display_name"]
    provider.upload(make_doc(tmp_path, rel_b), rel_b)
    name_b = captured["config"]["display_name"]
    name_a.encode("ascii")
    name_b.encode("ascii")
    assert name_a != name_b


def test_upload_carries_original_utf8_path_in_custom_metadata(monkeypatch, tmp_path) -> None:
    # custom_metadata travels in the JSON request body (not an ASCII-only
    # header), so the exact corpus-relative path is preserved remotely.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    metadata = captured["config"]["custom_metadata"]
    assert {"key": "corpus_rel_path", "string_value": THAI_REL} in metadata


def test_upload_ascii_path_display_name_is_stable(monkeypatch, tmp_path) -> None:
    # Pure-ASCII paths keep the corpus-relative path verbatim as display
    # name: already-synced documents are unaffected by the repair.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    provider.upload(make_doc(tmp_path, "source/a.md"), "source/a.md")
    assert captured["config"]["display_name"] == "source/a.md"


def test_upload_config_never_sets_mime_type(monkeypatch, tmp_path) -> None:
    # Live repro 2: config.mime_type is copied into the request body and
    # Gemini 400-rejects the DOCX vendor type, so the provider must omit it
    # entirely and let the SDK infer the MIME from the (ASCII) file path.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert "mime_type" not in captured["config"]


def test_upload_sends_ascii_temp_path_with_original_suffix_and_bytes(monkeypatch, tmp_path) -> None:
    # The SDK echoes a path argument's basename into the ASCII-only
    # X-Goog-Upload-File-Name header and infers the MIME from the suffix, so
    # the provider must hand it a temporary ASCII path that keeps the
    # original suffix and the exact original bytes.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    doc = make_doc(tmp_path, THAI_REL)
    original_bytes = doc.read_bytes()
    provider.upload(doc, THAI_REL)
    sent = captured["file"]
    assert isinstance(sent, (str, Path))
    str(sent).encode("ascii")  # must never raise: header stays ASCII
    assert Path(sent).suffix == ".docx"  # original suffix preserved for MIME inference
    assert Path(sent) != doc  # a temporary copy, never the corpus file itself
    assert captured["file_existed_at_call"] is True
    assert captured["file_bytes_at_call"] == original_bytes


def test_upload_removes_temp_file_after_success(monkeypatch, tmp_path) -> None:
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert not Path(captured["file"]).exists()


def test_upload_removes_temp_file_after_sdk_exception(monkeypatch, tmp_path) -> None:
    # A transport/SDK failure must not leak the temporary copy.
    captured = install_fake_genai(monkeypatch, fail=RuntimeError("transport exploded"))
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    with pytest.raises(RuntimeError, match="transport exploded"):
        provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert not Path(captured["file"]).exists()


def test_upload_removes_temp_file_after_provider_error(monkeypatch, tmp_path) -> None:
    # A provider error on the finished LRO (the live 400 case) must also
    # clean up before the SyncError propagates.
    captured = install_fake_genai(
        monkeypatch, error={"status": "INVALID_ARGUMENT", "code": 400}
    )
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    with pytest.raises(sync_mod.SyncError, match="INVALID_ARGUMENT"):
        provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert not Path(captured["file"]).exists()


def test_upload_ascii_source_also_uses_temp_path(monkeypatch, tmp_path) -> None:
    # Uniform contract: even ASCII sources upload via a temp path (never a
    # raw handle), so MIME inference and header safety behave identically.
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    doc = make_doc(tmp_path, "source/a.md")
    provider.upload(doc, "source/a.md")
    sent = captured["file"]
    assert isinstance(sent, (str, Path))
    str(sent).encode("ascii")
    assert Path(sent).suffix == ".md"
    assert captured["file_bytes_at_call"] == doc.read_bytes()
    assert not Path(sent).exists()


def test_upload_keeps_provider_default_chunking(monkeypatch, tmp_path) -> None:
    captured = install_fake_genai(monkeypatch)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert "chunking_config" not in captured["config"]


def test_manifest_keeps_original_utf8_path_for_thai_source(tmp_path) -> None:
    # The local manifest remains the authoritative UTF-8 path record: its key
    # is the exact corpus-relative path, independent of the remote name.
    make_source_corpus(tmp_path, {Path(THAI_REL).name: "content"})
    provider = FakeProvider()
    code = sync_mod.run_sync(args_for(tmp_path), provider=provider)
    assert code == 0
    assert provider.uploaded == [THAI_REL]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert THAI_REL in manifest["files"]
    assert manifest["files"][THAI_REL]["documentName"]


# --- LRO polling seam: operations.get compatibility ---------------------------
#
# Live repro 3 (google-genai 1.75): the upload itself succeeded (Unicode
# header and MIME initiation fixed) but polling crashed inside the SDK with
# AttributeError: 'str' object has no attribute 'name'. The real signature is
# Operations.get(self, operation: T, *, config=None): it reads
# ``operation.name`` from the passed object, and the official example polls
# with ``client.operations.get(operation)``. Passing ``operation.name`` (a
# string) is therefore wrong. The fake below mirrors the SDK's attribute
# access so the contract is pinned: every poll must receive the operation
# object itself (identity/chaining), never its name string, and the existing
# timeout/sleep/error semantics must survive.

class FakeOperation:
    """Stand-in for a google-genai long-running operation object."""

    def __init__(self, *, done: bool, error: dict | None = None, response=None):
        self.name = "fileSearchStores/test/operations/op-live"
        self.done = done
        self.error = error
        self.response = response


class FakeClock:
    """Deterministic time source so LRO polling never sleeps in real time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def install_fake_genai_lro(monkeypatch, poll_operations) -> dict:
    """Fake SDK whose upload returns an unfinished operation.

    ``poll_operations`` is an iterable of the operations returned by
    successive ``client.operations.get`` calls. The fake records every
    argument passed to ``get`` and mirrors the real SDK's ``operation.name``
    access, so a string argument crashes exactly like google-genai 1.75.
    """
    captured: dict = {"get_args": [], "get_kwargs": [], "upload_kwargs": {}}
    clock = FakeClock()
    pending = FakeOperation(done=False)
    polls = iter(poll_operations)

    class FakeOperations:
        def get(self, operation, **kwargs):
            captured["get_args"].append(operation)
            captured["get_kwargs"].append(kwargs)
            # The real SDK reads operation.name first; a string crashes
            # here with AttributeError, reproducing the live failure.
            if not operation.name:
                raise ValueError("Operation name is empty.")
            return next(polls)

    class FakeStores:
        def upload_to_file_search_store(self, **kwargs):
            captured["upload_kwargs"] = kwargs
            return pending

    class FakeClient:
        def __init__(self, **kwargs):
            self.file_search_stores = FakeStores()
            self.operations = FakeOperations()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = types.SimpleNamespace(
        UploadToFileSearchStoreConfig=lambda **kw: dict(kw),
        CustomMetadata=lambda **kw: dict(kw),
    )
    monkeypatch.setattr(sync_mod, "_import_genai", lambda: fake_genai)
    monkeypatch.setattr(sync_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(sync_mod.time, "sleep", clock.sleep)
    captured["clock"] = clock
    captured["pending"] = pending
    return captured


def test_poll_passes_operation_object_not_name_string(monkeypatch, tmp_path) -> None:
    # The poll must receive the operation object itself (identity), never the
    # name string that crashed google-genai 1.75 inside Operations.get.
    done_op = FakeOperation(
        done=True,
        response=types.SimpleNamespace(
            document_name="fileSearchStores/test/documents/doc-live"
        ),
    )
    captured = install_fake_genai_lro(monkeypatch, [done_op])
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    document_name = provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    assert document_name == "fileSearchStores/test/documents/doc-live"
    assert len(captured["get_args"]) == 1
    polled = captured["get_args"][0]
    assert not isinstance(polled, str)  # never the name string
    assert polled is captured["pending"]  # the exact operation object
    assert captured["get_kwargs"] == [{}]  # no extra config needed
    assert not Path(captured["upload_kwargs"]["file"]).exists()


def test_poll_keeps_latest_object_until_done(monkeypatch, tmp_path) -> None:
    # Polling continues until done, always handing the latest object over.
    first = FakeOperation(done=False)
    second = FakeOperation(done=False)
    final = FakeOperation(
        done=True,
        response=types.SimpleNamespace(
            document_name="fileSearchStores/test/documents/doc-live"
        ),
    )
    captured = install_fake_genai_lro(monkeypatch, [first, second, final])
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    assert (
        provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
        == "fileSearchStores/test/documents/doc-live"
    )
    assert captured["get_args"] == [captured["pending"], first, second]
    assert captured["clock"].sleeps == [sync_mod.LRO_POLL_SECONDS] * 3


def test_poll_timeout_semantics_preserved(monkeypatch, tmp_path) -> None:
    # An operation that never finishes must still fail closed with the same
    # user-safe timeout message after the same deadline/sleep cadence.
    never_done = (FakeOperation(done=False) for _ in range(10_000))
    captured = install_fake_genai_lro(monkeypatch, never_done)
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    with pytest.raises(
        sync_mod.SyncError,
        match="timed out waiting for the provider upload to finish",
    ):
        provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    clock = captured["clock"]
    assert clock.now > sync_mod.LRO_TIMEOUT_SECONDS
    assert set(clock.sleeps) == {sync_mod.LRO_POLL_SECONDS}
    assert (
        len(clock.sleeps)
        == sync_mod.LRO_TIMEOUT_SECONDS / sync_mod.LRO_POLL_SECONDS + 1
    )
    assert all(not isinstance(op, str) for op in captured["get_args"])
    assert not Path(captured["upload_kwargs"]["file"]).exists()


def test_poll_surfaces_provider_error_without_detail_leak(monkeypatch, tmp_path) -> None:
    # A provider error that arrives via polling must raise the same
    # user-safe SyncError (status + code only, no raw provider detail).
    errored = FakeOperation(
        done=True,
        error={
            "status": "INVALID_ARGUMENT",
            "code": 400,
            "message": "internal provider detail",
        },
    )
    captured = install_fake_genai_lro(monkeypatch, [errored])
    provider = sync_mod.GeminiStoreProvider("fileSearchStores/test", "k")
    with pytest.raises(sync_mod.SyncError) as excinfo:
        provider.upload(make_doc(tmp_path, THAI_REL), THAI_REL)
    message = str(excinfo.value)
    assert "INVALID_ARGUMENT" in message
    assert "400" in message
    assert "internal provider detail" not in message  # user-safe message only
    assert not Path(captured["upload_kwargs"]["file"]).exists()


# --- ascii_display_name (pure helper) -----------------------------------------

def test_ascii_display_name_pure_ascii_passes_through() -> None:
    assert sync_mod.ascii_display_name("source/a.md") == "source/a.md"
    assert sync_mod.ascii_display_name("source/sub/dir-01_File.pdf") == "source/sub/dir-01_File.pdf"


def test_ascii_display_name_is_deterministic_and_ascii_only() -> None:
    name = sync_mod.ascii_display_name(THAI_REL)
    assert name == sync_mod.ascii_display_name(THAI_REL)
    name.encode("ascii")
    assert "01_PEA_SabuyService" in name
    assert name.endswith(".docx")


def test_ascii_display_name_distinct_paths_never_collide() -> None:
    names = {
        sync_mod.ascii_display_name(rel)
        for rel in ("source/ไฟฟ้า.md", "source/สายดิน.md", "source/หม้อแปลง.md", "source/_.md")
    }
    assert len(names) == 4


def test_ascii_display_name_caps_length_and_keeps_uniqueness() -> None:
    long_rel = "source/" + "x" * 300 + ".md"
    other_rel = "source/" + "x" * 300 + "y.md"
    name = sync_mod.ascii_display_name(long_rel)
    assert len(name) <= sync_mod.DISPLAY_NAME_MAX_LENGTH
    name.encode("ascii")
    assert sync_mod.ascii_display_name(other_rel) != name
