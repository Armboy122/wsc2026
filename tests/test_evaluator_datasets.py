"""ตรวจชุดข้อมูลที่ evaluator ของ runtime สองเครื่องมือเปิดใช้จริง"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = ROOT / "evaluation" / "datasets"
ACTIVE_DATASETS = (
    "knowledge.jsonl",
    "oms.jsonl",
    "multi_tool.jsonl",
    "adversarial.jsonl",
)


def rows(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (DATA / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_active_dataset_counts_and_tool_scope() -> None:
    assert {name: len(rows(name)) for name in ACTIVE_DATASETS} == {
        "knowledge.jsonl": 40,
        "oms.jsonl": 10,
        "multi_tool.jsonl": 10,
        "adversarial.jsonl": 10,
    }
    text = "\n".join((DATA / name).read_text(encoding="utf-8") for name in ACTIVE_DATASETS)
    assert not re.search(
        r"(?i)sabuy|voc_tool|prepare_payment|prepare_case|list_categories|get_case|paymentMethod",
        text,
    )
    assert not re.search(r"(?<![A-Za-z0-9])(?:BKK-01|CNX-02|HKT-03)(?![A-Za-z0-9])", text)
    assert "voc.jsonl" not in ACTIVE_DATASETS


def test_evaluator_uses_explicit_active_allowlist() -> None:
    source = (ROOT / "scripts" / "evaluate").read_text(encoding="utf-8")
    assert "ACTIVE_DATASETS" in source
    assert 'DATA.glob("*.jsonl")' not in source


def test_active_oms_rows_use_current_semantic_actions_and_inputs() -> None:
    allowed = {
        "get_outage_by_ca",
        "prepare_outage_with_ca",
        "prepare_anonymous_outage",
        "search",
    }
    for name in ("oms.jsonl", "multi_tool.jsonl"):
        for row in rows(name):
            actions = [row["expectedAction"]] if row.get("expectedAction") else row.get("expectedActions", [])
            assert actions and set(actions) <= allowed
            query = row["query"]
            if "get_outage_by_ca" in actions:
                assert re.search(r"(?<![A-Za-z0-9])[0-9]{12}(?![A-Za-z0-9])", query)
            if "prepare_anonymous_outage" in actions:
                assert all(label in query for label in ("description:", "location:", "contactPhone:"))
            if "prepare_outage_with_ca" in actions:
                assert "description:" in query
