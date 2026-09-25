# Ticket 001 — Knowledge index core (chunker, hybrid retrieval, Q&A lane)

Type: implementation
Status: planned
Blocked by: none (D0 approved and D4 decided 2026-09-26)

## TASK

Create a pure, deterministic library `app/knowledge/index/` that turns approved Markdown into
chunks and answers `search(query)` with a Q&A lane plus hybrid (BM25 + dense, RRF) chunks.
No ADK, no FastAPI, no startup wiring in this ticket.

## FILES / COMPONENTS IN SCOPE

`app/knowledge/index/{__init__,chunker,tokenize,bm25,embedder,fusion,aliases_expand,searcher,models}.py`,
reuse `app/knowledge/catalog.py` allowlist and `app/knowledge/aliases.py`,
`pyproject.toml` (new optional group `index`: `pythainlp`, `rank-bm25`, `numpy`,
`sentence-transformers`), `project.md` install command, tests under `tests/knowledge_index/`.

## MUST DO

- Heading-aware Markdown chunker with no configuration: split on `#`–`###`, keep heading path as
  chunk context prefix, merge tiny sections, split oversize sections on paragraph/line
  boundaries with fixed defaults (port logic from `~/rag-eval/retr.py`). Never alter source text;
  every chunk maps back to `sourceId` + heading path + char span.
- Q&A files (`knowledge/source/qa/qa_*.md`) are a separate lane: one unit per Q&A file, indexed on
  the question line (including `คำถามใกล้เคียง` paraphrases) and answer; returned as full Q&A text.
- Tokenizer: PyThaiNLP `newmm` (offline dictionary), lowercase, drop whitespace/punctuation.
- `Embedder` protocol (`embed_documents`, `embed_query`, `model_id`, `dim`); `BgeM3Embedder`
  (sentence-transformers, CPU, normalized, lazy-loaded); `FakeEmbedder` for tests (deterministic
  hashing). A `gemini-embedding` adapter is NOT implemented, only the seam.
- RRF fusion (k=60) of BM25 and dense ranks; Q&A lane scored the same way on Q&A units.
- Alias query expansion: append alias terms from `knowledge/aliases/*.md` whose triggers match the
  normalized query (deterministic, no LLM).
- `Searcher.search(query) -> SearchResult(qa=[≤2], chunks=[≤5], sources=[...])`, with a total
  character budget (~4K tokens); dedupe chunks from a Q&A already returned.

## MUST NOT DO

- Do not modify any file under `knowledge/source/` or `knowledge/aliases/`.
- No generative model calls, no network at import or test time, no vector DB service.
- Do not change the ADK tool or prompt yet.

## ACCEPTANCE CRITERIA

- Chunking the real corpus is deterministic (same input → identical chunk IDs) and loses no
  text (concatenated chunk bodies cover every non-empty line of each source).
- On the real corpus with `FakeEmbedder`+BM25, each Q&A main question retrieves its own Q&A file
  as Q&A rank 1 (11/11).
- Opt-in `-m model` test with cached bge-m3: Q&A-lane hit@2 on the 35 paraphrases reported
  (target ≥ the research run); skipped when the model is not cached.
- Full suite passes offline.

## TESTS

Chunker (headings, tiny/oversize sections, Thai text, no loss, stable IDs); tokenizer; RRF math;
Q&A lane precedence and budget; alias expansion; path-safety of sourceIds; no generative import
(extend `tests/test_architecture.py`).

## STOP CONDITION

Stop when the library and its tests are green; wiring is ticket 002/003.
