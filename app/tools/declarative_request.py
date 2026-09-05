"""ประกอบ ``DeclarativeHttpRequest`` จาก ``urlTemplate`` + input ที่ผ่าน validate แล้ว — D2.6

กลไก "LLM เติมค่า" เดียวที่ระบบเลือกใช้ (ARCHITECTURE-V2.md §3.7 บังคับให้เลือกอันเดียว
ตั้งแต่วันแรก — n8n มีสองอัน (``$fromAI()`` + placeholder) แล้วถอยไม่ได้):

- placeholder ``{fieldName}`` ใน ``urlTemplate`` ดึงค่าจาก field ระดับบนสุดของ input เสมอ
  (เข้ารหัส URL ด้วย ``urllib.parse.quote`` เสมอ ป้องกัน field ที่มีอักขระพิเศษทำลาย URL)
- field ที่ ``urlTemplate`` ใช้ไปแล้วไม่ถูกส่งซ้ำที่อื่น
- field ที่เหลือทั้งหมดไปเป็น query string เมื่อ method ไม่มี body (GET/DELETE)
  หรือ JSON body เมื่อ method มี body (POST/PUT/PATCH)

ไม่ตรวจ business shape ของ ``input`` ซ้ำ — สมมติว่าผ่าน ``validate_schema_instance``
(D1.2/D2.6) มาก่อนแล้วเสมอ
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import quote

from app.tools.declarative_executor import DeclarativeHttpRequest, DeclarativeToolAuth

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_METHODS_WITHOUT_BODY = frozenset({"GET", "DELETE"})


class UrlTemplateError(ValueError):
    """urlTemplate อ้างถึง field ที่ input ไม่มี — เป็นความผิดของการตั้งค่า tool ไม่ใช่ผู้ใช้"""


def build_declarative_http_request(
    *,
    http_method: str,
    url_template: str,
    input: Mapping[str, Any],
    auth: DeclarativeToolAuth | None = None,
    idempotency_key: str | None = None,
) -> DeclarativeHttpRequest:
    method = http_method.upper()
    consumed: set[str] = set()

    def _substitute(match: re.Match[str]) -> str:
        field = match.group(1)
        if field not in input:
            raise UrlTemplateError(f"urlTemplate อ้างถึง field ที่ไม่มีใน input: {field}")
        consumed.add(field)
        return quote(str(input[field]), safe="")

    url = _PLACEHOLDER.sub(_substitute, url_template)
    remaining = {key: value for key, value in input.items() if key not in consumed}
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}

    if method in _METHODS_WITHOUT_BODY:
        query = {key: str(value) for key, value in remaining.items()}
        return DeclarativeHttpRequest(method=method, url=url, headers=headers, query=query, auth=auth)
    return DeclarativeHttpRequest(method=method, url=url, headers=headers, json_body=remaining or None, auth=auth)
