# ADK Live runtime migration

## Pre-change architecture audit

Baseline: main `2c8932d688b8ec70d38327ae5ad12f71d141ef85`.
Work branch: `feat/adk-live-runtime`. No changes to main.

- Entry point: `app.main:app` composes settings, full-document Knowledge,
  manifest-loaded VOC/OMS plugins, ToolRegistry, MainAgent and FastAPI routes.
- Audio: `web/app.js` → `gemini-live-client.js` → MediaHandler/AudioWorklet
  (PCM16 mono 16 kHz) → `/ws/live` → `GeminiLiveSession` → Gemini Live.
  Binary PCM16 24 kHz returns to MediaHandler; interruption flushes playback.
- Legacy Live exposes chat and confirm bridge functions. VoiceBridge keeps a
  conversation ID and current pending action, then calls MainAgent. MainAgent
  runs a separate bounded JSON planner/tool loop and enforces domain policies.
- State: per-socket VoiceBridge; process-local conversation, pending action,
  trace and plugin intake stores. Reconnecting starts a new conversation.
- ToolRegistry validates input/output using `app/contracts.py`. Knowledge uses
  selected full DOCX documents, grounded citations and tariff calculation.
  VOC owns catalog/consent/intake/prefill; OMS owns outage lookup and preparation.
  Operational calls go through existing REST adapters and remain simulated.
- Writes: prepare → session-bound explicit confirmation → idempotent submit.
  Pending actions and traces are also accessible through existing HTTP routes.
- Legacy voice is deliberately scoped to Knowledge/OMS; VOC is available in
  text. The requested ADK path adds voice access to enabled VOC without changing
  the legacy allowlist or disabling its intake/consent requirements.
- Active legacy planner instructions come from `app/llm/prompting.py` and plugin
  response policies; voice instructions live in `app/live/gemini_live.py`.
  Markdown prompts also document domain expectations; they are not all loaded.
- Configuration: `.env`, `llm-settings.yaml`, Settings; Gemini key/model/voice,
  separate Knowledge provider settings, OMS/VOC URLs, credentials and timeouts.
- Existing regression suites cover contracts, orchestration, write safety,
  grounding, plugins, Live transport/bridge and frontend audio behavior.

## Migration boundary

ADK will own the live model session, conversation event history, tool dispatch,
tool-result return and streaming. WSC keeps contracts, validation, grounding,
plugin intake, pending-action state machine, presentation and HTTP contracts.
The new path must not invoke MainAgent.handle_chat's planner loop. Small domain
entry points may reuse its existing deterministic execution/presentation methods.
Legacy remains the default until real microphone acceptance is verified.

## Official API verification

Checked 2026-09-16: stable Google ADK release v2.9.1 (2026-09-15).
Sources: https://github.com/google/adk-python/releases/tag/v2.9.1,
https://adk.dev/live/sessions/, https://adk.dev/live/configuration/,
https://adk.dev/live/events/, https://adk.dev/live/custom-server/,
https://ai.google.dev/gemini-api/docs/live-api/capabilities.

Use Agent, Runner, an injected SessionService, LiveRequestQueue.send_realtime,
RunConfig and Runner.run_live. Run input and output concurrently. Configure
AUDIO output, input/output transcription, automatic activity detection with
START_OF_ACTIVITY_INTERRUPTS, and SessionResumptionConfig. Forward typed ADK
events to the existing wire protocol; do not implement a second tool loop.
ADK upstream resumption and browser reconnect are separate lifecycles.
