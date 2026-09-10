from __future__ import annotations

import asyncio
from contextlib import closing
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from .contracts import DomainError


class Sessions:
    """ประวัติถาวรเข้ารหัส; CAS ป้องกันผลเทิร์นทับกันข้าม process"""

    def __init__(self, path: Path, key: str, ttl: int = 86400):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.cipher, self.ttl = path, Fernet(key.encode()), ttl

    def connect(self):
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    async def initialize(self):
        def run():
            with closing(self.connect()) as c, c:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("CREATE TABLE IF NOT EXISTS session (id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL, expires REAL NOT NULL, payload TEXT NOT NULL)")
                c.execute("DELETE FROM session WHERE expires < ?", (time.time(),))
        await asyncio.to_thread(run)

    async def load(self, owner: str, session_id: str | None):
        def run():
            with closing(self.connect()) as c, c:
                if session_id is None:
                    sid = str(uuid4())
                    data = {"history": [], "sources": []}
                    c.execute("INSERT INTO session VALUES (?, ?, 0, ?, ?)",
                        (sid, owner, time.time() + self.ttl, self.seal(data)))
                    return sid, 0, data
                row = c.execute("SELECT * FROM session WHERE id=? AND owner=? AND expires>?",
                    (session_id, owner, time.time())).fetchone()
                if row is None:
                    raise DomainError("session_not_found", "ไม่พบเซสชันหรือเซสชันหมดอายุ", 404)
                return session_id, row["revision"], json.loads(self.cipher.decrypt(row["payload"].encode()))
        return await asyncio.to_thread(run)

    def seal(self, data):
        return self.cipher.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()

    async def save(self, owner: str, session_id: str, revision: int, data: dict):
        def run():
            with closing(self.connect()) as c, c:
                result = c.execute("UPDATE session SET payload=?, revision=revision+1, expires=? WHERE id=? AND owner=? AND revision=? AND expires>?",
                    (self.seal(data), time.time() + self.ttl, session_id, owner, revision, time.time()))
                if result.rowcount != 1:
                    raise DomainError("session_conflict", "มีคำถามอีกข้อกำลังใช้เซสชันนี้ กรุณาลองใหม่", 409)
        await asyncio.to_thread(run)

    async def delete(self, owner: str, session_id: str):
        def run():
            with closing(self.connect()) as c, c:
                c.execute("DELETE FROM session WHERE id=? AND owner=?", (session_id, owner))
        await asyncio.to_thread(run)
