# Ticket 002 — Delete obsolete platform code and rewrite documentation

Type: implementation
Status: open
Blocked by: 001

## TASK

After active references are removed, delete dead MainAgent/planner, legacy Voice, OMS/VOC, business API, pending-action, Chat/LINE code/tests/config/dependencies and align product documentation with the Voice-only result.

## FILES / COMPONENTS IN SCOPE

Obsolete `app/agent/`, `app/live/`, `app/plugins/`, `app/line/`, `app/tools/`, `app/backends/`, contracts/tests/dependencies/docs/frontend assets as identified by reference search; README, ARCHITECTURE, PRD, CONTRACTS, `knowledge/README.md`, ADK migration docs, `.env.example`, `pyproject.toml` and lockfile if required.

## MUST DO

- Search references before deletion; remove only components with no remaining valid dependency in the Voice path.
- Delete OMS/VOC, MainAgent/planner/registry, legacy GeminiLiveSession/VoiceBridge, business REST adapters, Chat/LINE runtimes, pending-action/confirmation contracts and their feature-only tests.
- Reclassify obsolete tests as removed-feature or stale-contract; retain/fix valid Knowledge and Voice coverage.
- Remove obsolete dependencies/settings and regenerate lock state only if needed.
- Rewrite or remove stale docs; document current flow, manual voice checklist, required environment variables, run/install commands, verified performance measures, and real-provider limitations truthfully.
- Keep the existing Voice UI working; remove only stale product UI/code.

## MUST NOT DO

- Do not delete or rewrite approved Knowledge source documents.
- Do not introduce MCP, future OMS/VOC/Chat/LINE scaffolding, a new database, provider, or UI framework.
- Do not claim manual voice/performance acceptance that was not performed.

## DEPENDENCIES

Ticket 001.

## ACCEPTANCE CRITERIA

- No active or dead code for excluded product capabilities remains, except clearly documented unavoidable dependencies with evidence.
- Static architecture checks and all relevant tests pass; full pytest and frontend syntax checks pass.
- Documentation, configuration, frontend, and actual runtime agree.
- Manual/provider-only checks and performance measurements are explicitly marked performed or pending with evidence.

## STOP CONDITION

Stop when the minimal Knowledge Voice Agent is stable, checks pass, docs are truthful, and unresolved live acceptance is documented. Do not start any future product phase.
