# Ticket 002 Report — Let Gemini Live select and retrieve source documents

## Implementation Summary

The ADK Voice Agent now receives the deterministic Knowledge catalog (source IDs, titles,
headings, approved aliases) appended to its instruction and exposes exactly one Knowledge
capability, `get_knowledge_documents(source_ids)`. The tool validates the model-selected IDs
through Ticket 001's `KnowledgeDocumentService` and returns either complete Markdown documents
with `sourceId`/title/`knowledge://` provenance or one structured safe failure. It never
answers, summarizes, or searches by query; the same Gemini Live session receives the result
and answers.

Knowledge model clients, router/answer calls, and their settings were removed:

- `FullDocumentKnowledgeBackend` lost its Gemini client, router prompt, answer prompt, JSON
  model call, API-key/model/provider/base-URL/timeout parameters, and query alias routing. It
  now keeps only the deterministic, hash-verified tariff evidence used by the legacy Chat bill
  calculation; legacy free-text Chat Knowledge search fails closed with a structured
  `unavailable` error. The module is deleted with Chat in Story 3.
- Settings `knowledge_llm`, `knowledge_provider`, `knowledge_backend_name`,
  `gemini_long_context_model` (env `KNOWLEDGE_LLM_*`, `KNOWLEDGE_PROVIDER`,
  `KNOWLEDGE_BACKEND_NAME`, `GEMINI_LONG_CONTEXT_MODEL`) and the `knowledge` role in
  `llm-settings.yaml` were removed; `.env.example` updated.
- The unused router/answer prompt `app/prompts/knowledge.md` was deleted.
- App wiring builds `KnowledgeCatalog → KnowledgeDocumentService` at startup; DI, `/ws/live`,
  and `AdkLiveSession` take the service. Health readiness for Knowledge is now "catalog has
  approved documents" instead of a model-client check.

Realtime transport (`app/runtime/adk_live.py` streaming, transcription, interruption,
resumption, teardown) is unchanged apart from the Knowledge dependency type.

## Files Changed

- `app/agent/adk_agent.py`, `app/runtime/adk_live.py`, `app/api/live.py`, `app/core/di.py`,
  `app/main.py`, `app/core/config.py`, `app/prompts/adk_voice.md`
- `app/backends/full_document_knowledge.py` (model code removed)
- `app/prompts/knowledge.md` (deleted), `.env.example`, `llm-settings.yaml`
- Tests: `tests/test_adk_knowledge_tool.py`, `tests/test_adk_runtime.py`,
  `knowledge/tests/test_full_document_knowledge.py`, `tests/test_qa_chat_flow.py`,
  `tests/test_tariff_critical_path_api.py`, `app/core/tests/test_config.py`,
  `app/core/tests/test_startup.py`

## Test Classification

- Removed (B, feature intentionally removed): 17 router/answer tests in
  `knowledge/tests/test_full_document_knowledge.py` (Gemini JSON call, router selection,
  answer citation/URL/concise-format validation, context budget before answer call, alias routing and unknown-alias config, router timeouts, TOU grounded answer). Alias and
  selection safety are covered by Ticket 001's catalog/service tests.
- Replaced (C, stale contract): `search_knowledge` ADK tool tests → `get_knowledge_documents`
  tests; Chat QA answer test → Chat Knowledge fails closed without fabricated answer/citations;
  Knowledge LLM config assertions → absence of Knowledge model settings; startup test → wires
  the deterministic service; DOCX line-break test now checks extraction directly.
- Kept (A): tariff evidence, tamper, TOU catalogue tests (constructor args updated).

## Verification

- New/updated runtime tests with the real ADK `Runner.run_live` and a fake Live connection:
  the model's `get_knowledge_documents` call returns complete documents and provenance over
  the same Live connection and session; `google.genai` `Models/AsyncModels.generate_content`
  are patched to fail and record zero calls; an unsafe selection returns a structured error
  into the same session; the agent instruction contains the catalog metadata but no document
  bodies.
- Tool tests: one focused declaration; traversal, absolute, unknown, duplicate, too many,
  wrong type, extra argument, empty, and over-budget selections fail closed; no absolute
  source path in results; static checks that the ADK tool and `app/knowledge` make no
  generative calls and the Voice runtime imports neither MainAgent nor the legacy backend.
- Focused: `tests/test_adk_knowledge_tool.py tests/test_adk_runtime.py tests/test_knowledge_*.py
  knowledge/tests app/core/tests tests/test_qa_chat_flow.py` — 115 passed.
- Full suite: `.venv/bin/python -m pytest -q` — **384 passed**.
- `git diff --check` clean; `ruff --select F` on changed Python files reports only two
  pre-existing unused `typing.Any` imports (`app/core/di.py`, `app/core/tests/test_startup.py`).

## Acceptance Status

**PASS** — reviewer: `xai/grok-4.7` (read-only acceptance review via pi, 2026-09-26).
Verdict: PASS, no blocking findings. The reviewer re-ran the focused set (115 passed) and the
full suite (384 passed), checked `git diff --check`, and probed the production catalog
instruction (45 entries with sourceId/title/headings/aliases, 3 aliased, no absolute source
root).

Sol (`openai-codex/gpt-6-sol`) was tried first per project rules and failed with
`Codex error: The usage limit has been reached`.
Deviation: reviewer was `xai/grok-4.7` instead of Sol because the Codex usage limit was
reached; approved by owner 2026-09-26.

## Notes and Residual Risks

- No live Gemini Live request, microphone, or audio was exercised; tool-calling behavior of the
  real `gemini-3.8-live` model against this catalog is unverified.
- Legacy Chat routes still exist until Story 3; Chat free-text Knowledge questions now return
  a structured "unavailable" error (bill calculation still works from verified evidence).
- Docs (`ARCHITECTURE.md`, `PRD.md`, `CONTRACTS.md`, `knowledge/README.md`,
  `knowledge/source/README.md`, `web/README.md`) still describe the removed Document Router;
  Story 3 Ticket 002 owns the documentation rewrite.
- The catalog is embedded in the instruction at session creation (about 45 documents); catalog
  changes require a new session/restart.
- Limits remain the Ticket 001 defaults (`max_documents=5`, `max_total_chars=120000`); not
  configurable via settings (no current requirement).
- Reviewer non-blocking notes (not fixed; PASS means stop):
  - The catalog JSON is placed in `Agent.instruction`, which ADK scans for `{identifier}`
    session-state placeholders. The current corpus has no valid placeholders, so Gemini Live
    receives it intact, but a future heading/alias containing `{name}` could raise `KeyError`
    and fail the turn. Escape braces or use an instruction provider if documents may contain
    them.
  - `AdkKnowledgeTool.service` property is unused.
  - Instruction tests assert sourceId/title only, not headings/aliases (production instruction
    does include all four).
