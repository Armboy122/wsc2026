"""Evaluator fixture invariants owned by AI-06."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = ROOT / "evaluation" / "datasets"


def rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line.strip()]


def test_dataset_counts_and_fixture_identifiers() -> None:
    assert {name: len(rows(name)) for name in ("knowledge.jsonl", "oms.jsonl", "sabuy.jsonl", "voc.jsonl", "multi_tool.jsonl", "adversarial.jsonl")} == {
        "knowledge.jsonl": 40, "oms.jsonl": 10, "sabuy.jsonl": 10, "voc.jsonl": 10, "multi_tool.jsonl": 10, "adversarial.jsonl": 10,
    }
    text = "\n".join(p.read_text() for p in DATA.glob("*.jsonl"))
    assert not any(token in text for token in ("A-100", "A-101", "A-102", "A-103", "A-104", "PKN-03", "NMA-04"))
    assert all(account in text for account in ("PEA-1001", "PEA-1002", "PEA-1003"))
    assert all(area in text for area in ("BKK-01", "CNX-02", "HKT-03"))


def test_prepare_prompts_supply_required_user_details() -> None:
    for name in ("oms.jsonl", "voc.jsonl", "multi_tool.jsonl"):
        for row in rows(name):
            if row.get("expectedAction") == "prepare_outage_report" or "prepare_outage_report" in row.get("expectedActions", []):
                assert "location:" in row["query"] and "symptoms:" in row["query"]
            if row.get("expectedAction") == "prepare_case" or "prepare_case" in row.get("expectedActions", []):
                assert "subject:" in row["query"] and "detail:" in row["query"]
