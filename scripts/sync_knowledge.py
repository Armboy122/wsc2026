#!/usr/bin/env python3
"""Sync the authoritative PEA knowledge corpus into a Gemini File Search store.

Safety-critical source policy: only files under ``<corpus root>/source/`` are
ever syncable. The default corpus root is ``<repo>/knowledge``, so the default
run uploads exactly ``knowledge/source/**``. README files, the manifest,
hidden files, and non-document files are never uploaded, at any depth. The
repository intentionally ships no PEA content in ``source/`` (only a
non-factual placeholder); only lead-approved, authoritative PEA exports may
be placed there. With no approved export present, a sync run is a no-op and
the store cannot be populated with fabricated facts.

The script keeps a SHA256 source manifest (default: ``knowledge/manifest.json``)
that maps each corpus-relative path to its content hash and the remote document
name. Each run uploads only new or changed sources; unchanged sources are
touched, and remote documents whose local source disappeared are deleted only
when both ``--prune`` and ``--yes`` are given.

Flags:
    --root      corpus root (default: <repo>/knowledge); only <root>/source/**
                is syncable. A root without a source/ directory is a usage error.
    --manifest  manifest path (default: <corpus root>/manifest.json, i.e.
                knowledge/manifest.json for the default root)
    --file      limit the run to one corpus-relative path (repeatable), e.g.
                source/<approved-export>.md
    --store     File Search store resource name (default: $GEMINI_FILE_SEARCH_STORE)
    --dry-run   print the plan only; no uploads, no manifest writes
    --force     re-upload unchanged sources as well
    --prune     delete remote documents whose local source is gone (needs --yes)
    --yes       confirm destructive prune deletions
    --verbose   per-file progress output

Provider defaults: chunking uses the provider default (no chunking
configuration is ever sent). Unicode safety: non-ASCII source names (e.g.
Thai) never reach an HTTP header — the source is streamed as a binary
handle with an explicit MIME type (the SDK would otherwise copy the local
basename into the ASCII-only ``X-Goog-Upload-File-Name`` header), the
remote display name is a deterministic ASCII-safe form of the corpus-
relative path with a path-hash suffix, and the original UTF-8 path is
carried in ``custom_metadata`` (JSON request body, never a header) when it
fits the conservative value budget. The local manifest always keeps the
exact UTF-8 corpus-relative path as its key, so the original path remains
available even for paths too long for metadata. The ``google-genai`` SDK is
imported lazily, so ``--dry-run`` works without the SDK installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Corpus root (default): holds source/ (the only syncable subtree), the
# manifest, and documentation/tests — none of which are ever uploaded except
# files under source/.
DEFAULT_CORPUS_ROOT = REPO_ROOT / "knowledge"
# Only files under <corpus root>/source/** are ever uploaded (fail-closed).
SOURCE_DIR_NAME = "source"
MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

ENV_STORE = "GEMINI_FILE_SEARCH_STORE"
ENV_API_KEY = "GEMINI_API_KEY"
ENV_FALLBACK_API_KEY = "GOOGLE_API_KEY"

ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx", ".csv", ".html"}
# Documentation/metadata files that are never uploaded, at any depth
# (compared case-insensitively).
EXCLUDED_FILENAMES = {MANIFEST_NAME, "readme.md"}

LRO_POLL_SECONDS = 0.5
LRO_TIMEOUT_SECONDS = 120.0
SHA256_CHUNK_SIZE = 1024 * 1024

# Remote display-name budget. The provider allows 512 characters; 200 keeps
# names comfortably ASCII-safe and comparable in listings.
DISPLAY_NAME_MAX_LENGTH = 200
# Hex digits of the SHA256 of the original UTF-8 path appended to every
# non-ASCII display name so distinct paths can never collide.
DISPLAY_NAME_HASH_LENGTH = 12
# custom_metadata key carrying the exact corpus-relative path (JSON body).
CUSTOM_METADATA_PATH_KEY = "corpus_rel_path"
# Conservative UTF-8 byte budget for a custom-metadata string value; the
# provider does not document a limit, so longer paths rely on the manifest.
CUSTOM_METADATA_MAX_VALUE_BYTES = 256


def _is_ascii_printable(char: str) -> bool:
    return 0x20 <= ord(char) <= 0x7E


def ascii_display_name(rel_path: str) -> str:
    """Deterministic ASCII-safe remote display name for a corpus-relative path.

    Pure-ASCII printable paths within the length budget pass through
    unchanged, so names of already-synced documents stay stable across runs.
    Any other path (e.g. Thai file names, which crash httpx when they leak
    into ASCII-only headers) is reduced to its printable-ASCII skeleton —
    runs of non-ASCII characters collapse to a single ``_`` — and the first
    ``DISPLAY_NAME_HASH_LENGTH`` hex digits of the SHA256 of the original
    UTF-8 path are appended before the extension. The path hash guarantees
    two distinct paths never collide even when their ASCII skeletons are
    identical, while the recognizable ASCII stem and extension are kept
    where possible. The result is always ASCII and at most
    ``DISPLAY_NAME_MAX_LENGTH`` characters long.
    """
    if (
        rel_path
        and len(rel_path) <= DISPLAY_NAME_MAX_LENGTH
        and all(_is_ascii_printable(char) for char in rel_path)
    ):
        return rel_path
    digest = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:DISPLAY_NAME_HASH_LENGTH]
    skeleton = re.sub(
        r"_+", "_", "".join(char if _is_ascii_printable(char) else "_" for char in rel_path)
    )
    stem, ext = os.path.splitext(skeleton)
    stem = stem.rstrip(" _") or "file"
    if stem.endswith("/"):
        stem += "file"
    budget = max(DISPLAY_NAME_MAX_LENGTH - len(ext) - len(digest) - 1, len("file"))
    return f"{stem[:budget]}-{digest}{ext}"


def _mime_type_for(rel_path: str) -> str:
    """MIME type from the (ASCII) file extension; never inferred from a path
    the SDK would echo into a header."""
    guessed, _ = mimetypes.guess_type(rel_path)
    return guessed or "application/octet-stream"


def _custom_metadata(genai, rel_path: str) -> list | None:
    """Original UTF-8 path as remote metadata, when it fits the budget.

    ``custom_metadata`` is serialized into the JSON request body — never an
    ASCII-only header — so the exact corpus-relative path survives. Paths
    beyond the conservative value budget are not faked or truncated remotely;
    the local manifest remains the authoritative record for every path.
    """
    if len(rel_path.encode("utf-8")) > CUSTOM_METADATA_MAX_VALUE_BYTES:
        return None
    return [genai.types.CustomMetadata(key=CUSTOM_METADATA_PATH_KEY, string_value=rel_path)]


class SyncError(Exception):
    """Provider or I/O failure with a user-safe message."""


class UsageError(SyncError):
    """Invalid command-line usage."""


@dataclass(frozen=True)
class LocalSource:
    """One syncable source file, addressed by corpus-relative POSIX path."""

    rel_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class UploadItem:
    """A source that must be (re-)uploaded this run."""

    rel_path: str
    sha256: str
    size_bytes: int
    kind: str  # "new" | "changed" | "forced"


@dataclass(frozen=True)
class PruneItem:
    """A manifest entry whose local source no longer exists."""

    rel_path: str
    document_name: str | None


@dataclass(frozen=True)
class SyncPlan:
    """Pure diff between the local corpus and the manifest."""

    uploads: tuple[UploadItem, ...]
    unchanged: tuple[str, ...]
    prune: tuple[PruneItem, ...]


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(SHA256_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_sources(corpus_root: Path, only: tuple[str, ...] = ()) -> list[LocalSource]:
    """List syncable sources under ``corpus_root`` (sorted, stable order).

    Fail-closed source policy: only files inside ``corpus_root/source/`` are
    syncable; everything else in the corpus (README, docs, tests, metadata)
    can never be uploaded. Inside ``source/``, hidden files/directories,
    README and manifest files (any case, any depth), and files without an
    allowed document suffix are skipped. A corpus root without a ``source/``
    directory is a :class:`UsageError`, never a silent no-op. Relative paths
    are corpus-root-relative (``source/...``). When ``only`` is given, every
    listed path must resolve to a syncable source or a :class:`UsageError`
    is raised.
    """
    source_dir = corpus_root / SOURCE_DIR_NAME
    if not source_dir.is_dir():
        raise UsageError(
            f"corpus root {corpus_root} has no {SOURCE_DIR_NAME}/ directory; "
            f"only {SOURCE_DIR_NAME}/** is syncable"
        )
    found: list[LocalSource] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(corpus_root).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts):
            continue
        if path.name.lower() in EXCLUDED_FILENAMES:
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        found.append(
            LocalSource(
                rel_path=rel,
                sha256=compute_sha256(path),
                size_bytes=path.stat().st_size,
            )
        )
    if only:
        wanted = set(only)
        found = [source for source in found if source.rel_path in wanted]
        missing = sorted(
            path for path in wanted
            if path not in {source.rel_path for source in found}
        )
        if missing:
            raise UsageError(f"not a syncable source in the corpus: {', '.join(missing)}")
        found.sort(key=lambda source: source.rel_path)
    return found


def load_manifest(manifest_path: Path) -> dict:
    """Load the manifest; a missing file yields an empty skeleton."""
    if not manifest_path.exists():
        return {"schemaVersion": MANIFEST_SCHEMA_VERSION, "storeName": None, "files": {}}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot read manifest {manifest_path.name}: unreadable JSON") from exc
    files = raw.get("files")
    if not isinstance(files, dict):
        raise SyncError(f"cannot read manifest {manifest_path.name}: malformed file map")
    return {
        "schemaVersion": raw.get("schemaVersion", MANIFEST_SCHEMA_VERSION),
        "storeName": raw.get("storeName"),
        "files": files,
    }


def build_plan(
    local: list[LocalSource],
    manifest_files: dict,
    *,
    force: bool = False,
    scope: tuple[str, ...] | None = None,
) -> SyncPlan:
    """Diff local sources against the manifest (pure, no provider access).

    With ``scope`` set (``--file``), only scoped sources produce uploads and
    no prune candidates are produced; pruning is a whole-corpus operation.
    """
    uploads: list[UploadItem] = []
    unchanged: list[str] = []
    local_paths = {source.rel_path for source in local}
    for source in local:
        entry = manifest_files.get(source.rel_path)
        if entry is None:
            kind = "new"
        elif force:
            kind = "forced"
        elif not isinstance(entry, dict) or entry.get("sha256") != source.sha256:
            kind = "changed"
        else:
            unchanged.append(source.rel_path)
            continue
        uploads.append(
            UploadItem(
                rel_path=source.rel_path,
                sha256=source.sha256,
                size_bytes=source.size_bytes,
                kind=kind,
            )
        )
    prune: list[PruneItem] = []
    if scope is None:
        for rel_path, entry in sorted(manifest_files.items()):
            if rel_path in local_paths:
                continue
            document_name = entry.get("documentName") if isinstance(entry, dict) else None
            prune.append(PruneItem(rel_path=rel_path, document_name=document_name))
    return SyncPlan(tuple(uploads), tuple(unchanged), tuple(prune))


def write_manifest(manifest_path: Path, store_name: str | None, files: dict) -> None:
    """Atomically replace the manifest (tmp file + rename)."""
    payload = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "storeName": store_name,
        "files": files,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, manifest_path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _import_genai():
    """Lazy provider import: the SDK is optional at module import time."""
    try:
        from google import genai
    except ImportError as exc:
        raise SyncError(
            "the google-genai SDK is not installed; run: pip install google-genai"
        ) from exc
    return genai


def _describe_error(error: object) -> str:
    """User-safe one-line description of a provider error dict."""
    if isinstance(error, dict):
        status = error.get("status") or "ERROR"
        code = error.get("code", "?")
        return f"{status} (code {code})"
    return "provider error"


class GeminiStoreProvider:
    """Thin SDK adapter: upload a source, delete a remote document."""

    def __init__(self, store_name: str, api_key: str) -> None:
        self._store_name = store_name
        self._api_key = api_key

    def upload(self, local_path: Path, rel_path: str) -> str:
        """Upload one source; returns the remote document name.

        Unicode safety (live repro: Thai names crashed httpx while
        ASCII-encoding headers): the source is streamed as a binary handle
        with an explicit MIME type, because the SDK echoes a path argument's
        basename into the ASCII-only ``X-Goog-Upload-File-Name`` header. The
        display name is the deterministic ASCII-safe form of the corpus-
        relative path (:func:`ascii_display_name`), and the original UTF-8
        path travels in ``custom_metadata`` — the JSON request body, never a
        header — when it fits the value budget; the local manifest always
        keeps the exact path as its key regardless.
        No chunking configuration is sent — provider default chunking applies.
        """
        genai = _import_genai()
        client = genai.Client(api_key=self._api_key)
        config_kwargs: dict = {
            "display_name": ascii_display_name(rel_path),
            "mime_type": _mime_type_for(rel_path),
        }
        metadata = _custom_metadata(genai, rel_path)
        if metadata is not None:
            config_kwargs["custom_metadata"] = metadata
        with local_path.open("rb") as handle:
            operation = client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=self._store_name,
                file=handle,
                config=genai.types.UploadToFileSearchStoreConfig(**config_kwargs),
            )
        operation = self._wait_for_operation(client, operation)
        if operation.error:
            raise SyncError(
                f"provider error while uploading {rel_path}: {_describe_error(operation.error)}"
            )
        response = operation.response
        document_name = getattr(response, "document_name", None) if response is not None else None
        if not document_name:
            raise SyncError(f"provider returned no document name for {rel_path}")
        return document_name

    def delete_document(self, document_name: str) -> None:
        genai = _import_genai()
        client = genai.Client(api_key=self._api_key)
        client.file_search_stores.documents.delete(name=document_name)

    def _wait_for_operation(self, client, operation) -> object:
        if operation.done:
            return operation
        deadline = time.monotonic() + LRO_TIMEOUT_SECONDS
        while not operation.done:
            if time.monotonic() > deadline:
                raise SyncError("timed out waiting for the provider upload to finish")
            time.sleep(LRO_POLL_SECONDS)
            operation = client.operations.get(operation=operation.name)
        return operation


def _resolve_store_name(args: argparse.Namespace, manifest: dict) -> str | None:
    return args.store or os.environ.get(ENV_STORE) or manifest.get("storeName")


def run_sync(args: argparse.Namespace, provider: object | None = None) -> int:
    """Execute the sync; returns a process exit code.

    ``provider`` is injectable for tests; when omitted it is constructed
    lazily (and only when a real upload or prune is about to happen).
    """
    corpus_root = Path(args.root).expanduser().resolve() if args.root else DEFAULT_CORPUS_ROOT
    if not corpus_root.is_dir():
        raise UsageError(f"corpus root not found: {corpus_root}")
    manifest_path = (
        Path(args.manifest).expanduser().resolve() if args.manifest
        else corpus_root / MANIFEST_NAME
    )
    only = tuple(Path(path).as_posix() for path in (args.file or ()))

    local = discover_sources(corpus_root, only)
    manifest = load_manifest(manifest_path)
    plan = build_plan(local, manifest["files"], force=args.force, scope=only or None)
    store_name = _resolve_store_name(args, manifest)

    def log(message: str) -> None:
        if args.verbose:
            print(message)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}corpus: {corpus_root}")
    for item in plan.uploads:
        print(f"{prefix}upload {item.kind}: {item.rel_path}")
    print(f"{prefix}unchanged: {len(plan.unchanged)} file(s)")
    if plan.prune:
        for item in plan.prune:
            print(f"{prefix}prune candidate: {item.rel_path}")
    if args.dry_run:
        print(f"{prefix}dry run complete; nothing uploaded, manifest untouched")
        return 0

    will_prune = bool(plan.prune) and args.prune and args.yes
    if plan.prune and args.prune and not args.yes:
        print(
            f"warning: prune requested without --yes; "
            f"skipping {len(plan.prune)} remote deletion(s)"
        )
    if not plan.uploads and not will_prune:
        print("up to date; nothing to do")
        return 0

    if provider is None:
        if not store_name:
            raise UsageError(
                "no File Search store configured (set GEMINI_FILE_SEARCH_STORE or pass --store)"
            )
        api_key = os.environ.get(ENV_API_KEY) or os.environ.get(ENV_FALLBACK_API_KEY)
        if not api_key:
            raise UsageError("no provider API key configured (set GEMINI_API_KEY)")
        provider = GeminiStoreProvider(store_name, api_key)

    files = dict(manifest["files"])
    for item in plan.uploads:
        log(f"uploading {item.rel_path} ({item.size_bytes} bytes)")
        document_name = provider.upload(corpus_root / item.rel_path, item.rel_path)
        files[item.rel_path] = {
            "sha256": item.sha256,
            "sizeBytes": item.size_bytes,
            "documentName": document_name,
            "uploadedAt": utc_now_iso(),
        }
        write_manifest(manifest_path, store_name, files)
        log(f"uploaded {item.rel_path} -> {document_name}")

    pruned: list[str] = []
    if will_prune:
        for item in plan.prune:
            if item.document_name:
                log(f"deleting remote document for {item.rel_path}")
                provider.delete_document(item.document_name)
            files.pop(item.rel_path, None)
            pruned.append(item.rel_path)
        write_manifest(manifest_path, store_name, files)
    elif plan.prune:
        log(f"note: {len(plan.prune)} stale manifest entr(y/ies) not pruned (no --prune)")

    print(
        f"done: uploaded {len(plan.uploads)}, unchanged {len(plan.unchanged)}, "
        f"pruned {len(pruned)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync_knowledge.py",
        description=(
            "Sync the authoritative PEA knowledge corpus into a Gemini File Search "
            "store. Only <root>/source/** is ever uploaded; the repository ships no "
            "PEA content (lead-approved exports only)."
        ),
    )
    parser.add_argument(
        "--root",
        help="corpus root (default: <repo>/knowledge); only <root>/source/** is syncable",
    )
    parser.add_argument(
        "--manifest",
        help="manifest path (default: <corpus root>/manifest.json, i.e. knowledge/manifest.json)",
    )
    parser.add_argument(
        "--file",
        action="append",
        metavar="PATH",
        help="limit the run to this corpus-relative path, e.g. source/<export>.md (repeatable)",
    )
    parser.add_argument(
        "--store",
        help="File Search store resource name (default: $GEMINI_FILE_SEARCH_STORE)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan only; no uploads, no manifest writes"
    )
    parser.add_argument("--force", action="store_true", help="re-upload unchanged sources as well")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete remote documents whose local source is gone (requires --yes)",
    )
    parser.add_argument("--yes", action="store_true", help="confirm destructive prune deletions")
    parser.add_argument("--verbose", action="store_true", help="per-file progress output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_sync(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
