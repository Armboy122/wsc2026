# Ticket 001 Report — Direct ADK Knowledge Tool

## Implementation Summary

The ADK agent/runtime now accepts a direct `KnowledgeTool`, wraps it in the sole ADK-facing `AdkKnowledgeTool`, and forwards its typed result and citations into the same Live session. The ADK graph no longer imports or depends on `MainAgent` or `WscTools`. Existing Legacy routing remains temporarily for Story 1 Ticket 002.

## Files Changed

- `app/agent/adk_agent.py`
- `app/api/live.py`
- `app/core/di.py`
- `app/main.py`
- `app/runtime/adk_live.py`
- `tests/test_adk_runtime.py`
- `tests/test_adk_knowledge_tool.py`

## Verification

- Focused: `.venv/bin/python -m pytest -q tests/test_adk_knowledge_tool.py tests/test_adk_runtime.py` — 16 passed.
- Full suite: `.venv/bin/python -m pytest -q` — 346 passed (baseline 343; three new tests).
- `git diff --check` — clean.
- Sol review / Chief review-code gate — PASS, no blocking findings.

## Notes and Residual Risks

- Knowledge still uses the existing nested model calls. This is intentionally deferred to Story 2 and must be removed before final product acceptance.
- `/ws/live` still has its legacy/ADK selector until Story 1 Ticket 002.
- Real Gemini Live, microphone, Thai audio quality, and live barge-in were not exercised.
- LSP surfaced type findings in pre-existing fake-WebSocket/test harness code and existing `app.main` interfaces; no project type-check command is configured. These were not introduced by this ticket and do not affect the passing runtime tests.
