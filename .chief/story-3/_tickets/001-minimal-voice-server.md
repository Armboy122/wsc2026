# Ticket 001 — Reduce server surface, DI, and settings to Voice

Type: implementation
Status: open
Blocked by: Story 1 tickets 001–002; Story 2 tickets 001–002

## TASK

Remove active Chat/LINE and business API entry points and simplify app construction/configuration to the completed Voice + deterministic Knowledge architecture.

## FILES / COMPONENTS IN SCOPE

`app/main.py`, `app/api/` routes and health/live wiring, `app/core/config.py`, `app/core/di.py`, `.env.example`, route/config/startup tests, route references in frontend as required.

## MUST DO

- Keep only static Voice hosting, `GET /health`, and `WS /ws/live` as public application features.
- Remove Chat, trace, reset, action-confirm/reject, and LINE HTTP routes and runtime wiring.
- Replace MainAgent/adapter registries with direct minimal construction of catalog → Knowledge service → Knowledge tool → ADK Live runtime.
- Remove obsolete model/OMS/VOC/LINE/runtime-selector configuration and retain only settings proven necessary for the target architecture.
- Add tests for startup, minimal routes, health, ADK WebSocket routing, and absence of obsolete settings.

## MUST NOT DO

- Do not delete core OMS/VOC/MainAgent implementation files until Ticket 002 removes remaining imports and tests.
- Do not redesign the Voice UI or add infrastructure.
- Do not modify approved Knowledge documents.

## DEPENDENCIES

Story 1 tickets 001–002 and Story 2 tickets 001–002.

## ACCEPTANCE CRITERIA

- App startup and static hosting use the minimal direct dependency graph.
- Only health and live voice API surfaces remain.
- No obsolete route, LINE startup hook, or removed setting is active.
- Focused tests and full suite pass.

## STOP CONDITION

Stop when the minimal active application graph/routes/config are green; keep unused modules for the next deletion ticket only if they still have references.
