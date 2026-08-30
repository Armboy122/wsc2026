# PEA One Agent QA integration report

## Scope

AI-06 owns the black-box frozen-contract checks in `tests/test_mvp_evaluation.py`, deterministic datasets, `scripts/evaluate`, and this report. Production modules and frozen contracts are read-only. Tests exercise public HTTP routes and preserve write-safety policy.

## Reproducible setup and run

From the repository root, install the development and hosted-knowledge extras, enter Gemini settings without displaying them, then start the application and open its UI:

```bash
python3 -m pip install -e ".[dev,knowledge]"
read -rsp "Gemini API key: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
read -rp "Gemini File Search store: " GEMINI_FILE_SEARCH_STORE; export GEMINI_FILE_SEARCH_STORE
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

In another terminal:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

`GEMINI_API_KEY` and `GEMINI_FILE_SEARCH_STORE` are required for hosted Gemini File Search. Gemini is fail-closed: missing or unavailable configuration leaves health degraded and must not become a successful knowledge result. OMS, Sabuy, and VOC are **SIMULATED** throughout the demo.

## Dataset inventory

| Dataset | Cases | Coverage |
|---|---:|---|
| Knowledge | 40 | retrieval, citations, no-evidence behavior |
| OMS | 10 | status, safety-first outage reporting with explicit location/symptoms (**SIMULATED**) |
| Sabuy | 10 | fixture account reads and payment preparation (**SIMULATED**) |
| VOC | 10 | categories and case preparation with explicit subject/detail (**SIMULATED**) |
| Multi-tool | 10 | bounded multi-action orchestration |
| Adversarial | 10 | injection, leakage, invalid fields, duplicate/write safety |

All operational identifiers are exact demo fixtures: `PEA-1001` through `PEA-1003`, and `BKK-01`, `CNX-02`, `HKT-03`. The suite retains 40/10/10/10/10/10 cases.

## Gates and scoring

The evaluator resets demo state before and after scoring, consumes only public HTTP envelopes, handles HTTP/non-JSON/network failures without crashing, and prints numeric `routingAccuracy`, `knowledgeCorrectness`, `citationPresence`, `unsupportedClaimRate`, `writeSafety`, `scenarioCompletion`, and response-time statistics. `unsupportedClaimRate` is a violation rate (lower is better). Missing Gemini configuration is reported in `notes` and knowledge results are not treated as successful.

The pytest suite additionally proves envelope validation, simulation markers, no chat submission, idempotent confirmation, terminal rejection, trace ordering/redaction, reset, and malformed action failures. The outage journey uses a valid explicit prepare request and asserts a real pending action before rejection.

## Latest lead-supplied live evidence

| Check | Result |
|---|---:|
| Actual model | OpenAI Terra |
| `pytest` | 107 passed |
| `routingAccuracy` | 1.0 |
| `writeSafety` | 1.0 |
| `scenarioCompletion` | 1.0 |
| `unsupportedClaimRate` | 0.0 |
| `knowledgeCorrectness` | 0.0 |
| `citationPresence` | 0.025 |
| Health | degraded because Gemini configuration is absent |

The operational and write-safety results above do not demonstrate grounded hosted knowledge. **Release status: NOT READY.** Release requires a real Gemini File Search store/credential run that produces grounded citations. No simulated or fabricated citation result may satisfy this gate.

## Current integrated truth

`app.main` is present and composes one Main Agent with exactly four registered tools. The deterministic demo adapter is available offline; Gemini readiness may be degraded when credentials/configuration are absent, which is an explicit environment state rather than a fake knowledge success.

Evaluation repair traceability: commit `07419b1` is preserved. OpenAI Luna omitted the mandatory `[model=...]` tag on repair commits `07419b1` and `f41b5e1`, meeting the reassignment threshold; ownership is reassigned to OpenAI Terra. Commit `f41b5e1` contains the fixture-ID test repair implemented by OpenAI Luna, but its message omitted the mandatory model tag.
