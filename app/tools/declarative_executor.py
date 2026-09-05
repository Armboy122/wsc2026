"""executor กลางของ declarative tool (HTTP) — D2.4, ARCHITECTURE-V2.md §3.4/§3.7

รับผิดชอบเพียงอย่างเดียว: ยิง HTTP request ที่มาจาก declarative tool (เก็บใน SQLite ตาม D2.1)
ให้ปลอดภัย และเป็นจุดเดียวที่ declarative tool ทุกตัวต้องยิงผ่าน — **ไม่มีทางลัด**:

- ผ่าน ``app.tools.network_policy`` (D1.3) **ทุกครั้งก่อนยิงจริง** ทั้งตรวจรูปแบบ URL/HTTPS/
  allowlist และ resolve DNS เทียบ blocklist (กัน DNS rebinding) — เรียกซ้ำทุกครั้งที่ ``execute()``
  ถูกเรียก ไม่แคชผลจากตอน save เพราะโดเมนอาจถูกเปลี่ยนให้ resolve ไป IP ภายในได้ภายหลัง
- **ฉีด secret จาก environment variable ตอน execute เท่านั้น** — ``DeclarativeToolAuth.env_var``
  เป็นแค่ *ชื่อ* ตัวแปร (ตรงกับ ``tool_auth.secret_ref`` ของ D2.1) ค่าจริงถูกอ่านสด ๆ จาก
  ``os.environ`` ตอนสร้าง request เท่านั้น ไม่ถูกโหลดมาเก็บพักไว้ที่ไหนล่วงหน้า เพราะ secret
  ต้องไม่มีทางรั่วผ่าน schema/description/trace ที่ LLM หรือ admin เห็น (CONTRACTS-V2 §3.7/§1)
- ใช้เพดานทรัพยากรเดียวกับนโยบาย (``OutboundLimits``): timeout/response size/retry/redirect
  — 3xx ถือว่า config ผิด ไม่ตามอัตโนมัติ (CONTRACTS-V2 §7.4)
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import httpx

from app.tools.network_policy import OutboundLimits, Resolver, enforce_outbound_request

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class DeclarativeToolError(RuntimeError):
    """executor ยิงไม่สำเร็จ

    ``reason`` เป็นรหัสที่เครื่องอ่านได้ (ใช้บันทึกลง trace ได้โดยไม่มีข้อมูลอ่อนไหว)
    ``message`` ปลอดภัยสำหรับผู้ใช้ — ไม่มี stack trace / URL ปลายทาง / ชื่อ header
    (CONTRACTS-V2 §4.2)
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class DeclarativeToolAuth:
    """ตำแหน่งของ secret สำหรับ request หนึ่งครั้ง

    ``env_var`` คือ **ชื่อ** environment variable เท่านั้น (ตรงกับ ``tool_auth.secret_ref``
    ของ D2.1) ไม่ใช่ค่าจริง — ค่าจริงถูกอ่านจาก env ตอน ``execute()`` เท่านั้น
    """

    env_var: str
    header_name: str = "Authorization"
    scheme: str = "Bearer"


@dataclass(frozen=True, slots=True)
class DeclarativeHttpRequest:
    """คำขอ HTTP หนึ่งครั้งของ declarative tool

    สร้างจาก operation + input ที่ผ่านการ validate ด้วย ``inputSchema`` (D1.2) มาแล้วเท่านั้น
    — โมดูลนี้ไม่ตรวจ business shape ของ ``input`` ซ้ำ รับผิดชอบแค่ชั้นเครือข่าย
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)
    json_body: Any | None = None
    auth: DeclarativeToolAuth | None = None

    def __post_init__(self) -> None:
        method = self.method.upper()
        if method not in _ALLOWED_METHODS:
            raise ValueError(f"method ไม่รองรับ: {self.method}")
        object.__setattr__(self, "method", method)


@dataclass(frozen=True, slots=True)
class DeclarativeHttpResponse:
    """ผลลัพธ์ของ request หนึ่งครั้ง — เก็บเฉพาะสิ่งที่ปลอดภัยให้ trace บันทึกต่อ (CONTRACTS-V2 §8.3)"""

    status_code: int
    json_body: Any | None
    elapsed_seconds: float


class DeclarativeToolExecutor:
    """executor กลางตัวเดียวที่ declarative tool ทุกตัวต้องยิงผ่าน — ไม่มีทางลัด

    ``app_env``/``allowlist`` ต้องมาจากค่าเดียวกับที่ D1.3 ใช้ตรวจตอน save เสมอ
    ``environ``/``resolver`` แยกให้ inject ได้ในเทส (กัน DNS จริงระหว่างรันเทส) —
    ค่าเริ่มต้นคือ ``os.environ`` และ DNS resolver จริงของ process
    """

    def __init__(
        self,
        *,
        app_env: str | None,
        allowlist: Iterable[str] = (),
        environ: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._app_env = app_env
        self._allowlist = tuple(allowlist)
        self._environ = environ if environ is not None else os.environ
        self._transport = transport
        self._resolver = resolver

    async def execute(self, request: DeclarativeHttpRequest) -> DeclarativeHttpResponse:
        """ยิง ``request`` หนึ่งครั้งหลังผ่านนโยบายเครือข่ายขาออกครบทุกขั้น

        ลำดับตรึงไว้ตาม CONTRACTS-V2 §7.3: ตรวจ URL/allowlist ก่อน แล้ว resolve DNS
        เทียบ blocklist ก่อนยิงจริงเสมอ — เรียก ``enforce_outbound_request`` ตรง ๆ
        ไม่มี flag หรือ mode ใดให้ข้ามขั้นนี้ได้
        """
        # DNS resolution เป็น blocking call (stdlib socket) — ย้ายออกจาก event loop
        # เหมือนที่ app/db/connection.py ทำกับ sqlite3 (ARCHITECTURE-V2.md §8.5)
        await asyncio.to_thread(
            enforce_outbound_request,
            request.url,
            app_env=self._app_env,
            allowlist=self._allowlist,
            resolver=self._resolver,
        )

        headers = dict(request.headers)
        if request.auth is not None:
            secret = self._environ.get(request.auth.env_var)
            if not secret:
                raise DeclarativeToolError(
                    "missing_secret",
                    f"ไม่พบค่าลับใน environment variable: {request.auth.env_var}",
                )
            headers[request.auth.header_name] = f"{request.auth.scheme} {secret}".strip()

        limits = OutboundLimits()
        try:
            async with httpx.AsyncClient(
                timeout=limits.timeout_seconds,
                follow_redirects=limits.follow_redirects,
                transport=self._transport,
            ) as client:
                # สตรีมอ่านทีละ chunk แทนที่จะให้ client.request() บัฟเฟอร์ทั้งก้อนก่อน
                # เพราะ max_response_bytes ต้องบังคับ "ระหว่างดาวน์โหลด" ไม่ใช่ตรวจย้อนหลัง
                # หลังโหลดครบแล้ว — ไม่งั้นปลายทางที่ตอบก้อนใหญ่มากบังคับให้หน่วยความจำพองได้
                # ก่อนเพดานจะทำงาน (CONTRACTS-V2 §7.4)
                async with client.stream(
                    request.method,
                    request.url,
                    headers=headers,
                    params=dict(request.query) or None,
                    json=request.json_body,
                ) as response:
                    if response.status_code in _REDIRECT_STATUS_CODES:
                        # follow_redirects=False แล้ว httpx คืน response 3xx ตรง ๆ ไม่ raise เอง —
                        # ถือว่า config ผิด ต้องแจ้ง admin ให้แก้ URL (CONTRACTS-V2 §7.4)
                        raise DeclarativeToolError(
                            "redirect_blocked",
                            "ปลายทางพยายาม redirect — ระบบไม่ตามอัตโนมัติ กรุณาแก้ URL ให้ตรงปลายทางจริง",
                        )
                    content_type = response.headers.get("content-type", "")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > limits.max_response_bytes:
                            raise DeclarativeToolError(
                                "response_too_large",
                                f"response ใหญ่เกินเพดานที่กำหนด ({limits.max_response_bytes} ไบต์)",
                            )
        except httpx.RequestError as exc:
            raise DeclarativeToolError("request_failed", "ไม่สามารถเชื่อมต่อปลายทางได้") from exc

        json_body: Any | None = None
        if "application/json" in content_type:
            try:
                json_body = json.loads(bytes(body))
            except ValueError:
                json_body = None

        try:
            elapsed_seconds = response.elapsed.total_seconds()
        except RuntimeError:
            # บาง transport ในเทส (เช่น MockTransport) ไม่บันทึกเวลาไว้
            elapsed_seconds = 0.0

        return DeclarativeHttpResponse(
            status_code=response.status_code,
            json_body=json_body,
            elapsed_seconds=elapsed_seconds,
        )
