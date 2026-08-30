"""Tests for the simulated VOC tool (voc_tool)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.backends.simulated_voc import SimulatedVocBackend
from app.contracts import ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.voc_tool import VocTool


def _call(action: ToolAction, input_data: dict) -> ToolCall:
    return ToolCall(call_id=uuid4(), name=ToolName.VOC, action=action, input=input_data)


def test_execute_list_categories_success_is_simulated():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.VOC_LIST_CATEGORIES, {})))
    assert result.status is ToolResultStatus.SUCCESS
    assert result.simulation is True
    assert [c["code"] for c in result.data["categories"]] == ["billing", "service", "safety", "other"]


def test_execute_invalid_category_returns_invalid_input():
    tool = VocTool(backend=SimulatedVocBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.VOC_PREPARE_CASE,
                {
                    "category": "not_a_category",
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
    prep = _call(
        ToolAction.VOC_PREPARE_CASE,
        {
            "category": "safety",
            "subject": "Fallen line",
            "detail": "A power line is down.",
            "contactChannel": "phone",
            "idempotencyKey": "k1",
        },
    )
    prepared = asyncio.run(tool.execute(prep))
    assert prepared.status is ToolResultStatus.SUCCESS
    assert prepared.data["category"] == "safety"

    sub_input = {"pendingActionId": str(uuid4()), "idempotencyKey": "k1"}
    first = asyncio.run(tool.execute(_call(ToolAction.VOC_SUBMIT_CASE, sub_input)))
    assert first.status is ToolResultStatus.SUCCESS
    assert first.data["status"] == "submitted"

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
