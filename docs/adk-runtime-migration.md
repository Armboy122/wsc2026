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
Sources: <https://github.com/google/adk-python/releases/tag/v2.9.1>,
<https://adk.dev/live/sessions/>, <https://adk.dev/live/configuration/>,
<https://adk.dev/live/events/>, <https://adk.dev/live/custom-server/>,
<https://ai.google.dev/gemini-api/docs/live-api/capabilities>,
<https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live>.

Use Agent, Runner, an injected SessionService, LiveRequestQueue.send_realtime,
RunConfig and Runner.run_live. Run input and output concurrently. Configure
AUDIO output, input/output transcription, automatic activity detection with
START_OF_ACTIVITY_INTERRUPTS, and SessionResumptionConfig. Forward typed ADK
events to the existing wire protocol; do not implement a second tool loop.
ADK upstream resumption and browser reconnect are separate lifecycles.

## Old and new execution

Old: microphone → existing UI → WebSocket → custom GeminiLiveSession →
VoiceBridge → MainAgent JSON planner loop → domain tools → Gemini Live → speaker.

New: microphone → existing UI → WebSocket → ADK Runner/run_live → PEA One Agent
→ WSC tool adapters → existing domain execution → ADK tool response → Gemini
Live → existing speaker playback. Gemini Live is the model connection held by
ADK, not an additional planner downstream of the domain tools.

Knowledge/VOC/OMS implementations remain authoritative. The only changes inside
existing tool execution/intake are moving synchronous REST/catalog waits off the
async event loop. No business schemas, sources, taxonomy or REST URLs changed.
New MainAgent methods expose deterministic execution/intake/pending status only.
The existing planner remains for legacy voice, text and LINE.

## Run

```bash
git switch feat/adk-live-runtime
uv sync --frozen --extra dev --extra voice --extra adk
# If .env does not already exist, copy .env.example, then configure it.
VOICE_RUNTIME=adk uv run --frozen --extra voice --extra adk uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, allow microphone access and press the existing mic
button. Use localhost or HTTPS for browser microphone access. Roll back by
restarting the same command with `VOICE_RUNTIME=legacy`. No data migration.

| Setting | Purpose |
| --- | --- |
| `VOICE_RUNTIME` | `legacy` default, or `adk`; unknown values fail closed |
| `GEMINI_API_KEY` | Required for real Live and default Knowledge provider |
| `GEMINI_LIVE_MODEL` | Default `gemini-3.8-live`; requires account access |
| `GEMINI_LIVE_VOICE` | Existing default `Puck`; Thai instructed by agent prompt |
| `KNOWLEDGE_LLM_MODEL`, `KNOWLEDGE_SOURCE_ROOT` | Existing Knowledge settings; retain verified documents |
| `OMS_BASE_URL`, `OMS_API_KEY`, `OMS_TIMEOUT_SECONDS` | Existing OMS REST service configuration |
| `VOC_BASE_URL`, `VOC_API_KEY`, `VOC_TIMEOUT_SECONDS` | Existing VOC REST service configuration |
| `VOC_CONSENT_NOTICE_VERSION` | Existing VOC consent configuration |
| `MAIN_LLM_*` / `llm-settings.yaml` | Still used by text/legacy and VOC's existing prefill helper |

ADK is an optional extra pinned at `2.9.1`; `uv.lock` resolves GenAI `2.23.0`.
The voice constraint now permits GenAI 2.x. All old regression tests passed with
that SDK. No GOOGLE_API_KEY duplicate or process-global credential mutation is
needed: the existing GEMINI_API_KEY is passed explicitly to the ADK Gemini model.

## Validation results

Baseline: **330 passed** on the SDK required by ADK. Initial failures were caused
by this workspace's SOCKS proxy lacking `socksio`; installing that environment
dependency resolved them without project changes.

Final suite: **343 passed**, 6 dependency deprecation warnings.
Commands: `.venv/bin/python -m pytest -q`, `node --check web/app.js`,
`node --check web/gemini-live-client.js`, `git diff --check`.
No separate project build/lint/type-check configuration exists.

A real Uvicorn process served the UI (HTTP 200). The missing-key WebSocket path
returned the expected safe error and closed with 1011. `scripts/evaluate` ran
against localhost using the demo planner: exit 0, 70 scenarios, routing/write
safety 1.0, health degraded because Knowledge credentials were absent, Knowledge
correctness 0.0. This is an offline envelope/safety result, **not live acceptance**.

The ADK tests use the installed Runner/run_live/SessionService with a fake
BaseLlmConnection, real WSC domain services and mocked HTTP/provider boundaries.
They prove ADK dispatch/result-return wiring rather than merely stubbing Runner.

| Acceptance | Evidence / remaining gate |
| --- | --- |
| A startup | Uvicorn/static UI and existing app regression suite pass |
| B WebSocket | FastAPI tests select both runtimes; actual socket missing-key error/close verified |
| C microphone → Gemini | PCM reaches ADK's model connection in test; real device/provider pending |
| D Gemini → browser | PCM event mapping and existing playback tests pass; audible playback pending |
| E interruption | Event flush mapping and nonblocking operational wait tested; real barge-in pending |
| F Knowledge | Existing grounding/citation suite + ADK adapter and Runner test pass; live answer pending |
| G VOC | Catalog intake through preparation, consent boundary and lookup tested; real configured API pending |
| H OMS | Lookup/preparation/confirmation and idempotent submission tested using mocked HTTP |
| I return to conversation | Real ADK Runner returns tool results and subsequent audio in the same run |
| J follow-up context | Two turns, ADK event history and pending state persistence tested; natural Thai follow-up pending |
| K complete first utterance | Complete structured input prepares without clarification; spoken extraction not verified |
| L missing information | Adapter validates required fields and returns only missing field names; spoken question quality pending |
| M cleanup | Queue/task/client/session cleanup, fresh reconnect and disconnected socket tests pass |
| N error isolation | Safe provider errors, no raw payload disclosure, subsequent connection remains usable |

## Limitations and remaining TODOs

- No WSC Gemini key was available in this checkout/environment. No real Gemini
  audio, microphone, subjective Thai quality or real OMS/VOC integration is claimed.
- Before promoting ADK: configure credentials/test REST endpoints and complete
  C–L with the actual browser. Include all-details-first, incomplete details,
  correction, cancellation, HTTP button confirmation and repeated follow-up cases.
- VOC intake intentionally retains its existing consent/CA and catalog rules.
  Its prefiller only fills eligible catalog choices; it may still ask for free-text
  details given earlier. K/L require live evaluation and may expose this existing
  limitation. Do not silently skip consent to make a conversation appear smoother.
- Speech confirmation intent is model-interpreted, as in legacy. The adapter
  additionally rejects prepare+confirm in the same user turn and foreign IDs.
- Browser reconnect starts fresh, by design; upstream Live resumption is enabled
  but has not been exercised against Google's service. In-memory state is not
  durable across process restarts. WSC action/trace retention is unchanged.
- `session.ready` in ADK mode means input readiness, not provider authentication.
- No production rollout/merge was performed. Keep legacy default; the branch is
  ready for review, **not yet approved as a verified replacement runtime**.
