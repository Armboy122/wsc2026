# Ticket 004 — Port `~/rag-eval` as an offline regression evaluation

Type: implementation
Status: planned
Blocked by: Ticket 001 (retrieval part); Ticket 003 (tool-payload part)

## TASK

Bring the research harness into the repo as `evaluation/rag/` so retrieval and answer quality can
be re-measured after Knowledge changes, with a swappable answer/judge model (later Gemini).

## FILES / COMPONENTS IN SCOPE

`evaluation/rag/{dataset,retrieval_eval,answer_eval,models,report}.py`, `scripts/eval_rag`
(CLI), `evaluation/rag/README.md`, tests under `tests/eval_rag/`. Results/caches go to a
gitignored `evaluation/rag/out/`.

## MUST DO

- Dataset loader from `knowledge/source/qa/qa_*.md` (main + `คำถามใกล้เคียง` paraphrases; gold = `## ตอบ`),
  holding out paraphrases from the indexed Q&A text exactly as `~/rag-eval/common.py` does.
- Retrieval eval uses the production `app/knowledge/index` (not a copy): Q&A-lane hit@1/2,
  chunk hit@k, ms/search, returned tokens. Runs fully offline with bge-m3 (or fake embedder).
- Answer eval: `AnswerModel` / `JudgeModel` protocols; adapters `PiCliModel` (current research
  path, `pi -p` provider/model configurable), `GeminiModel` (google-genai; key read from the
  environment only, never logged), `StubModel` for tests. Modes: `hybrid_qafirst` (tool payload
  from ticket 003) and `longctx_qafirst`. Response cache keyed by prompt hash.
- Report: summary table like `~/rag-eval/summary.txt` + JSONL per answer; a checked-in
  baseline (`evaluation/rag/baseline.md`) recording the research numbers and their provenance.

## MUST NOT DO

- pytest must never call a real model or network; answer eval runs only via the CLI.
- Do not hard-code `/workspace/...` paths or read `.env` in code paths other than normal settings.

## ACCEPTANCE CRITERIA

- `scripts/eval_rag retrieval --embedder fake` runs offline in CI time and prints the table.
- `scripts/eval_rag answer --model stub` produces JSONL + summary end-to-end offline.
- Switching to `--model gemini:<name>` needs no code change (D6 measurement later).
- Full suite passes offline.

## TESTS

Dataset parsing on the real Q&A files (11 main, 35 paraphrases), holdout correctness,
metric math, stub answer/judge pipeline, CLI arg parsing, cache keying.

## STOP CONDITION

Stop when the harness runs offline and baseline is recorded; real-model runs are an owner action.
