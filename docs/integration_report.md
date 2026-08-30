# PEA One Agent QA integration report

## Scope

AI-06 owns the black-box frozen-contract checks in `tests/test_mvp_evaluation.py`, deterministic datasets, `scripts/evaluate`, and this report. Production modules and frozen contracts are read-only. Tests exercise public HTTP routes and preserve write-safety policy.

## Dataset inventory

| Dataset | Cases | Coverage |
|---|---:|---|
| Knowledge | 40 | retrieval, citations, no-evidence behavior |
| OMS | 10 | status, safety-first outage reporting with explicit location/symptoms |
| Sabuy | 10 | fixture account reads and payment preparation |
| VOC | 10 | categories and case preparation with explicit subject/detail |
| Multi-tool | 10 | bounded multi-action orchestration |
| Adversarial | 10 | injection, leakage, invalid fields, duplicate/write safety |

All operational identifiers are exact demo fixtures: `PEA-1001` through `PEA-1003`, and `BKK-01`, `CNX-02`, `HKT-03`. The suite retains 40/10/10/10/10/10 cases.

## Gates and scoring

The evaluator resets demo state before and after scoring, consumes only public HTTP envelopes, handles HTTP/non-JSON/network failures without crashing, and prints numeric `routingAccuracy`, `knowledgeCorrectness`, `citationPresence`, `unsupportedClaimRate`, `writeSafety`, `scenarioCompletion`, and response-time statistics. `unsupportedClaimRate` is a violation rate (lower is better). Missing Gemini configuration is reported in `notes` and knowledge results are not treated as successful.

The pytest suite additionally proves envelope validation, simulation markers, no chat submission, idempotent confirmation, terminal rejection, trace ordering/redaction, reset, and malformed action failures. The outage journey uses a valid explicit prepare request and asserts a real pending action before rejection.

## Current integrated truth

`app.main` is present and composes one Main Agent with exactly four registered tools. The deterministic demo adapter is available offline; Gemini readiness may be degraded when credentials/configuration are absent, which is an explicit environment state rather than a fake knowledge success.

Evaluation repair traceability: commit `07419b1` is preserved. OpenAI Luna omitted the mandatory `[model=...]` tag on repair commits `07419b1` and `f41b5e1`, meeting the reassignment threshold; ownership is reassigned to OpenAI Terra. Commit `f41b5e1` contains the fixture-ID test repair implemented by OpenAI Luna, but its message omitted the mandatory model tag.

Run from the repository root:

```bash
python3 -m pytest -q
python3 -m py_compile scripts/evaluate tests/test_mvp_evaluation.py
./scripts/evaluate http://127.0.0.1:8000
```
