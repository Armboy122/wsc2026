# Verification

## Default repository check

```bash
.venv/bin/python -m pytest -q
```

`pytest` is installed only in the project virtualenv. `python3 -m pytest` fails with
`No module named pytest`.

## Verified baseline (pre-refactor, commit 718d40b)

`343 passed` on branch `refactor/adk-live-knowledge-only` before any source change.
Any later count must be explainable by tickets that intentionally added or deleted tests.

## Definition of done for a ticket

- The requested behavior works on the critical path.
- `.venv/bin/python -m pytest -q` passes.
- No test was deleted merely because it failed. Every removed test is classified:
  (A) still valid → fix code, (B) feature intentionally removed → remove with the feature,
  (C) stale contract → replace with the correct new contract test.
- Debug code, dead code, and unused imports introduced by the change are removed.

## Static architecture assertions that must hold at the end

- The active Knowledge implementation must not import or call a generative provider:
  no `generate_content`, no `google.genai` client construction, no OpenAI-compatible client.
- The ADK tool surface must expose exactly one Knowledge tool, `search_knowledge`. The removed
  catalog tool (`get_knowledge_documents`) and its catalog JSON must not remain in `app/` code,
  prompts or tests.
- The `search_knowledge` tool must run the index off the event loop (`asyncio.to_thread`) and
  may log only status, result counts and latency — never the query text or returned content.
- The voice runtime must not import `MainAgent`.
- OMS, VOC, pending actions, and confirm/reject tools must be absent from the ADK tool surface.

## Not provable in this environment

Real microphone capture, real Gemini Live audio, and true barge-in timing need a browser plus
valid `GEMINI_API_KEY`. Never report those as verified from mocked tests alone.
