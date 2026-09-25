# Product scope (FINAL — user decision, not re-openable)

WSC is now a Voice-first Knowledge Agent.

- ADK + Gemini Live owns the whole conversation.
- Knowledge is local trusted data only.
- Operational systems and Chat are postponed.

## In scope

PEA Real-Time Knowledge Voice Agent, and only that.

## Explicitly NOT in scope on this branch

No MainAgent. No second planner. No second answering LLM. No Knowledge LLM. No OMS. No VOC.
No business REST APIs. No MCP. No Chat runtime. No LINE runtime. No write/mutation workflow.
No pending action system. No confirmation tools.

## Non-negotiable constraints

1. Exactly ONE conversational/reasoning model: Gemini Live used by the ADK agent.
2. Knowledge performs ZERO generative model calls. The path is
   `Gemini Live → Knowledge Tool → local documents → Gemini Live`.
3. Gemini Live selects which source documents it needs from a compact deterministic catalog;
   the server validates every requested sourceId against the allowlist.
4. Full approved Markdown is returned without silent truncation. Over-budget fails safely
   with a structured result so Gemini can ask the user to narrow the topic.
5. ADK is the only voice runtime. No `VOICE_RUNTIME` selector.
6. Do not preserve architecture "just in case" — git history already preserves removed code.

## Stop condition

When the Knowledge Voice Agent is stable, STOP. Do not begin OMS, VOC, Chat, LINE, MCP,
dynamic REST tools, telephony, or admin UI. Those belong to a later phase.
