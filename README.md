# PEA One Agent MVP

## Setup, run, and QA

From the repository root, install the development and hosted-knowledge extras, provide the Gemini settings without echoing their values, start the API, and open the UI:

```bash
python3 -m pip install -e ".[dev,knowledge]"
read -rsp "Gemini API key: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
read -rp "Gemini File Search store: " GEMINI_FILE_SEARCH_STORE; export GEMINI_FILE_SEARCH_STORE
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

In a second terminal, run the frozen-contract suite and public-envelope evaluator:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

The frozen-contract QA suite is in `tests/test_mvp_evaluation.py`. It covers route envelopes and validation, exact tool behavior, hosted knowledge evidence/citations, simulated operational facts, prepare/confirm/reject state transitions, idempotent writes, trace ordering and redaction, reset, multi-tool safety, and adversarial prompts.

Deterministic target datasets live under `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10). They use only the frozen demo fixtures (`PEA-1001`..`PEA-1003`, `BKK-01`, `CNX-02`, `HKT-03`); prepare prompts include explicit user details.

OMS, Sabuy, and VOC are **SIMULATED**. Gemini File Search is the hosted knowledge provider and is fail-closed: absent or unavailable Gemini configuration must be reported as degraded, never as grounded knowledge success. Chat text is never confirmation.

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
| Health | degraded: Gemini configuration absent |

**Release status: NOT READY.** A real Gemini File Search store and credential run must produce grounded citations before release. Do not substitute simulated or fabricated citation success.

See [`docs/integration_report.md`](docs/integration_report.md) for the integration evidence and release gate.
