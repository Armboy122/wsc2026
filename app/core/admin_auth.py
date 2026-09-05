"""การยืนยันตัวตนหน้า admin (D3.1, TASKS-3DAYS.md)

หน้า admin สร้าง tool ที่ยิง HTTP ออกนอกระบบได้ = ยึดระบบได้ทั้งระบบ จึง fail closed ทุกทาง:

- ไม่ตั้ง ``ADMIN_PASSWORD`` → ทุก endpoint ที่ต้อง auth ตอบ 503 (ปิดใช้งาน)
  **ไม่มี default password** ในทุกกรณี
- session เป็น opaque token (``secrets.token_urlsafe``) เก็บใน RAM ต่อ process เท่านั้น
  restart = logout ทุก session (เดโมยอมรับได้ — เทียบกับ trace/pending ที่อยู่ RAM เหมือนกัน)
- เทียบรหัสผ่านแบบ constant-time (``secrets.compare_digest``)
- cookie เป็น HttpOnly + SameSite=Lax (เดโมรัน http จึงตั้ง Secure ไม่ได้)
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.core.config import Settings

ADMIN_SESSION_COOKIE = "pea_admin_session"


class AdminSessionStore:
    """คลัง session token ในหน่วยความจำ — token ไม่มีข้อมูลใด ๆ ฝังอยู่ในตัว"""

    def __init__(self) -> None:
        self._tokens: set[str] = set()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens.add(token)
        return token

    def validate(self, token: str | None) -> bool:
        return token is not None and token in self._tokens

    def revoke(self, token: str | None) -> None:
        if token is not None:
            self._tokens.discard(token)


# singleton ต่อ process (เทียบ agent_service ใน app/core/di.py) — เทส replace ด้วย monkeypatch
admin_session_store = AdminSessionStore()


def verify_admin_password(admin_password: str | None, candidate: str) -> bool:
    if not admin_password:
        return False
    # compare_digest รับเฉพาะ ASCII string — เข้ารหัสเป็น UTF-8 ก่อน ไม่งั้นรหัสผ่านภาษาไทยจะ TypeError
    return secrets.compare_digest(admin_password.encode("utf-8"), candidate.encode("utf-8"))


async def require_admin(request: Request) -> None:
    """FastAPI dependency ป้องกัน endpoint ของ admin — D3.3/D3.4 ต้องใช้ตัวนี้ทุก endpoint"""
    settings: Settings = request.app.state.settings
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ปิดใช้งานหน้า admin: ยังไม่ได้ตั้งค่า ADMIN_PASSWORD",
        )
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not admin_session_store.validate(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ต้องเข้าสู่ระบบ admin ก่อน",
        )
