"""ทดสอบผลลัพธ์ปุ่ม "ลองยิงดู" ให้ครบตามสเปก — D3.5 (T7)

ความเสี่ยงที่เทสนี้กันไว้:

- แผงผลลัพธ์ต้องเห็นครบ: HTTP method, final URL (หลัง render template), query string,
  JSON request body, status code, elapsed time และ response body
- response ที่ไม่ใช่ JSON ต้องแสดงเป็นข้อความแบบจำกัดขนาด (truncate พร้อมบอกว่าตัดแล้ว)
- secret จาก environment variable ต้องไม่โผล่ในผลลัพธ์ทุกช่อง (URL/query/body/response)
  แม้ปลายทาง echo Authorization กลับมา หรือ secret อยู่ในข้อความที่ถูก truncate
- ต้องยังยิงผ่าน DeclarativeToolExecutor เส้นทางเดิม — นโยบาย SSRF ยังบล็อกปลายทางต้องห้าม
- ห้ามส่ง request headers (ที่มี credential) กลับมาแสดงเด็ดขาด — fail-safe คือไม่ส่งเลย
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.registry import ToolRegistry
from app.api.admin import router as admin_router
from app.contracts import ToolCall, ToolName, ToolResult, ToolResultStatus
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings
from app.core.startup import create_platform_app
from app.core.tool_admin import ToolAdminService
from app.db import Database

_SECRET = "super-secret-token-9f2a"


class _KnowledgeStub:
    """registry บังคับว่าต้องมี Knowledge เสมอ — ตัวปลอมที่เบาที่สุดสำหรับเทส"""

    name = ToolName.KNOWLEDGE

    async def execute(self, call: ToolCall, context: Any = None) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.ERROR,
            simulation=False,
        )


def _settings(app_env: str) -> Settings:
    return Settings.from_env({"APP_ENV": app_env, "ADMIN_PASSWORD": "pw"})


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str = "development",
    transport: httpx.BaseTransport | None = None,
) -> TestClient:
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())
    db = Database(":memory:")
    db.migrate()
    service = ToolAdminService(
        db,
        settings=_settings(app_env),
        registry=ToolRegistry([_KnowledgeStub()]),
        transport=transport,
    )
    app = create_platform_app(_settings(app_env))
    app.state.tool_admin = service
    app.include_router(admin_router)
    client = TestClient(app)
    assert client.post("/api/v1/admin/login", json={"password": "pw"}).status_code == 200
    return client


def _try(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/admin/tools/try", json=payload)
    assert response.status_code == 200
    return response.json()


_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "q": {"type": "string"},
        "text": {"type": "string"},
        "token": {"type": "string"},
    },
    "required": [],
    "additionalProperties": False,
}


# ------------------------------------------------------- ความครบถ้วนของ request --


def test_try_get_shows_method_final_url_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET: ผลลัพธ์ต้องบอก method, final URL หลัง render template และ query string"""
    client = _make_client(monkeypatch, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})))
    body = _try(
        client,
        {
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/items/{id}",
            "input": {"id": "abc", "q": "แมว"},
            "inputSchema": _INPUT_SCHEMA,
        },
    )
    assert body["ok"] is True, body
    request = body["request"]
    assert request["method"] == "GET"
    # placeholder {id} ถูก render แล้ว — ไม่เหลือ {id} ใน URL
    assert request["url"] == "http://127.0.0.1:9999/items/abc"
    assert request["query"] == {"q": "แมว"}
    # GET ไม่มี body
    assert request.get("body") in (None, {})
    # response ครบทุกช่องตามสเปก
    assert body["response"]["statusCode"] == 200
    assert "elapsedMs" in body["response"]
    assert body["response"]["body"] == {"ok": True}


def test_try_post_shows_json_request_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST: ฟิลด์ที่เหลือจาก template ต้องแสดงเป็น JSON request body"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"received": json.loads(request.content)})

    client = _make_client(monkeypatch, transport=httpx.MockTransport(handler))
    body = _try(
        client,
        {
            "httpMethod": "POST",
            "urlTemplate": "http://127.0.0.1:9999/items",
            "input": {"text": "hello"},
            "inputSchema": _INPUT_SCHEMA,
        },
    )
    assert body["ok"] is True, body
    assert body["request"]["method"] == "POST"
    assert body["request"]["url"] == "http://127.0.0.1:9999/items"
    assert body["request"]["body"] == {"text": "hello"}
    assert body["response"]["statusCode"] == 201


# ------------------------------------------------ response ที่ไม่ใช่ JSON + truncate --

_TEXT_LIMIT = 2000


def test_try_non_json_response_shown_as_truncated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """response ไม่ใช่ JSON: แสดงเป็นข้อความ และถูก truncate พร้อม flag บอกว่าตัดแล้ว"""
    long_text = "A" * 5000
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=long_text, headers={"content-type": "text/plain"})
        ),
    )
    body = _try(
        client,
        {"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:9999/log"},
    )
    assert body["ok"] is True, body
    response = body["response"]
    assert response["isJson"] is False
    assert response["body"] is None
    assert response["text"] == "A" * _TEXT_LIMIT
    assert response["textTruncated"] is True

    # response สั้นกว่าเพดาน: แสดงเต็ม ไม่ตั้ง flag ตัด
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="สวัสดี", headers={"content-type": "text/plain"})
        ),
    )
    body = _try(client, {"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:9999/log"})
    assert body["response"]["text"] == "สวัสดี"
    assert not body["response"].get("textTruncated")


# ------------------------------------------------------------ secret redaction --


def _echo_all_transport() -> httpx.MockTransport:
    """ปลายทางจอมกวน: echo ทุกอย่างที่ได้รับ (URL, query, body, Authorization) กลับมา"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "url": str(request.url),
                "authorization": request.headers.get("authorization", ""),
                "query": {key: values[0] for key, values in request.url.params.multi_items()},
                "body": json.loads(request.content.decode("utf-8")) if request.content else None,
            },
        )

    return httpx.MockTransport(handler)


def test_try_redacts_secret_from_every_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """secret จาก env ห้ามโผล่ทุกช่อง: final URL, query, request body, response (รวม Authorization echo)

    และห้ามส่ง request headers กลับมาแสดงเด็ดขาด (fail-safe: ไม่ส่งเลย)
    """
    monkeypatch.setenv("ADMIN_TRY_SECRET", _SECRET)
    client = _make_client(monkeypatch, transport=_echo_all_transport())
    payload = {
        "urlTemplate": "http://127.0.0.1:9999/items/{token}",
        "input": {"token": _SECRET, "q": _SECRET, "text": _SECRET},
        "inputSchema": _INPUT_SCHEMA,
        "authEnvVar": "ADMIN_TRY_SECRET",
    }
    # GET: ฟิลด์ที่เหลือจาก template ไปเป็น query string
    get_body = _try(client, {"httpMethod": "GET", **payload})
    assert get_body["ok"] is True, get_body
    # ค่าจริงห้ามปรากฏที่ไหนใน response แม้แต่ตัวเดียว (เทียบ raw text ทั้งก้อน)
    assert _SECRET not in json.dumps(get_body)
    assert "[REDACTED]" in get_body["request"]["url"]
    assert get_body["request"]["query"] == {"q": "[REDACTED]", "text": "[REDACTED]"}
    assert get_body["response"]["body"]["authorization"] == "[REDACTED]"
    assert get_body["response"]["body"]["url"].count("[REDACTED]") >= 2
    # fail-safe: ไม่ส่ง request headers กลับมาแสดงเลย
    assert "headers" not in get_body["request"]

    # POST: ฟิลด์ที่เหลือจาก template ไปเป็น JSON request body
    post_body = _try(client, {"httpMethod": "POST", **payload})
    assert post_body["ok"] is True, post_body
    assert _SECRET not in json.dumps(post_body)
    assert post_body["request"]["body"] == {"q": "[REDACTED]", "text": "[REDACTED]"}
    assert post_body["response"]["body"]["authorization"] == "[REDACTED]"
    assert _SECRET not in post_body["response"]["body"]["body"]["text"]


def test_try_redacts_secret_before_truncating_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """secret ใน response ข้อความต้องถูก redact ก่อน truncate — การตัดต้องไม่เปิด secret ให้เห็น"""
    monkeypatch.setenv("ADMIN_TRY_SECRET", _SECRET)
    payload = "x" * 1500 + _SECRET + "y" * 1500
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=payload, headers={"content-type": "text/plain"})
        ),
    )
    body = _try(
        client,
        {
            "httpMethod": "GET",
            "urlTemplate": "http://127.0.0.1:9999/log",
            "authEnvVar": "ADMIN_TRY_SECRET",
        },
    )
    assert body["ok"] is True, body
    text = body["response"]["text"]
    assert len(text) == _TEXT_LIMIT
    assert body["response"]["textTruncated"] is True
    assert _SECRET not in text
    assert "[REDACTED]" in text


# --------------------------------------- ok:true ครอบคลุมทุก status code (A2) --
#
# พิสูจน์ก่อนแก้ (A2): backend คืน ok:true ทันทีที่ได้ HTTP response จริง โดยไม่ดู
# status code เลย (ดู app/core/tool_admin.py::_try_operation_raw บรรทัดคืนผลตอนท้าย)
# เทสกลุ่มนี้ยืนยันว่า statusCode จริงถูกส่งกลับให้ frontend แยก 2xx/4xx/5xx เอง (web/admin.js)


def test_try_reports_401_status_code_with_ok_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """upstream ตอบ 401: ยังเป็น ok:true (HTTP สำเร็จ) แต่ statusCode ต้องเป็น 401 จริง"""
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "unauthorized"})
        ),
    )
    body = _try(client, {"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:9999/secure"})
    assert body["ok"] is True, body
    assert body["response"]["statusCode"] == 401
    assert body["response"]["body"] == {"error": "unauthorized"}


def test_try_reports_500_status_code_with_ok_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """upstream ตอบ 500: ยังเป็น ok:true แต่ statusCode ต้องเป็น 500 จริง"""
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "boom"})
        ),
    )
    body = _try(client, {"httpMethod": "GET", "urlTemplate": "http://127.0.0.1:9999/broken"})
    assert body["ok"] is True, body
    assert body["response"]["statusCode"] == 500


def test_try_handles_204_empty_body_without_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """204/body ว่างต้องไม่ทำให้ try_operation ล้ม — isJson=False, body/text เป็นค่าว่างที่ปลอดภัย"""
    client = _make_client(
        monkeypatch,
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )
    body = _try(client, {"httpMethod": "DELETE", "urlTemplate": "http://127.0.0.1:9999/items/1"})
    assert body["ok"] is True, body
    assert body["response"]["statusCode"] == 204
    assert body["response"]["isJson"] is False
    assert body["response"]["body"] is None


def test_try_redirect_failure_reports_request_was_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect is returned by the upstream after the request has reached it."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1:9999/other"})

    body = _try(
        _make_client(monkeypatch, transport=httpx.MockTransport(handler)),
        {
            "httpMethod": "POST",
            "urlTemplate": "http://127.0.0.1:9999/side-effect",
            "input": {"value": "x"},
        },
    )

    assert len(captured) == 1
    assert body == {
        "ok": False,
        "reason": "redirect_blocked",
        "error": "ปลายทางพยายาม redirect — ระบบไม่ตามอัตโนมัติ กรุณาแก้ URL ให้ตรงปลายทางจริง",
    }


def test_try_response_size_failure_reports_request_was_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response-size guard trips while downloading a response to a sent request."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=b"x" * 2_000_000)

    body = _try(
        _make_client(monkeypatch, transport=httpx.MockTransport(handler)),
        {
            "httpMethod": "POST",
            "urlTemplate": "http://127.0.0.1:9999/side-effect",
            "input": {"value": "x"},
        },
    )

    assert len(captured) == 1
    assert body["ok"] is False
    assert body["reason"] == "response_too_large"


# --------------------------------------------------- SSRF policy ยังบล็อกเสมอ --


def test_try_still_blocks_metadata_ip_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """ยิงผ่าน executor/นโยบาย SSRF เดิมเท่านั้น — 169.254.169.254 บน production ต้องถูกบล็อก"""
    client = _make_client(
        monkeypatch,
        app_env="production",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
    )
    body = _try(
        client,
        {"httpMethod": "GET", "urlTemplate": "https://169.254.169.254/latest/meta-data"},
    )
    assert body["ok"] is False
    assert body["reason"] == "internal_ip"
