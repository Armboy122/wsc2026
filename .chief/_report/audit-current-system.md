# Audit: current system before the refactor

Branch `refactor/adk-live-knowledge-only`, from `main` @ `718d40b`. Test baseline `343 passed`.
Every statement below was read from source, not inferred.

## Current voice path (traced end to end)

```text
web/ (app.js, media-handler.js, pcm-processor.js)
  → WS /ws/live                      app/api/live.py
  → branch on settings.voice_runtime ("legacy" DEFAULT, or "adk")
      legacy → app/live/gemini_live.py GeminiLiveSession
               + scoped_voice_agent(agent_service.agent)   app/live/scoped_agent.py
      adk    → app/runtime/adk_live.py AdkLiveSession
               → WscTools(agent=MainAgent, ...)            app/tools/adk_tools.py
               → create_adk_agent(model, client, tools)    app/agent/adk_agent.py
               → Runner.run_live(StreamingMode.BIDI)
```

Critical finding: `app/core/config.py:69` defaults `voice_runtime = "legacy"`, and
`app/api/live.py:33` only picks ADK when `VOICE_RUNTIME=adk`. So ADK is currently opt-in and
the legacy `GeminiLiveSession` is the default runtime.

## Where ADK depends on MainAgent

- `app/runtime/adk_live.py` imports `MainAgent` and takes `agent: MainAgent` in `__init__`,
  passes it to `WscTools`, and calls `self._agent.cancel_domain_intake(...)` on teardown.
- `app/tools/adk_tools.py` `WscTools.__init__(agent: MainAgent, ...)` builds its entire tool
  surface from `agent.tool_catalogue`, and calls `agent.execute_domain_tool`,
  `agent.advance_domain_intake`, `agent.confirm_pending_action`, `agent.reject_pending_action`,
  `agent.domain_action_is_open`.
- `app/agent/adk_agent.py` `create_adk_agent(*, model, client, tools: WscTools)` — tools are
  MainAgent-derived, exactly the shape the goal says to remove.

So the current ADK graph is `ADK → WscTools → MainAgent → ToolRegistry → KnowledgeTool`.

## Where Knowledge performs extra LLM calls (the nested-model problem)

`app/backends/full_document_knowledge.py` makes TWO generative calls per search:

1. `_route(client, query, catalog, max_results)` — line ~330. Sends catalog metadata and asks
   the model to return `{"sourceIds":[...]}`. This is the Document Router LLM.
2. `_answer(client, query, selected, texts)` — line ~360. Sends the full documents and asks the
   model to return `{"answer":..., "citations":[...]}`. This is the answering LLM.

Both go through `_json_response(client, model, prompt)` →
`client.models.generate_content(...)` at line 433. The client is built in `_make_client()`
(line ~254) via `from google import genai; genai.Client(api_key=...)`.

Result: today the runtime path is
`Gemini Live → Knowledge Tool → Gemini Router → Gemini Long Context → Gemini Live`
— three model calls per question. The goal requires exactly one.

There is one already-deterministic path worth keeping as precedent: `bill_evidence()` /
`_bill_evidence_sync()` load and SHA256-verify a fixed tariff document with **no** provider call.

## Deterministic pieces that must survive

In `full_document_knowledge.py`:

- `_catalog()` — allowlist builder. Resolves `source_root` strictly, skips symlinks, rejects
  anything not relative to the root, derives relative POSIX `sourceId`, skips dotfiles and
  `readme.md`. This is the allowlist and must be preserved.
- `_full_text()` — mtime/size-keyed text cache, raises on empty document.
- `_extract_document_title` / `_extract_markdown_title` — deterministic titles.
- `_hard_context_chars` budget check (`DEFAULT_HARD_CONTEXT_CHARS = 1_000_000`).
- `app/backends/knowledge_aliases.py` — `load_alias_rules` / `matching_rule`, deterministic
  query→sourceId rules validated against known source IDs. Already LLM-free.

DOCX support exists (`_extract_docx_text`, ~150 lines) but `knowledge/source/` contains only
`.md` files — verified by listing the tree.

## Scope to remove (reference counts by file, from grep)

- MainAgent referenced by 25 files (11 under `app/`, plus tests).
- `VOICE_RUNTIME`: `app/core/config.py:69,205`, `app/api/live.py:22,24,33`,
  `tests/test_adk_runtime.py:435,439`, `.env.example:137`.
- OMS/VOC/LINE touch ~40 files including `app/plugins/oms/`, `app/plugins/voc/`,
  `app/backends/simulated_oms.py`, `simulated_voc.py`, `app/tools/oms_tool.py`,
  `app/tools/voc_tool.py`, `app/line/`, `app/api/line.py`.
- Chat/REST surface in `app/api/routes.py`: `POST /api/v1/chat`, two action endpoints,
  `GET /api/v1/traces/{trace_id}`, `POST /api/v1/reset`, `GET /health`.
  Only `/health` survives the target scope.

## Prompt

`app/prompts/adk_voice.md` (4717 bytes) is dominated by OMS, VOC, CA numbers, taxonomy,
consent, pendingAction, confirm/reject, idempotencyKey, and billCalculation rules — all of
which leave scope. It needs a complete rewrite, not an edit.

## Sizes relevant to deletion

`app/agent/main_agent.py` 970 lines, `app/contracts.py` 681, `tests/test_adk_runtime.py` 441,
`app/live/bridge.py` 309, `app/live/gemini_live.py` 248, `app/agent/registry.py` 135,
`app/live/scoped_agent.py` 103, `app/api/routes.py` 92.
