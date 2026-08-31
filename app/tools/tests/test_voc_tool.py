"""ทดสอบเครื่องมือ VOC จำลอง (voc_tool)"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.backends.simulated_voc import SimulatedVocBackend
from app.contracts import ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.voc_tool import VocTool


def _call(action: ToolAction, input_data: dict) -> ToolCall:
    return ToolCall(call_id=uuid4(), name=ToolName.VOC, action=action, input=input_data)


def _prepare_input(**overrides: object) -> dict:
    base = {
        "category": "service",
        "subject": "บริการล่าช้า",
        "detail": "รอเจ้าหน้าที่ติดต่อกลับมาเจ็ดวันแล้ว",
        "contactName": "สมชาย ใจดี",
        "contactPhone": "0812345678",
        "location": "ถนนสุขุมวิท กรุงเทพฯ",
        "contactChannel": "phone",
        "idempotencyKey": "k1",
    }
    base.update(overrides)
    return base


def test_execute_list_categories_success_is_simulated():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.VOC_LIST_CATEGORIES, {})))
    assert result.status is ToolResultStatus.SUCCESS
    assert result.simulation is True
    assert [c["code"] for c in result.data["categories"]] == ["power_quality", "service", "compliment", "tip_off", "operations", "stakeholder_feedback"]


def test_execute_invalid_category_returns_invalid_input():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.VOC_PREPARE_CASE,
                _prepare_input(category="not_a_category"),
            )
        )
    )
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_execute_missing_contact_fields_returns_invalid_input():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.VOC_PREPARE_CASE,
                {
                    "category": "service",
                    "subject": "x",
                    "detail": "y",
                    "contactChannel": "email",
                    "idempotencyKey": "k1",
                },
            )
        )
    )
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_execute_prepare_then_submit_deduplicates():
    backend = SimulatedVocBackend()
    tool = VocTool(backend=backend)
    prep = _call(ToolAction.VOC_PREPARE_CASE, _prepare_input(category="tip_off"))
    prepared = asyncio.run(tool.execute(prep))
    assert prepared.status is ToolResultStatus.SUCCESS
    assert prepared.data["category"] == "tip_off"

    sub_input = {"pendingActionId": str(uuid4()), "idempotencyKey": "k1"}
    first = asyncio.run(tool.execute(_call(ToolAction.VOC_SUBMIT_CASE, sub_input)))
    assert first.status is ToolResultStatus.SUCCESS
    assert first.data["status"] == "submitted"
    assert first.data["vocId"]
    assert first.data["trackingKey"]

    second = asyncio.run(tool.execute(_call(ToolAction.VOC_SUBMIT_CASE, sub_input)))
    assert second.data == first.data
    assert len(backend._cases) == 1


def test_execute_submit_without_prepare_returns_not_found():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.VOC_SUBMIT_CASE,
                {"pendingActionId": str(uuid4()), "idempotencyKey": "nope"},
            )
        )
    )
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_execute_get_case_success_and_wrong_key():
    backend = SimulatedVocBackend()
    tool = VocTool(backend=backend)
    asyncio.run(tool.execute(_call(ToolAction.VOC_PREPARE_CASE, _prepare_input())))
    submitted = asyncio.run(tool.execute(_call(ToolAction.VOC_SUBMIT_CASE, {"pendingActionId": str(uuid4()), "idempotencyKey": "k1"})))
    assert submitted.status is ToolResultStatus.SUCCESS

    ok = asyncio.run(
        tool.execute(
            _call(ToolAction.VOC_GET_CASE, {
                "vocId": submitted.data["vocId"],
                "trackingKey": submitted.data["trackingKey"],
            })
        )
    )
    assert ok.status is ToolResultStatus.SUCCESS
    assert ok.simulation is True
    assert ok.data["status"] == "submitted"
    assert ok.data["vocId"] == submitted.data["vocId"]

    bad = asyncio.run(
        tool.execute(
            _call(ToolAction.VOC_GET_CASE, {
                "vocId": submitted.data["vocId"],
                "trackingKey": "wrong-key",
            })
        )
    )
    assert bad.status is ToolResultStatus.ERROR
    assert bad.error.code is ToolErrorCode.NOT_FOUND
