# Contract (Story 4)

## Knowledge (deterministic, local)

- All approved documents are kept; their content is never edited, reformatted, deleted or renamed
  by code or tickets. The index is a derived artefact (gitignored cache), never a source of truth.
- Allowlist and safety rules from Stories 1–2 still hold: only files under
  `KNOWLEDGE_SOURCE_ROOT`, relative source IDs, no path traversal, no hallucinated citations.
  Every returned chunk/Q&A carries `sourceId`, `title`, `uri` (`knowledge://source/<sourceId>`)
  and heading path.
- Knowledge performs ZERO generative model calls. Embedding models are allowed (not generative).
  Default embedder is self-hosted `BAAI/bge-m3`; it sits behind an `Embedder` protocol so
  `gemini-embedding` can be swapped in by configuration only.
- Retrieval = PyThaiNLP-tokenized BM25 + dense cosine, fused with RRF (k=60), plus a separate
  Q&A lane over `knowledge/source/qa/`. Approved Q&A always ranks above document chunks.
- Zero config: chunking is heading-aware Markdown with fixed defaults; no per-file settings.
- Index builds at startup and rebuilds automatically when files are added/changed/removed.
  A failed rebuild keeps serving the last good index and is reported by `/health`.

## ADK tool surface

- `search_knowledge(query: str)` replaces `get_knowledge_documents` and the catalog in the
  instruction. It returns top 1–2 approved Q&As (full Q&A text) + ~5 chunks with sources,
  bounded to roughly 4K tokens, and runs off the event loop via `asyncio.to_thread`.
- Empty/over-long/invalid queries and index-unavailable return the existing structured error
  shape (`{"status":"error","error":{"code","message"}}`) with wire codes
  `invalid_input` / `unavailable` / `internal`.
- `ask_knowledge_deep` exists only if decision D5 approves it.

## Prompt rule (Thai, in `app/prompts/adk_voice.md`)

Approved Q&A wins over any other document; do not add conditions, numbers, channels or scope the
Q&A does not state; if unsure or nothing relevant is found, ask the customer a clarifying
question or refer to the PEA 1129 call center.

## Testing decisions

- The whole pytest suite runs offline: no Gemini calls, no network, no model download.
  Unit tests use a deterministic fake embedder; real bge-m3 tests are opt-in
  (`-m model`, skipped unless the model is already cached locally).
- Architecture tests keep asserting that `app/knowledge` has no generative client.
- Latency/quality claims only from measured runs (eval harness, ticket 004); real Gemini Live
  voice acceptance stays a manual, pending check.

## Process

- Commits: `refactor(story-4/ticket-NNN): <summary>`, on `refactor/adk-live-knowledge-only`.
- Review order: Sol first; if unavailable, `xai/grok-4.7` (owner-approved fallback). Record the
  reviewer and rounds in `_report/ticket-NNN-report.md`.
- Never read, print or commit `.env`.
