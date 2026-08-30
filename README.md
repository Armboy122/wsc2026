# PEA One Agent MVP

## QA and evaluation

The frozen-contract QA suite is in `tests/test_mvp_evaluation.py`. It covers route envelopes and validation, exact tool behavior, hosted knowledge evidence/citations, simulated operational facts, prepare/confirm/reject state transitions, idempotent writes, trace ordering and redaction, reset, multi-tool safety, and adversarial prompts.

Deterministic target datasets live under `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10). They use only the frozen demo fixtures (`PEA-1001`..`PEA-1003`, `BKK-01`, `CNX-02`, `HKT-03`); prepare prompts include explicit user details.

Run the public-envelope scoring entry point with:

```bash
./scripts/evaluate http://127.0.0.1:8000
```

It resets demo state before and after, reports numeric routing/knowledge/citation/unsupported-claim/write-safety/completion metrics and response-time statistics, and explicitly reports missing Gemini configuration instead of fabricating knowledge success. Run contract checks with:

```bash
python3 -m pytest -q
python3 -m py_compile scripts/evaluate tests/test_mvp_evaluation.py
```

See [`docs/integration_report.md`](docs/integration_report.md) for current integration truth and gates. All OMS, Sabuy, and VOC data remain visibly simulated; chat text is never confirmation.
