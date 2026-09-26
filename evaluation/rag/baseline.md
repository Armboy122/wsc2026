# `rag-eval` research baseline

These numbers come from the **research harness**, not from this repository's harness. They are
recorded here so a future re-run can be compared against the run that motivated Story 4. They
were **not** re-measured by `evaluation/rag` and must be read with the provenance and caveats
below.

## Provenance

| Item | Value |
| --- | --- |
| Harness | `~/rag-eval` (owner's Mac; an audited copy was also reviewed on the build machine) |
| Date | 2026-09-26 (research only; the `wsc2026` repo was untouched) |
| Files | `common.py` (dataset/corpus), `retr.py` (chunking + bge-m3 dense + PyThaiNLP BM25 + RRF), `run.py` (longctx / rag_hybrid / catalog_select + LLM judge), `run2.py` (Q&A-first variants), `retr_eval.py`, `summarize.py`, `summary.txt`, `results_*.jsonl` |
| Embedder | `BAAI/bge-m3`, CPU |
| Answer model | `maxplus/deepseek-v4.1-flash`, thinking off (via `pi -p`) |
| Judge model | `maxplus/glm-5.3`, thinking low |
| Questions | 11 Q&A files → 11 main + 35 paraphrase questions; gold = the `## ตอบ` section |
| `docs_only` corpus | 34 `PEA_*.md` documents + `docs/research/electricity-tariff-sep-2569.md`, no Q&A files; 46 questions |
| `with_qa` corpus | the same documents plus the Q&A files **with the `คำถามใกล้เคียง` list removed from the heading**; only the 35 held-out paraphrases were asked |
| Run count | single run per setting; with n=35/46, a difference of 1–3 questions is within noise |

## Answer quality (`~/rag-eval/summary.txt`)

Copied verbatim from `summary.txt`, which summarizes row-by-row JSONL
(`results_docs_only.jsonl`, `results_with_qa.jsonl`). "strict" = `CORRECT / n`; "lenient" =
`(CORRECT + PARTIAL) / n`.

### `with_qa` setting — 35 held-out paraphrases

| Approach | CORRECT | PARTIAL | WRONG | NO_ANSWER | strict | lenient | median sec | median answer-call input tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `longctx` | 26 | 6 | 3 | 0 | 74% | 91% | 12.2 | 131,845 |
| `rag_hybrid` | 23 | 10 | 1 | 1 | 66% | 94% | 6.8 | 3,229 |
| `catalog_select` | 23 | 9 | 3 | 0 | 66% | 91% | 12.3 | 4,623 |
| `rag_qafirst` | **29** | 3 | 2 | 1 | **83%** | 91% | 6.2 | 3,823 |
| `longctx_qafirst` | **32** | 3 | 0 | 0 | **91%** | **100%** | 11.5 | 132,147 |

### `docs_only` setting — 46 questions (no Q&A files)

| Approach | CORRECT | PARTIAL | WRONG | NO_ANSWER | strict | lenient | median sec | median answer-call input tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `longctx` | 3 | 15 | 9 | 19 | 7% | 39% | 14.1 | 124,984 |
| `rag_hybrid` | 3 | 18 | 3 | 22 | 7% | 46% | 7.9 | 6,142 |
| `catalog_select` | 1 | 14 | 12 | 19 | 2% | 33% | 14.7 | 9,641 |

The Story 4 goal table sums the `with_qa` results differently: it reports `longctx_qafirst`
32/35 correct with 0 wrong and ~132K input tokens, and `rag_qafirst` 29/35 correct with 2 wrong,
~3.8K input tokens and **~160 ms per search** (Story 4
`.chief/story-4/_goal/rag-knowledge-search.md`).

## Retrieval hit rates — not recorded

`retr_eval.py` printed `hit@1/3/6` for `bm25`, `dense` and `hybrid` over the 35 paraphrases, but
its stdout was **not saved** anywhere under `~/rag-eval`, so no retrieval hit numbers can be
quoted from the research files. `tests/knowledge_index/test_index_model.py` cites Q&A-lane hit@2
= 34/35 for that run, but that figure is a comment in this repository and is not traceable to a
saved harness output; treat it as unverified.

## Caveats when comparing with `evaluation/rag`

1. **Corpus differs (decision D7).** The research `with_qa` corpus also included
   `docs/research/electricity-tariff-sep-2569.md`; the ported harness indexes only
   `knowledge/source/**`, so the two runs are not directly comparable.
2. **Chunkers differ.** The research `retr.py` chunker was a separate implementation; the ported
   harness uses the production `app/knowledge.index` chunker.
3. **Prompt micro-differences.** The ported prompts were transcribed from `run.py`/`run2.py`;
   any wording drift changes answer quality.
4. **Non-determinism.** Real answer/judge models are non-deterministic; a single run is not a
   significance test.

## Recorded at port time (ticket 004, not research)

For offline regression tracking only. Measured with the deterministic `FakeEmbedder` (35 held-out
paraphrases, paraphrases held out of the index, real approved corpus, this machine). The hit
counts and returned-token estimate are deterministic; the latency is a single sample and varies
with machine load:

```text
n=35 | qa_hit@1=24/35 (69%) | qa_hit@2=33/35 (94%) | hit@1=24 hit@2=33 hit@5=33
     | chunk_hit@5=0/35 | mean≈0.7 ms/search (varies) | median returned tokens=2617
```

The fake embedder is a hashing stand-in, not `bge-m3`; these numbers exist so an unintended
retrieval regression is visible without downloading a model, and they are **not** comparable to
the research hit rates (which were never saved).
