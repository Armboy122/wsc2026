"""ทดสอบ DeclarativeTool แบบ end-to-end (schema validate → build request → executor) — D2.6

🔒 security boundary: ต้องผ่านนโยบายเครือข่ายของ D1.3 เหมือนเครื่องมือปฏิบัติการอื่นทุกประการ
ไม่มีทางลัดเฉพาะเพราะมาจาก DB
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest

from app.agent.tool_shape import ToolOperationShape, ToolShape
from app.contracts import ToolCall, ToolErrorCode, ToolResultStatus
from app.tools.declarative_executor import DeclarativeToolExecutor
from app.tools.declarative_tool import DeclarativeTool

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"maxLength": {"type": "integer"}},
    "required": [],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"fact": {"type": "string"}, "length": {"type": "integer"}},
    "required": ["fact"],
    "additionalProperties": False,
}


def _shape(*, http_method: str | None = "GET", url_template: str | None = "https://catfact.ninja/fact") -> ToolShape:
    return ToolShape(
        slug="cat_fact_tool",
        display_name="สุ่มข้อเท็จจริงเกี่ยวกับแมว",
        description="ดึงข้อเท็จจริงเกี่ยวกับแมวแบบสุ่มจากบริการสาธารณะ",
        operations=(
            ToolOperationShape(
                action="get_random_fact",
                description="สุ่มข้อเท็จจริงหนึ่งเรื่อง",
                input_schema=_INPUT_SCHEMA,
                output_schema=_OUTPUT_SCHEMA,
                exposure="llm",
                mode="read",
                submit_action=None,
                policy="plain_read",
                limits=None,
                client_context=None,
                http_method=http_method,
                url_template=url_template,
            ),
        ),
        executor=None,
        source="db",
    )


def _tool(
    handler,
    *,
    app_env: str = "production",
    allowlist: tuple[str, ...] = ("catfact.ninja",),
    shape: ToolShape | None = None,
) -> DeclarativeTool:
    executor = DeclarativeToolExecutor(
        app_env=app_env,
        allowlist=allowlist,
        environ={},
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"],
    )
    return DeclarativeTool(shape or _shape(), executor)


def _call(action: str = "get_random_fact", input: dict | None = None) -> ToolCall:
    return ToolCall(call_id=uuid.uuid4(), name="cat_fact_tool", action=action, input=input or {})


def test_success_maps_response_to_tool_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "catfact.ninja"
        return httpx.Response(200, json={"fact": "Cats sleep a lot.", "length": 18})

    result = asyncio.run(_tool(handler).execute(_call()))

    assert result.status is ToolResultStatus.SUCCESS
    assert result.data == {"fact": "Cats sleep a lot.", "length": 18}
    assert result.simulation is True


def test_query_param_reaches_the_real_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["max_length"] = request.url.params.get("maxLength")
        return httpx.Response(200, json={"fact": "short", "length": 5})

    asyncio.run(_tool(handler).execute(_call(input={"maxLength": 20})))

    assert seen["max_length"] == "20"


def test_input_failing_schema_is_rejected_before_any_http_call():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"fact": "x"})

    result = asyncio.run(_tool(handler).execute(_call(input={"maxLength": "twenty"})))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert called is False


def test_output_not_matching_schema_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": "wrong shape"})

    result = asyncio.run(_tool(handler).execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INTERNAL


def test_unknown_action_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    result = asyncio.run(_tool(handler).execute(_call(action="not_a_real_action")))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_upstream_failure_maps_to_unavailable_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = asyncio.run(_tool(handler).execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.UNAVAILABLE


# ---------------------------------------------------------------------------
# 🔒 ไม่มีทางลัด — SSRF ของ D1.3 บังคับใช้กับ declarative tool เหมือนกันทุกประการ
# ---------------------------------------------------------------------------


def test_production_blocks_domain_not_in_allowlist_even_for_declarative_tool():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"fact": "x"})

    tool = _tool(handler, app_env="production", allowlist=())  # ไม่มี catfact.ninja ใน allowlist
    result = asyncio.run(tool.execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.UNAVAILABLE
    assert called is False


def test_operation_missing_url_template_is_rejected_not_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    tool = _tool(handler, shape=_shape(url_template=None))

    result = asyncio.run(tool.execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_rejects_tool_shape_from_code_source():
    shape = ToolShape(
        slug="x", display_name="x", description="x", operations=(), executor=object(), source="code"
    )
    with pytest.raises(ValueError):
        DeclarativeTool(shape, DeclarativeToolExecutor(app_env="development"))


# ---------------------------------------------------------------------------
# D2.7: write_confirm สองจังหวะ — mode=prepare ไม่ยิง HTTP, mode=submit ยิงจริงครั้งเดียว
# ---------------------------------------------------------------------------


def _write_confirm_shape(*, submit_url_template: str | None = "https://outage.test/reports") -> ToolShape:
    prepare_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "idempotencyKey": {"type": "string"},
        },
        "required": ["description", "idempotencyKey"],
        "additionalProperties": False,
    }
    submit_schema = {
        "type": "object",
        "properties": {
            "pendingActionId": {"type": "string"},
            "idempotencyKey": {"type": "string"},
        },
        "required": ["pendingActionId", "idempotencyKey"],
        "additionalProperties": False,
    }
    return ToolShape(
        slug="outage_tool",
        display_name="แจ้งเหตุ",
        description="แจ้งเหตุไฟฟ้าขัดข้อง",
        operations=(
            ToolOperationShape(
                action="prepare_report",
                description="เตรียมแจ้งเหตุ",
                input_schema=prepare_schema,
                output_schema=None,
                exposure="llm",
                mode="prepare",
                submit_action="submit_report",
                policy="write_confirm",
                limits=None,
                client_context=None,
                http_method=None,
                url_template=None,
            ),
            ToolOperationShape(
                action="submit_report",
                description="ส่งรายงาน",
                input_schema=submit_schema,
                output_schema=None,
                exposure="internal",
                mode="submit",
                submit_action=None,
                policy="write_confirm",
                limits=None,
                client_context=None,
                http_method="POST",
                url_template=submit_url_template,
            ),
        ),
        executor=None,
        source="db",
    )


def _write_confirm_tool(handler, *, shape: ToolShape | None = None) -> DeclarativeTool:
    executor = DeclarativeToolExecutor(
        app_env="production",
        allowlist=("outage.test",),
        environ={},
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"],
    )
    return DeclarativeTool(shape or _write_confirm_shape(), executor)


def test_prepare_mode_never_calls_http_and_caches_the_draft():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    tool = _write_confirm_tool(handler)
    call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="prepare_report",
        input={"description": "ไฟดับ", "idempotencyKey": "key-1"},
    )

    result = asyncio.run(tool.execute(call))

    assert result.status is ToolResultStatus.SUCCESS
    assert isinstance(result.data["summary"], str) and result.data["summary"]
    assert called is False


def test_submit_mode_sends_only_the_prepared_payload_not_idempotency_key():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"reportId": "R-1"})

    tool = _write_confirm_tool(handler)
    prepare_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="prepare_report",
        input={"description": "ไฟดับ", "idempotencyKey": "key-1"},
    )
    asyncio.run(tool.execute(prepare_call))

    submit_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="submit_report",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "key-1"},
    )
    result = asyncio.run(tool.execute(submit_call))

    assert result.status is ToolResultStatus.SUCCESS
    assert result.data == {"reportId": "R-1"}
    assert seen["body"] == {"description": "ไฟดับ"}


def test_submit_without_a_matching_prepared_draft_is_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={})

    tool = _write_confirm_tool(handler)
    submit_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="submit_report",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "missing"},
    )

    result = asyncio.run(tool.execute(submit_call))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_submit_is_not_replayable_once_the_draft_is_consumed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"reportId": "R-1"})

    tool = _write_confirm_tool(handler)
    asyncio.run(tool.execute(ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="prepare_report",
        input={"description": "ไฟดับ", "idempotencyKey": "key-1"},
    )))
    submit_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="submit_report",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "key-1"},
    )
    asyncio.run(tool.execute(submit_call))

    replay = asyncio.run(tool.execute(submit_call))

    assert replay.status is ToolResultStatus.ERROR
    assert replay.error.code is ToolErrorCode.NOT_FOUND


def test_reset_clears_drafts_that_were_never_submitted():
    tool = _write_confirm_tool(lambda request: httpx.Response(201, json={}))
    asyncio.run(tool.execute(ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="prepare_report",
        input={"description": "ไฟดับ", "idempotencyKey": "key-1"},
    )))

    tool.reset()

    submit_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="submit_report",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "key-1"},
    )
    result = asyncio.run(tool.execute(submit_call))
    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND


def test_submit_with_a_misconfigured_url_template_is_internal_error():
    tool = _write_confirm_tool(
        lambda request: httpx.Response(201, json={}), shape=_write_confirm_shape(submit_url_template=None)
    )
    asyncio.run(tool.execute(ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="prepare_report",
        input={"description": "ไฟดับ", "idempotencyKey": "key-1"},
    )))
    submit_call = ToolCall(
        call_id=uuid.uuid4(), name="outage_tool", action="submit_report",
        input={"pendingActionId": str(uuid.uuid4()), "idempotencyKey": "key-1"},
    )

    result = asyncio.run(tool.execute(submit_call))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.INTERNAL


# ---------------------------------------------------------------------------
# D2.7: HTTP status code แปลเป็น ToolErrorCode ที่จำเพาะขึ้น — ธรรมเนียม REST ทั่วไป
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, ToolErrorCode.INVALID_INPUT),
        (404, ToolErrorCode.NOT_FOUND),
        (409, ToolErrorCode.CONFLICT),
        (500, ToolErrorCode.UNAVAILABLE),
        (418, ToolErrorCode.UNAVAILABLE),
    ],
)
def test_upstream_status_code_maps_to_a_specific_error_code(status_code, expected_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={})

    result = asyncio.run(_tool(handler).execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is expected_code


def test_error_status_code_maps_correctly_even_when_the_body_is_not_a_json_object():
    """สถานะ error ต้องแปลถูกแม้ปลายทางไม่ตอบ JSON object กลับมา (เช่น 404 ตัวเปล่า หรือ
    text/html) — เช็ค status code ต้องมาก่อนเช็ครูปร่าง body เสมอ ไม่งั้นถูกกลืนเป็น
    unavailable ทั้งหมดซึ่งทำให้การแปล status code ของ D2.7 ไม่มีผลกับปลายทางจริงจำนวนมาก"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found", headers={"content-type": "text/plain"})

    result = asyncio.run(_tool(handler).execute(_call()))

    assert result.status is ToolResultStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_FOUND
