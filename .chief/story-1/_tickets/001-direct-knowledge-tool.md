# Ticket 001 — Connect the ADK Agent directly to Knowledge

Type: implementation
Status: resolved
Blocked by: None

## TASK

Replace the MainAgent/WscTools dependency in the ADK voice graph with one focused Knowledge capability, retaining the current Knowledge backend temporarily until Story 2.

## FILES / COMPONENTS IN SCOPE

`app/agent/adk_agent.py`, `app/runtime/adk_live.py`, `app/tools/adk_tools.py` (or its replacement), relevant ADK tests.

## MUST DO

- Construct the ADK Agent with a direct Knowledge tool dependency; do not accept/import MainAgent or WscTools in the voice runtime.
- Expose Knowledge as the only ADK business capability; remove OMS, VOC, pending-action, confirmation, and rejection functions from the ADK tool surface.
- Keep tool errors safe and return successful Knowledge results to the same Live session.
- Add tests asserting the active ADK surface and constructor graph exclude MainAgent and write capabilities.

## MUST NOT DO

- Do not remove Chat/LINE/OMS/VOC modules outside the ADK voice surface; Story 3 owns cleanup.
- Do not redesign wire protocol or frontend.
- Do not remove nested Knowledge model calls in this ticket; Story 2 owns that change.

## DEPENDENCIES

None.

## ACCEPTANCE CRITERIA

- ADK Agent is constructed with a direct Knowledge tool.
- `app/runtime/adk_live.py` and ADK Agent construction do not import or accept MainAgent/WscTools.
- ADK exposes only Knowledge; no confirmation/rejection tool is callable.
- Relevant tests pass, including same-session Live tool result flow.

## STOP CONDITION

Stop when this direct Knowledge-only ADK seam and its tests are green; leave platform deletion and deterministic Knowledge migration to later tickets.
