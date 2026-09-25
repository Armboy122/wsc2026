# Project Configuration

## Project

PEA Real-Time Knowledge Voice Agent — a Thai-language voice agent where ADK + Gemini Live
owns the entire conversation and the only business capability is deterministic retrieval of
approved local PEA Markdown documents.

## Development Commands

| Purpose | Command |
| --- | --- |
| Create venv (CPython 3.11) | `uv venv --python 3.11 .venv` |
| Install deps | `uv pip install --python .venv/bin/python 'fastapi>=0.115,<1.0' 'pydantic>=2.8,<3.0' 'uvicorn[standard]>=0.30,<1.0' 'httpx>=0.27' 'pyyaml>=6.0,<7.0' 'google-genai>=1.0,<3.0' 'google-adk==2.9.1' 'pytest>=8.0' 'pytest-asyncio>=0.24'` |
| Run tests | `.venv/bin/python -m pytest -q` |
| Run server | `.venv/bin/python -m uvicorn app.main:app --reload --port 8000` |

Notes verified during audit:

- `pytest` exists only inside the project virtualenv. `python3 -m pytest` fails with
  `No module named pytest`.
- `uv pip install -e .` fails: setuptools rejects the flat layout
  (`Multiple top-level packages discovered: ['app', 'web', 'data', 'knowledge', 'evaluation']`).
  Installing dependencies only is correct — `pyproject.toml` already sets `pythonpath = "."`.

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

- `app/` — FastAPI app, ADK agent/runtime, tools, knowledge, prompts, config
- `knowledge/source/` — approved Markdown documents, the only authoritative knowledge
- `knowledge/aliases/` — deterministic query→sourceId alias rules
- `web/` — existing voice UI (keep, do not redesign)
- `tests/`, plus colocated `*/tests/` packages

### Important Development Rules

- Branch for this work: `refactor/adk-live-knowledge-only`. Never commit to `main`.
- Never expose credentials, API keys, or customer-sensitive data in code, logs, or responses.
- Knowledge stays fail-closed: allowlisted local files only, relative source IDs, no path
  traversal, no arbitrary filesystem reads, no hallucinated citations.
- Do not silently truncate authoritative documents; exceed-budget is a structured failure.
- Do not add vector DB, embeddings, RAG, MCP, queues, or extra agents/LLMs.
