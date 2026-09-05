"""ทดสอบการยืนยันตัวตนหน้า admin (D3.1, TASKS-3DAYS.md)

ความเสี่ยงที่เทสนี้กันไว้: "ใครก็เข้ามาสร้าง tool ที่ยิง HTTP ได้" —
ทุก endpoint ใต้ /api/v1/admin ต้อง fail closed เสมอ ไม่ว่าจะตั้ง ADMIN_PASSWORD หรือไม่
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import router as admin_router
from app.core.admin_auth import AdminSessionStore
from app.core.config import Settings


@pytest.fixture()
def fresh_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """แยก session store รายเทส — ไม่ให้ token จากเทสก่อนหน้าหลุดมา valid"""
    monkeypatch.setattr("app.core.admin_auth.admin_session_store", AdminSessionStore())


def _client(admin_password: str | None) -> TestClient:
    app = FastAPI()
    env = {"ADMIN_PASSWORD": admin_password} if admin_password else {}
    app.state.settings = Settings.from_env(env)
    app.include_router(admin_router)
    return TestClient(app)


@pytest.fixture()
def client(fresh_store: None) -> TestClient:
    return _client("s3cret-demo")


@pytest.fixture()
def client_without_password(fresh_store: None) -> TestClient:
    return _client(None)


def test_settings_reads_and_redacts_admin_password() -> None:
    settings = Settings.from_env({"ADMIN_PASSWORD": "pw-123"})
    assert settings.admin_password == "pw-123"
    assert settings.admin_password not in repr(settings)
    assert "[REDACTED]" in repr(settings)
    assert Settings.from_env({}).admin_password is None


def test_fail_closed_when_admin_password_not_configured(
    client_without_password: TestClient,
) -> None:
    """ไม่ตั้ง ADMIN_PASSWORD = ปิด admin ทั้งหมด ไม่มี default password"""
    login = client_without_password.post(
        "/api/v1/admin/login", json={"password": "anything"}
    )
    assert login.status_code == 503
    assert client_without_password.get("/api/v1/admin/session").status_code == 503


def test_login_wrong_password_is_401_and_sets_no_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/admin/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert "pea_admin_session" not in response.cookies


def test_login_accepts_non_ascii_password(fresh_store: None) -> None:
    """regression: compare_digest เดิมเรียกบน str ทำให้รหัสผ่านภาษาไทย TypeError (500)"""
    client = _client("รหัสผ่านไทย")
    assert client.post("/api/v1/admin/login", json={"password": "ผิด"}).status_code == 401
    assert client.post("/api/v1/admin/login", json={"password": "รหัสผ่านไทย"}).status_code == 200


def test_login_rejects_empty_body(client: TestClient) -> None:
    assert client.post("/api/v1/admin/login", json={}).status_code == 422
    assert client.post("/api/v1/admin/login", json={"extra": "x"}).status_code == 422


def test_login_success_sets_httponly_session_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/admin/login", json={"password": "s3cret-demo"})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}

    set_cookie = response.headers["set-cookie"]
    assert "pea_admin_session=" in set_cookie
    assert "httponly" in set_cookie.lower()

    session = client.get("/api/v1/admin/session")
    assert session.status_code == 200
    assert session.json() == {"authenticated": True}


def test_protected_endpoint_rejects_missing_or_invalid_cookie(client: TestClient) -> None:
    assert client.get("/api/v1/admin/session").status_code == 401

    client.cookies.set("pea_admin_session", "forged-token")
    assert client.get("/api/v1/admin/session").status_code == 401


def test_logout_revokes_session(client: TestClient) -> None:
    client.post("/api/v1/admin/login", json={"password": "s3cret-demo"})
    assert client.get("/api/v1/admin/session").status_code == 200

    logout = client.post("/api/v1/admin/logout")
    assert logout.status_code == 200

    session = client.get("/api/v1/admin/session")
    assert session.status_code == 401
