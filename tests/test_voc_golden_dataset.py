"""golden set VOC ต้อง route ถูกต้องแบบ deterministic ผ่านตัววางแผนเดโม

ทดสอบอ่าน ``evaluation/datasets/voc.jsonl`` แล้วส่งทุกแถวเข้าแอปจริงที่ใช้
``MAIN_LLM_PROVIDER=demo`` เพื่อล็อกพฤติกรรมการเลือก action ของ voc_tool
(รวมถึง write safety ที่ห้าม submit ผ่านแชต) โดยไม่ติดต่อ provider จริง
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
ROWS = [
    json.loads(line)
    for line in (ROOT / "evaluation" / "datasets" / "voc.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MAIN_LLM_PROVIDER", "demo")
    from app.main import app  # type: ignore[import-not-found]

    return TestClient(app)


@pytest.mark.parametrize("row", ROWS, ids=[row["id"] for row in ROWS])
def test_golden_voc_row_routes_to_expected_action(client: TestClient, row: dict) -> None:
    response = client.post("/api/v1/chat", json={"message": row["query"]})
    assert response.status_code == 200
    body = response.json()
    observed = [result["action"] for result in body["toolResults"]]

    assert row["expectedAction"] in observed
    assert all(result["simulation"] is True for result in body["toolResults"] if result["name"] == "voc_tool")

    if row["expectedAction"] == "prepare_case":
        pending = body["pendingAction"]
        assert pending is not None
        assert pending["status"] == "pending_confirmation"
        assert pending["prepareAction"] == "prepare_case"
        assert pending["submitAction"] == "submit_case"
        assert all(action != "submit_case" for action in observed)

    if row.get("risk") == "write_without_confirm":
        assert all(not action.startswith("submit_") for action in observed)
