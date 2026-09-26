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
   `Gemini Live → search_knowledge → local hybrid index → Gemini Live`. Embedding models
   (self-hosted `BAAI/bge-m3` behind the `Embedder` protocol) are not generative and are allowed.
3. Gemini Live sends one Thai query to `search_knowledge`; the deterministic local index
   validates the query and returns approved Q&A first, then source-attributed document chunks.
4. Approved documents are never edited, reformatted, deleted or renamed. The index is a derived
   artefact; results are bounded to a small, relevant, source-attributed context, and empty or
   invalid queries fail safely with a structured error.
5. ADK is the only voice runtime. No `VOICE_RUNTIME` selector.
6. Do not preserve architecture "just in case" — git history already preserves removed code.

## Stop condition

When the Knowledge Voice Agent is stable, STOP. Do not begin OMS, VOC, Chat, LINE, MCP,
dynamic REST tools, telephony, or admin UI. Those belong to a later phase.
