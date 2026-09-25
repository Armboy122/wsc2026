# Story 1 — ADK-only Voice Core

## Goal

Make ADK + Gemini Live the only voice runtime, and remove MainAgent from the voice execution
graph. After this story `/ws/live` always serves an `AdkLiveSession`, and the ADK agent depends
on a Knowledge tool directly rather than on `MainAgent`/`WscTools`.

## Why now

Audit finding: `VOICE_RUNTIME` defaults to `legacy`, so ADK is currently opt-in and the legacy
`GeminiLiveSession` is what actually runs. The new spine must be unconditional before any
dead-scope deletion is safe.

## Delivers

1. `/ws/live` unconditionally uses ADK. No `VOICE_RUNTIME` selector anywhere.
2. `create_adk_agent(model=..., knowledge_tool=...)` — no `MainAgent`, no `WscTools`.
3. A single Knowledge tool is the only capability exposed to ADK.
4. Streaming, transcription, interruption, and teardown behavior preserved.
5. The rewritten voice prompt, scoped to Knowledge only.

## Out of Scope

- Removing the nested Knowledge LLM calls. Story 1 may route the ADK tool at the existing
  deterministic seam, but the router/answer model removal itself is Story 2.
- Deleting `main_agent.py`, `app/plugins/oms|voc`, `app/line/`, `app/live/` legacy modules, or
  the chat REST routes. Story 3 owns deletion once nothing references them.
- Frontend redesign. The existing `web/` UI stays.

## Done when

`.venv/bin/python -m pytest -q` passes, the voice runtime imports no `MainAgent`, and no
`VOICE_RUNTIME` value can change which runtime serves `/ws/live`.
