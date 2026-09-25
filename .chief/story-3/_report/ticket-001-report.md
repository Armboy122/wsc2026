# Ticket 001 Report — Reduce server surface, DI, and settings to Voice

## Implementation Summary

The running application is now the minimal Voice graph:
`settings → KnowledgeCatalog → KnowledgeDocumentService → (per /ws/live connection)
AdkKnowledgeTool → ADK Gemini Live runtime`, plus static Voice UI hosting and `GET /health`.

- `app/main.py` constructs only settings, the deterministic catalog/service, the FastAPI app,
  the health and live routers, and the static mount. No MainAgent, ToolRegistry, plugins, LLM
  adapters, judge client, guided flows, legacy Knowledge backend, or LINE startup hook.
- `app/api/routes.py` keeps only `GET /health`. Chat, action confirm/reject, trace, and reset
  routes were removed; `app/api/line.py` (LINE webhook route) was deleted.
- `/health` now reports `status` (`ok`/`degraded`), `knowledgeBackend` (catalog has approved
  documents) and `liveVoice` (`configured`/`not_configured`, boolean presence of
  `GEMINI_API_KEY` only). The obsolete `llmAdapter` and `simulationMode` fields were removed
  from `HealthResponse` in `app/contracts.py` (integration-level contract change;
  `CONTRACTS.md` is rewritten in Ticket 002).
- `app/core/di.py` holds only the Knowledge service (MainAgent/adapter registries removed).
- `app/core/startup.py` builds the FastAPI app only (tool-registry validation and startup hook
  removed). CORS middleware and `CORS_ORIGINS` were removed: the UI and `/ws/live` are served
  same-origin by this process, so CORS is not proven necessary.
- `app/core/config.py` retains only `APP_ENV`, `LOG_LEVEL`, `GEMINI_API_KEY`,
  `GEMINI_LIVE_MODEL`, `GEMINI_LIVE_VOICE`, `KNOWLEDGE_SOURCE_ROOT`. Removed: main/judge LLM
  settings and `llm-settings.yaml` loading (file deleted), OMS, VOC, LINE, CORS settings.
  `.env.example` rewritten to match.

Per the MUST NOT, core OMS/VOC/MainAgent/LINE/legacy-voice implementation files were not
deleted; they are now unreferenced by the running app and are removed in Ticket 002. The
Voice UI and realtime transport were not changed.

## Test Classification

- Removed (B, feature removed with its route): `tests/test_mvp_evaluation.py` (12, Chat/action/
  trace/reset HTTP envelope), `tests/test_tariff_critical_path_api.py` (5, bill calculation via
  `/api/v1/chat`), 8 client-based tests in `tests/test_contracts.py`, 9 Chat/action/trace/reset/health
  route tests in `app/api/tests/test_routes.py`, 5 tool-registry validation tests in
  `app/core/tests/test_startup.py`, and main/judge/local LLM settings tests in
  `app/core/tests/test_config.py`.
- Replaced (C): route tests → only `/health` and `/ws/live` registered, obsolete routes return
  404/405, static UI served, health ok/degraded shape without leaking the key; startup test →
  minimal graph and entry-point import allowlist; config tests → exact settings field set,
  obsolete env ignored and not leaked, dotenv precedence, redaction.
- Kept (A) with a test-only shim: legacy plugin loader tests and one MainAgent catalogue test
  now build plugins from `app/plugins/tests/_legacy_settings.py` because OMS/VOC settings no
  longer exist in the app; these modules/tests are deleted in Ticket 002.
- Bill-calculation unit coverage (`tests/test_electricity_bill.py`,
  `knowledge/tests/test_knowledge_tool.py`) is unchanged.

## Verification

- `.venv/bin/python -m pytest -q` — **353 passed** (384 before; 31 fewer from removed route/
  settings/registry tests listed above, net of new tests).
- `ruff --select F` on added/modified Python files — clean. `git diff --check` — clean.
- ADK WebSocket routing remains covered by
  `tests/test_adk_runtime.py::test_fastapi_websocket_always_uses_adk_without_runtime_selector`.

## Acceptance Status

**PASS** — reviewer: `xai/grok-4.7` (read-only acceptance review via pi, 2026-09-26).
Verdict: PASS, no blocking findings. The reviewer re-ran the full suite (353 passed) and
probed the app with `TestClient`: `/health` returns the new shape without leaking the key,
`/` and `/phone.html` are served, removed Chat/LINE paths return 404, and the settings field
set is exactly the six Voice/Knowledge settings.

Sol (`openai-codex/gpt-6-sol`) was tried first and failed with
`Codex error: The usage limit has been reached`.
Deviation: reviewer was `xai/grok-4.7` instead of Sol because the Codex usage limit was
reached; owner-approved fallback (2026-09-26).

## Notes and Residual Risks

- The chat-first `web/index.html` / `web/app.js` still contains Chat, pending-action, trace
  and reset UI that now calls removed routes (404/405). The voice toggle there and
  `web/phone.html` use only `/ws/live`. Removing stale product UI is Ticket 002 scope.
- Bill calculation is no longer reachable from any running entry point (it was only exposed
  through Chat; Story 2 Ticket 002 already replaced the voice tool that accepted
  `billCalculation`). Its code remains until an owner decision in Ticket 002.
- `scripts/evaluate` and `evaluation/datasets` target the removed Chat API; README,
  ARCHITECTURE, CONTRACTS, PRD, and docs still describe removed routes/settings (Ticket 002).
- No live Gemini/microphone check was performed.
- Reviewer non-blocking notes (not fixed; PASS means stop):
  - FastAPI's default `/openapi.json` (always) and `/docs`, `/redoc` (development only)
    remain; they are framework defaults, not product routes. The route test inspects only
    `APIRoute`s.
  - Health tests cover both-ready and both-missing but not split readiness (the handler does
    report it correctly).
