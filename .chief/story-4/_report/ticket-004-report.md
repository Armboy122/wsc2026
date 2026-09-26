# story-4 ticket-004 report

Implementer: maxplus/deepseek-v4.1-flash-x via pi on the assistant's server. Reviewer: maxplus-claude/claude-opus-5. Review rounds: 1.

Final tests: 194 passed, 1 deselected, 2 warnings in 4.70s

## Review
# Story 4 Ticket 004 Review — Offline Regression Evaluation Harness

**Reviewer:** Sol (or xai/grok-4.7 fallback per contract)  
**Date:** 2026-09-26  
**Commit:** uncommitted work on `refactor/adk-live-knowledge-only`

---

## BLOCKING FINDINGS

None.

---

## ACCEPTANCE CRITERIA — ALL MET

✅ **Dataset**: 11 main + 35 paraphrases parsed from real `knowledge/source/qa/qa_*.md`  
✅ **Holdout**: Paraphrases removed from indexed Q&A text (verified in `test_eval_rag_dataset.py`)  
✅ **Retrieval eval**: Uses production `app/knowledge/index`, runs offline with `fake` embedder  
✅ **Answer eval**: `AnswerModel`/`JudgeModel` protocols; `StubModel`, `PiCliModel`, `GeminiModel` adapters  
✅ **Modes**: `hybrid_qafirst` (ticket 003 payload) and `longctx_qafirst` implemented  
✅ **CLI**: `scripts/eval_rag retrieval --embedder fake` runs offline (0.80 ms/search, printed table)  
✅ **CLI**: `scripts/eval_rag answer --model stub` produces JSONL + summary offline (100% correct stub)  
✅ **Switching models**: `--model gemini:<name>` / `pi:<provider/model>` needs no code change  
✅ **Baseline**: `evaluation/rag/baseline.md` records research numbers (verbatim from `~/rag-eval/summary.txt`) with provenance and caveats, plus port-time fake-embedder retrieval baseline  
✅ **Tests**: Full suite passes offline (194 passed in 4.64s); no real model/network calls  
✅ **Outputs gitignored**: `evaluation/rag/out/` present in `.gitignore`

---

## VERIFICATION RESULTS

### Tests
```
uv run --all-extras pytest -q
194 passed, 1 deselected, 2 warnings in 4.64s
```

All eval tests offline, no subprocess/network/model download.

### Ruff
`scripts/eval_rag` is a bash script; ruff correctly rejects it as Python. Checking Python files only:
```bash
uvx ruff check evaluation tests/eval_rag
# (passes; no Python syntax issues)
```

### CLI Commands (Offline)

**Retrieval:**
```
scripts/eval_rag retrieval --embedder fake
===== retrieval eval — embedder=fake, questions=paraphrase
n=35 | qa_hit@1=24/35 (69%) | qa_hit@2=33/35 (94%) | hit@1=24/35 hit@2=33/35 hit@5=33/35 
     | chunk_hit@5=0/35 | mean=0.80 ms/search | median returned tokens=2617
```
✅ Runs in ~1 second, fully offline, deterministic.

**Answer:**
```
scripts/eval_rag answer --model stub
===== answer eval — mode=hybrid_qafirst, model=stub, questions=paraphrase
stub n=35 CORRECT=35 PARTIAL=0 WRONG=0 NO_ANSWER=0 other=0 
     | strict=100% lenient(C+P)=100% | median sec=0.0 | median context tokens=3301
```
✅ Runs in ~2 seconds, fully offline, produces 4 files in `evaluation/rag/out/`.

### Hard-coded paths
```bash
rg -n '/workspace' evaluation scripts tests/eval_rag
# No matches found
```
✅ No hard-coded `/workspace/...` paths in repo code.

### API key handling
- `GEMINI_API_KEY` read via `Settings.from_env()` on first use only (lazy client construction)
- Never printed, logged, or written to JSONL/summary/cache
- Docstrings explicitly state "never logged, returned, or written to any evaluation output"
- Tests never import `google.genai` or call real models
✅ Secure credential handling.

### Dataset counts
```python
# tests/eval_rag/test_eval_rag_dataset.py
def test_dataset_has_eleven_main_and_thirtyfive_paraphrases(dataset):
    mains = [q for q in dataset if q.kind == MAIN]
    paraphrases = [q for q in dataset if q.kind == PARAPHRASE]
    assert len(mains) == 11
    assert len(paraphrases) == 35
```
✅ Correct counts verified by test.

### Baseline provenance
`evaluation/rag/baseline.md` contains:
- Research harness numbers verbatim from `~/rag-eval/summary.txt`
- `rag_qafirst` 29/35 (83%), `longctx_qafirst` 32/35 (91%), ~132K tokens
- Port-time fake-embedder baseline: `qa_hit@1=24/35 (69%)`, `qa_hit@2=33/35 (94%)`
- Clear provenance table (harness, date, models, corpus, caveats)
✅ Numbers match reference, properly attributed.

### Production integration
- `evaluation/rag/retrieval_eval.py`: imports `app.knowledge.index.KnowledgeIndex`, `build_embedder`
- `evaluation/rag/answer_eval.py`: imports `app.agent.adk_agent.search_result_payload`, `app.knowledge.catalog`
- `evaluation/rag/dataset.py`: imports `app.knowledge.catalog.KnowledgeCatalog`, `app.knowledge.index.parse_qa_unit`
✅ Uses production code, not a copy.

### app/ knowledge/ docs/ unchanged
```bash
git diff app/ knowledge/ docs/
# (no output)
```
✅ Source documents and production code untouched.

---

## MINOR NOTES (Non-blocking)

1. **Ruff false positive on bash script**: `scripts/eval_rag` is a bash script with a shebang; ruff tries to parse it as Python. This is a tooling issue, not a code issue. The script is executable and works correctly.

2. **`~/rag-eval` not archived**: The research harness exists at `/workspace/rag-eval` and baseline numbers are copied from it, but it's outside the repo. This is correct per the ticket ("bring the research harness into the repo" means port, not move).

3. **Baseline latency caveat**: `baseline.md` correctly notes "latency is a single sample and varies with machine load" for the port-time fake-embedder run. This is appropriate for a deterministic regression baseline.

4. **Test coverage**: 508 lines across 6 test files. Coverage is appropriate for the scope: dataset parsing, holdout, metric math, stub pipeline, CLI, cache keying. Real-model runs are explicitly owner actions and correctly excluded from pytest.

5. **README integration**: `README.md` now documents the harness location, commands, and that real-model runs are owner actions. `ARCHITECTURE.md` notes the new test files and output directory.

---

## DOCUMENTATION QUALITY

- `evaluation/rag/README.md`: comprehensive, correct commands, clear table of model specs/modes
- `evaluation/rag/baseline.md`: excellent provenance, caveats, and distinction between research and port-time numbers
- Module docstrings: detailed, explain holdout semantics, token estimation, cache keying
- `scripts/eval_rag`: clear comment that it prefers `.venv` and falls back to `uv run`

---

## CODE QUALITY

- Clean separation: dataset, retrieval_eval, answer_eval, models, report, cli
- Protocols (`AnswerModel`, `JudgeModel`) allow swapping providers without code change
- Lazy construction: Gemini client built on first call, not at import
- Explicit error messages: "GEMINI_API_KEY is not set; real Gemini runs are an owner action"
- Type hints present on new interfaces
- No dead code, no commented-out blocks, no debugging prints

---

## SUMMARY

The offline regression evaluation harness is complete, correct, and ready. It ports the research harness faithfully, uses the production index and payload builder (not a copy), runs both CLI commands fully offline by default, records the research baseline with full provenance, and leaves app/ knowledge/ docs/ untouched. The full test suite passes offline in under 5 seconds. Dataset counts (11 main, 35 paraphrases), holdout correctness, metric math, stub pipeline, CLI args, and cache keying are all tested. Real-model runs (Gemini, pi, bge-m3) are correctly owner actions and never called by pytest. API keys are read securely and never logged. Outputs are gitignored. No hard-coded `/workspace/` paths.

All acceptance criteria met. No blocking issues.

VERDICT: PASS
