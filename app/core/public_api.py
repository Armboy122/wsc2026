"""Authentication, ownership, and throttling for the V2 public API."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.db import Database

WEB_SESSION_COOKIE = "pea_web_session"


def hash_api_key(value: str) -> str:
    """Return a one-way digest suitable for indexed lookup of random API keys."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_api_key() -> str:
    return f"pea_{secrets.token_urlsafe(32)}"


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    id: UUID
    name: str
    tenant_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedApiKey:
    record: ApiKeyRecord
    value: str


@dataclass(frozen=True, slots=True)
class WebSession:
    id: UUID


class WebSessionStore:
    """Short-lived identities and resource ownership for bundled web clients."""

    def __init__(
        self,
        ttl_seconds: int = 8 * 60 * 60,
        max_sessions: int = 1024,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max(1, max_sessions)
        self._sessions: dict[str, tuple[WebSession, float]] = {}
        self._conversation_owners: dict[UUID, UUID] = {}
        self._pending_owners: dict[UUID, UUID] = {}

    def create(self) -> str:
        now = time.monotonic()
        if len(self._sessions) >= self._max_sessions:
            self._discard_expired(now)
        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError("web session capacity reached")
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (WebSession(uuid4()), now + self._ttl_seconds)
        return token

    def authenticate(self, token: str | None) -> WebSession | None:
        if token is None:
            return None
        now = time.monotonic()
        stored = self._sessions.get(token)
        if stored is None:
            return None
        session, expires_at = stored
        if expires_at <= now:
            self._discard_session(token, session.id)
            return None
        return session

    def owns_conversation(self, session: WebSession, conversation_id: UUID) -> bool:
        return self._conversation_owners.get(conversation_id) == session.id

    def claim_conversation(self, session: WebSession, conversation_id: UUID) -> bool:
        existing = self._conversation_owners.get(conversation_id)
        if existing is not None and existing != session.id:
            return False
        self._conversation_owners[conversation_id] = session.id
        return True

    def owns_pending(self, session: WebSession, pending_action_id: UUID) -> bool:
        return self._pending_owners.get(pending_action_id) == session.id

    def claim_pending(self, session: WebSession, pending_action_id: UUID) -> bool:
        existing = self._pending_owners.get(pending_action_id)
        if existing is not None and existing != session.id:
            return False
        self._pending_owners[pending_action_id] = session.id
        return True

    def _discard_expired(self, now: float) -> None:
        for token, (session, expires_at) in tuple(self._sessions.items()):
            if expires_at <= now:
                self._discard_session(token, session.id)

    def _discard_session(self, token: str, session_id: UUID) -> None:
        self._sessions.pop(token, None)
        self._conversation_owners = {
            resource_id: owner_id
            for resource_id, owner_id in self._conversation_owners.items()
            if owner_id != session_id
        }
        self._pending_owners = {
            resource_id: owner_id
            for resource_id, owner_id in self._pending_owners.items()
            if owner_id != session_id
        }


class ApiKeyStore:
    """SQLite-backed API keys; plaintext values are never persisted."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, name: str, *, tenant_id: str = "default") -> CreatedApiKey:
        if tenant_id != "default":
            raise ValueError("P8 supports only the default tenant")
        key_id = uuid4()
        value = _new_api_key()
        created_at = datetime.now(UTC)
        await self._db.execute(
            "INSERT INTO api_key (id, name, key_hash, tenant_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(key_id), name, hash_api_key(value), tenant_id, created_at.isoformat()),
        )
        return CreatedApiKey(
            ApiKeyRecord(key_id, name, tenant_id, created_at),
            value,
        )

    async def authenticate(self, value: str | None) -> ApiKeyRecord | None:
        if not value:
            return None
        row = await self._db.fetch_one(
            "SELECT id, name, tenant_id, created_at FROM api_key "
            "WHERE key_hash = ? AND revoked_at IS NULL",
            (hash_api_key(value),),
        )
        if row is None:
            return None
        try:
            return ApiKeyRecord(
                id=UUID(row["id"]),
                name=row["name"],
                tenant_id=row["tenant_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        except (KeyError, TypeError, ValueError):
            # A malformed row must not turn authentication into a server error.
            return None

    async def list(self) -> list[dict[str, Any]]:
        rows = await self._db.fetch_all(
            "SELECT id, name, tenant_id, created_at, revoked_at FROM api_key "
            "ORDER BY created_at, id"
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "tenantId": row["tenant_id"],
                "createdAt": row["created_at"],
                "revokedAt": row["revoked_at"],
                "revoked": row["revoked_at"] is not None,
            }
            for row in rows
        ]

    async def revoke(self, key_id: UUID) -> bool:
        updated = await self._db.run_in_transaction(
            lambda conn: conn.execute(
                "UPDATE api_key SET revoked_at = ? "
                "WHERE id = ? AND revoked_at IS NULL",
                (datetime.now(UTC).isoformat(), str(key_id)),
            ).rowcount
        )
        return updated == 1


class ConversationOwnership:
    """Own conversations in RAM and durable pending actions in SQLite."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._owners: dict[UUID, UUID] = {}
        self._pending_owners: dict[UUID, UUID] = {}
        if db is not None:
            self._load_pending_owners()

    def owner_of(self, conversation_id: UUID) -> UUID | None:
        return self._owners.get(conversation_id)

    def claim(self, conversation_id: UUID, key_id: UUID) -> bool:
        existing = self._owners.get(conversation_id)
        if existing is not None and existing != key_id:
            return False
        self._owners[conversation_id] = key_id
        return True

    async def claim_pending(self, pending_action_id: UUID, key_id: UUID) -> bool:
        existing = self._pending_owners.get(pending_action_id)
        if existing is not None and existing != key_id:
            return False
        if self._db is not None:
            updated = await self._db.run_in_transaction(
                lambda conn: conn.execute(
                    "UPDATE pending_action SET api_key_id = ? "
                    "WHERE id = ? AND (api_key_id IS NULL OR api_key_id = ?)",
                    (str(key_id), str(pending_action_id), str(key_id)),
                ).rowcount
            )
            if updated != 1:
                return False
        self._pending_owners[pending_action_id] = key_id
        return True

    def pending_owner_of(self, pending_action_id: UUID) -> UUID | None:
        return self._pending_owners.get(pending_action_id)

    def clear(self) -> None:
        self._owners.clear()

    def _load_pending_owners(self) -> None:
        assert self._db is not None
        rows = self._db.read_all_sync(
            "SELECT id, api_key_id FROM pending_action WHERE api_key_id IS NOT NULL"
        )
        for row in rows:
            try:
                self._pending_owners[UUID(row["id"])] = UUID(row["api_key_id"])
            except (KeyError, TypeError, ValueError):
                # Malformed ownership must deny access instead of breaking startup.
                continue


class InMemoryRateLimiter:
    """Fixed one-minute request counter, keyed by API key id."""

    def __init__(self, limit_per_minute: int = 60) -> None:
        self.limit_per_minute = max(1, limit_per_minute)
        self._windows: dict[UUID, tuple[int, int]] = {}

    def allow(self, key_id: UUID, *, now: float | None = None) -> bool:
        current_window = int((time.monotonic() if now is None else now) // 60)
        window, count = self._windows.get(key_id, (current_window, 0))
        if window != current_window:
            window, count = current_window, 0
        if count >= self.limit_per_minute:
            self._windows[key_id] = (window, count)
            return False
        self._windows[key_id] = (window, count + 1)
        return True

    def clear(self) -> None:
        self._windows.clear()
