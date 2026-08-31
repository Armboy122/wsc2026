"""ทดสอบเครื่องมือ OMS จำลอง (oms_tool)"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.backends.simulated_oms import SimulatedOmsBackend
from app.contracts import ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.oms_tool import OmsTool


def _call(action: ToolAction, input_data: dict) -> ToolCall:
    return ToolCall(call_id=uuid4(), name=ToolName.OMS, action=action, input=input_data)


def test_execute_outage_status_includes_safety_message():
    tool = OmsTool(backend=SimulatedOmsBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_OUTAGE_STATUS, {"areaCode": "BKK-01"})))
    assert result.status is ToolResultStatus.SUCCESS
    assert result.simulation is True
    assert result.data["status"] == "normal"
    assert result.data["safetyMessage"]


def test_execute_unknown_area_returns_not_found():
    tool = OmsTool(backend=SimulatedOmsBackend())
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_OUTAGE_STATUS, {"areaCode": "NOPE"})))
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_execute_prepare_report_includes_safety_message():
    tool = OmsTool(backend=SimulatedOmsBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.OMS_PREPARE_OUTAGE_REPORT,
                {
                    "areaCode": "CNX-02",
                    "locationNote": "Market street",
                    "symptoms": "Power flickered then went out.",
                    "idempotencyKey": "k1",
                },
            )
        )
    )
    assert result.status is ToolResultStatus.SUCCESS
    assert result.data["areaCode"] == "CNX-02"
    assert result.data["safetyMessage"]


def test_execute_prepare_then_submit_deduplicates():
    backend = SimulatedOmsBackend()
    tool = OmsTool(backend=backend)
    prep = _call(
        ToolAction.OMS_PREPARE_OUTAGE_REPORT,
        {
            "areaCode": "HKT-03",
            "locationNote": "Near pier",
            "symptoms": "No power since morning.",
            "idempotencyKey": "k1",
        },
    )
    prepared = asyncio.run(tool.execute(prep))
    assert prepared.status is ToolResultStatus.SUCCESS

    sub_input = {"pendingActionId": str(uuid4()), "idempotencyKey": "k1"}
    first = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_OUTAGE_REPORT, sub_input)))
    assert first.status is ToolResultStatus.SUCCESS
    assert first.data["status"] == "submitted"

    second = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_OUTAGE_REPORT, sub_input)))
    assert second.data == first.data
    assert len(backend._reports) == 1


def test_execute_submit_without_prepare_returns_not_found():
    tool = OmsTool(backend=SimulatedOmsBackend())
    result = asyncio.run(
        tool.execute(
            _call(
                ToolAction.OMS_SUBMIT_OUTAGE_REPORT,
                {"pendingActionId": str(uuid4()), "idempotencyKey": "nope"},
            )
        )
    )
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND
