"""ทดสอบ OMS REST ด้วย MockTransport โดยไม่เรียกปลายทางจริง"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx

from app.contracts import ToolAction, ToolCall, ToolErrorCode, ToolName, ToolResultStatus
from app.tools.oms_tool import OmsTool


def _call(action: ToolAction, input_data: dict) -> ToolCall:
    return ToolCall(call_id=uuid4(), name=ToolName.OMS, action=action, input=input_data)


def _tool(handler: httpx.MockTransport, *, base_url: str = "http://oms.test/api/v1", api_key: str | None = None) -> OmsTool:
    """สร้างเครื่องมือด้วยราก direct contract เพื่อไม่ใช้ค่า gateway production"""
    return OmsTool(base_url=base_url, api_key=api_key, transport=handler)


def test_get_exact_200_and_prepare_does_not_post() -> None:
    requests: list[httpx.Request] = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"caNumber": "100000000003", "customerFound": True, "network": {"meterId": "M", "transformerId": "T", "feederId": "F"}, "activeEvent": None, "recommendedAction": "CREATE_METER_EVENT"})
    tool = _tool(httpx.MockTransport(handler))
    got = asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "100000000003"})))
    prepared = asyncio.run(tool.execute(_call(ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, {"caNumber": "100000000003", "description": "ไฟดับ", "idempotencyKey": "k"})))
    assert got.status is ToolResultStatus.SUCCESS
    assert prepared.status is ToolResultStatus.SUCCESS
    assert [request.method for request in requests] == ["GET"]
    assert requests[0].url.path == "/api/v1/outages/by-ca/100000000003"
    assert requests[0].content == b""
    assert got.simulation is True
    tool.close()


def test_get_accepts_real_gateway_active_event_with_location() -> None:
    """Regression: gateway จริงส่ง activeEvent.location (GeoPoint) กลับมา ซึ่งเคยทำให้ output validation ล้มเหลว"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "caNumber": "020027219860",
                "customerFound": True,
                "network": {"meterId": "6602846772", "transformerId": "LNTW0329", "feederId": "LNTW-FDR"},
                "activeEvent": {
                    "eventId": "OMS-TR-0001",
                    "level": "TRANSFORMER",
                    "status": "IN_PROGRESS",
                    "message": "พบเหตุไฟฟ้าขัดข้องที่หม้อแปลงซึ่งจ่ายไฟให้ผู้ใช้ไฟรายนี้",
                    "startedAt": "2026-09-01T12:04:36.969150+07:00",
                    "estimatedRestoreAt": None,
                    "location": {"lat": 6.41051256, "lon": 101.8209484, "gisType": "POINT"},
                },
                "recommendedAction": "INFORM_EXISTING_EVENT",
            },
        )
    tool = _tool(httpx.MockTransport(handler))
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "020027219860"})))
    assert result.status is ToolResultStatus.SUCCESS
    assert result.data["activeEvent"]["location"] == {"lat": 6.41051256, "lon": 101.8209484, "gisType": "POINT"}
    tool.close()


def test_submit_maps_exact_201_and_reset_clears_local_draft() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/api/v1/outages"
        assert json.loads(request.content) == {"caNumber": "100000000003", "description": "ไฟดับ", "contactPhone": None, "locationNote": None}
        assert "idempotencyKey" not in request.content.decode() and not any("idempotency" in name.casefold() for name in request.headers)
        return httpx.Response(201, json={"eventId": "OMS-METER-1", "caNumber": "100000000003", "level": "METER", "status": "RECEIVED", "message": "รับแจ้งแล้ว", "location": {"lat": 6.42, "lon": 101.8, "gisType": "POINT"}})
    tool = _tool(httpx.MockTransport(handler))
    asyncio.run(tool.execute(_call(ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, {"caNumber": "100000000003", "description": "ไฟดับ", "idempotencyKey": "k"})))
    submitted = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, {"pendingActionId": str(uuid4()), "idempotencyKey": "k"})))
    assert submitted.status is ToolResultStatus.SUCCESS
    assert submitted.data["eventId"] == "OMS-METER-1"
    assert submitted.data["location"] == {"lat": 6.42, "lon": 101.8, "gisType": "POINT"}
    tool.reset()
    missing = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, {"pendingActionId": str(uuid4()), "idempotencyKey": "k"})))
    assert missing.error.code is ToolErrorCode.NOT_FOUND
    tool.close()


def test_safe_http_errors_and_request_error_normalize() -> None:
    for status, code in ((400, ToolErrorCode.INVALID_INPUT), (404, ToolErrorCode.NOT_FOUND), (503, ToolErrorCode.UNAVAILABLE), (418, ToolErrorCode.UNAVAILABLE)):
        tool = _tool(httpx.MockTransport(lambda request, status=status: httpx.Response(status, json={})))
        result = asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "100000000003"})))
        assert result.status is ToolResultStatus.ERROR
        assert result.error.code is code


def test_anonymous_post_wire_and_submit_conflict() -> None:
    requests: list[httpx.Request] = []
    tool = _tool(httpx.MockTransport(lambda request: (requests.append(request), httpx.Response(409, json={}))[1]))
    asyncio.run(tool.execute(_call(ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE, {"description": "ไฟดับ", "location": "บ้าน", "contactPhone": "0812345678", "idempotencyKey": "k"})))
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE, {"pendingActionId": str(uuid4()), "idempotencyKey": "k"})))
    assert result.error.code is ToolErrorCode.CONFLICT
    assert requests[0].method == "POST" and requests[0].url.path == "/api/v1/outages/anonymous"
    assert json.loads(requests[0].content) == {"description": "ไฟดับ", "location": "บ้าน", "contactPhone": "0812345678"}
    assert "idempotencyKey" not in requests[0].content.decode() and "idempotency" not in requests[0].headers
    tool.close()


def test_request_errors_and_invalid_successes_are_safe() -> None:
    for error in (httpx.ReadTimeout("timeout"), httpx.ConnectError("offline")):
        tool = _tool(httpx.MockTransport(lambda request, error=error: (_ for _ in ()).throw(error)))
        assert asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "100000000003"}))).error.code is ToolErrorCode.UNAVAILABLE
    for response in (httpx.Response(200, content=b"bad"), httpx.Response(200, json={"caNumber": "100000000003"})):
        tool = _tool(httpx.MockTransport(lambda request, response=response: response))
        assert asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "100000000003"}))).error.code is ToolErrorCode.INTERNAL


def test_gateway_root_sends_api_key_and_resolves_gateway_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"caNumber": "100000000003", "customerFound": True, "network": {"meterId": "M", "transformerId": "T", "feederId": "F"}, "activeEvent": None, "recommendedAction": "CREATE_METER_EVENT"})

    tool = _tool(httpx.MockTransport(handler), base_url="http://oms.test/api/v1/oms", api_key="demo-key")
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_GET_OUTAGE_BY_CA, {"caNumber": "100000000003"})))
    assert result.status is ToolResultStatus.SUCCESS
    assert seen[0].url.path == "/api/v1/oms/outages/by-ca/100000000003"
    assert dict(seen[0].headers)["x-api-key"] == "demo-key"
    tool.close()


def test_submit_post_requires_201() -> None:
    tool = _tool(httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    asyncio.run(tool.execute(_call(ToolAction.OMS_PREPARE_OUTAGE_WITH_CA, {"caNumber": "100000000003", "description": "ไฟดับ", "idempotencyKey": "k"})))
    result = asyncio.run(tool.execute(_call(ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, {"pendingActionId": str(uuid4()), "idempotencyKey": "k"})))
    assert result.error.code is ToolErrorCode.UNAVAILABLE
