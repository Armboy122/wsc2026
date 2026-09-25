# Ticket 005 — OPTIONAL `ask_knowledge_deep` long-context fallback

Type: implementation
Status: planned — blocked on decision D5 (may be dropped)
Blocked by: D5 approval; Tickets 003–004

## TASK

If approved, add a second tool `ask_knowledge_deep(question)` that Gemini Live calls only when
`search_knowledge` is insufficient: one non-conversational Gemini Flash call over the whole
corpus (Q&A first, tagged `[APPROVED_QA]`) using explicit context caching, returning a short
grounded answer with sources.

## FILES / COMPONENTS IN SCOPE

`app/knowledge/deep/` (outside the no-LLM `app/knowledge/index` boundary), `app/agent/adk_agent.py`,
prompt, config (`KNOWLEDGE_DEEP_MODEL`, enable flag default off), tests, rule docs.

## MUST DO

- Disabled by default; enabled only by config. Cache created/refreshed on index rebuild.
- Timeout (e.g. 8 s) → structured `unavailable`, Live asks back / refers to 1129.
- Architecture test allows the generative client only in `app/knowledge/deep/`.
- Measure latency and correctness with the ticket 004 harness before enabling.

## MUST NOT DO

- No network in tests (fake client). Not a conversational agent; no tool chaining.

## ACCEPTANCE CRITERIA

- With the flag off, the tool surface equals ticket 003. With it on, both tools exist and
  deep answers include sources. Full suite passes offline.

## STOP CONDITION

Stop after the flag-gated tool and measurements are recorded, or close as "won't do" if D5 is
declined.
