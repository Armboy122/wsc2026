import hashlib
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from voice_assistant.bootstrap import Settings, build


def publication(root: Path, docs: dict[str, str]):
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, text in docs.items():
        (root/name).write_text(text, encoding="utf-8")
        rows.append({"id": name, "title": name, "path": name, "sha256": hashlib.sha256(text.encode()).hexdigest(), "status": "published"})
    (root/"publication.json").write_text(json.dumps({"documents": rows}), encoding="utf-8")


@pytest.fixture
def settings(tmp_path):
    root = tmp_path/"knowledge"
    publication(root, {
        "ขอใช้ไฟฟ้าใหม่.md": "# ขอใช้ไฟฟ้าใหม่\n\nขอใช้ไฟฟ้าใหม่ต้องเตรียมบัตรประชาชนและทะเบียนบ้าน\n\nยื่นคำขอผ่าน https://example.org/new ได้",
        "คืนเงินประกัน.md": "# คืนเงินประกัน\n\nการคืนเงินประกันให้ระบุหมายเลขผู้ใช้ไฟและบัญชีรับเงิน\n\nตรวจสอบขั้นตอนคืนเงินประกันกับเจ้าหน้าที่",
    })
    return Settings(root, tmp_path/"sessions.db", Fernet.generate_key().decode(), {
        "a"*32: {"id": "alice", "scopes": ["knowledge:read"]},
        "b"*32: {"id": "bob", "scopes": ["knowledge:read"]},
    })


@pytest.fixture
async def service(settings):
    result = build(settings)
    await result.sessions.initialize()
    yield result
    await result.provider.close()
