# Goal: Build the VOC REST Plugin from `voc.openapi.yaml`

> **สถานะ: postponed / dormant future specification.** เอกสารนี้ไม่ใช่ขอบเขตของ MVP ปัจจุบัน ห้ามใช้เพื่อเปิด VOC ใน runtime, UI, prompt, docs หรือ evaluator จนกว่าจะมีคำสั่งงานใหม่โดยตรง ปัจจุบันเปิดใช้เฉพาะ Knowledge และ OMS; เนื้อหาด้านล่างเก็บไว้เพื่อการออกแบบในอนาคตเท่านั้น

## Purpose

Implement the smallest complete VOC plugin vertical slice for PEA One Agent.

The target is a **demo clone of the real VOC user journey**, not a production connection to PEA VOC. The demo may implement deterministic fixtures and in-memory state, but its visible behavior and data structure must resemble the real public VOC flow closely enough to validate the end-to-end user experience.

This document is written for the implementation agent. Follow it as an execution specification, not as optional design guidance.

## Required output

Deliver a working VOC plugin integration that:

1. uses `voc.openapi.yaml` as the immutable external REST contract;
2. registers `VocPlugin` directly in the active plugin registry;
3. removes the old `VocTool`/`SimulatedVocBackend` implementation from the active runtime;
4. restores and improves the MainAgent VOC conversation flow;
5. preserves `prepare → explicit confirm → submit` write safety;
6. supports the six public VOC journeys;
7. creates a demo case and returns `vocNumber + keyCode`;
8. tracks one case using `vocNumber + keyCode`;
9. keeps every VOC result visibly simulated;
10. adds only tests that protect the critical path and safety rules.

Do not deploy anything.

## Communication and code style

- Progress updates and the final report must be in Thai.
- New or changed source-code comments/docstrings must be in Thai.
- Identifiers, class names, types, environment variables and JSON fields remain conventional English.
- User-facing messages must be natural Thai.
- Prefer direct code over a generic plugin framework.
- Do not introduce TDD. Implement the vertical slice first, then add the essential tests listed below.

## Mandatory first actions

Before editing:

1. Inspect the current branch, `git status`, latest commits and active diffs. Another goal may have completed the OMS plugin seam after this document was written.
2. Preserve every unrelated user or agent change. Never reset, checkout or overwrite a dirty file blindly.
3. Read these files completely or in all relevant sections:
   - `AGENTS.md`
   - `PRD.md`
   - `ARCHITECTURE.md`
   - `CONTRACTS.md`
   - `voc.openapi.yaml`
   - `oms.openapi.yaml`
   - `docs/research/voc-external-spec-research.md`
   - `app/contracts.py`
   - `app/agent/main_agent.py`
   - `app/agent/registry.py`
   - `app/agent/voc_intake.py`
   - `app/agent/stores.py`
   - `app/core/config.py`
   - `app/core/startup.py`
   - `app/main.py`
   - the final OMS plugin implementation and its focused tests
   - existing VOC tests and evaluation rows
   - voice bridge tests covering VOC and confirmation
4. Verify the final plugin seam instead of assuming file names from this specification still match the working tree.
5. Treat `voc.openapi.yaml` as immutable during implementation. If implementation is impossible without changing it, stop and report the exact mismatch instead of silently changing the contract.

## Authoritative sources

Use this priority order:

1. `voc.openapi.yaml` — external VOC demo REST wire contract
2. this `spec.md` — plugin and MainAgent behavior
3. `CONTRACTS.md` and `app/contracts.py` — public Agent envelopes and pending-action safety
4. `ARCHITECTURE.md` — module ownership and runtime topology
5. `docs/research/voc-external-spec-research.md` — evidence from the public VOC site
6. existing tests — current implementation evidence, not permission to preserve stale behavior

When old VOC tests or code conflict with `voc.openapi.yaml` and this document, update or remove the stale VOC test/code. Do not weaken Knowledge, OMS, trace, confirmation or voice safety to make VOC pass.

## Product scope

### In scope

- Six user-facing VOC journeys
- Catalog read
- Rich structured intake data needed by those journeys
- Local prepare and pending action
- Explicit confirm/reject
- External demo case creation
- Idempotent case submission
- Single-case tracking
- Conversation interruption/resume
- Voice-compatible field collection and explicit confirmation
- Safe errors, trace redaction and simulation labeling
- VOC Plugin HTTP behavior verified with deterministic transport mocks
- Optional live smoke verification when the separately owned VOC demo application is available

### Explicitly out of scope for this MVP

- Production PEA VOC connectivity
- Authentication/authorization for production
- Public or staff `list all cases`
- Admin case management
- File upload
- CAPTCHA
- Satisfaction survey
- Cancellation or editing after submission
- Notification delivery by real SMS/email
- Persistent database
- queues, microservices or generic OpenAPI auto-loading
- plugin marketplace/discovery
- generic dynamic form engine
- TDD or exhaustive coverage
- deployment

## Core architecture

The required runtime flow is:

```text
User / Voice
    ↓
MainAgent
    ↓
PluginRegistry
    ↓
VocPlugin
    ↓ HTTP according to voc.openapi.yaml
External VOC Demo Application
```

The external VOC demo application is a separate deliverable owned by the team that receives `voc.openapi.yaml`. This assignment implements the Agent-side `VocPlugin` only; do not add a second FastAPI server to the PEA One Agent repository. Verify transport behavior with `httpx.MockTransport`. If a separately running VOC demo endpoint is available, also run one non-production smoke flow for catalog → create → lookup. If it is unavailable, report that live verification was not performed and do not claim end-to-end external integration.

### MainAgent ownership

MainAgent owns:

- VOC intent detection;
- choosing between OMS and VOC;
- the deterministic intake state;
- deciding the next missing field;
- presenting catalog choices;
- asking for consent;
- preparing the review summary;
- creating and storing pending actions;
- accepting explicit confirm/reject through existing decision paths;
- deciding when the plugin may submit;
- conversation interruption/resume;
- final Thai response from authoritative plugin results.

### VocPlugin ownership

VocPlugin owns:

- the HTTP base URL and timeout;
- exact path/method/header/body mapping from `voc.openapi.yaml`;
- typed wire request and response validation;
- catalog caching for the current process if useful;
- local prepared-draft storage keyed by idempotency key;
- translating external errors into safe internal error codes;
- returning authoritative typed results to MainAgent;
- clearing only local drafts/cache on reset;
- closing the HTTP client cleanly.

VocPlugin must not own the conversation, decide which question to ask, generate user-facing prose, auto-confirm a write or infer missing user data.

## No retained `VocTool`

The application module must be a plugin, not the old simulated tool implementation.

Required outcome:

- Create a class named `VocPlugin`.
- Place it with the final plugin convention established by OMS, preferably under `app/plugins/`.
- Register `VocPlugin` directly at the registry seam.
- Do not create or retain a `VocTool` wrapper.
- Do not subclass `SimulatedTool`.
- Remove `SimulatedVocBackend` from runtime composition.
- Remove the mock category fixture from runtime after catalog comes from the plugin.
- Delete dormant VOC tool/backend files and obsolete isolated tests when safe; do not leave two competing implementations.

The LLM provider may still use the word “tool” for function calling. That transport terminology does not justify keeping an application module named `VocTool`.

## Small plugin interface

Use the existing final OMS plugin seam where possible. Do not build a second framework for VOC.

The VOC plugin needs these semantic actions:

| Semantic action | Visibility | Behavior | External HTTP |
|---|---|---|---|
| `get_catalog` | MainAgent/LLM read | Return six journeys and valid intake options | `GET /api/v1/voc/catalog` |
| `prepare_case` | MainAgent/LLM prepare | Validate/store a local draft and return normalized safe preview data | none |
| `submit_case` | internal only | Submit the prepared draft once after explicit confirmation | `POST /api/v1/voc/cases` |
| `get_case` | MainAgent/LLM read | Track one case | `POST /api/v1/voc/cases/lookup` |

Do not expose `submit_case` to normal chat planning or the LLM catalogue. The existing confirm path must be the only caller.

If the final generic function-call envelope is still named `ToolCall`/`ToolResult`, it may be reused to avoid a repository-wide rename. The concrete VOC implementation and registration must still be `VocPlugin`, with no `VocTool` wrapper.

## Local prepare contract and ownership

Use one explicit lifecycle:

1. MainAgent generates a new opaque `idempotencyKey` immediately before `prepare_case`. The LLM and user never supply it.
2. MainAgent calls `prepare_case` with a typed `VocPrepareCaseInput`:

```text
VocPrepareCaseInput
  idempotencyKey: string
  request: CreateVocCaseRequest
```

3. VocPlugin validates the request/catalog relationships and stores one `PreparedVocDraft`:

```text
PreparedVocDraft
  idempotencyKey: string
  payload: CreateVocCaseRequest
  payloadHash: string
  state: PREPARED | SUBMITTING | SEALED
```

4. VocPlugin returns typed `VocPrepareCaseOutput` containing only normalized preview data:

```text
VocPrepareCaseOutput
  journeyCode
  journeyLabel
  classificationLabels
  frequencyLabel?: string
  severityLevel?: integer
  reporterDisplay: string
  maskedPhone?: string
  incidentDisplay: string
  detail: string
```

5. MainAgent alone renders the Thai review message from that output and creates the pending action that stores the same `idempotencyKey`.
6. PendingActionStore remains the single owner of the terminal decision and terminal submit result used for repeated-confirmation replay.
7. On confirm, MainAgent passes only the pending action identity to the existing confirm path; the confirm path resolves the stored `idempotencyKey`, and VocPlugin submits the exact stored draft. It never rebuilds the body from LLM output.
8. On reject, MainAgent marks the pending action terminal and calls an internal plugin cleanup method to discard that prepared draft without external HTTP.
9. On timeout/unknown outcome, VocPlugin returns the draft to `PREPARED` so a retry uses the same payload and key.
10. On success, VocPlugin changes the draft to `SEALED` and may discard the raw PII payload after the PendingActionStore has persisted the typed terminal result for the current process.

Do not let MainAgent and VocPlugin both generate prose, keys or competing terminal-result caches.

## External REST mapping

### Configuration

Add only the settings required by the plugin:

```text
VOC_BASE_URL=http://127.0.0.1:8102
VOC_TIMEOUT_SECONDS=5
```

Normalize the base URL once. Do not hard-code paths outside the plugin.

No VOC API key is required for this local demo contract. Do not add a fake production credential.

### `get_catalog`

Call:

```http
GET /api/v1/voc/catalog
```

Validate the full response. It must contain exactly:

- all six `JourneyCode` enum values exactly once, with no duplicate `code` even when other fields differ;
- all seven `RequestTypeCode` enum values exactly once, with no duplicate `code` even when other fields differ;
- taxonomy nodes with valid parent relationships;
- incident frequencies;
- severity levels;
- title prefixes;
- at least one service area;
- `simulation: true`.

Catalog values are authoritative. MainAgent must not hard-code a second six-item category table.

A small in-process cache is allowed because the catalog is read-only. Reset may clear it. Do not add Redis, disk caching or background refresh.

### `prepare_case`

`prepare_case` performs no HTTP request.

It must:

1. validate the payload using the action-specific typed model;
2. validate every selected journey/taxonomy/location code against the loaded catalog;
3. enforce journey-specific required fields;
4. require a valid consent record;
5. store the exact full draft locally using the MainAgent-generated idempotency key;
6. return the typed normalized preview data defined above, without user-facing prose;
7. avoid creating a VOC number or case.

The prepared draft survives ordinary chat turns in the current process but may be cleared by demo reset. Never serialize it into logs.

### `submit_case`

After explicit confirmation only, call:

```http
POST /api/v1/voc/cases
Idempotency-Key: <the same key created during prepare>
Content-Type: application/json
```

Send the exact prepared payload. Do not reconstruct it from a model response during confirmation.

Required behavior:

- repeated confirmation for the same completed pending action returns the stored terminal result;
- repeated HTTP submission with the same key and payload must not create a second case;
- the plugin must preserve the draft when a timeout makes the remote outcome unknown so a safe retry can reuse the same key;
- a successful submit marks the local draft `SEALED`; PendingActionStore owns terminal-result replay, and the plugin may then discard the raw PII payload;
- a rejected pending action never calls the external endpoint;
- direct chat/LLM-selected submit fails closed.

### `get_case`

Call:

```http
POST /api/v1/voc/cases/lookup
Content-Type: application/json

{
  "vocNumber": "I-68100011",
  "keyCode": "123456"
}
```

Both fields are required in this demo contract.

Do not implement `GET /cases`, `list_cases` or “latest six cases”. The six homepage items are journeys, not cases.

Wrong VOC Number and wrong Key Code must map to the same safe `not_found` result. Do not expose whether a VOC Number exists.

## Six journeys

Use these exact stable journey codes:

| Code | Thai label | Reporter | Frequency/severity | Root request types |
|---|---|---|---|---|
| `POWER_QUALITY` | แจ้งปัญหาคุณภาพไฟฟ้า | required | required | `REQUEST_6` |
| `SERVICE_ISSUE` | แจ้งปัญหาด้านบริการ | required | required | `REQUEST_1`, `REQUEST_2` |
| `PRAISE` | ชื่นชม | required | not required | `REQUEST_3` |
| `TIP_OFF` | แจ้งเบาะแส | optional | not required | `REQUEST_4` |
| `STAKEHOLDER_ISSUE` | แจ้งปัญหาการดำเนินงาน | required | not required | `REQUEST_7` |
| `STAKEHOLDER_FEEDBACK` | ชื่นชม เสนอแนะ ข้อคิดเห็น | required | not required | `REQUEST_8` |

The catalog is authoritative for labels and available child options. These codes are stable integration identifiers.

## MainAgent VOC flow

Replace the old uniform intake:

```text
category → subject → detail → contact_name → contact_phone → location
```

with the journey-aware flow below.

### Start and journey selection

1. Detect an explicit VOC intent.
2. If the user already states one journey clearly, select it without showing the full menu.
3. If ambiguous, call `get_catalog` and display exactly the six journeys with Thai labels.
4. Do not call the six entries cases, requests or status results. Call them “ประเภทเรื่อง” or “เส้นทางรับเรื่อง”.

### OMS versus VOC routing

MainAgent must own this decision:

- current outage/status check or immediate outage report → OMS;
- repeated voltage quality, formal complaint, service complaint, praise, tip-off or stakeholder voice → VOC;
- ambiguous “ไฟดับและอยากร้องเรียน” → ask whether the user wants immediate outage handling, a formal VOC case, or both sequentially;
- never create OMS and VOC writes in the same chat turn;
- never silently redirect a formal complaint into OMS only.

### Field collection order

Collect one missing logical group at a time. Reuse information already supplied and never ask twice.

Recommended order:

```text
journey
→ classification
→ frequency/severity when required
→ reporter identity or anonymous choice
→ CA/meter when supplied and supported
→ incident/service area
→ detail
→ consent
→ review/prepare
```

### Classification

The selected `requestTypeCode` must be allowed by the journey. Topic, issue and optional sub-issue must be a valid chain from the catalog.

- Ask only from catalog options.
- Do not invent taxonomy codes.
- When an upstream selection changes, clear invalid downstream selections.
- `productImportance` is optional except when catalog/policy requires it for `REQUEST_2` or `REQUEST_8`.

### Reporter rules

For all journeys except `TIP_OFF`, require:

- title prefix;
- first name;
- last name;
- phone.

Email, national ID, CA, meter and contact address are optional unless the user volunteers them or a later approved requirement makes them mandatory.

For `TIP_OFF`:

1. ask whether the user wants to identify themselves or remain anonymous;
2. if anonymous, do not ask for name, phone, email, national ID, CA or meter;
3. if identified, accept partial contact information without inventing missing values;
4. never claim anonymity if identifying data was retained.

### Incident location

Require:

- province;
- district;
- subdistrict;
- responsible PEA office;
- free-text location description.

Resolve codes from catalog labels. Do not send arbitrary labels in code fields.

### Detail

Use one free-text `detail` field with a maximum of 2,000 characters. The old free-text `subject` and `contactChannel` fields are not part of the external contract and must be removed from the new VOC payload.

### Consent

Consent and write confirmation are separate decisions.

Before prepare, ask for explicit acceptance of the demo VOC privacy notice. Store:

- `accepted: true`;
- the configured notice version;
- acceptance timestamp;
- `CHAT` or `VOICE` channel.

Do not infer consent from continuing the conversation. If consent is rejected, keep the conversation non-transactional and do not prepare or submit.

After consent, show the review summary and use the existing pending action for the separate write confirmation.

### Prepare preview and redaction

The review preview should show enough for the user to catch mistakes:

- journey label;
- classification labels;
- frequency/severity where applicable;
- reporter display name or “ไม่เปิดเผยตัวตน”;
- masked phone;
- incident location/PEA office;
- detail.

Never expose in traces/logs:

- national ID;
- raw phone;
- email;
- full contact address;
- Key Code;
- raw request body;
- idempotency key.

### Confirmation, rejection and resumption

- Confirmation must use the existing confirm endpoint or the existing explicit voice confirmation path.
- Chat text alone must not bypass the decision state machine.
- Rejection is terminal for that pending action and performs no POST.
- After rejection, restore the intake draft for correction rather than starting from zero.
- A Knowledge question may temporarily interrupt VOC intake; after answering, allow the user to continue the same draft.
- Reset clears local intake/prepared drafts but does not call the external VOC app to delete cases.

### Submission response

After successful submission, tell the user clearly:

- this is a simulated VOC case;
- the VOC Number;
- the Key Code;
- that both values are needed for tracking;
- the initial status.

Do not include the Key Code in a trace event or log.

### Tracking response

`get_case` should present:

- VOC Number;
- current Thai status label;
- journey label;
- classification summary;
- responsible office/location;
- latest timeline message;
- last updated time;
- simulation label.

Do not dump raw JSON to the user.

## Typed contracts

Add or update typed internal models that mirror `voc.openapi.yaml` exactly.

Required internal model groups:

- catalog request/response;
- six journey codes;
- seven request type codes;
- nested taxonomy nodes;
- frequency, severity, title prefix and service area;
- identified and optional reporter;
- contact address and incident location;
- classification selection;
- consent record;
- six discriminated case request variants;
- submit response;
- lookup request and case detail response;
- status/timeline;
- normalized VOC errors.

At all external seams:

- JSON uses camelCase exactly as OpenAPI;
- unknown fields are rejected;
- successful payloads are validated before MainAgent sees them;
- malformed JSON or schema-invalid success responses fail closed;
- internal exceptions and raw server bodies are never exposed.

Update `CONTRACTS.md`, `ARCHITECTURE.md`, `PRD.md` and `app/contracts.py` only where the declared active behavior changes. Keep all four consistent.

## Error mapping

Normalize external responses at minimum:

| External condition | Internal code | User behavior |
|---|---|---|
| HTTP 400 invalid body/catalog selection/consent | `invalid_input` | identify the missing/invalid field safely |
| HTTP 404 lookup mismatch | `not_found` | generic “ไม่พบเคสสำหรับข้อมูลติดตามที่ระบุ” |
| HTTP 409 idempotency conflict | `conflict` | do not retry with a new key automatically |
| timeout/connection failure | `unavailable` | say VOC demo is temporarily unavailable |
| HTTP 5xx | `unavailable` | safe temporary failure |
| malformed/schema-invalid success JSON | `internal` | safe invalid-response message |
| unexpected status | `unavailable` | safe temporary failure |

Never expose endpoint URLs, headers, stack traces, HTTP client messages, credentials or raw bodies.

## Separate VOC demo application contract

The VOC demo application is not implemented in this Agent repository or by this plugin assignment. Give `voc.openapi.yaml` to its separate implementation owner. That application must expose only the three OpenAPI operations and deterministic in-memory state.

Required external demo behavior:

- catalog always returns six journeys and seven request types;
- fixture taxonomy contains at least one complete valid chain for every journey;
- fixture service areas contain enough deterministic options for evaluation;
- case creation validates catalog relationships and consent;
- case creation generates unique UUID `caseId`, `I-########` VOC Number and six-digit Key Code;
- idempotency is enforced in process;
- created cases remain trackable until process restart;
- lookup requires both values and fails closed;
- case status may advance deterministically for demo evidence, but must never claim real PEA handling;
- no reset/delete route is exposed.

Do not add a database, authentication, notifications, uploads, queue or admin UI.

## Essential tests only

Do not use TDD. Finish the implementation path first, then add the narrow tests below.

### Contract/plugin tests

1. Catalog success validates complete enum coverage and application-level unique codes for all six journeys and seven request types.
2. MainAgent generates the idempotency key; `prepare_case` stores the exact draft, returns normalized preview data and performs zero outbound HTTP calls.
3. Confirmed `submit_case` sends exactly one POST with the stored original payload and same idempotency key.
4. PendingActionStore replays the terminal result on repeated confirmation and no duplicate case is created.
5. `TIP_OFF` accepts an anonymous reporter; identified journeys reject missing required reporter fields.
6. Tracking requires `vocNumber + keyCode` and maps both wrong-number and wrong-key cases to the same safe error.
7. Timeout, connection failure, HTTP 5xx and malformed success JSON fail safely.

### MainAgent tests

8. Ambiguous VOC intent displays six journeys from the plugin catalog.
9. Explicit journey skips the six-item menu.
10. MainAgent collects journey-specific fields, consent and then produces a pending action without POST.
11. Reject performs no POST and allows correction.
12. Knowledge interruption/resume retains the VOC draft.
13. OMS versus VOC outage routing follows the rules in this document.
14. Direct LLM/chat `submit_case` fails closed.

### Regression smoke tests

Run the existing focused checks for:

- Knowledge grounding/citations;
- OMS plugin critical flow;
- pending action confirm/reject/idempotency;
- trace ordering/redaction;
- voice VOC collection and explicit confirmation;
- public API contract validation.

Do not add tests for trivial getters, static labels, framework behavior or every taxonomy fixture row.

## Suggested implementation order

Use implementation-first execution in this order:

1. Add typed VOC wire models from `voc.openapi.yaml`.
2. Implement `VocPlugin` HTTP mapping and local draft behavior.
3. Register the plugin directly in the existing plugin registry/composition.
4. Add VOC configuration.
5. Replace MainAgent’s old six-category/uniform intake with the journey-aware state.
6. Preserve confirm/reject/reset/trace/voice behavior.
7. Remove old VOC tool/backend/fixture and stale tests.
8. Update documentation/contracts.
9. Add the essential tests.
10. Run focused tests, then `python3 -m pytest -q` once.
11. Review the final diff for scope, contract fidelity, unsafe writes and leaked sensitive values.

Do not start by rewriting every contract or building generic abstractions.

## Acceptance criteria

The implementation is complete when all of the following are true:

1. `VocPlugin` is the only active VOC implementation.
2. There is no active or dormant competing `VocTool`/`SimulatedVocBackend` path.
3. The runtime catalog contains every journey code exactly once and every request-type code exactly once.
4. MainAgent distinguishes six journeys from seven internal request types.
5. No public list-all-cases capability exists.
6. All six journeys can reach a valid prepared pending action using appropriate required fields.
7. Prepare performs no external POST.
8. Submit occurs only after explicit confirmation.
9. Duplicate confirmation cannot create a duplicate case.
10. Successful submission returns a simulated VOC Number and Key Code.
11. Tracking one case works with both values and fails closed otherwise.
12. Tip-off can remain anonymous.
13. Consent is explicit and separate from write confirmation.
14. OMS/VOC routing is deterministic and safe.
15. VOC transport failures are safe and actionable.
16. Logs/traces contain no raw PII, Key Code, idempotency key or request body.
17. Reset never deletes an external VOC case.
18. Knowledge, OMS, voice and public Agent contracts are not knowingly broken.
19. The essential focused tests and the full suite pass.
20. Plugin transport behavior is proven with deterministic HTTP mocks; a live smoke flow is also reported when the separate demo endpoint is available.
21. No VOC demo server is added to the Agent repository.
22. Final documentation states clearly that VOC is an external REST demo clone, not production PEA VOC.

## Final report requirements

Report in Thai:

1. final MainAgent → PluginRegistry → VocPlugin → VOC demo flow;
2. every file created;
3. every existing file modified and why;
4. every old VOC tool/backend file removed;
5. exact tests/commands and results;
6. what was transport-mocked versus actually verified against a running demo app;
7. protected Knowledge/OMS/voice/confirmation behavior;
8. remaining genuine limitations;
9. explicit confirmation that no production VOC system was called and nothing was deployed.
