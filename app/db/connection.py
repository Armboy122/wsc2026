"""ชั้นเข้าถึง SQLite แบบบางที่สุดสำหรับ tool/prompt config (D2.1, ARCHITECTURE-V2.md §8)

หลักการที่ล็อกไว้:
- ``sqlite3`` stdlib ผ่าน ``asyncio.to_thread`` เท่านั้น ไม่เพิ่ม dependency
  (เรียก sqlite3 ตรงในโค้ด async จะบล็อก event loop — ARCHITECTURE-V2.md §8.5)
- WAL mode + **connection เดียวต่อ process** + เขียนผ่าน lock เดียว
  ระบบนี้ประกาศชัดว่ารองรับ single process เท่านั้น ไม่ทำ connection pool ที่ซ่อนปัญหา
- migration เป็น raw SQL (ไฟล์ ``NNN_*.sql`` ใต้ ``migrations/``) + ตาราง ``schema_version``
  ไม่ใช้ alembic เพราะระบบมีตารางไม่มากและ deps ของ alembic หนักกว่าปัญหาที่แก้
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Callable, TypeVar

from cryptography.fernet import Fernet

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
# path จาก env DB_PATH ค่าเริ่มต้น data/pea.db (ARCHITECTURE-V2.md §8.8)
DEFAULT_DB_PATH = Path("data/pea.db")
# In-memory databases need no restart durability and may use an ephemeral key.
# File-backed state must receive a durable key explicitly and fails closed otherwise.
_PROCESS_STATE_KEY = Fernet.generate_key()

T = TypeVar("T")


class Database:
    """connection เดียวต่อ process บน WAL mode พร้อม migration runner"""

    def __init__(
        self,
        path: Path | str = DEFAULT_DB_PATH,
        *,
        state_key: str | bytes | None = None,
    ) -> None:
        self._path = Path(path)
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # เขียนพร้อมกันคือที่มาของ "database is locked" — ให้เขียนผ่าน lock เดียวเสมอ
        self._write_lock = asyncio.Lock()
        self._state_cipher: Fernet | None = None
        self._configured_state_key = state_key

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
        self._conn.commit()
        applied = {row[0] for row in self._conn.execute("SELECT version FROM schema_version")}
        for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = _version_of(migration_path)
            if version in applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._execute_migration(sql)
                self._conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (version,)
                )
            except Exception:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    def _execute_migration(self, sql: str) -> None:
        """Execute migration statements while tolerating repeated ADD COLUMN statements.

        SQLite has no portable ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``.  Running
        each complete statement separately lets a partially applied migration continue
        with its remaining columns, while every other SQL error still aborts the
        migration and prevents recording a false schema version.
        """
        pending = ""
        for line in sql.splitlines(keepends=True):
            pending += line
            if not sqlite3.complete_statement(pending):
                continue
            statement = pending.strip()
            pending = ""
            if not _has_sql_statement(statement):
                continue
            try:
                self._conn.execute(statement)
            except sqlite3.OperationalError as exc:
                normalized = statement.upper()
                if "DUPLICATE COLUMN NAME" in str(exc).upper() and (
                    "ALTER TABLE" in normalized and "ADD COLUMN" in normalized
                ):
                    continue
                raise
        if _has_sql_statement(pending.strip()):
            self._conn.execute(pending)

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """รัน statement ที่เขียนข้อมูลหนึ่งคำสั่ง คืน ``lastrowid``"""
        async with self._write_lock:
            worker = asyncio.create_task(asyncio.to_thread(self._execute_sync, sql, params))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Once sqlite has started a write, cancellation cannot stop the worker.
                # Return its committed result so callers can update their RAM cache too.
                return await worker

    def _execute_sync(self, sql: str, params: tuple) -> int:
        with self._conn:
            cursor = self._conn.execute(sql, params)
            return cursor.lastrowid or 0

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._fetch_all_sync, sql, params)

    def read_all_sync(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Read rows during startup hydration without exposing the connection object."""
        return self._fetch_all_sync(sql, params)

    def state_cipher(self) -> Fernet:
        """Return the authenticated cipher for persisted customer/action state.

        ``PEA_STATE_KEY`` (or the injected settings value) is the only durable key
        source. File-backed state fails closed when it is absent; only ``:memory:``
        databases may use the process-local fallback.
        """
        if self._state_cipher is not None:
            return self._state_cipher
        configured = self._configured_state_key or os.environ.get("PEA_STATE_KEY")
        if configured:
            try:
                key = configured.encode("ascii") if isinstance(configured, str) else configured
            except (UnicodeEncodeError, AttributeError) as exc:
                raise RuntimeError("state encryption key is invalid") from exc
        elif str(self._path) != ":memory:":
            raise RuntimeError("PEA_STATE_KEY is required for file-backed state")
        else:
            key = _PROCESS_STATE_KEY
        try:
            self._state_cipher = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("state encryption key is invalid") from exc
        return self._state_cipher

    async def run_in_transaction(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """รันหลาย statement ในธุรกรรมเดียว (commit พร้อมกันหรือ rollback พร้อมกัน)

        ใช้กับการ save tool ที่เขียนหลายตาราง (tool + tool_operation + tool_auth) —
        ล้มกลางทางต้องไม่เหลือ tool ครึ่ง ๆ กลาง ๆ ใน DB (fail closed ของ D3.4)
        """
        async with self._write_lock:
            worker = asyncio.create_task(asyncio.to_thread(self._run_in_transaction_sync, fn))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                # The thread may already have committed. Finish the logical write so
                # the store can reconcile its in-memory view with SQLite.
                return await worker

    def _run_in_transaction_sync(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        with self._conn:
            return fn(self._conn)

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


def _has_sql_statement(statement: str) -> bool:
    """Return false for whitespace/comment-only chunks produced by the splitter."""
    return any(
        line.strip() and not line.lstrip().startswith("--")
        for line in statement.splitlines()
    )
