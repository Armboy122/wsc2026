"""Index lifecycle: background build, disk cache, automatic re-index and health.

The manager owns the current immutable :class:`~app.knowledge.index.searcher.KnowledgeIndex`
and swaps it atomically after a successful rebuild. Builds run on a background thread so the
asyncio event loop is never blocked; a rebuild that fails keeps the last good index.

The on-disk cache is a derived artefact under ``KNOWLEDGE_INDEX_DIR``: a JSON header plus a
NumPy matrix. Embeddings are keyed by the SHA-256 of the indexed text (``json`` + ``npy``
only, never pickle), so an edited corpus re-embeds only its new or changed text. A missing,
corrupt, or mismatched cache is ignored and the index is rebuilt from scratch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index.embedder import BgeM3Embedder, Embedder, FakeEmbedder
from app.knowledge.index.models import CHUNKER_VERSION, SearchResult
from app.knowledge.index.searcher import KnowledgeIndex

logger = logging.getLogger(__name__)

CACHE_FORMAT_VERSION = 1
CACHE_HEADER_NAME = "cache.json"
CACHE_VECTORS_NAME = "vectors.npy"
DEFAULT_DEBOUNCE_MS = 300
DEFAULT_POLL_INTERVAL_S = 1.0
CACHE_WRITE_TIMEOUT_S = 5.0
_ALIAS_DIRNAME = "aliases"
_MARKDOWN_SUFFIX = ".md"


class IndexState(str, Enum):
    """Lifecycle state reported by ``/health``."""

    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    ERROR = "error"


class IndexUnavailableError(RuntimeError):
    """Raised by :meth:`IndexManager.search` before any index has been built.

    ``code`` matches the ``unavailable`` wire code the Knowledge tool returns.
    """

    code = "unavailable"


@dataclass(frozen=True)
class IndexHealth:
    """Counts-only health snapshot; never carries paths, content, or error text."""

    status: IndexState
    documents: int
    chunks: int


def build_embedder(name: str) -> Embedder:
    """Construct the configured embedder without loading any model weights.

    ``bge-m3`` is lazy (the model loads on first use inside the background build thread);
    ``fake`` is the deterministic offline stand-in used by the test suite.
    """
    normalized = (name or "").strip().lower()
    if normalized == "fake":
        return FakeEmbedder()
    if normalized in {"bge-m3", "bge_m3", "bgem3"}:
        return BgeM3Embedder()
    raise ValueError(
        f"unsupported KNOWLEDGE_EMBEDDER {name!r}: expected 'bge-m3' or 'fake'"
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def corpus_fingerprint(
    catalog: KnowledgeCatalog,
    alias_root: Path | str,
    *,
    chunker_version: str,
    model_id: str,
) -> str:
    """Digest approved source files and alias rules: relative name + size + SHA-256.

    Used only to decide whether a rebuild is needed; it is stored in the cache header for
    diagnostics. It never exposes file contents.
    """
    digest = hashlib.sha256()
    digest.update(f"chunker={chunker_version}\nmodel={model_id}\n".encode())
    for document in sorted(catalog.documents, key=lambda item: item.source_id):
        data = document.path.read_bytes()
        digest.update(b"doc:")
        digest.update(document.source_id.encode("utf-8"))
        digest.update(b":")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b":")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\n")
    alias_dir = Path(alias_root)
    if alias_dir.is_dir():
        for path in sorted(alias_dir.glob(f"*{_MARKDOWN_SUFFIX}")):
            if path.is_symlink() or path.name.lower() == "readme.md":
                continue
            data = path.read_bytes()
            digest.update(b"alias:")
            digest.update(path.name.encode("utf-8"))
            digest.update(b":")
            digest.update(str(len(data)).encode("ascii"))
            digest.update(b":")
            digest.update(hashlib.sha256(data).digest())
            digest.update(b"\n")
    return digest.hexdigest()


class _CachingEmbedder:
    """Embedder proxy that serves cached vectors and embeds only cache misses."""

    def __init__(self, inner: Embedder, embeddings: dict[str, np.ndarray]) -> None:
        self._inner = inner
        self._embeddings: dict[str, np.ndarray] = embeddings
        self._used_keys: set[str] = set()

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dim(self) -> int:
        return self._inner.dim

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        keys = [_sha256_text(text) for text in texts]
        self._used_keys.update(keys)
        missing_keys: list[str] = []
        missing_text: dict[str, str] = {}
        for text, key in zip(texts, keys):
            if key not in self._embeddings and key not in missing_text:
                missing_keys.append(key)
                missing_text[key] = text
        if missing_keys:
            fresh = np.asarray(
                self._inner.embed_documents([missing_text[key] for key in missing_keys]),
                dtype=np.float32,
            )
            if fresh.shape != (len(missing_keys), self.dim):
                raise ValueError(
                    "embedder returned an unexpected vector shape: "
                    f"{fresh.shape} != {(len(missing_keys), self.dim)}"
                )
            for key, row in zip(missing_keys, fresh):
                self._embeddings[key] = row
        return np.vstack([self._embeddings[key] for key in keys])

    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray(self._inner.embed_query(text), dtype=np.float32)

    def used_embeddings(self) -> dict[str, np.ndarray]:
        """Every vector touched by this build, dropping entries for removed text."""
        return {key: self._embeddings[key] for key in self._used_keys}


def _load_embedding_cache(
    cache_dir: Path,
    *,
    chunker_version: str,
    model_id: str,
    dim: int,
) -> dict[str, np.ndarray]:
    """Load cached text->vector entries; a missing, corrupt, or mismatched cache is empty."""
    header_path = cache_dir / CACHE_HEADER_NAME
    vectors_path = cache_dir / CACHE_VECTORS_NAME
    try:
        header = json.loads(header_path.read_text(encoding="utf-8"))
        if not isinstance(header, dict):
            raise TypeError("cache header is not an object")
        if header.get("cacheVersion") != CACHE_FORMAT_VERSION:
            raise ValueError("cache format version mismatch")
        if header.get("chunkerVersion") != chunker_version:
            raise ValueError("cache chunker version mismatch")
        if header.get("modelId") != model_id:
            raise ValueError("cache embedder model mismatch")
        if header.get("dim") != dim:
            raise ValueError("cache embedder dimension mismatch")
        text_hashes = header.get("textHashes")
        if not isinstance(text_hashes, list) or not all(
            isinstance(item, str) for item in text_hashes
        ):
            raise ValueError("cache text hash list is invalid")
        vectors = np.load(vectors_path, allow_pickle=False)
        if vectors.ndim != 2 or vectors.shape != (len(text_hashes), dim):
            raise ValueError("cache vector matrix shape mismatch")
        return {text_hash: vectors[index] for index, text_hash in enumerate(text_hashes)}
    except (OSError, ValueError, TypeError, EOFError, json.JSONDecodeError) as exc:
        if any((header_path.exists(), vectors_path.exists())):
            logger.warning("knowledge index cache ignored (%s)", type(exc).__name__)
        return {}


def _save_embedding_cache(
    cache_dir: Path,
    *,
    chunker_version: str,
    model_id: str,
    dim: int,
    fingerprint: str,
    embeddings: dict[str, np.ndarray],
) -> None:
    """Persist the current corpus embeddings atomically; cache failures never fail a build."""
    text_hashes = sorted(embeddings)
    if text_hashes:
        vectors = np.vstack([embeddings[key] for key in text_hashes]).astype(
            np.float32, copy=False
        )
    else:
        vectors = np.zeros((0, dim), dtype=np.float32)
    header = {
        "cacheVersion": CACHE_FORMAT_VERSION,
        "chunkerVersion": chunker_version,
        "modelId": model_id,
        "dim": dim,
        "fingerprint": fingerprint,
        "textHashes": text_hashes,
    }
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        vectors_tmp = cache_dir / f"{CACHE_VECTORS_NAME}.tmp"
        with vectors_tmp.open("wb") as handle:
            np.save(handle, vectors)
        os.replace(vectors_tmp, cache_dir / CACHE_VECTORS_NAME)
        header_tmp = cache_dir / f"{CACHE_HEADER_NAME}.tmp"
        header_tmp.write_text(json.dumps(header), encoding="utf-8")
        os.replace(header_tmp, cache_dir / CACHE_HEADER_NAME)
    except OSError as exc:
        logger.warning("could not persist knowledge index cache (%s)", type(exc).__name__)


class IndexManager:
    """Owns the current immutable searcher, rebuilds it off the event loop, and reports health."""

    def __init__(
        self,
        *,
        source_root: Path | str,
        index_dir: Path | str,
        embedder: Embedder,
        alias_root: Path | str | None = None,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        watch: bool = True,
        chunker_version: str = CHUNKER_VERSION,
    ) -> None:
        root = Path(source_root)
        self._source_root = root
        self._alias_root = (
            Path(alias_root) if alias_root is not None else root.parent / _ALIAS_DIRNAME
        )
        self._index_dir = Path(index_dir)
        self._embedder = embedder
        self._debounce_ms = max(debounce_ms, 1)
        self._poll_interval_s = max(poll_interval_s, 0.01)
        self._watch_enabled = watch
        self._chunker_version = chunker_version

        self._build_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._searcher: KnowledgeIndex | None = None
        self._status = IndexState.BUILDING
        self._documents = 0
        self._chunks = 0
        self._fingerprint: str | None = None

        self._stop_event = threading.Event()
        self._started = False
        self._threads: list[threading.Thread] = []

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def index_dir(self) -> Path:
        return self._index_dir

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def searcher(self) -> KnowledgeIndex | None:
        """The current immutable searcher, or ``None`` before the first successful build."""
        return self._searcher

    def health(self) -> IndexHealth:
        """Return a locked, counts-only snapshot safe to expose over HTTP."""
        with self._state_lock:
            return IndexHealth(
                status=self._status, documents=self._documents, chunks=self._chunks
            )

    def search(self, query: str) -> SearchResult:
        """Search the current index, or raise :class:`IndexUnavailableError` before ready."""
        searcher = self._searcher
        if searcher is None:
            raise IndexUnavailableError("knowledge index is not ready")
        return searcher.search(query)

    def start(self) -> None:
        """Begin the initial build and the watcher; returns without blocking."""
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        self._threads = [
            self._spawn("knowledge-index-build", self._initial_build),
        ]
        if self._watch_enabled:
            self._threads.append(self._spawn("knowledge-index-watch", self._watch_loop))

    def stop(self) -> None:
        """Stop the watcher and wait briefly for in-flight builds to finish."""
        if not self._started:
            return
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=CACHE_WRITE_TIMEOUT_S)
            if thread.is_alive():
                logger.warning("knowledge index thread %s did not stop in time", thread.name)
        self._threads = []
        self._started = False

    def refresh_if_stale(self) -> bool:
        """Rebuild when the on-disk corpus changed; return whether a build ran."""
        return self._rebuild(force=False)

    def rebuild(self) -> bool:
        """Force a rebuild regardless of the stored fingerprint."""
        return self._rebuild(force=True)

    def _spawn(self, name: str, target) -> threading.Thread:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        return thread

    def _initial_build(self) -> None:
        self._rebuild(force=True)

    def _rebuild(self, *, force: bool) -> bool:
        """Build a new index and swap it in only on success; failures keep the last good one."""
        with self._build_lock:
            try:
                catalog = KnowledgeCatalog(self._source_root, alias_root=self._alias_root)
                fingerprint = corpus_fingerprint(
                    catalog,
                    self._alias_root,
                    chunker_version=self._chunker_version,
                    model_id=self._embedder.model_id,
                )
                if not force and fingerprint == self._fingerprint:
                    return False
                cache = _load_embedding_cache(
                    self._index_dir,
                    chunker_version=self._chunker_version,
                    model_id=self._embedder.model_id,
                    dim=self._embedder.dim,
                )
                caching = _CachingEmbedder(self._embedder, cache)
                index = KnowledgeIndex(catalog, embedder=caching, alias_root=self._alias_root)
            except Exception as exc:  # noqa: BLE001 - any build failure must keep serving
                self._record_failure(exc)
                return False

            _save_embedding_cache(
                self._index_dir,
                chunker_version=self._chunker_version,
                model_id=self._embedder.model_id,
                dim=self._embedder.dim,
                fingerprint=fingerprint,
                embeddings=caching.used_embeddings(),
            )
            with self._state_lock:
                self._searcher = index
                self._documents = len(catalog.documents)
                self._chunks = len(index.chunks) + len(index.qa_units)
                self._fingerprint = fingerprint
                self._status = IndexState.READY
            logger.info(
                "knowledge index ready: %d documents, %d units",
                self._documents,
                self._chunks,
            )
            return True

    def _record_failure(self, exc: Exception) -> None:
        with self._state_lock:
            # Last good index keeps serving: report stale, or error when nothing ever built.
            self._status = IndexState.STALE if self._searcher is not None else IndexState.ERROR
        logger.exception("knowledge index rebuild failed (%s)", type(exc).__name__)

    def _watch_loop(self) -> None:
        watched = [
            str(path)
            for path in (self._source_root, self._alias_root)
            if Path(path).is_dir()
        ]
        if not watched:
            self._poll_loop()
            return
        try:
            from watchfiles import watch
        except ImportError:
            logger.warning("watchfiles is unavailable; polling the knowledge corpus instead")
            self._poll_loop()
            return
        step_ms = max(self._debounce_ms, round(self._poll_interval_s * 1000), 10)
        try:
            # ``yield_on_timeout`` makes the generator wake periodically, which doubles as
            # the cheap fingerprint-check fallback when the native watcher misses an event.
            for _changes in watch(
                *watched,
                watch_filter=_markdown_filter,
                debounce=self._debounce_ms,
                step=step_ms,
                rust_timeout=step_ms,
                yield_on_timeout=True,
                stop_event=self._stop_event,
            ):
                if self._stop_event.is_set():
                    break
                self.refresh_if_stale()
        except Exception:
            logger.exception("knowledge index watcher failed; falling back to polling")
            self._poll_loop()

    def _poll_loop(self) -> None:
        while not self._stop_event.wait(self._poll_interval_s):
            self.refresh_if_stale()


def _markdown_filter(_change: object, path: str) -> bool:
    """Watch only non-hidden Markdown files, so editor temp files never trigger a rebuild."""
    name = Path(path).name
    return path.lower().endswith(_MARKDOWN_SUFFIX) and not name.startswith(".")
