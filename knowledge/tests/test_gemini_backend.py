"""Tests for the Gemini File Search backend seam (no live provider calls)."""

from __future__ import annotations

import asyncio
import sys
import types

from app.backends.gemini_file_search import (
    ENV_API_KEY,
    ENV_FALLBACK_API_KEY,
    ENV_STORE,
    USER_SAFE_NOT_CONFIGURED,
    USER_SAFE_UNAVAILABLE,
    GeminiFileSearchKnowledgeBackend,
    GroundedEvidence,
    KnowledgeBackendError,
    normalize_grounding,
)
from app.contracts import ToolErrorCode


# --- lightweight stand-ins for the SDK response shape -----------------------

class Ctx:
    def __init__(self, uri=None, title=None, text=None, page_number=None, document_name=None):
        self.uri = uri
        self.title = title
        self.text = text
        self.page_number = page_number
        self.document_name = document_name


class Chunk:
    def __init__(self, retrieved_context):
        self.retrieved_context = retrieved_context


class Meta:
    def __init__(self, chunks):
        self.grounding_chunks = chunks


class Candidate:
    def __init__(self, metadata):
        self.grounding_metadata = metadata


class Response:
    def __init__(self, candidates):
        self.candidates = candidates


def make_response(*ctxs) -> Response:
    return Response([Candidate(Meta([Chunk(ctx) for ctx in ctxs]))])


# --- normalize_grounding ----------------------------------------------------

def test_normalize_two_chunks_builds_citations_and_context() -> None:
    evidence = normalize_grounding(
        make_response(
            Ctx(uri="https://pea.example/a", title="A", text="text-a", page_number=1, document_name="doc/a"),
            Ctx(uri="https://pea.example/b", title="B", text="text-b", document_name="doc/b"),
        ),
        max_results=3,
    )
    assert isinstance(evidence, GroundedEvidence)
    assert evidence.result_count == 2
    assert [c.source_id for c in evidence.citations] == ["doc/a", "doc/b"]
    assert evidence.citations[0].uri == "https://pea.example/a"
    assert evidence.citations[0].title == "A"
    assert evidence.citations[0].snippet == "text-a"
    assert evidence.citations[0].page == 1
    assert evidence.citations[1].page is None
    assert evidence.answer_context.startswith("[1] A")
    assert "[2] B" in evidence.answer_context
    assert len(evidence.answer_context) <= 4000


def test_normalize_no_evidence_means_empty_context() -> None:
    for response in (Response([]), Response([Candidate(None)]), make_response()):
        evidence = normalize_grounding(response, max_results=3)
        assert evidence == GroundedEvidence("", 0, ())


def test_normalize_dedupes_by_source_and_page() -> None:
    ctx = Ctx(uri="https://pea.example/a", title="A", text="t", page_number=1, document_name="doc/a")
    evidence = normalize_grounding(make_response(ctx, Ctx(**vars(ctx))), max_results=5)
    assert evidence.result_count == 1
    assert len(evidence.citations) == 1


def test_normalize_caps_at_max_results() -> None:
    ctxs = [
        Ctx(uri=f"https://pea.example/{i}", title=f"T{i}", text=f"t{i}", document_name=f"doc/{i}")
        for i in range(5)
    ]
    evidence = normalize_grounding(make_response(*ctxs), max_results=3)
    assert evidence.result_count == 3
    assert len(evidence.citations) == 3


def test_normalize_skips_chunks_without_uri_or_text() -> None:
    evidence = normalize_grounding(
        make_response(
            Ctx(uri=None, title="no uri", text="x", document_name="d1"),
            Ctx(uri="https://pea.example/2", title="no text", text="", document_name="d2"),
            Ctx(uri="https://pea.example/3", title="good", text="ok", document_name="d3"),
        ),
        max_results=5,
    )
    assert evidence.result_count == 1
    assert evidence.citations[0].source_id == "d3"


def test_normalize_source_id_falls_back_to_uri() -> None:
    evidence = normalize_grounding(
        make_response(Ctx(uri="https://pea.example/only", title="T", text="t", page_number=4)),
        max_results=1,
    )
    assert evidence.citations[0].source_id == "https://pea.example/only#page-4"


def test_normalize_clips_long_fields_to_contract_limits() -> None:
    evidence = normalize_grounding(
        make_response(
            Ctx(
                uri="https://pea.example/" + "x" * 3000,
                title="t" * 600,
                text="s" * 5000,
                document_name="d",
            )
        ),
        max_results=1,
    )
    citation = evidence.citations[0]
    assert len(citation.uri) == 2000
    assert len(citation.title) == 500
    assert len(citation.snippet) == 1000
    assert len(evidence.answer_context) <= 4000


# --- search(): configuration, lazy import, provider boundary ----------------

def make_backend(**kwargs) -> GeminiFileSearchKnowledgeBackend:
    return GeminiFileSearchKnowledgeBackend(**kwargs)


def test_search_without_config_is_typed_unavailable(monkeypatch) -> None:
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.delenv(ENV_FALLBACK_API_KEY, raising=False)
    monkeypatch.delenv(ENV_STORE, raising=False)
    backend = make_backend()
    assert backend.is_configured() is False
    try:
        asyncio.run(backend.search("q", 3))
    except KnowledgeBackendError as exc:
        assert exc.code is ToolErrorCode.UNAVAILABLE
        assert exc.message == USER_SAFE_NOT_CONFIGURED
    else:
        raise AssertionError("expected KnowledgeBackendError")


def test_search_without_sdk_is_typed_unavailable(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "google", None)  # force ImportError
    backend = make_backend(api_key="k", store_name="fileSearchStores/x")
    assert backend.is_configured() is True
    try:
        asyncio.run(backend.search("q", 3))
    except KnowledgeBackendError as exc:
        assert exc.code is ToolErrorCode.UNAVAILABLE
        assert exc.message == USER_SAFE_NOT_CONFIGURED
    else:
        raise AssertionError("expected KnowledgeBackendError")


def test_provider_failure_never_leaks_details(monkeypatch) -> None:
    fake_genai = types.ModuleType("google.genai")
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai

    class BoomClient:
        def __init__(self, **kwargs):
            raise RuntimeError("boom api_key=SECRET-123 endpoint=https://secret.example")

    fake_genai.Client = BoomClient
    fake_genai.types = types.SimpleNamespace(
        GenerateContentConfig=object, Tool=object, FileSearch=object
    )
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    backend = make_backend(api_key="k", store_name="fileSearchStores/x")
    try:
        asyncio.run(backend.search("q", 3))
    except KnowledgeBackendError as exc:
        assert exc.code is ToolErrorCode.UNAVAILABLE
        assert exc.message == USER_SAFE_UNAVAILABLE
        assert "SECRET-123" not in exc.message
        assert "secret.example" not in exc.message
    else:
        raise AssertionError("expected KnowledgeBackendError")


def test_search_normalizes_live_shaped_response(monkeypatch) -> None:
    """A well-formed provider response flows through to frozen evidence."""
    fake_genai = types.ModuleType("google.genai")
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    captured: dict = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return make_response(
                Ctx(uri="https://pea.example/rates", title="Rates", text="tier 1 = 150 kWh",
                    page_number=1, document_name="fileSearchStores/x/documents/1")
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    fake_genai.Client = FakeClient
    fake_genai.types = types.SimpleNamespace(
        GenerateContentConfig=lambda **kw: kw,
        Tool=lambda **kw: kw,
        FileSearch=lambda **kw: kw,
    )
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    backend = make_backend(api_key="k", store_name="fileSearchStores/x", model="gemini-2.5-flash")
    evidence = asyncio.run(backend.search("what are the tiers", 3))
    assert evidence.result_count == 1
    assert evidence.citations[0].source_id == "fileSearchStores/x/documents/1"
    assert evidence.citations[0].snippet == "tier 1 = 150 kWh"
    # the retrieval query is forwarded verbatim, top_k follows maxResults
    assert captured["contents"] == "what are the tiers"
    tool_cfg = captured["config"]["tools"][0]["file_search"]
    assert tool_cfg["file_search_store_names"] == ["fileSearchStores/x"]
    assert tool_cfg["top_k"] == 3
