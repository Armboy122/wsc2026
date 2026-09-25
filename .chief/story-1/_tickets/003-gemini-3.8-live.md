# Ticket 003 — Use Gemini 3.8 Live

Type: configuration
Status: resolved
Blocked by: 002

## TASK

Switch the ADK voice runtime default and this checkout's local setting to the user-requested `gemini-3.8-live` model.

## FILES / COMPONENTS IN SCOPE

`app/core/config.py`, `.env.example`, local `.env` (model line only), `app/core/tests/test_config.py`, `README.md`, `PRD.md`, and `docs/adk-runtime-migration.md` model references.

## MUST DO

- Make `gemini-3.8-live` the default `GEMINI_LIVE_MODEL` and document it.
- Update only the model setting in the existing local `.env`; preserve all credentials and other values without displaying them.
- Record that the repository already pins ADK `2.9.1`; do not unnecessarily change the dependency.
- Add a deterministic config test for the default model.
- Do not claim real Gemini Live or microphone validation unless actually performed.

## MUST NOT DO

- Do not read, print, log, or modify the user's API key or other secret values.
- Do not add dependencies, change the ADK version, or alter voice transport behavior.
- Do not make a live provider call without explicit confirmation that may consume account quota.

## DEPENDENCIES

Story 1 Tickets 001 and 002; official Gemini model documentation.

## ACCEPTANCE CRITERIA

- `load_settings()` resolves the requested model in this checkout without exposing credentials.
- Fresh `.env.example` and relevant docs use the new model.
- Configuration tests pass and the working tree remains free of secrets.

## STOP CONDITION

Stop after model configuration/documentation, deterministic tests, and local setting verification pass. Real provider testing is a separate explicit step.
