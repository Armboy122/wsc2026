# Project Configuration

## Project

PEA Real-Time Knowledge Voice Agent — a Thai-language voice agent where ADK + Gemini Live
owns the entire conversation and the only business capability is deterministic retrieval of
approved local PEA Markdown documents.

## Development Commands

| Purpose | Command |
| --- | --- |
| Create venv (CPython 3.11) | `uv venv --python 3.11 .venv` |
| Install deps | `uv sync --all-extras` (includes the `index` extra: `numpy`, `pythainlp`, `rank-bm25`, `sentence-transformers`) |
| Run tests | `uv run --all-extras pytest -q` (real-model tests are opt-in: `uv run --all-extras pytest -m model`; they skip unless `BAAI/bge-m3` is already cached) |
| Run server | `.venv/bin/python -m uvicorn app.main:app --reload --port 8000` |

Notes verified during audit:

- `pytest` exists only inside the project virtualenv. `python3 -m pytest` fails with
  `No module named pytest`.
- `uv pip install -e .` fails: setuptools rejects the flat layout
  (multiple top-level packages, e.g. `app`, `web`, `knowledge`).
  Installing dependencies only is correct — `pyproject.toml` already sets `pythonpath = "."`.
- Story 4 index settings: `KNOWLEDGE_INDEX_DIR` (derived cache, gitignored, default
  `.cache/knowledge-index`) and `KNOWLEDGE_EMBEDDER` (`bge-m3` default, or `fake` for the
  offline test suite). The cache is never written under `knowledge/`.

## Architecture Overview

### Tech Stack

Python 3.11, FastAPI (WebSocket + static hosting), Pydantic v2, Google ADK 2.9.1,
google-genai (Gemini Live), vanilla JS/HTML voice frontend under `web/`.

### Key Architectural Patterns

Target runtime (this branch), single conversational model only:

```text
Browser microphone → WS /ws/live → ADK Runner.run_live() → Gemini Live
  → search_knowledge(query) → local hybrid index (Q&A first + chunks) → same Gemini Live session → speaker
```

- Gemini Live via ADK is the ONLY conversational/reasoning model and the only orchestrator.
- Knowledge is deterministic infrastructure: it answers nothing and never calls a generative
  model. Gemini Live calls `search_knowledge(query)`; the tool returns approved Q&A first and
  then source-attributed chunks from the local hybrid index.

### Directory Structure

- `app/` — FastAPI app (`api/`, `core/`), ADK agent (`agent/`), Live runtime (`runtime/`), deterministic knowledge (`knowledge/`), prompt, contracts
- `knowledge/source/` — approved Markdown documents, the only authoritative knowledge
- `knowledge/aliases/` — maintainer alias metadata used to expand index queries (not evidence)
- `.cache/knowledge-index/` — derived, gitignored index cache (never a source of truth)
- `web/` — existing voice UI (keep, do not redesign)
- `tests/`, plus colocated `*/tests/` packages

### Important Development Rules

- Branch for this work: `refactor/adk-live-knowledge-only`. Never commit to `main`.
- Never expose credentials, API keys, or customer-sensitive data in code, logs, or responses.
- Knowledge stays fail-closed: allowlisted local files only, relative source IDs, no path
  traversal, no arbitrary filesystem reads, no hallucinated citations.
- Knowledge performs zero generative model calls. Embedding models (`BAAI/bge-m3` behind the
  `Embedder` protocol) are allowed and are not generative.
- Approved documents are never edited, reformatted, deleted or renamed by code or tickets;
  the index is a derived artefact that rebuilds automatically.
- Do not add another conversational model, MCP, queues, or extra agents/LLMs. Vector DB
  servers, RAGFlow and Gemini File Search stay out of scope.

## Stories

| Story | Title | Status |
| --- | --- | --- |
| story-1 | ADK-only Voice core | done |
| story-2 | Single-model deterministic Knowledge | done |
| story-3 | Remove platform scope (Voice-only) | done |
| story-4 | RAG redesign: hybrid local Knowledge search (`search_knowledge`) | in progress — tickets 001–003 implemented; owner decisions D0–D7 recorded (`.chief/story-4/_decisions/pending-decisions.md`) |
