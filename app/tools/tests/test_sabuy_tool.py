"""Tests for the simulated Sabuy tool (sabuy_tool)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.backends.simulated_sabuy import SimulatedSabuyBackend
from app.contracts import ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.sabuy_tool import SabuyTool


def _call(action: ToolAction, input_data: dict) -> ToolCall:
    return ToolCall(call_id=uuid4(), name=ToolName.SABUY, action=action, input=input_data)


def test_execute_account_summary_success_is_simulated():
    tool = SabuyTool(backend=SimulatedSabuyBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.SABUY_ACCOUNT_SUMMARY, {"accountRef": "PEA-1001"})))
    assert result.status is ToolResultStatus.SUCCESS
    assert result.simulation is True
    assert result.error is None
    assert result.data["accountRef"] == "PEA-1001"
    assert result.data["customerDisplayName"] == "Somchai Jaidee"


def test_execute_unknown_account_returns_not_found_error():
    tool = SabuyTool(backend=SimulatedSabuyBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.SABUY_ACCOUNT_SUMMARY, {"accountRef": "NOPE"})))
    assert result.status is ToolResultStatus.ERROR
    assert result.simulation is True
    assert result.data is None
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_execute_invalid_input_returns_invalid_input_error():
    tool = SabuyTool(backend=SimulatedSabuyBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.SABUY_ACCOUNT_SUMMARY, {"accountRef": ""})))
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_execute_prepare_then_submit_deduplicates():
    backend = SimulatedSabuyBackend()
    tool = SabuyTool(backend=backend)
    prep = _call(
        ToolAction.SABUY_PREPARE_PAYMENT,
        {
            "accountRef": "PEA-1001",
            "amountThb": "100.00",
            "paymentMethod": "demo_card",
            "idempotencyKey": "k1",
        },
    )
    prepared = asyncio.run(tool.execute(prep))
    assert prepared.status is ToolResultStatus.SUCCESS
    assert prepared.data["summary"]

    sub_input = {"pendingActionId": str(uuid4()), "idempotencyKey": "k1"}
    first = asyncio.run(tool.execute(_call(ToolAction.SABUY_SUBMIT_PAYMENT, sub_input)))
    assert first.status is ToolResultStatus.SUCCESS
    assert first.data["status"] == "accepted"

    second = asyncio.run(tool.execute(_call(ToolAction.SABUY_SUBMIT_PAYMENT, sub_input)))
    assert second.status is ToolResultStatus.SUCCESS
    assert second.data == first.data
    assert len(backend._receipts) == 1


def test_execute_submit_without_prepare_returns_not_found():
    tool = SabuyTool(backend=SimulatedSabuyBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.SABUY_SUBMIT_PAYMENT,
                {"pendingActionId": str(uuid4()), "idempotencyKey": "nope"},
            )
        )
    )
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_execute_rejects_call_for_another_tool():
    tool = SabuyTool(backend=SimulatedSabuyBackend())
    foreign = ToolCall(
        call_id=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_LIST_CATEGORIES,
        input={},
    )
    result = asyncio.run(tool.execute(foreign))
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT
