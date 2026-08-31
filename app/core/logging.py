"""ยูทิลิตี logging แบบมีโครงสร้างและจำกัดขอบเขตตามคำขอ"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(request_id: str | None) -> None:
    _request_id.set(request_id)


class _RedactingFormatter(logging.Formatter):
    """ตัวจัดรูปแบบ console ที่ปกปิดค่าลับที่เห็นได้ชัด"""

    SENSITIVE_KEYS = frozenset(
        {"token", "password", "secret", "api_key", "apikey", "authorization", "cookie"}
    )

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s")

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: "[REDACTED]" if k.lower() in self.SENSITIVE_KEYS else self._redact_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact_value(v) for v in value]
        return value

    def format(self, record: logging.LogRecord) -> str:
        if hasattr(record, "request_id") and record.request_id is not None:
            record.msg = f"[req:{record.request_id}] {record.msg}"
        if record.exc_info:
            return super().format(record)
        # พยายามปกปิดข้อมูลใน structured extras ให้ดีที่สุด
        for key in self.SENSITIVE_KEYS:
            if hasattr(record, key):
                setattr(record, key, "[REDACTED]")
        return super().format(record)


def configure_logging(level: str = "info") -> None:
    """กำหนดค่า logger สำหรับ console แบบมีโครงสร้างและเรียบง่าย"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_RedactingFormatter())
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """ส่งคืน dict ที่รวม request id ปัจจุบันเข้ากับข้อมูลเสริมของ log"""
    extra: dict[str, Any] = {"request_id": get_request_id()}
    extra.update(kwargs)
    return extra
