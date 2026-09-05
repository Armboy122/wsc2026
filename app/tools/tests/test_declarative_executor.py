"""ทดสอบ executor กลางของ declarative tool — D2.4

🔒 security boundary: ยิง httpx ผ่านนโยบาย D1.3 ทุกครั้ง ไม่มีทางลัด
เทสบังคับ: executor ที่ยิงไป private IP บน production = ถูกบล็อก
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.tools.declarative_executor import (
    DeclarativeHttpRequest,
    DeclarativeToolAuth,
    DeclarativeToolError,
    DeclarativeToolExecutor,
)
from app.tools.network_policy import NetworkPolicyError


def _fake_resolver(host: str) -> list[str]:
    # โดเมนทดสอบทั้งหมดในไฟล์นี้แกล้ง resolve เป็น IP สาธารณะเสมอ กันไม่ให้เทสพึ่ง DNS จริง
    return ["93.184.216.34"]


def _executor(
    *,
    app_env: str | None = "production",
    allowlist: tuple[str, ...] = (),
    environ: dict[str, str] | None = None,
    handler=None,
) -> DeclarativeToolExecutor:
    transport = httpx.MockTransport(handler) if handler is not None else None
    return DeclarativeToolExecutor(
        app_env=app_env,
        allowlist=allowlist,
        environ=environ or {},
        transport=transport,
        resolver=_fake_resolver,
    )


# ---------------------------------------------------------------------------
# 🔒 ไม่มีทางลัด — SSRF ของ D1.3 ต้องบังคับใช้เสมอ
# ---------------------------------------------------------------------------


def test_production_blocks_private_ip_even_when_url_looks_fine():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    executor = _executor(app_env="production", handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="https://169.254.169.254/latest/meta-data")

    with pytest.raises(NetworkPolicyError) as exc_info:
        asyncio.run(executor.execute(request))

    assert exc_info.value.reason == "internal_ip"
    assert called is False  # ต้องไม่ยิงออกไปเลยแม้แต่ครั้งเดียว


def test_production_blocks_domain_not_in_allowlist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    executor = _executor(app_env="production", allowlist=("api.example.com",), handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="https://evil.example.net/x")

    with pytest.raises(NetworkPolicyError) as exc_info:
        asyncio.run(executor.execute(request))
    assert exc_info.value.reason == "domain_not_in_allowlist"


def test_production_blocks_http_scheme():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    executor = _executor(app_env="production", allowlist=("api.example.com",), handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="http://api.example.com/x")

    with pytest.raises(NetworkPolicyError) as exc_info:
        asyncio.run(executor.execute(request))
    assert exc_info.value.reason == "not_https"


def test_development_allows_private_ip():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    executor = _executor(app_env="development", handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="http://169.254.169.254/x")

    result = asyncio.run(executor.execute(request))
    assert result.status_code == 200
    assert result.json_body == {"ok": True}


# ---------------------------------------------------------------------------
# secret ฉีดจาก env ตอน execute เท่านั้น
# ---------------------------------------------------------------------------


def test_secret_injected_from_env_only_at_execute_time():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    executor = _executor(
        app_env="production",
        allowlist=("api.example.com",),
        environ={"MY_TOOL_API_KEY": "s3cret-token"},
        handler=handler,
    )
    request = DeclarativeHttpRequest(
        method="GET",
        url="https://api.example.com/v1",
        auth=DeclarativeToolAuth(env_var="MY_TOOL_API_KEY"),
    )

    asyncio.run(executor.execute(request))

    assert captured[0].headers["authorization"] == "Bearer s3cret-token"
    # request/executor เองไม่เก็บค่า secret ไว้ที่ไหนนอกจาก header ที่ส่งออกไปครั้งนี้
    assert not hasattr(request, "secret")


def test_missing_secret_env_var_raises_without_calling_backend():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    executor = _executor(
        app_env="production",
        allowlist=("api.example.com",),
        environ={},
        handler=handler,
    )
    request = DeclarativeHttpRequest(
        method="GET",
        url="https://api.example.com/v1",
        auth=DeclarativeToolAuth(env_var="MISSING_ENV_VAR"),
    )

    with pytest.raises(DeclarativeToolError) as exc_info:
        asyncio.run(executor.execute(request))
    assert exc_info.value.reason == "missing_secret"
    assert called is False


# ---------------------------------------------------------------------------
# เพดานทรัพยากร — redirect/response size
# ---------------------------------------------------------------------------


def test_redirect_response_is_rejected_not_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://api.example.com/other"})

    executor = _executor(app_env="production", allowlist=("api.example.com",), handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="https://api.example.com/v1")

    with pytest.raises(DeclarativeToolError) as exc_info:
        asyncio.run(executor.execute(request))
    assert exc_info.value.reason == "redirect_blocked"


def test_oversized_response_is_rejected():
    big_body = b"x" * 2_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_body)

    executor = _executor(app_env="production", allowlist=("api.example.com",), handler=handler)
    request = DeclarativeHttpRequest(method="GET", url="https://api.example.com/v1")

    with pytest.raises(DeclarativeToolError) as exc_info:
        asyncio.run(executor.execute(request))
    assert exc_info.value.reason == "response_too_large"


def test_invalid_method_rejected_at_construction():
    with pytest.raises(ValueError):
        DeclarativeHttpRequest(method="TRACE", url="https://api.example.com/v1")
