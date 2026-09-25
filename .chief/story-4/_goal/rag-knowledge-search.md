# Goal (Story 4 — in progress; D0 approved 2026-09-26)

Replace "Gemini Live picks whole documents from a catalog" with a deterministic, zero-config
hybrid search over all approved Knowledge, so the Live session receives a small, relevant,
source-attributed context (approved Q&A first) instead of whole documents.

Users only drop Markdown files into `knowledge/source/` (and Q&A into `knowledge/source/qa/`);
the system chunks, indexes and re-indexes by itself.

## Why (research, 2026-09-26, `~/rag-eval`, measured on this repo's documents)

- The 34 PEA documents alone cannot answer most real questions (docs-only: best strict 7%).
  The approved Q&A files in `knowledge/source/qa/` are required and must take precedence.
- 35 held-out paraphrase questions, corpus = docs + Q&A:

  | Approach | Correct | Wrong | Input tokens | Note |
  | --- | --- | --- | --- | --- |
  | long context, Q&A first | 32/35 (91%) | 0 | ~132K | too large for a Live session (131K limit) |
  | hybrid bge-m3 + PyThaiNLP BM25 + RRF, Q&A-first lane | 29/35 (83%) | 2 | ~3.8K | ~160 ms per search |
  | current catalog/whole-document selection | 23/35 (66%) | 3 | ~4.6K | |

- Corpus is ~70K–130K tokens, so it cannot be put in the Live session.
- RAGFlow is broken for Thai. Gemini File Search is not supported by the Live API.
- Single run, n=35: differences of 1–3 questions are within noise.

## Target runtime

```text
Browser mic → WS /ws/live → ADK run_live() → Gemini Live
  → search_knowledge(query) → app/knowledge/index (Q&A lane + hybrid chunks, local, no LLM)
  → same Gemini Live session → speaker
(optional, pending D5) → ask_knowledge_deep(question) → long-context Gemini Flash + context cache
```

## Ticket sequence

1. `001-knowledge-index-core` — chunker, tokenizer, BM25, embedder interface, RRF, Q&A lane, alias expansion (library only).
2. `002-index-lifecycle-auto-reindex` — persistent index cache, build at startup, re-index on file change, health.
3. `003-search-knowledge-tool-and-prompt` — `search_knowledge` ADK tool replaces the catalog tool; Q&A-wins prompt rule.
4. `004-offline-regression-eval` — port `~/rag-eval` into the repo with a swappable answer model.
5. `005-optional-deep-fallback` — `ask_knowledge_deep`; blocked on decision D5, may be dropped.

## Out of scope

Editing/deleting/renaming any Knowledge document; vector DB servers, RAGFlow, Gemini File
Search, MCP, OMS/VOC/Chat/LINE, UI redesign, extra conversational agents.

## Pending decisions

See `_decisions/pending-decisions.md`. Ticket 001 must not start until D0 is confirmed.
