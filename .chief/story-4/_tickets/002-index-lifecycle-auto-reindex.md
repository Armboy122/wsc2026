# Ticket 002 — Index lifecycle: startup build, cache, automatic re-index

Type: implementation
Status: planned
Blocked by: Ticket 001

## TASK

Make the index manage itself: build (or load from cache) at app startup, rebuild automatically
when Knowledge files change, and expose readiness in `/health`.

## FILES / COMPONENTS IN SCOPE

`app/knowledge/index/manager.py` (new), `app/main.py` / `app/core/startup.py` lifespan,
`app/core/config.py` (only `KNOWLEDGE_INDEX_DIR`, `KNOWLEDGE_EMBEDDER` = `bge-m3|fake`),
`.env.example`, `.gitignore` (index cache dir), `app/api/routes.py` health, tests.

## MUST DO

- `IndexManager` holds the current immutable `Searcher`; swaps atomically after a successful
  rebuild; a failed rebuild keeps the last good index and records the error.
- Cache on disk keyed by corpus fingerprint (paths + sizes + sha256) + chunker version +
  embedder `model_id`; unchanged files reuse cached embeddings (incremental).
- Startup: build/load in a background thread so the server starts immediately; `search` before
  ready returns `unavailable`.
- File change detection: debounced watcher (`watchfiles`, already installed with
  `uvicorn[standard]`) on `KNOWLEDGE_SOURCE_ROOT` and `knowledge/aliases/`; plus a cheap
  fingerprint check fallback. Adding a new `.md` or Q&A file needs no restart or config.
- `/health` adds `knowledgeIndex`: `building|ready|stale|error`, document/chunk counts
  (no paths or content).

## MUST NOT DO

- Do not write into `knowledge/`; the cache lives only in `KNOWLEDGE_INDEX_DIR` (gitignored).
- Do not block the event loop during build/embedding.

## ACCEPTANCE CRITERIA

- Fresh start builds; second start loads from cache without re-embedding (asserted via fake
  embedder call counts).
- Adding, editing and deleting a file in a temp Knowledge root is reflected in search results
  after the debounce, without restart.
- Corrupt cache or embedder failure → last good index kept, health shows `error/stale`.
- Full suite passes offline.

## TESTS

Manager swap/ready states, cache hit/miss/invalidation (chunker version, model id), incremental
re-embed counts, watcher debounce (tmp_path, short debounce), health payload shape, settings.

## STOP CONDITION

Stop when lifecycle is green; tool replacement is ticket 003.
