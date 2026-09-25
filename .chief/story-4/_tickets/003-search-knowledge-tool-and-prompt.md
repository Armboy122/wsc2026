# Ticket 003 — `search_knowledge` ADK tool replaces catalog tool; Q&A-wins prompt

Type: implementation
Status: planned
Blocked by: Tickets 001–002; decision D0 approved

## TASK

Replace `get_knowledge_documents` + the catalog in the instruction with one tool
`search_knowledge(query)` backed by `IndexManager`, and add the approved-Q&A precedence rule to
the voice prompt. Update the rule documents that Story 4 amends.

## FILES / COMPONENTS IN SCOPE

`app/agent/adk_agent.py`, `app/prompts/adk_voice.md`, `app/runtime/adk_live.py` and `app/api/live.py`
wiring, `app/knowledge/service.py` (remove catalog selection path if unused), `CONTRACTS.md`,
`ARCHITECTURE.md`, `README.md`, `knowledge/README.md` wording about the tool (not `knowledge/source/`),
`.chief/project.md`, `.chief/_rules/_goal/product-scope.md`, `.chief/_rules/_verification/checks.md`,
`tests/test_adk_knowledge_tool.py`, `tests/test_architecture.py`, `tests/test_adk_runtime.py`.

## MUST DO

- Tool schema: `{query: string, 1..500 chars}`, `additionalProperties: false`.
- `run_async` calls `await asyncio.to_thread(manager.search, query)`; payload:
  `{"status":"success","approvedQa":[{sourceId,title,uri,content}],"chunks":[{sourceId,title,uri,heading,content}],"sources":[...]}`
  with Q&A always first; errors use existing wire codes.
- Remove the catalog JSON from the instruction (also removes the ADK `{...}` templating risk
  noted in Story 2/3).
- Prompt rule (Thai): approved Q&A wins; never add conditions/numbers/channels not stated;
  call `search_knowledge` before answering factual PEA questions; if nothing relevant or unsure,
  ask back or refer to 1129.
- Log only status, counts and latency (no query text beyond existing logging policy).

## MUST NOT DO

- No second model call; no document edits; no UI change.

## ACCEPTANCE CRITERIA

- ADK agent exposes exactly one Knowledge tool, `search_knowledge`; `get_knowledge_documents`
  and the catalog are gone from code, prompt and tests (classified B/C in the report).
- Tool result for a Q&A paraphrase (fake embedder) lists that Q&A first, with sources.
- The event loop is not blocked (test: slow fake searcher, concurrent coroutine still progresses).
- Rules docs updated to the approved Story 4 scope; full suite passes offline.

## TESTS

Tool schema/declaration, arg validation, success/error payloads, to_thread offloading,
instruction contains the Q&A rule and no catalog, architecture assertions (tool surface, no
generative client in `app/knowledge`).

## STOP CONDITION

Stop when the Live agent uses `search_knowledge` and the suite is green. Real voice acceptance
remains manual/pending.
