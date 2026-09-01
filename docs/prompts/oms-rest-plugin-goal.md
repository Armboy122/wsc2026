/goal

# Goal: Integrate the External OMS REST Application as the First Small REST Plugin

Implement the smallest complete MVP that connects PEA One Agent to the separately deployed OMS application through the immutable `oms.openapi.yaml` contract, removes Sabuy from the active tool runtime, and lets the existing Knowledge flow return verified Sabuy website links already present in the approved DOCX sources.

This is an implementation goal, not a planning-only request. Continue until the critical paths work, focused validation passes, and the repository documentation matches the implementation. Do not deploy anything.

## Required communication style

- This prompt is intentionally written in English.
- Write all new or changed source-code comments and docstrings in Thai.
- Keep identifiers, types, class names, function names, environment variables, and wire fields in conventional English.
- User-facing application messages must be natural Thai.
- Progress updates and the final response to the user must be in Thai.

## Mandatory first actions

Before editing anything:

1. Read the attached handoff document.
2. Inspect the current branch, working tree, latest commit, and recent diffs. Do not assume the repository still matches this prompt.
3. Read these files completely or in all relevant sections:
   - `AGENTS.md`
   - `README.md`
   - `PRD.md`
   - `ARCHITECTURE.md`
   - `CONTRACTS.md`
   - `oms.openapi.yaml`
   - `pyproject.toml`
   - `.env.example`
   - `app/main.py`
   - `app/contracts.py`
   - `app/agent/main_agent.py`
   - `app/agent/registry.py`
   - `app/agent/stores.py`
   - `app/core/config.py`
   - `app/core/startup.py`
   - `app/core/di.py`
   - `app/llm/models.py`
   - `app/llm/prompting.py`
   - `app/llm/demo.py`
   - `app/tools/_base.py`
   - `app/tools/knowledge_tool.py`
   - `app/tools/oms_tool.py`
   - `app/tools/sabuy_tool.py`
   - `app/tools/voc_tool.py`
   - `app/backends/full_document_knowledge.py`
   - `app/backends/simulated_oms.py`
   - `app/live/bridge.py`
   - `app/live/gemini_live.py`
   - `web/app.js`
   - the nearby tests covering contracts, orchestration, OMS, Knowledge, VOC, startup, routes, and voice
4. Inspect commit `3fbca55` and all commits after it. Its subject mentions OMS, but verify the actual diff instead of trusting the subject.
5. Verify that the working tree is safe to edit. Preserve all existing user work and never overwrite unrelated changes.
6. Load and follow the `implement` and `codebase-design` skills. Use `scrutinize` or `code-review` for the final independent review if available.

## Team execution constraints

Use AgentTeams for delegated execution. Stage the team with explicit user review before running, unless the user explicitly instructs you to skip review in that session.

Use no more than three worker agents, and never create a fourth worker, nested subagents, or an additional workflow. The captain coordinates, integrates, resolves conflicts, and owns the final report.

Use these exact worker routes:

1. `terra-core`
   - provider: `openai-codex`
   - model: `gpt-5.6-terra`
   - responsibility: repository/contract audit, the smallest plugin seam, ToolRegistry/MainAgent/contracts integration, and preservation of the confirmation state machine.

2. `luna-oms`
   - provider: `openai-codex`
   - model: `gpt-5.6-luna`
   - responsibility: immutable OpenAPI mapping, typed OMS wire models, the OMS HTTP plugin, configuration, composition, and OMS-specific error normalization.

3. `deepseek-verification`
   - provider: `maxplus-claude`
   - model: `deepseek-v4-flash-0731`
   - responsibility: Sabuy-through-Knowledge link path, safe UI link rendering, focused tests, regression checks, documentation review, and adversarial verification of the finished critical paths.

Create the smallest useful task DAG. Parallelize only genuinely independent work. Give each worker explicit file ownership to avoid concurrent edits to the same files. Contract and integration files such as `app/contracts.py`, `app/main.py`, `ARCHITECTURE.md`, and `CONTRACTS.md` must have one clear owner. Do not let workers duplicate work.

## Development method: explicitly not TDD

Do not use TDD for this task.

Do not begin by writing tests. Do not create a large mock hierarchy. Do not stop implementation repeatedly to chase coverage. Do not refactor unrelated code for testability.

Use this sequence:

```text
inspect
→ agree the smallest contract changes
→ implement the working vertical slice
→ run focused smoke checks
→ fix important failures
→ add only high-value regression tests
→ run the relevant broader suite
→ finish
```

Priority:

```text
correct and safe competition demo
> finished end-to-end behavior
> small understandable implementation
> broad test coverage
> architectural purity
```

Never delete or weaken an existing meaningful test merely to make the suite green. Update tests only where the intentionally changed product contract makes the previous assertion obsolete.

## Current verified repository facts

Treat these as orientation only and verify them against the current checkout:

- Current baseline commit at prompt creation: `3fbca55`.
- `oms.openapi.yaml` was added earlier and is already committed.
- OMS is still commented out of the LLM runtime catalogue.
- Sabuy is also commented out of the LLM catalogue but is still instantiated in `app/main.py` because the registry currently requires exactly four tools.
- Existing OMS contracts still use the obsolete `areaCode` model and `SimulatedOmsBackend`.
- MainAgent currently contains important recent VOC behavior: resumable rejected VOC intake, duplicate read suppression, user-correctable operational error messages, and existing prepare/confirm/submit protection.
- Voice is a thin transport through MainAgent and has recent tracking-key safety behavior. Preserve it.
- The tracked working tree was clean before this prompt artifact was created. The prompt file itself may be untracked, and branch tracking may change. Re-check before editing.

## Non-negotiable external OMS ownership

The OMS application is owned and implemented in a different repository.

This repository must not implement:

- an OMS FastAPI server
- the three external OMS routes
- OMS persistence
- OMS network hierarchy resolution
- meter/transformer/feeder correlation
- OMS authentication that is not present in the contract
- a generated fake OMS server

`oms.openapi.yaml` is an immutable, already-approved contract that reflects the real OMS interface used for this demo.

Do not modify, move, regenerate, reinterpret, or extend `oms.openapi.yaml`. In particular:

- do not add an idempotency header
- do not add authentication
- do not change status codes
- do not rename fields
- do not add endpoints
- do not change required/optional fields

Implement the Agent-side caller exactly against it.

## What “client” means here

Do not build an `OmsClient` protocol, `MockOmsClient`, and `RestOmsClient` hierarchy for this MVP.

The Agent repository still needs a small HTTP caller because it is the consumer of the external OMS application. Keep that caller inside the OMS plugin implementation, using the existing `httpx` dependency. A small internal adapter/helper is acceptable when it makes the module clearer, but do not add a speculative multi-layer client framework.

There must be no runtime OMS mock mode. Unit tests may use `httpx.MockTransport` or an equivalent focused fake transport to exercise the immutable wire contract without starting the external OMS repository.

Use configurable values equivalent to:

```env
OMS_BASE_URL=http://127.0.0.1:8101
OMS_TIMEOUT_SECONDS=5
```

Do not invent secret configuration. Normalize trailing slashes safely. Do not log CA numbers, phone numbers, locations, descriptions, headers, or raw response bodies.

The external OMS application is still a demo integration for this project, so OMS `ToolResult.simulation` remains `true`. REST transport does not by itself mean production truth.

## Small plugin seam: required meaning and scope

The plugin seam is not simulation. It is the narrow interface between MainAgent/ToolRegistry and external REST integrations.

Build only the smallest seam that makes OMS isolated and establishes a repeatable pattern for future external REST plugins. A future integration may add its own typed plugin plus one explicit registration point without placing service-specific HTTP details in MainAgent.

The seam may expose concepts equivalent to:

- a stable plugin/tool name
- an LLM-facing semantic description
- exposed read/prepare actions and their input schemas
- internal submit actions that are never advertised to the LLM
- execution through the existing typed `ToolCall`/`ToolResult` flow
- prepare-to-submit mapping
- local reset of temporary prepared drafts only

Do not build:

- OpenAPI auto-discovery
- automatic exposure of arbitrary endpoints
- filesystem scanning
- Python entry points
- remote manifests
- dynamic package installation
- a plugin marketplace
- MCP
- LangChain or LangGraph
- a generic REST DSL
- a generic authentication framework

A new future REST integration may still require a typed adapter and explicit contract/registration change. The requirement is that MainAgent does not need service-specific URLs, HTTP methods, headers, paths, or response parsing.

Do not convert Knowledge or VOC into plugins. Preserve their current implementations and behavior except for the explicitly requested Sabuy-link change to Knowledge output.

## OMS semantic capabilities inside the Agent

The external OMS contract has exactly three HTTP operations:

```text
GET  /api/v1/outages/by-ca/{caNumber}
POST /api/v1/outages
POST /api/v1/outages/anonymous
```

The Agent must expose semantic capabilities while preserving write confirmation. Use clear internal action names consistent with repository conventions, covering:

```text
check outage by 12-digit CA
prepare outage report with CA
submit outage report with CA (internal only)
prepare anonymous outage report
submit anonymous outage report (internal only)
```

The exact internal names may follow the repository’s naming style, but both submit actions must be hidden from the LLM and must only run through the existing confirmation path.

### CA validation

A CA is exactly 12 ASCII digits:

```regex
^[0-9]{12}$
```

Trim surrounding whitespace at the user boundary when appropriate, but reject embedded spaces, dashes, letters, short values, and long values.

### Flow A: CA has an active related event

```text
User reports outage
→ collect/recognize CA
→ GET outage by CA
→ activeEvent is present
→ report the authoritative OMS message/status to the user
→ do not prepare or create another event
```

OMS owns all CA → meter → transformer → feeder resolution. MainAgent must never reproduce or infer that hierarchy.

### Flow B: CA has no active related event

```text
User reports outage
→ collect/recognize CA
→ GET outage by CA
→ activeEvent is null and recommendedAction is CREATE_METER_EVENT
→ collect or reuse the user’s outage description
→ optionally collect contactPhone/locationNote only when needed by the current UX
→ prepare a write without calling POST
→ show a reviewable pending action
→ explicit confirm endpoint/voice confirmation
→ internal submit
→ POST /api/v1/outages
→ return the authoritative OMS result
```

`description` is required by the immutable OpenAPI contract. `contactPhone` and `locationNote` are optional for the known-CA POST.

### Flow C: user does not know CA

Do not repeatedly demand a CA. Collect exactly the immutable required fields:

```text
description
location
contactPhone
```

Then:

```text
prepare without POST
→ show reviewable pending action
→ explicit confirmation
→ internal submit
→ POST /api/v1/outages/anonymous
→ return the authoritative OMS result
```

### Flow D: CA not found

Map HTTP 404 / `CA_NOT_FOUND` safely. Tell the user the CA was not found and offer to continue through the anonymous report flow. Do not disclose network identifiers or internal lookup details.

### Race/conflict behavior

Map HTTP 409 / `ACTIVE_EVENT_EXISTS` as an existing related event instead of crashing or reporting a successful duplicate creation.

### Failure behavior

Normalize at least:

```text
INVALID_CA / invalid input
CA_NOT_FOUND / not found
ACTIVE_EVENT_EXISTS / conflict
OMS timeout / unavailable
connection failure / unavailable
malformed or schema-invalid JSON / internal or unavailable, following repository conventions
unexpected HTTP status / unavailable
```

Never expose traceback text, `httpx` internals, endpoint URLs, headers, credentials, raw server errors, or raw response bodies to the user.

## Preserve the existing write state machine

Keep the existing invariant:

```text
prepare_*
→ pending_confirmation
→ explicit confirm endpoint or existing voice confirmation
→ internal submit_*
→ submitted | failed
```

Rules:

- Chat/LLM may call reads and `prepare_*` only.
- `prepare_*` validates and stores a local in-process draft but performs no OMS POST.
- MainAgent’s existing confirm path triggers the matching internal submit exactly once in the current process.
- Direct LLM-selected submit must fail closed.
- Rejected actions remain terminal.
- Preserve existing trace ordering and redaction.
- Keep the project’s internal idempotency behavior, but do not extend the external OpenAPI contract.
- `reset` may clear local OMS prepared drafts/caches but must never call the external OMS application to delete or reset data.

## Sabuy runtime removal and Knowledge continuation links

Sabuy must no longer be an active runtime tool.

Required behavior:

- Do not instantiate/register `SabuyTool` in the active runtime.
- Do not advertise Sabuy payment/account actions to any LLM catalogue.
- Remove stale greeting, capability, direct-response, prompt, demo-planner, startup, documentation, and active evaluation claims that say the Agent can perform Sabuy account/payment operations.
- It is acceptable to leave dormant Sabuy implementation files and their isolated unit tests in place if deleting them would create unrelated risk. Clearly document that they are not registered or user-accessible.
- Do not enable payment writes.

The approved Knowledge source already contains seven Sabuy Service DOCX files under `knowledge/source/`, including website URLs. Do not create a new QA document and do not rewrite these approved DOCX files.

Make the smallest safe Knowledge/UI change so a user asking how to continue a Sabuy service online can receive a clickable URL that exists verbatim in the selected full document:

1. Preserve document routing, full-file loading, citation validation, and no-evidence behavior.
2. Replace the current blanket “Do not provide links” answer instruction with a narrow rule: exact URLs may be returned only when they occur verbatim in the selected source text and are relevant to the user’s request.
3. Add deterministic post-validation: every `http://` or `https://` URL in the generated answer must occur verbatim in one of the selected full documents. If any URL is invented or modified, fail closed rather than returning it.
4. Render allowed URLs as safe clickable links in the web UI. Escape all surrounding text first, allow only `http://` and `https://`, use `target="_blank"` and `rel="noopener noreferrer"`, and do not introduce an XSS path.
5. Keep citation `uri` behavior and full-document citations unchanged unless an actual defect requires a narrow fix.

## Protected behavior from recent commits

Do not regress or redesign:

- VOC category/intake flow
- resumable correction after rejecting a prepared VOC case
- VOC `vocId` plus case-sensitive `trackingKey` tracking behavior
- persistence of submitted VOC cases across demo reset within the process, as currently documented
- duplicate read-call suppression
- user-correctable operational error messages
- Knowledge document routing/full-file/citation grounding
- VoiceBridge session-bound confirmation/rejection safety
- Gemini Live audio and tracking-key instructions
- thin public HTTP routes
- trace redaction and final-only output protection

Do not expand or redesign voice mode as part of this task. Existing voice behavior must continue to pass its tests. If OMS becomes reachable through the unchanged MainAgent bridge naturally, do not add a second voice-specific OMS implementation.

## Documentation that must match reality

Update the minimum required documentation and configuration examples so they no longer claim the old architecture. Keep `ARCHITECTURE.md`, `CONTRACTS.md`, `PRD.md`, `README.md`, `app/contracts.py`, runtime composition, and tests consistent where the changed behavior requires it.

Document this topology:

```text
MainAgent
→ existing ToolRegistry / small external plugin seam
→ OmsPlugin
→ httpx
→ external OMS application
```

Document that:

- `oms.openapi.yaml` is immutable and owned by the external integration contract
- this repository contains only the Agent-side connector
- OMS remains marked simulated for the competition demo
- Sabuy is not an active tool
- Sabuy website continuation uses verified URLs from the existing Knowledge DOCX sources
- future REST plugins require explicit typed adapters and registration; arbitrary OpenAPI auto-loading is not supported

## Essential tests only

Add tests after the implementation works. Keep them few and risk-driven.

At minimum, prove:

1. CA validation accepts exactly 12 ASCII digits and rejects malformed values.
2. Existing transformer/feeder/meter event result causes an informative response and no prepare/POST.
3. No active event leads to known-CA prepare; no POST occurs before confirmation; confirmation maps exactly to `POST /api/v1/outages`.
4. Unknown-CA flow collects description, location, and contact phone; no POST occurs before confirmation; confirmation maps exactly to `POST /api/v1/outages/anonymous`.
5. LLM-selected submit actions are never advertised and are rejected from chat.
6. REST mapping uses the exact paths, methods, request fields, success status `201`, and response schemas from `oms.openapi.yaml`.
7. `404`, `409`, timeout/connection failure, malformed JSON, and unexpected status are normalized safely.
8. Sabuy is absent from the active registry/catalogue/capability messages.
9. Knowledge can return an exact Sabuy URL from a selected existing DOCX, rejects an invented URL, and the UI renders an allowed URL safely.
10. Existing focused VOC, Knowledge, confirmation, trace, startup/routes, and voice regression tests still pass.

Use `httpx.MockTransport` or an equivalent transport fake for wire tests. Do not create a runtime `MockOmsClient`.

Run the narrowest checks while iterating, then run the relevant broader suite. Prefer repository commands such as:

```bash
uv run pytest -q <targeted test paths>
uv run pytest -q
```

Run `./scripts/evaluate http://127.0.0.1:8000` only when the application is intentionally running and the evaluation is relevant. Do not claim a live OMS integration was verified unless you actually exercised the separately running OMS application. Never issue a real OMS POST without explicit user approval and confirmation that the target is the demo environment.

## Scope exclusions

Do not implement:

- the OMS server or database
- a runtime OMS mock backend/client
- Sabuy REST integration
- Sabuy payments
- dynamic OpenAPI tool generation
- generic authentication
- MCP
- LangChain
- LangGraph
- multi-service orchestration infrastructure
- database or message queue
- WebSocket between Agent and OMS
- automatic background submission
- broad Knowledge refactoring
- VOC refactoring
- voice redesign
- production deployment

## Definition of done

The goal is complete only when:

- OMS is an active semantic tool backed by the external REST contract, not `SimulatedOmsBackend`.
- MainAgent contains no OMS URL/path/header/wire parsing or network hierarchy logic.
- Known-CA existing-event, known-CA no-event, and anonymous-report critical paths work.
- Both OMS writes remain prepare/confirm/submit and cannot be directly selected by the LLM.
- Sabuy is absent from the active runtime and no payment capability is advertised.
- Knowledge returns only verified Sabuy URLs already present in selected DOCX files, and the UI makes them safely clickable.
- Recent VOC, Knowledge, confirmation, trace, and voice behavior is not knowingly broken.
- Focused tests and the relevant full suite pass, or any unrelated pre-existing failure is reported with evidence.
- Documentation and `.env.example` match the actual implementation.
- No unnecessary abstraction or unrelated refactor was introduced.

## Required final response format

Respond to the user in Thai with these sections:

### Implemented
A concise list of working behavior.

### Architecture
Show the final MainAgent → plugin → external OMS flow and explain the small plugin seam.

### OMS contract mapping
List the exact three immutable HTTP operations and their internal safe actions.

### Sabuy and Knowledge
Explain that Sabuy is no longer an active tool and how verified DOCX links are returned.

### Files created
List every new file.

### Files modified
List every changed existing file and why it changed.

### Protected behavior
Explicitly report the status of Knowledge grounding, VOC, voice, confirmation safety, and Sabuy runtime removal.

### Validation performed
List exact commands and outcomes. Distinguish transport-mocked tests from any real external OMS verification.

### Remaining limitations
Report only genuine limitations, including the absence of live OMS verification if the external application was not run.

### Explicit non-actions
Confirm that you did not modify `oms.openapi.yaml`, implement the OMS server, create a runtime OMS mock client, enable Sabuy payments, bypass confirmation, use TDD, or build a large plugin framework.
