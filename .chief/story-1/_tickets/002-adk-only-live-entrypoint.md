# Ticket 002 — Make ADK the only Voice runtime

Type: implementation
Status: resolved
Blocked by: 001

## TASK

Make `/ws/live` unconditionally construct `AdkLiveSession`, remove the Voice runtime selector, and reduce the active voice prompt/protocol to the Knowledge Voice Agent.

## FILES / COMPONENTS IN SCOPE

`app/api/live.py`, `app/runtime/adk_live.py`, `app/core/config.py`, `app/prompts/adk_voice.md`, `.env.example`, ADK/runtime/config tests, and only directly affected voice documentation.

## MUST DO

- Remove `VOICE_RUNTIME` branching and configuration; `/ws/live` always serves ADK.
- Preserve PCM16 validation/streaming, BIDI config, transcription, interruption and playback-flush events, safe errors, session deletion, client/queue/task cleanup, and clean reconnect behavior.
- Remove legacy write-related response event handling from the active ADK protocol.
- Rewrite the ADK prompt as concise Thai Knowledge-only instructions: retrieve approved PEA sources for PEA facts, use only retrieved evidence, admit insufficient evidence, use Live conversation history for follow-ups, concise natural speech, do not read citations aloud.
- Add tests that runtime selection is unnecessary and event/cleanup behavior remains intact.

## MUST NOT DO

- Do not delete legacy runtime modules yet; Story 3 owns deletion after all references/tests are handled.
- Do not redesign the existing Voice UI or WebSocket event contract beyond removing obsolete write events.
- Do not change approved documents or invent live-provider acceptance evidence.

## DEPENDENCIES

Ticket 001.

## ACCEPTANCE CRITERIA

- `/ws/live` always constructs ADK and no `VOICE_RUNTIME` setting is needed or read.
- All preserved realtime invariants are covered by tests.
- Active prompt contains no OMS/VOC/CA/consent/write/pending/confirmation/rejection instructions.
- Full test suite passes.

## STOP CONDITION

Stop when the ADK-only endpoint, focused prompt, preserved transport behaviors, and tests are green. Do not delete unrelated platform subsystems.
