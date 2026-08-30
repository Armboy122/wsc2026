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

## Final hardened release evidence

The lead-supplied final evidence used the reassigned **OpenAI Terra** model. Full `pytest` completed with **129 passed** and **4 deprecation warnings**. The live evaluator at `127.0.0.1:8010` evaluated all **90 dataset cases plus health**:

| Check | Result |
|---|---:|
| `routingAccuracy` | 1.0 |
| `writeSafety` | 1.0 |
| `scenarioCompletion` | 1.0 |
| `completion` | 1.0 |
| `unsupportedClaimRate` | 0.0 |
| Mean response time | 0.95 ms |
| P95 response time | 1.34 ms |
| Maximum response time | 7.93 ms |
| `knowledgeCorrectness` | 0.0 |
| `citationPresence` | 0.025 |
| Health | degraded: knowledge unavailable |

The `citationPresence` value of `0.025` is the single `mustCite=false` negative control. It does **not** evidence grounded citations. `knowledgeCorrectness` remains `0.0` and health is degraded because knowledge is unavailable.

The repository intentionally ships no authoritative PEA source documents under `knowledge/source`; unsourced sample facts were removed. OMS, Sabuy, and VOC remain visibly **SIMULATED**. No secret values are recorded in this report.

## Release gate

**Release status: NOT READY.** The operational and write-safety scores do not demonstrate a successful external knowledge integration, and unavailable external integration is not reported as passed. Release requires both of the following:

1. Lead-approved authoritative PEA documents must be synced to a real Gemini File Search store with credentials, followed by a live run that passes citations.
2. If the competition requires a live judge provider rather than the deterministic `DemoLLMAdapter`, that provider's `LLMAdapter` must be supplied and connected. The code includes only the provider-agnostic `JudgeLLMClient` seam.

No simulated or fabricated citation result may satisfy either gate.

## Current integrated truth

`app.main` is present and composes one Main Agent with exactly four registered tools. The deterministic demo adapter is available offline; Gemini readiness may be degraded when credentials/configuration are absent, which is an explicit environment state rather than a fake knowledge success.

Evaluation repair traceability: commit `07419b1` is preserved. OpenAI Luna omitted the mandatory `[model=...]` tag on repair commits `07419b1` and `f41b5e1`, meeting the reassignment threshold; ownership is reassigned to OpenAI Terra. Commit `f41b5e1` contains the fixture-ID test repair implemented by OpenAI Luna, but its message omitted the mandatory model tag.
