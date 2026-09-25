# Ticket 002 Report — Delete obsolete platform code and rewrite documentation

## Owner decisions applied (2026-09-26)

1. Bill calculation is dead code per the plan → deleted (`app/backends/electricity_bill.py`, its
   use in `app/tools/knowledge_tool.py`, its contracts in `app/contracts.py`, `tests/test_electricity_bill.py`).
2. **All knowledge documents kept** — nothing under `knowledge/source/**`, `knowledge/aliases/**`
   or `docs/research/**` was deleted or edited (verified: `git ls-files knowledge docs` at HEAD vs
   now differs only by the deleted non-knowledge files listed below).
3. Approved deletions: LINE; Chat/pending-action/trace/reset/geolocation UI; `data/mock/*`,
   `evaluation/datasets`, `scripts/evaluate`, `scripts/add-plugin`, `docs/integration_report.md`
   (checked first: none is under `KNOWLEDGE_SOURCE_ROOT`, none is referenced by the catalog);
   remaining OMS/VOC/MainAgent/plugin code; AGENTS.md update; CONTRACTS.md rewrite; pyyaml removal;
   `/docs`, `/redoc`, `/openapi.json` disabled.

## Deleted

- **Agent/planner**: `app/agent/{main_agent,registry,guided_flow,response_policy,stores}.py`,
  `app/prompts/{main_agent,json_planner,final_response}.md`.
- **Packages removed entirely**: `app/backends/` (simulated OMS/Sabuy/VOC, Gemini LLM adapter,
  legacy full-document knowledge, electricity bill), `app/tools/` (knowledge/OMS/VOC/Sabuy tools,
  WscTools), `app/plugins/` (loader, OMS/VOC/Sabuy/demo plugins + manifests), `app/llm/` (LLM
  clients/factory/prompting), `app/live/` (legacy GeminiLiveSession/VoiceBridge/scoped agent),
  `app/line/` (LINE runtime).
- **Contracts**: `app/contracts.py` reduced to `to_camel`, `FrozenModel`, `ToolErrorCode`
  (wire values `invalid_input`/`unavailable`/`internal`) and `HealthResponse` (chat, pending action, trace,
  citation, tool names, bill calculation, OMS/VOC models removed). `app/core/errors.py`: unused
  `PlatformException` family + handler removed (validation/catch-all handlers kept).
- **Data/scripts/docs**: `data/` (mock OMS/Sabuy/VOC), `evaluation/` (datasets/evaluator),
  `scripts/` (`evaluate`, `add-plugin`), `docs/integration_report.md`,
  `docs/qa-learning-roadmap.md` (stale Chat-escalation roadmap, not knowledge content),
  `docs/adk-runtime-migration.md` (legacy/ADK migration notes; current architecture now in
  ARCHITECTURE.md).
- **Web**: `web/linkify.js`; Chat textarea/send, prompt chips, geolocation, trace panel/button,
  reset button, SIMULATED/backend badges and `agent.response` rendering removed from
  `index.html`, `app.js`, `gemini-live-client.js`, `phone.js`; unused CSS rules/keyframes pruned
  from `styles.css` (1083 → ~400 lines; only selectors not referenced by any page/script).
- **Dependencies**: `pyyaml` removed from `pyproject.toml`; `uv lock` succeeded (network
  available) and `uv.lock` no longer lists it as a direct dependency. pyyaml remains in the lock
  only as a transitive dependency (`google-adk`, `uvicorn[standard]`); no application code imports it. `uv sync --frozen --extra dev --extra voice
  --extra adk` passes. `testpaths` pruned to existing dirs.
- **Tests** (see classification).

Moved: `app/backends/knowledge_aliases.py` → `app/knowledge/aliases.py` (used by the catalog;
unused query-matching helper `matching_rule` removed).

## Kept (knowledge content — untouched)

- `knowledge/source/PEA_*.md` — 34 service/announcement documents
- `knowledge/source/qa/qa_*.md` — 11 approved Q&A documents (catalog total: 45)
- `knowledge/source/README.md`, `knowledge/source/qa/README.md` — policy files (not catalogued)
- `knowledge/aliases/README.md`, `installment-electricity-bill.md`, `new-electricity-connection.md`,
  `refund-electricity-deposit.md`
- `docs/research/electricity-tariff-sep-2569.md` — tariff research note (outside the runtime
  catalog; kept as knowledge content)
- `knowledge/README.md` — kept; content rewritten to describe the deterministic ADK tool flow.

`tests/test_architecture.py::test_all_knowledge_documents_are_retained` guards these counts.

## Documentation

- `CONTRACTS.md` rewritten: `GET /health`, `WS /ws/live` wire protocol, `get_knowledge_documents`
  input/success/error contract and limits, settings.
- `AGENTS.md`: mission/boundaries/testing now describe Voice + deterministic Knowledge;
  `./scripts/evaluate`, OMS/VOC, write state machine and pending-action rules removed.
- `README.md`, `ARCHITECTURE.md`, `PRD.md`, `knowledge/README.md`, `web/README.md` rewritten to the
  actual system: flow, install/run commands, env vars, test commands, manual voice checklist
  (**pending, not performed**), performance (**not measured**), real-provider limitations.
- `.env.example`: comment updated (docs/openapi always disabled). `.env` not touched.
- `.chief/project.md`: install command without pyyaml, directory overview updated.

## Test Classification

- **B — removed with the feature**: `tests/test_agent_orchestration.py` (42), `app/live/tests/*`
  (bridge 32, scoped agent 10), `app/plugins/tests/*` (loader 13, VOC intake 12, VOC flow 11,
  VOC prefill 8), `app/backends/tests/*` (simulated VOC/Sabuy/OMS 25, Gemini adapter 3),
  `app/tools/tests/*` (OMS/VOC/Sabuy 21), `app/llm/tests/*` (18), `app/line/tests` (9),
  `app/core/tests/test_llm_factory.py` (6), `tests/test_line_signature.py` (4),
  `tests/test_electricity_bill.py` (4), `tests/test_evaluator_datasets.py`,
  `tests/test_voc_golden_dataset.py`, `tests/test_qa_chat_flow.py`, `tests/test_live_session.py`,
  `tests/test_frontend_linkify.py`, `tests/test_contracts.py` (removed models), and 8 WscTools/
  MainAgent tests in `tests/test_adk_runtime.py` (OMS/VOC/prepare/confirm/pending/slow-op).
- **C — replaced by existing coverage**: `knowledge/tests/*` (legacy KnowledgeTool/full-document
  backend) → `tests/test_knowledge_catalog.py`, `tests/test_knowledge_documents.py`,
  `tests/test_adk_knowledge_tool.py` (added in Story 2).
- **A — kept**: ADK wire/transport/event tests in `tests/test_adk_runtime.py`, Knowledge tests,
  `tests/test_live_frontend_audio.py`, `app/api/tests`, `app/core/tests`.
- **New**: `tests/test_architecture.py` (deleted paths absent, no imports of deleted modules or
  `yaml`, contracts reduced, web JS/HTML has no `/api/v1`/`agent.response`/geolocation/pending,
  no pyyaml direct dependency, knowledge documents retained); `/docs`, `/redoc`,
  `/openapi.json` added to the obsolete-route 404 test.

## Verification

- `.venv/bin/python -m pytest -q` — **107 passed** (353 before; decrease = removed-feature tests above, +25 new cases: 22 architecture, 3 docs/openapi route).
- `uvx ruff check --select F app tests` — clean.
- `node --check` on every `web/*.js` — clean.
- No live Gemini call was made; `.env` not created or read.

## Residual Risks / Open Items

- Manual voice acceptance (real Gemini Live, microphone, Thai speech quality, barge-in) and any
  latency/performance measurement are **pending** — documented as such in README/PRD.
- `knowledge/source/README.md` and `knowledge/aliases/README.md` still use older "Document Router" /
  alias-matching wording; left untouched under the owner's keep-all-knowledge rule.
- ADK instruction injection: `{...}` in the catalog JSON can be interpreted by ADK's instruction
  templating (noted in Story 2); not changed here.
- CSS pruning was selector-based; the voice UI was not visually verified in a browser.
- `httpx` remains a runtime dependency although only tests use it (outside this ticket's scope).
- `web/phone.js` mute/speaker buttons are visual-only mocks (pre-existing, unchanged).
- `APP_ENV` is now only a label (no behaviour depends on it since docs are always disabled).

## Acceptance Status

**PASS** — reviewer: `xai/grok-4.7` (read-only acceptance review via pi, 2026-09-26), round 2.

- Round 1 FAIL: CONTRACTS.md/knowledge/README.md listed error codes by enum name instead of the
  wire values (`invalid_input`/`unavailable`/`internal`). Fixed; URI wording aligned to
  `knowledge://source/<sourceId>`, stale `styles.css` header updated.
- Round 2 PASS, no blocking findings. Non-blocking: phone.js mute/speaker are visual-only; `httpx`
  is a direct dependency not imported by app code; `gemini-live-client.js` sends an ignored
  `?channel=` query; phone.js transcript overlay ignores the `replace` flag (index page honours it).

Deviation: reviewer was xai/grok-4.7 instead of Sol because the Codex usage limit was reached; owner-approved fallback (2026-09-26).
