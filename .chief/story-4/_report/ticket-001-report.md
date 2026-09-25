# story-4 ticket-001 report

Implementer: maxplus/deepseek-v4.1-flash-x via pi. Reviewer: maxplus-claude/claude-opus-5 (owner-approved change from Sol/grok-4.7 to save Grok Bot usage). Review rounds: 1.

Final tests: 155 passed, 1 deselected, 3 warnings in 1.60s

## Review
# Story 4 / Ticket 001 Review

**Ticket**: 001-knowledge-index-core.md  
**Reviewer**: reviewer (fallback)  
**Date**: 2026-09-26  

---

## Summary

Ticket 001 implements a pure, deterministic knowledge index library (`app/knowledge/index/`) with heading-aware Markdown chunking, hybrid retrieval (BM25 + dense cosine via RRF), and a Q&A lane that ranks above document chunks. The implementation is complete, well-tested, and meets all acceptance criteria.

**Tests**: 155 passed (46 new index tests + 109 existing), 1 deselected (opt-in model test)  
**Linter**: 9 pre-existing ruff issues (none introduced by this ticket)  
**Architecture**: No generative imports, torch/sentence-transformers stay lazy, knowledge files unchanged

---

## Blocking Findings

**None.**

---

## Minor Notes

### 1. Pre-existing ruff issues (not blocking)

The ticket introduces no new linter violations. The 9 reported issues existed before this work:

- `app/agent/adk_agent.py:94` — BLE001 (blind Exception catch)
- `app/core/config.py:12` — UP035 (import from collections.abc)
- `app/knowledge/aliases.py:113,116` — TRY004 (prefer TypeError)
- `app/runtime/adk_live.py:3,106` — I001 (import sort), BLE001
- `tests/test_adk_runtime.py:15,336` — I001 (import sort)
- `tests/test_live_frontend_audio.py:1` — I001 (import sort)

These are not introduced by the index library and are outside ticket scope.

### 2. Knowledge documents untouched (verified)

- 47 Markdown files under `knowledge/source/` remain byte-identical
- 12 Q&A files in `knowledge/source/qa/` (11 actual Q&As + README.md, which is filtered at runtime)
- `git status knowledge/` shows no changes
- Test `test_building_and_searching_the_index_leaves_knowledge_files_byte_identical` passes

### 3. Acceptance criteria met

**✓ Chunking is deterministic**  
- `test_chunk_ids_are_identical_across_independent_builds` passes
- `test_concatenated_chunks_reproduce_the_source_exactly` passes
- `test_real_corpus_chunking_loses_no_text` passes (34+ documents, all text preserved)

**✓ Q&A main questions retrieve their own Q&A at rank 1**  
- `test_every_main_question_retrieves_its_own_qa_at_rank_one` passes (11/11 hits)
- Uses `FakeEmbedder`, fully offline

**✓ Opt-in bge-m3 test present**  
- `test_bge_m3_qa_lane_hit_at_2_on_paraphrases` is marked `-m model` and deselected by default
- Skips when model not cached locally; forces `HF_HUB_OFFLINE=1` when run
- Target: ≥29/35 correct Q&A-lane hit@2 on held-out paraphrases (research baseline)

**✓ Full suite passes offline**  
- No network required, no Gemini calls, no model download at runtime
- Imports `app.knowledge.index` without pulling in `torch` or `sentence_transformers`
- `test_knowledge_index_package_has_no_generative_or_adk_imports` and `test_importing_knowledge_index_keeps_torch_and_sentence_transformers_lazy` pass

### 4. Implementation quality

**Strengths:**
- Clean separation: `Embedder` protocol allows swapping `BgeM3Embedder` for `gemini-embedding` or `FakeEmbedder` with no library changes
- Immutable data structures (`@dataclass(frozen=True)`) for all models
- Heading-aware chunking preserves source text exactly (`chunk.text == source[chunk.start:chunk.end]`)
- Q&A lane precedence enforced: Q&As rank above chunks, chunks deduplicated against returned Q&A sources
- Alias expansion is deterministic (no LLM) and applied before retrieval
- Character budget enforced across Q&A + chunks (~4K tokens total)
- All tests use real corpus read-only; no synthetic fixtures except for focused unit tests

**Architecture compliance:**
- No generative model calls anywhere in `app/knowledge/index/`
- PyThaiNLP `newmm` tokenizer is offline (bundled dictionary)
- BM25 via `rank-bm25`, RRF fusion with k=60, numpy for dense scoring
- `sentence-transformers` lazy-loaded only on first `BgeM3Embedder` use

**Test coverage:**
- Chunker: headings, tiny/oversize sections, Thai text, no loss, stable IDs, fenced code
- Tokenizer: Thai segmentation, lowercase, punctuation/whitespace filtering
- RRF: formula correctness, stable ties, k validation
- Searcher: Q&A precedence, budget, dedupe, query validation, alias expansion, determinism
- Corpus: lossless chunking, stable chunk IDs, path safety, Q&A count, Q&A-first retrieval
- Architecture: no generative/ADK imports, lazy torch/sentence-transformers

### 5. Dependencies added correctly

`pyproject.toml` optional group `index`:
- `numpy>=2.4.6`
- `pythainlp>=5.3.8`
- `rank-bm25>=0.2.2`
- `sentence-transformers>=6.1.0`

Installed via `uv sync --all-extras` (updated in `.chief/project.md`).

pytest markers added:
```toml
markers = [
  "model: opt-in test needing a locally cached real embedding model (deselected by default)",
]
addopts = "-m 'not model'"
```

### 6. Scope discipline

The ticket correctly:
- Does NOT wire the index into ADK or FastAPI (ticket 002/003)
- Does NOT modify any file under `knowledge/source/` or `knowledge/aliases/`
- Does NOT implement `gemini-embedding` adapter (seam exists, implementation deferred)
- Does NOT build `ask_knowledge_deep` (decision D5: not approved)

---

## Conclusion

Ticket 001 delivers a production-ready, deterministic knowledge index library that satisfies all acceptance criteria. The implementation is clean, well-tested (46 new tests, all pass), and respects the MVP contract: no generative calls, offline by default, lossless chunking, Q&A-first retrieval. Knowledge documents remain untouched. The opt-in bge-m3 test is correctly gated and will validate the retrieval quality claim when the model is cached locally.

Pre-existing ruff issues are noted but not blocking. The library is ready for integration (tickets 002/003).

VERDICT: PASS
