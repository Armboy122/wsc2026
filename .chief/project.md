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
  → Knowledge Tool → approved local Markdown → same Gemini Live session → speaker
```

- Gemini Live via ADK is the ONLY conversational/reasoning model and the only orchestrator.
- Knowledge is deterministic infrastructure: it selects nothing and answers nothing, it only
  returns trusted approved documents chosen by Gemini Live.
- Knowledge must perform zero generative model calls.

### Directory Structure

- `app/` — FastAPI app (`api/`, `core/`), ADK agent (`agent/`), Live runtime (`runtime/`), deterministic knowledge (`knowledge/`), prompt, contracts
- `knowledge/source/` — approved Markdown documents, the only authoritative knowledge
- `knowledge/aliases/` — maintainer alias metadata shown in the catalog (no server-side query matching)
- `web/` — existing voice UI (keep, do not redesign)
- `tests/`, plus colocated `*/tests/` packages

### Important Development Rules

- Branch for this work: `refactor/adk-live-knowledge-only`. Never commit to `main`.
- Never expose credentials, API keys, or customer-sensitive data in code, logs, or responses.
- Knowledge stays fail-closed: allowlisted local files only, relative source IDs, no path
  traversal, no arbitrary filesystem reads, no hallucinated citations.
- Do not silently truncate authoritative documents; exceed-budget is a structured failure.
- Do not add vector DB, embeddings, RAG, MCP, queues, or extra agents/LLMs.
  (Owner approved decision D0 on 2026-09-26: Story 4 replaces this with a local hybrid index
  with embeddings (RAG, Q&A first). Ticket 003 rewrites this rule; see
  `.chief/story-4/_decisions/pending-decisions.md`.)

## Stories

| Story | Title | Status |
| --- | --- | --- |
| story-1 | ADK-only Voice core | done |
| story-2 | Single-model deterministic Knowledge | done |
| story-3 | Remove platform scope (Voice-only) | done |
| story-4 | RAG redesign: hybrid local Knowledge search (`search_knowledge`) | in progress — owner decisions D0–D7 recorded (`.chief/story-4/_decisions/pending-decisions.md`) |
