# PEA One Agent MVP

## QA and evaluation

The frozen-contract QA suite is in `tests/test_mvp_evaluation.py`. It covers route envelopes and validation, exact tool behavior, hosted knowledge evidence/citations, simulated operational facts, prepare/confirm/reject state transitions, idempotent writes, trace ordering and redaction, reset, multi-tool safety, and adversarial prompts.

Deterministic target datasets live under `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10). Run the live scoring entry point with:

```bash
./scripts/evaluate http://127.0.0.1:8000
```

Run contract checks with:

```bash
python -m pytest -q
```

See [`docs/integration_report.md`](docs/integration_report.md) for gates and expected B0 baseline behavior. All OMS, Sabuy, and VOC data must remain visibly simulated; chat text is never confirmation.
