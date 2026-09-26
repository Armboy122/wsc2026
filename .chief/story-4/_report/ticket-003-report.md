# story-4 ticket-003 report

Implementer: maxplus/deepseek-v4.1-flash-x via pi on the assistant's server. Reviewer: maxplus-claude/claude-opus-5. Review rounds: 1.

Final tests: 167 passed, 1 deselected, 2 warnings in 4.41s

## Review
# Story 4 Ticket 003 Review

Reviewer: xai/grok-4.7 (owner-approved fallback)
Date: 2026-09-26
Ticket: `.chief/story-4/_tickets/003-search-knowledge-tool-and-prompt.md`
Contract: `.chief/story-4/_contract/knowledge-search.md`

## Summary

Ticket 003 successfully replaces the `get_knowledge_documents` catalog tool with `search_knowledge(query)` backed by `IndexManager`. The ADK agent now exposes exactly one Knowledge tool that accepts a Thai query (1–500 chars) and returns approved Q&A first, followed by source-attributed chunks. The Thai Q&A-wins prompt rule is present. All acceptance criteria are met.

## Verification Results

### Suite Status
- **pytest**: 167 passed, 1 deselected, 2 warnings in 4.43s ✅
- **ruff check** (touched files): All checks passed ✅
- **No default tests requiring network/model downloads/Gemini** ✅

### Code Inspection
- **`get_knowledge_documents` absence**: Confirmed absent from `app/` and `tests/` (classified B: removed with feature) ✅
- **`search_knowledge` tool**: Declared in `app/agent/adk_agent.py`, name matches `KNOWLEDGE_TOOL_NAME` ✅
- **Tool schema**: `{query: string, 1..500, additionalProperties: false}` ✅
- **Event loop offloading**: `await asyncio.to_thread(manager.search, query)` in `run_async` ✅
- **Logging policy**: Only logs `status`, `approved_qa` count, `chunks` count, `latency_ms` — no query text or content ✅
- **Payload shape**: `{status, approvedQa, chunks, sources}` with Q&A first, errors use wire codes ✅
- **Prompt rule (Thai)**: `app/prompts/adk_voice.md` lines 4, 6 include approved Q&A precedence and 1129 referral ✅
- **Architecture tests**: `test_adk_agent_exposes_only_the_search_knowledge_tool`, `test_knowledge_modules_never_import_a_generative_provider` present ✅
- **Knowledge documents unchanged**: `git status knowledge/source/` shows no modifications ✅

### Contract Alignment
- **Tool name**: `search_knowledge` ✅
- **Input validation**: Query length 1–500 chars, `additionalProperties: false` ✅
- **Success payload**: Approved Q&A first, chunks with heading, sources, all with sourceId/title/uri ✅
- **Error codes**: `invalid_input`, `unavailable`, `internal` mapped correctly ✅
- **Off-loop execution**: `asyncio.to_thread` used ✅
- **No catalog in instruction**: Verified `app/agent/adk_agent.py` instruction loads from `adk_voice.md`, which has no catalog JSON or `{...}` template variables ✅

### Test Coverage
- Tool declaration, schema, arg validation ✅
- Success payload with real corpus (approved Q&A first with sources) ✅
- Invalid arguments fail closed ✅
- Query/content not logged ✅
- Index unavailable returns `unavailable` ✅
- Unexpected failure returns `internal` without leaking details ✅
- Event loop offloading verified (slow manager, concurrent coroutine progresses) ✅
- Instruction carries Q&A rule without catalog ✅
- Agent exposes exactly one tool ✅
- Architecture assertion: no generative provider in `app/knowledge` ✅

### Rule Documents
- **`.chief/_rules/_goal/product-scope.md`**: Updated constraints 2–4 to reflect `search_knowledge`, hybrid index, Q&A-first, embedder allowed ✅
- **`.chief/_rules/_verification/checks.md`**: Added assertions for `search_knowledge` only, `get_knowledge_documents` absent, offloading, logging policy ✅
- **`.chief/project.md`**: Architecture diagram and rules updated to Story 4 scope ✅
- **`ARCHITECTURE.md`**: Diagram, module table, Knowledge flow all reflect `search_knowledge` and no catalog ✅
- **`CONTRACTS.md`**: Tool 3 documents `search_knowledge` input/success/error with wire codes ✅
- **`README.md`**: (not checked in detail, assumed consistent per diff summary)
- **`knowledge/README.md`**: Runtime description updated to `search_knowledge`, Q&A first, index lifecycle ✅

## Blocking Issues

None.

## Minor Notes

1. **Deleted test file staged**: `tests/test_knowledge_documents.py` is staged for deletion, which is correct (classified B: feature intentionally removed). This is not a blocker.

2. **Modified files not staged**: All implementation files are modified but not staged. This is expected for a review-before-commit workflow and not a blocker.

3. **Deprecation warnings in test output**: Two warnings present (FastAPI/Starlette httpx deprecation, ADK BaseAgentConfig deprecation). These are upstream deprecations and not introduced by this ticket. Not a blocker.

4. **Test module imports**: `tests/test_adk_knowledge_tool.py` and `tests/test_adk_runtime.py` updated to use `IndexManager` and `FakeEmbedder` instead of `KnowledgeDocumentService`. Clean migration. ✅

5. **Contract consistency**: `CONTRACTS.md`, `ARCHITECTURE.md`, `knowledge/README.md`, and `.chief/project.md` are all consistent with the Story 4 contract. ✅

6. **No catalog remnants**: The string `get_knowledge_documents` appears only in `.chief/` history and old reports, never in `app/` or active `tests/`. ✅

## Acceptance Criteria

From ticket 003:

1. **ADK agent exposes exactly one Knowledge tool, `search_knowledge`; `get_knowledge_documents` and the catalog are gone from code, prompt and tests** ✅
   - Verified: `rg -n get_knowledge_documents app tests` returns no matches
   - Verified: `test_adk_agent_exposes_only_the_search_knowledge_tool` asserts exactly one tool
   - Verified: Instruction has no catalog JSON or `{...}` variables

2. **Tool result for a Q&A paraphrase (fake embedder) lists that Q&A first, with sources** ✅
   - Test: `test_real_corpus_paraphrase_returns_approved_qa_first_with_sources`
   - Verified: `result["approvedQa"]` is non-empty, first hit is the expected Q&A, sources present

3. **The event loop is not blocked (test: slow fake searcher, concurrent coroutine still progresses)** ✅
   - Test: `test_search_is_offloaded_so_the_event_loop_keeps_running`
   - Verified: `asyncio.to_thread` used, concurrent task progresses while search blocks

4. **Rules docs updated to the approved Story 4 scope; full suite passes offline** ✅
   - `.chief/_rules/_goal/product-scope.md`: constraints 2–4 rewritten ✅
   - `.chief/_rules/_verification/checks.md`: architecture assertions added ✅
   - `.chief/project.md`: architecture and rules updated ✅
   - Suite: 167 passed ✅

## Classification of Removed Tests

- `tests/test_knowledge_documents.py`: **Classified B** (feature intentionally removed). The old catalog selection service and its tests are replaced by `search_knowledge` and its tests in `tests/test_adk_knowledge_tool.py`. Correct removal.

## Verdict Reasoning

All acceptance criteria are met:
- The tool surface changed from catalog selection to query search
- The payload shape matches the contract
- Event loop offloading is verified
- Logging policy observed (no query/content logged)
- Q&A-wins prompt rule is present in Thai
- No `get_knowledge_documents` remnants in app code or active tests
- Rules documents updated
- Full suite passes offline (no network/model downloads required)
- Knowledge documents unchanged
- Architecture assertions hold

No blocking issues found.

VERDICT: PASS
