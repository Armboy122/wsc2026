"""Gemini File Search Hosted RAG backend (Worker B — knowledge).

This is the only knowledge backend in the demo. Retrieval and grounding are
delegated to Google's hosted File Search service; this module only turns the
returned grounding metadata into frozen ``Citation`` values and a compact
``answerContext``. There is deliberately no local embedding, chunking,
indexing, ranking, vector store, or model-memory fallback here (CONTRACTS.md:
explicit non-goals; ARCHITECTURE.md: "does not embed, chunk, index, rank, or
persist documents itself").

The provider SDK (``google-genai``) is optional and imported lazily on first
use, so this module can be imported and constructed without the SDK
installed. A missing SDK or missing configuration surfaces as a typed,
user-safe :class:`KnowledgeBackendError` — never an import-time crash and
never a credential or endpoint leak.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from app.contracts import Citation, ToolErrorCode

logger = logging.getLogger("pea_one_agent.gemini_file_search")

ENV_API_KEY = "GEMINI_API_KEY"
ENV_FALLBACK_API_KEY = "GOOGLE_API_KEY"
ENV_STORE = "GEMINI_FILE_SEARCH_STORE"
ENV_MODEL = "GEMINI_FILE_SEARCH_MODEL"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT_SECONDS = 30.0

# Frozen contract limits (app/contracts.py: Citation, KnowledgeSearchOutput).
MAX_ANSWER_CONTEXT_CHARS = 4000
MAX_SNIPPET_CHARS = 1000
MAX_TITLE_CHARS = 500
MAX_URI_CHARS = 2000

# User-safe, credential-free messages.
USER_SAFE_NOT_CONFIGURED = (
    "The knowledge service is not configured on this server. "
    "Please ask an administrator to check the service setup."
)
USER_SAFE_UNAVAILABLE = (
    "The knowledge service is temporarily unavailable. Please try again shortly."
)


class KnowledgeBackendError(Exception):
    """Typed backend failure whose ``message`` is safe to surface to a user.

    ``code`` is a frozen :class:`~app.contracts.ToolErrorCode`; ``message``
    must never contain credentials, endpoint URLs, or request details.
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GroundedEvidence:
    """Frozen-shape result of one hosted retrieval.

    ``answer_context`` is empty and ``result_count`` is zero when the
    provider returns no usable grounding (no evidence).
    """

    answer_context: str
    result_count: int
    citations: tuple[Citation, ...]


def _clip(text: str, limit: int) -> str:
    return text[:limit]


def _first_text(value: Any, *names: str) -> str:
    """First non-empty string attribute among ``names`` (provider-shape tolerant)."""
    for name in names:
        candidate = getattr(value, name, None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _first_int(value: Any, name: str) -> int | None:
    candidate = getattr(value, name, None)
    if isinstance(candidate, int) and candidate > 0:
        return candidate
    return None


def _grounding_contexts(response: Any) -> list[Any]:
    """Collect File Search grounding contexts from a provider response.

    Works structurally (attribute access) so tests can pass lightweight
    stand-ins for the SDK response object.
    """
    contexts: list[Any] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is None:
            continue
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            context = getattr(chunk, "retrieved_context", None)
            if context is not None:
                contexts.append(context)
    return contexts


def _build_context(citations: list[Citation]) -> str:
    """Pack citations into the ``answerContext`` the Main Agent answers from."""
    parts = [
        f"[{index}] {citation.title}\n{citation.snippet}\nsource: {citation.uri}"
        for index, citation in enumerate(citations, start=1)
    ]
    return _clip("\n\n".join(parts), MAX_ANSWER_CONTEXT_CHARS)


def normalize_grounding(response: Any, *, max_results: int) -> GroundedEvidence:
    """Turn a provider response into frozen evidence (no provider types).

    Rules (CONTRACTS.md, ``knowledge_tool.search``):
    - no usable grounding -> empty ``answerContext``, ``resultCount`` 0, no citations;
    - citations are capped at ``max_results`` and deduplicated by source + page;
    - a chunk without a source URI or excerpt text is unusable evidence and skipped.
    """
    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()
    for context in _grounding_contexts(response):
        uri = _first_text(context, "uri")
        if not uri:
            continue
        snippet = _first_text(context, "text")
        if not snippet:
            continue
        page = _first_int(context, "page_number")
        source_id = _first_text(context, "document_name") or (
            f"{uri}#page-{page}" if page is not None else uri
        )
        key = (source_id, page)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                source_id=_clip(source_id, MAX_URI_CHARS),
                title=_clip(_first_text(context, "title") or uri, MAX_TITLE_CHARS),
                uri=_clip(uri, MAX_URI_CHARS),
                snippet=_clip(snippet, MAX_SNIPPET_CHARS),
                page=page,
            )
        )
        if len(citations) >= max(1, max_results):
            break
    if not citations:
        return GroundedEvidence("", 0, ())
    return GroundedEvidence(_build_context(citations), len(citations), tuple(citations))


class GeminiFileSearchKnowledgeBackend:
    """Narrow seam over Gemini File Search Hosted RAG.

    One public operation: ``search(query, max_results) -> GroundedEvidence``.
    The SDK client is constructed lazily per call so configuration (env vars)
    is read fresh and provider failures stay inside the typed-error boundary.
    Provider default chunking applies: no chunking configuration is ever sent.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        store_name: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get(ENV_API_KEY) or os.environ.get(ENV_FALLBACK_API_KEY)
        )
        self._store_name = (
            store_name if store_name is not None else os.environ.get(ENV_STORE)
        )
        self._model = model if model is not None else os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self._timeout_seconds = timeout_seconds

    @property
    def store_name(self) -> str | None:
        """Configured File Search store (full resource name), if any."""
        return self._store_name

    @property
    def model(self) -> str:
        """Grounded-generation model used for hosted retrieval."""
        return self._model

    def is_configured(self) -> bool:
        """True when an API key and a store are available (cheap readiness probe)."""
        return bool(self._api_key and self._store_name)

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        """Run hosted retrieval and normalize grounding into frozen output.

        Raises:
            KnowledgeBackendError: typed, user-safe failure (``unavailable``)
                for any provider problem: missing SDK, missing config, network
                or API errors, or timeout.
        """
        try:
            evidence = await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, max_results),
                timeout=self._timeout_seconds,
            )
        except KnowledgeBackendError:
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("gemini file search timed out after %ss", self._timeout_seconds)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        except Exception as exc:  # provider failure boundary: never leak details
            logger.debug("gemini file search failed: %s", exc)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        return evidence

    def _search_sync(self, query: str, max_results: int) -> GroundedEvidence:
        try:
            from google import genai  # lazy: optional provider dependency
        except ImportError as exc:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_NOT_CONFIGURED) from exc
        if not self._api_key or not self._store_name:
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_NOT_CONFIGURED)
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=query,
                config=genai.types.GenerateContentConfig(
                    tools=[
                        genai.types.Tool(
                            file_search=genai.types.FileSearch(
                                file_search_store_names=[self._store_name],
                                top_k=max_results,
                            )
                        )
                    ]
                ),
            )
        except Exception as exc:  # provider failure boundary: never leak details
            logger.debug("gemini file search call failed: %s", exc)
            raise KnowledgeBackendError(ToolErrorCode.UNAVAILABLE, USER_SAFE_UNAVAILABLE) from exc
        return normalize_grounding(response, max_results=max_results)
