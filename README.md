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

## Final hardened release evidence

The lead-supplied final run used the reassigned **OpenAI Terra** model. Full `pytest` completed with **130 passed** and **4 deprecation warnings**. The live evaluator at `127.0.0.1:8010` scored all **90 dataset cases plus health** as follows:

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

`citationPresence` of `0.025` is the one `mustCite=false` negative control; it is **not** evidence of grounded citations. The repository intentionally ships no authoritative PEA source documents under `knowledge/source`; unsourced sample facts were removed.

Operational systems (OMS, Sabuy, and VOC) remain visibly **SIMULATED**. No secrets are recorded here.

**Release status: NOT READY.** Release requires both: (a) lead-approved authoritative PEA documents synced to a real Gemini File Search store with credentials and a live run that passes citations; and (b) if the competition requires a live judge provider rather than the deterministic `DemoLLMAdapter`, that provider's `LLMAdapter` must be supplied and connected. The code provides only the provider-agnostic `JudgeLLMClient` seam. Do not treat unavailable external integration as passed.

See [`docs/integration_report.md`](docs/integration_report.md) for the integration evidence and release gate.
