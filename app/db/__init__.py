"""ชั้นข้อมูล SQLite ของ tool/prompt/domain_allowlist (D2.1, ARCHITECTURE-V2.md §8)"""

from __future__ import annotations

from app.db.connection import DEFAULT_DB_PATH, Database

__all__ = ["Database", "DEFAULT_DB_PATH"]
