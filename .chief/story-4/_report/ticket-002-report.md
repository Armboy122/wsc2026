# story-4 ticket-002 report

Implementer: maxplus/deepseek-v4.1-flash-x via pi. Reviewer: xai/grok-4.7 (Opus review hung on MaxPlus; grok-4.7 is the approved fallback). Review rounds: 1.

Final tests: 186 passed, 1 deselected, 3 warnings in 4.36s

## Review
# Review: story-4 ticket-002 — index lifecycle

Scope reviewed: uncommitted diff (including staged `conftest.py` and untracked `app/knowledge/index/manager.py`, `tests/knowledge_index/test_manager.py`, `tests/test_health_knowledge_index.py`) against ticket 002, `.chief/story-4/_contract/knowledge-search.md`, and `.chief/story-4/_decisions/pending-decisions.md`. No repo files were modified. `.env` was not read.

## Blocking findings

None.

## Checks

- `uv run --all-extras pytest -q`: **186 passed, 1 deselected** in 4.07s. The deselected test is the opt-in `-m model` case in `tests/knowledge_index/test_index_model.py`. No Gemini, network, or model download on the default suite.
- `uvx ruff check` on the touched Python files (`manager.py`, `app/knowledge/index/__init__.py`, `app/main.py`, `app/core/startup.py`, `app/core/config.py`, `app/api/routes.py`, `app/contracts.py`, `app/api/tests/test_routes.py`, `app/core/tests/test_config.py`, `tests/knowledge_index/test_manager.py`, `tests/test_health_knowledge_index.py`, `conftest.py`): **All checks passed.**
- `knowledge/` and `docs/research/` are unchanged (no staged, unstaged, or untracked paths). Tests did not dirty them.

## Acceptance

- Fresh start builds; a second `IndexManager` on the same `index_dir` reuses cached vectors. `test_second_start_loads_from_cache_without_re_embedding` asserts the fake embedder is not called again.
- Add, edit, and delete under a temp source root (and an alias-file change) swap the searcher after the short debounce without restart. Watcher is `watchfiles` with debounce, recursive by default, plus `yield_on_timeout` fingerprint fallback and a poll loop if `watchfiles` is missing.
- Embedder failure keeps the previous searcher and reports `stale`, or `error` when nothing has ever built. A corrupt header or `vectors.npy` is ignored (`allow_pickle=False`; `OSError`/`ValueError`/`TypeError`/`EOFError`/`JSONDecodeError`) and rebuilt. Cache files are JSON + NPY only, written under `KNOWLEDGE_INDEX_DIR` (default `.cache/knowledge-index`, gitignored as `/.cache/`).
- Startup does not embed on the event loop. `create_knowledge_index_manager` only constructs a lazy embedder; `lifespan` calls `manager.start()` (background threads) and `await asyncio.to_thread(manager.stop)`. `search` before the first successful build raises `IndexUnavailableError` with code `unavailable`.
- `/health` adds `knowledgeIndex` (`building|ready|stale|error` plus document/chunk counts). Snapshots carry no paths, content, or error text. Missing manager is reported as `error` with zero counts so the field is always present.

## Minor notes

- `CONTRACTS.md` still documents the old `/health` body and env table. `app/contracts.py` now requires `knowledgeIndex`. Ticket 002 did not list `CONTRACTS.md`, and the runtime contract is tested, but AGENTS.md asks those two to stay aligned. Update it when the public health contract is next touched (likely with ticket 003).
- `_save_embedding_cache` sits outside the rebuild `try` and only swallows `OSError`. A non-`OSError` from save would skip the atomic swap and kill the build thread without `_record_failure`, leaving status at `building`. Normal float32 `np.save` failures are `OSError`; this is a narrow gap versus the “cache failures never fail a build” comment.
- `chunks` in health is `len(index.chunks) + len(index.qa_units)`. Counts stay path-free; the name is slightly broader than document chunks.
- `search()` reads `self._searcher` outside `_state_lock`. The swap itself is a single assignment under the lock, which is atomic on CPython. Not a startup or correctness failure for this runtime.
- The fingerprint fallback re-hashes every approved file on each watch timeout (default step 1s) on the watcher thread, not the event loop. Correct, not especially cheap.
- Root `conftest.py` forces `KNOWLEDGE_EMBEDDER=fake` and a throwaway `KNOWLEDGE_INDEX_DIR` before `app.main` import, and leaves that temp directory behind. That is what keeps the default suite offline.
- `KNOWLEDGE_EMBEDDER` correctly rejects `gemini-embedding` for this ticket (`bge-m3|fake` only). D4’s config swap is not this card.

VERDICT: PASS
