"""ชั้นเข้าถึง SQLite แบบบางที่สุดสำหรับ tool/prompt config (D2.1, ARCHITECTURE-V2.md §8)

หลักการที่ล็อกไว้:
- ``sqlite3`` stdlib ผ่าน ``asyncio.to_thread`` เท่านั้น ไม่เพิ่ม dependency
  (เรียก sqlite3 ตรงในโค้ด async จะบล็อก event loop — ARCHITECTURE-V2.md §8.5)
- WAL mode + **connection เดียวต่อ process** + เขียนผ่าน lock เดียว
  ระบบนี้ประกาศชัดว่ารองรับ single process เท่านั้น ไม่ทำ connection pool ที่ซ่อนปัญหา
- migration เป็น raw SQL (ไฟล์ ``NNN_*.sql`` ใต้ ``migrations/``) + ตาราง ``schema_version``
  ไม่ใช้ alembic เพราะระบบมีแค่ 5 ตารางและ deps 5 ตัวของ alembic หนักกว่าปัญหาที่แก้
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
# path จาก env DB_PATH ค่าเริ่มต้น data/pea.db (ARCHITECTURE-V2.md §8.8)
DEFAULT_DB_PATH = Path("data/pea.db")


class Database:
    """connection เดียวต่อ process บน WAL mode พร้อม migration runner"""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(path)
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # เขียนพร้อมกันคือที่มาของ "database is locked" — ให้เขียนผ่าน lock เดียวเสมอ
        self._write_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def migrate(self) -> None:
        """รัน migration ที่ยังไม่ถูก apply ตามลำดับชื่อไฟล์

        เรียกจาก thread ปกติตอน startup ก่อนเปิดรับ request ใด ๆ — ไม่ผ่าน asyncio.to_thread
        เพราะยังไม่มี event loop ให้บล็อกในจังหวะนั้น
        """
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        applied = {row[0] for row in self._conn.execute("SELECT version FROM schema_version")}
        for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = _version_of(migration_path)
            if version in applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            with self._conn:
                try:
                    self._conn.executescript(sql)
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" in str(exc).lower():
                        pass
                    else:
                        raise
                self._conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (version,)
                )

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """รัน statement ที่เขียนข้อมูลหนึ่งคำสั่ง คืน ``lastrowid``"""
        async with self._write_lock:
            return await asyncio.to_thread(self._execute_sync, sql, params)

    def _execute_sync(self, sql: str, params: tuple) -> int:
        with self._conn:
            cursor = self._conn.execute(sql, params)
            return cursor.lastrowid or 0

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._fetch_all_sync, sql, params)

    def _fetch_all_sync(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    async def fetch_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        self._conn.close()


def _version_of(migration_path: Path) -> int:
    prefix = migration_path.stem.split("_", 1)[0]
    return int(prefix)
