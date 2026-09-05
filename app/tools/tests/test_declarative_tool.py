"""ทดสอบ DeclarativeTool แบบ end-to-end (schema validate → build request → executor) — D2.6

🔒 security boundary: ต้องผ่านนโยบายเครือข่ายของ D1.3 เหมือนเครื่องมือปฏิบัติการอื่นทุกประการ
ไม่มีทางลัดเฉพาะเพราะมาจาก DB
"""

from __future__ import annotations

import asyncio
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
