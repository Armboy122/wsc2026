# Ticket 002 Report — Make ADK the only Voice runtime

## Implementation Summary

`/ws/live` now always creates `AdkLiveSession`; the `VOICE_RUNTIME` setting and `.env.example` entry are removed. The active ADK voice prompt now gives concise Thai, Knowledge-only instructions grounded in approved retrieved documents. Existing streaming, transcription, interruption, resumption, teardown, and reconnect behavior remains covered by tests. No legacy runtime modules or unrelated platform subsystems were deleted.

## Verification

- Focused ADK/runtime/config tests — 33 passed (Sol review run).
- Full suite: `.venv/bin/python -m pytest -q` — 352 passed.
- Changed-file LSP diagnostics — 0 findings.
- `git diff --check` — clean.
- Sol Standards and Spec review — PASS.

## Notes and Residual Risks

- Regression tests set the obsolete `VOICE_RUNTIME` environment variable only to verify it is ignored; application settings and `.env.example` no longer use it.
- Tests use fake WebSockets and an in-process ADK model; real Gemini Live, a physical microphone, Thai audio quality, and live barge-in were not exercised.
- Legacy platform/runtime removal and deterministic, single-model Knowledge are deferred to Stories 2 and 3.
