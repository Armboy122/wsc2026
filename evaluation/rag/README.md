# Offline RAG regression evaluation

`evaluation/rag/` measures Knowledge retrieval and answer quality against the **production**
index (`app/knowledge/index`) and the **production** `search_knowledge` payload builder
(`app/agent/adk_agent.search_result_payload`). It never copies the chunker or the retriever.

The dataset is the approved Q&A under `knowledge/source/qa/qa_*.md`: **11 main questions + 35
`คำถามใกล้เคียง` paraphrases**, gold answer = the `## ตอบ` section. The paraphrases are held out:
the index is built with `include_qa_paraphrases=False`, and any Q&A body placed in an answer
context has the paraphrase list stripped from its heading, so the evaluation cannot trivially
match the question. Retrieval indexes only `knowledge/source/**` (decision D7).

## Running it

The wrapper is `scripts/eval_rag`. Both commands are **fully offline by default**.

```bash
# Retrieval quality (fake embedder, offline, seconds)
scripts/eval_rag retrieval --embedder fake

# Answer + judge pipeline end to end (stub model, offline, seconds)
scripts/eval_rag answer --model stub
```

The same commands work as a module:

```bash
uv run --all-extras python -m evaluation.rag retrieval --embedder fake
uv run --all-extras python -m evaluation.rag answer --model stub
```

Useful options:

| Command | Option | Default | Meaning |
| --- | --- | --- | --- |
| both | `--questions main\|paraphrase\|all` | `paraphrase` | which questions to run |
| both | `--source-root PATH` | `<repo>/knowledge/source` | override the approved corpus |
| both | `--out DIR` | `evaluation/rag/out` | where summaries, JSONL and the cache go |
| `retrieval` | `--embedder fake\|bge-m3` | `fake` | `bge-m3` loads the real self-hosted model |
| `answer` | `--mode hybrid_qafirst\|longctx_qafirst` | `hybrid_qafirst` | context assembly |
| `answer` | `--model SPEC` / `--judge SPEC` | `stub` / same as `--model` | see model specs below |
| `answer` | `--limit N`, `--no-cache` | — | quick runs, bypass the response cache |

### Modes

- `hybrid_qafirst` — context is the ticket-003 `search_knowledge` payload (approved Q&A first,
  then source-attributed chunks), rendered from the production payload builder.
- `longctx_qafirst` — every approved document, Q&A first, then documents (the research harness
  long-context arm). This is large (~130K characters) and is not what the Live session uses.

### Model specs

| Spec | Adapter | Notes |
| --- | --- | --- |
| `stub` | `StubModel` | deterministic, offline; used by tests and smoke runs |
| `pi:<provider/model>` | `PiCliModel` | runs `pi -p --no-session --model <provider/model>` with stdin from `/dev/null`, a temp prompt file, a hard timeout and retries |
| `gemini:<name>` | `GeminiModel` | google-genai SDK; the key is read from `GEMINI_API_KEY` in the process environment on first use, never logged and never written to output |

Switching providers needs no code change:

```bash
scripts/eval_rag answer --model pi:maxplus/deepseek-v4.1-flash --judge pi:maxplus/glm-5.3
scripts/eval_rag answer --model gemini:gemini-3.6-flash --mode hybrid_qafirst
```

**Real-model runs are an owner action.** They need a configured `pi` provider or a
`GEMINI_API_KEY`, and they are never run by pytest. Building indexes with `--embedder bge-m3`
downloads/loads `BAAI/bge-m3` (~2.3 GB) and is also an owner action.

## Outputs

Everything is written under the gitignored `evaluation/rag/out/` (override with `--out`):

- `retrieval-<embedder>-<questions>.txt` / `.jsonl` — the summary table (also printed) and one
  line per question (`qa_source_ids`, `chunk_source_ids`, latency, returned tokens).
- `answers-<mode>-<model>-<questions>.txt` / `.jsonl` — the summary table (also printed) and one
  line per answer: question id, mode, answer/judge model, retrieved ids, answer, judge
  verdict/reason and latencies.
- `cache/<sha256>.json` — response cache keyed by `(model spec, mode, prompt)`, so re-running a
  run is free unless the model, the mode or the prompt changed.

### Metrics

- `qa_hit@1` / `qa_hit@2` — the gold Q&A source is the first / among the first two approved Q&A
  hits.
- `hit@k` — the gold source appears in the combined ranked result (Q&A first, then chunks); this
  is the research harness `hit@k` semantics.
- `chunk_hit@k` — the gold source appears in the document-chunk lane. On this Q&A-only question
  set it is expected to be `0` because approved Q&A sources are never emitted as chunks; it is a
  diagnostic for a future document-question set.
- `mean` — wall-clock `KnowledgeIndex.search` time per question.
- `median returned tokens` / `context tokens` — an estimate: `ceil(chars / 2)`. The production
  index has no tokenizer and bounds context by characters (8,000 chars ≈ 4K tokens), so this is a
  documented estimate, not a tokenizer count.

## Tests

```bash
uv run --all-extras pytest tests/eval_rag -q
```

The tests are offline and fast: they parse the real Q&A files, check the holdout, check the
metric math, run the stub answer+judge pipeline into a temp directory, exercise both CLI commands,
and verify cache keying. They never call `pi`, Gemini, or the network, and never download a model.

## Baseline

`baseline.md` records the `~/rag-eval` research numbers and their provenance, clearly labelled as
research-harness results, plus the port-time fake-embedder retrieval numbers for offline
regression tracking.
