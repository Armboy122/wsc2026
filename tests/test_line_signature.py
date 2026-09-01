"""การตรวจสอบลายเซ็น webhook ของ LINE ที่ขอบเขตความปลอดภัย

ทดสอบเฉพาะการตรวจลายเซ็น (security boundary ที่ต้อง fail closed)
ส่วนพฤติกรรมการสนทนาจะตรวจด้วยการทดสอบจริงผ่าน LINE app
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.line.signature import verify_webhook_signature

_SECRET = "test-channel-secret"
_BODY = '{"events":[{"type":"message","message":{"text":"ไฟดับ"}}]}'.encode("utf-8")


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def test_signature_valid_passes() -> None:
    assert verify_webhook_signature(_SECRET, _BODY, _sign(_SECRET, _BODY)) is True


def test_signature_wrong_secret_fails_closed() -> None:
    assert verify_webhook_signature(_SECRET, _BODY, _sign("wrong-secret", _BODY)) is False


def test_signature_tampered_body_fails_closed() -> None:
    signature = _sign(_SECRET, _BODY)
    assert verify_webhook_signature(_SECRET, _BODY + b"x", signature) is False


def test_signature_missing_inputs_fail_closed() -> None:
    assert verify_webhook_signature("", _BODY, _sign(_SECRET, _BODY)) is False
    assert verify_webhook_signature(_SECRET, _BODY, "") is False
