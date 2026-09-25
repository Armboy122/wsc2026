# AGENTS.md

## Mission

Build the smallest working version of the PEA Knowledge Voice Agent: a Thai-language voice agent where ADK + Gemini Live owns the whole conversation and the only business capability is deterministic retrieval of approved local PEA Markdown documents.

Use this priority order:

```text
Correctness and safety
> Working MVP
> Simplicity
> Maintainability
> Test coverage
> Architectural purity
> Hypothetical scalability
```

Security, customer data, critical API contracts, and Knowledge grounding are correctness requirements and must not be traded away for speed.

## Before Editing

1. Read the relevant code and nearby tests before changing it.
2. Identify the critical user path and the smallest set of files required.
3. Read `PRD.md` when changing product behavior, user journeys, feature scope, priorities, acceptance criteria, or presentation claims.
4. Read `ARCHITECTURE.md` when changing module boundaries, the ADK agent/tool, the Live transport, knowledge flow, or ownership boundaries.
5. Read `CONTRACTS.md` and `app/contracts.py` when changing `/health`, the `/ws/live` wire protocol, the Knowledge tool schema/results, settings, or public behavior.
6. Read `app/prompts/adk_voice.md` and `app/agent/adk_agent.py` when changing model behavior; it is the only runtime prompt.

Do not rewrite working code without a requirement or a demonstrated problem.

## MVP-First Implementation

Prefer this loop:

```text
Implement the smallest correct vertical slice
→ Exercise the real critical path
→ Fix important failures
→ Add risk-driven tests
→ Clean up only what the change needs
```

A vertical slice may cross the voice UI, WebSocket transport, ADK agent, and Knowledge boundaries when that is the shortest path to working end-to-end behavior.

Choose direct, explicit code over speculative abstractions. Some duplication is acceptable while requirements are changing. Consider abstraction after the third meaningful repetition, or earlier only when it clearly improves correctness or readability.

Use existing dependencies and patterns where practical. Add a dependency only when it materially reduces complexity and is maintained. Do not add infrastructure, generic frameworks, extension points, caching, queues, microservices, or performance optimization without a current requirement or measured bottleneck.

Make the smallest safe change. Keep unrelated refactors out of feature and bug-fix work.

## Project Boundaries

Preserve the architecture and contracts already declared by the repository:

- The public surface is the static voice UI (`web/`), `GET /health`, and `WS /ws/live`. Keep routes and the WebSocket entry point thin.
- ADK + Gemini Live is the only conversational model and the only orchestrator. Do not add a second LLM, planner, Chat/LINE channel, MCP, queue, or extra agent.
- `get_knowledge_documents` is the only tool. Knowledge is deterministic: it validates catalog `sourceId`s and returns complete approved Markdown with provenance. It must never call a generative model, search by query, embed, chunk, or silently truncate; over-budget selections are structured failures.
- Knowledge stays fail-closed: allowlisted files under `KNOWLEDGE_SOURCE_ROOT` only, relative source IDs, no path traversal or arbitrary filesystem reads.
- Answers must come from documents returned by the tool, not model memory. Do not introduce vector search, embeddings, chunk retrieval, or a new RAG architecture unless explicitly requested.
- No raw ADK events, thoughts, tool payloads, or provider errors may reach the browser.
- Never expose credentials, API keys, access tokens, hidden prompts, or customer-sensitive data.

Changes to `CONTRACTS.md`, `ARCHITECTURE.md`, or `app/contracts.py` are integration-level changes. Make them only when the requested behavior requires a contract or architecture change, keep all three consistent where applicable, and call the change out explicitly.

Do not delete, alter, or rewrite approved knowledge documents (`knowledge/source/**`, `knowledge/aliases/**`, `docs/research/**`) or user data unless the task explicitly requires it.

## Code Quality

Write boring, obvious code:

- descriptive names
- focused functions
- straightforward control flow
- explicit validation at system boundaries
- predictable typed data structures
- comments that explain why, not what

Follow the existing Python style and use type hints for changed or new interfaces. Reuse repository patterns unless they block the requested behavior.

Handle reasonably expected failures, especially invalid input, unavailable providers, malformed model output, invalid tool calls, permission failures, missing resources, and failed state transitions. Important failures must be visible and actionable; do not silently swallow them.

Log meaningful boundaries such as model invocation, tool execution, external API calls, state transitions, and unexpected errors. Keep secrets and sensitive payloads out of logs.

## Risk-Driven Testing

Full TDD is not required. Implementation-first exploration is acceptable for changing requirements, UI work, prototypes, model integration, and unfamiliar APIs.

Test where failure is expensive.

### Tests normally required

- public API and Pydantic contracts
- validation and authorization/permission boundaries
- the Knowledge tool schema, source-ID allowlist, limits, and success/error payloads
- the `/ws/live` wire protocol and event forwarding
- redaction of provider errors and secrets
- malformed model tool calls and invalid PCM frames
- architecture boundaries (single tool, no generative calls in Knowledge, no removed platform code)
- deterministic business rules and data transformations
- regression cases for significant bugs when practical

### Test when logic is meaningful

- orchestration and routing
- parsers and schema conversion
- retries, timeouts, fallbacks, and error mapping
- provider adapters and external API assumptions
- conversation context and state management

### Tests usually unnecessary for MVP

- trivial wrappers or getters
- static layout and styling
- framework behavior already covered upstream
- temporary exploratory code likely to be replaced

Do not write tests only to increase coverage. For probabilistic answer quality, prefer manual voice checks with representative questions over assertions on generated speech. Test deterministic boundaries around prompts, schemas, tools, and transport.

## External Integrations

Use official documentation or a verified reference implementation. First prove the smallest real request works, then handle important errors, introduce a wrapper only if it creates a useful boundary, and test this project's assumptions rather than the provider SDK itself.

Never claim a live integration (Gemini Live, microphone, Thai speech, barge-in, latency) was verified when only mocks or adapter tests ran. Never connect to a real PEA system without explicit user approval and appropriate credentials and safety review.

## Bug Fixes

For a significant bug:

1. Reproduce or establish concrete evidence of the failure.
2. Trace it to the root cause.
3. Make the smallest safe fix.
4. Add a regression test when the bug could realistically recur.
5. Verify the affected critical path.

## Validation

Use the narrowest relevant check during iteration, then run the broader suite when the change can affect shared behavior.

Default repository checks:

```bash
.venv/bin/python -m pytest -q
```

pytest ติดตั้งอยู่ใน virtualenv ของโปรเจกต์เท่านั้น การเรียก `python3 -m pytest` ตรง ๆ
จะได้ `No module named pytest`

Frontend syntax check for changed scripts:

```bash
node --check web/app.js
```

Smoke-check a running server with `curl http://127.0.0.1:8000/health`. Real voice behaviour needs a manual browser/microphone session with a valid `GEMINI_API_KEY`.

Do not treat compilation or mocked tests alone as proof that a real provider integration works. Report which checks ran, their results, and anything not verified.

## Definition of Done

A change is done when:

- the requested behavior works on the critical path
- validation exists at important boundaries
- expected high-impact errors are handled
- existing behavior is not knowingly broken
- high-risk behavior has appropriate tests
- relevant checks pass
- debugging code, dead code, and unused imports introduced by the change are removed
- no unnecessary architecture or dependency was added
- documentation and contracts are updated when their declared behavior changed

It does not require 100% coverage, full TDD, exhaustive theoretical edge cases, production-scale infrastructure, or speculative extensibility unless explicitly requested.

## Final Principle

> MVP first. Make the critical path correct. Test where failure is expensive. Refactor after requirements become real. Do not engineer imaginary problems.
