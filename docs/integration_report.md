# PEA One Agent QA integration report

## Scope

This branch supplies black-box contract checks in `tests/test_mvp_evaluation.py`, a deterministic dataset suite, and `scripts/evaluate`. The tests intentionally target the frozen HTTP and tool behavior and do not mock away write-safety policy.

## Dataset inventory

| Dataset | Cases | Coverage |
|---|---:|---|
| Knowledge | 40 | retrieval, citations, no-evidence behavior |
| OMS | 10 | status, safety-first outage reporting |
| Sabuy | 10 | account reads, payment preparation |
| VOC | 10 | categories, case preparation |
| Multi-tool | 10 | bounded multi-action orchestration |
| Adversarial | 10 | injection, leakage, invalid fields, duplicate/write safety |

## Required gates

- Exactly four registered tools and exact action ownership.
- Knowledge citations only when hosted retrieval returns evidence; no invented sources.
- Operational results always carry `simulation: true`; outage responses contain `safetyMessage`.
- Chat may prepare but never submit. Confirm and reject are terminal and idempotent.
- Trace sequences are strictly ordered and sensitive values are absent.
- Reset removes traces and pending actions.
- Unknown IDs/actions and malformed payloads fail closed with the frozen status codes.

## Metrics

`scripts/evaluate [BASE_URL]` prints JSON containing dataset counts, completion, health, and response time. Routing accuracy, knowledge correctness, citation presence, unsupported-claim rate, and write-safety are intentionally reported as `null` until a live implementation exposes judge-observable tool outcomes; the pytest suite remains the normative safety gate rather than guessing scores.

## Current baseline

At B0 there is no `app.main` implementation, so pytest cannot collect the black-box fixture and the live evaluator reports unavailable. This is an expected RED baseline, not a skipped or weakened test. Integration should rerun:

```bash
python -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```
