"""Stores for conversation-local state and SQLite-backed audit state."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Iterator
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken

from app.contracts import PendingAction, PendingActionStatus, ToolResult, TraceEvent, TraceEventKind, TraceResponse
from app.db import Database
from app.llm.models import LLMMessage

_SENSITIVE_KEYS = frozenset({
    "token", "paymenttoken", "apikey", "accesstoken", "authorization", "password",
    "secret", "secretref", "clientsecret", "idempotencykey", "detail",
    "locationnote", "symptoms", "chainofthought", "cot", "reasoning", "thought",
    "thoughts", "scratchpad", "systemprompt",
})
_PERSISTENCE_FORBIDDEN_KEYS = frozenset({
    "token", "password", "paymenttoken", "secret", "secretref", "clientsecret",
    "accesstoken", "authorization", "apikey", "chainofthought", "cot",
    "reasoning", "thought", "thoughts", "scratchpad", "systemprompt",
})
_TRACE_CHANNEL: ContextVar[str | None] = ContextVar("trace_channel", default=None)


def utc_now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def trace_channel(channel: str) -> Iterator[None]:
    """Attach trusted adapter provenance to traces across awaited agent work."""
    token = _TRACE_CHANNEL.set(channel)
    try:
        yield
    finally:
        _TRACE_CHANNEL.reset(token)


def current_trace_channel() -> str | None:
    """Return the active trace channel for the current context."""
    return _TRACE_CHANNEL.get()


def _normalized_field_key(key: str) -> str:
    """Canonicalize JSON field names across camelCase, snake_case, and separators."""
    return "".join(character for character in key.casefold() if character.isalnum())


def redact(value: Any, *, key: str = "") -> Any:
    """เก็บข้อมูลวินิจฉัย trace ให้มีประโยชน์โดยไม่เก็บข้อความหรือ payload ที่ละเอียดอ่อน"""
    norm_key = _normalized_field_key(key)
    if norm_key in _SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, key=str(item_key)) for item_key, item_value in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 200:
        return "[redacted]"
    return value


def _without_forbidden_persistence_fields(value: Any) -> Any:
    """Drop credentials and hidden reasoning before durable serialization.

    Fernet protects the remaining state at rest, but credentials and chain-of-thought
    must not be retained at all: they are neither needed for safe replay nor recoverable
    customer state.
    """
    if isinstance(value, dict):
        return {
            str(item_key): _without_forbidden_persistence_fields(item_value)
            for item_key, item_value in value.items()
            if _normalized_field_key(str(item_key)) not in _PERSISTENCE_FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_without_forbidden_persistence_fields(item) for item in value]
    return value


class ConversationStore:
    def __init__(self) -> None:
        self._messages: dict[UUID, list[LLMMessage]] = {}

    def messages_for(self, conversation_id: UUID) -> tuple[LLMMessage, ...]:
        return tuple(self._messages.get(conversation_id, ()))

    def append(self, conversation_id: UUID, message: LLMMessage) -> None:
        self._messages.setdefault(conversation_id, []).append(message)

    def clear(self) -> None:
        self._messages.clear()


class PendingActionStore:
    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._actions: dict[UUID, PendingAction] = {}
        self._trace_ids: dict[UUID, UUID] = {}
        self._execution_inputs: dict[UUID, dict[str, Any]] = {}
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._confirmation_events: dict[UUID, asyncio.Event] = {}
        self._confirmation_tasks: dict[UUID, asyncio.Task[Any]] = {}
        if db is not None:
            self._load()

    async def put(
        self,
        action: PendingAction,
        trace_id: UUID,
        *,
        execution_input: dict[str, Any] | None = None,
    ) -> None:
        async with self.lock_for(action.pending_action_id):
            source_input = action.prepared_input if execution_input is None else execution_input
            self._execution_inputs[action.pending_action_id] = dict(source_input)
            await self._persist(action, trace_id)
            self._actions[action.pending_action_id] = action
            self._trace_ids[action.pending_action_id] = trace_id

    def lock_for(self, pending_action_id: UUID) -> asyncio.Lock:
        return self._locks.setdefault(pending_action_id, asyncio.Lock())

    def get(self, pending_action_id: UUID) -> PendingAction | None:
        return self._actions.get(pending_action_id)

    def trace_id_for(self, pending_action_id: UUID) -> UUID | None:
        return self._trace_ids.get(pending_action_id)

    def execution_input_for(self, pending_action_id: UUID) -> dict[str, Any] | None:
        value = self._execution_inputs.get(pending_action_id)
        return dict(value) if value is not None else None

    def confirmation_task_for(self, pending_action_id: UUID) -> asyncio.Task[Any] | None:
        return self._confirmation_tasks.get(pending_action_id)

    def start_confirmation_task(
        self, pending_action_id: UUID, factory: Callable[[], Awaitable[Any]]
    ) -> asyncio.Task[Any]:
        """Run one confirmation worker per shared store, including scoped agents."""
        existing = self._confirmation_tasks.get(pending_action_id)
        if existing is not None:
            return existing
        task = asyncio.create_task(factory())
        self._confirmation_tasks[pending_action_id] = task

        def _discard_finished(done: asyncio.Task[Any]) -> None:
            if self._confirmation_tasks.get(pending_action_id) is done:
                self._confirmation_tasks.pop(pending_action_id, None)

        task.add_done_callback(_discard_finished)
        return task

    async def drain_confirmation_tasks(self) -> None:
        """Wait for confirmed writes; reset must not cancel a side effect mid-flight."""
        while self._confirmation_tasks:
            tasks = tuple(self._confirmation_tasks.values())
            await asyncio.gather(*tasks, return_exceptions=True)
        self._confirmation_tasks.clear()

    async def update(self, action: PendingAction) -> None:
        async with self.lock_for(action.pending_action_id):
            trace_id = self._trace_ids.get(action.pending_action_id)
            if trace_id is None:
                raise KeyError(f"ไม่พบ trace ของ pending action {action.pending_action_id}")
            await self._persist(action, trace_id)
            self._actions[action.pending_action_id] = action

    async def compare_and_set(
        self,
        action: PendingAction,
        expected: PendingActionStatus,
    ) -> bool:
        """Persist a state transition only if the stored state is still expected."""
        async with self.lock_for(action.pending_action_id):
            return await self._compare_and_set_unlocked(action, expected)

    async def claim_confirmation(
        self, action: PendingAction, expected: PendingActionStatus | None = None
    ) -> tuple[bool, asyncio.Event | None]:
        """Claim one confirmation; concurrent callers share the owner's completion event."""
        pending_id = action.pending_action_id
        async with self.lock_for(pending_id):
            current = self._actions.get(action.pending_action_id)
            if current is None:
                return False, None
            if pending_id in self._confirmation_events:
                return False, self._confirmation_events[pending_id]
            if expected is None and current.status is not PendingActionStatus.CONFIRMED:
                return False, None
            if expected is not None and current.status is not expected:
                return False, None
            if expected is not None and not await self._compare_and_set_unlocked(action, expected):
                return False, self._confirmation_events.get(pending_id)
            event = asyncio.Event()
            self._confirmation_events[pending_id] = event
            return True, event

    def finish_confirmation(self, pending_action_id: UUID) -> None:
        event = self._confirmation_events.pop(pending_action_id, None)
        if event is not None:
            event.set()

    async def release_confirmation(
        self, pending_action_id: UUID, confirmed: PendingAction
    ) -> None:
        """Release a claim while retaining durable CONFIRMED state for recovery."""
        del confirmed
        self.finish_confirmation(pending_action_id)

    async def _compare_and_set_unlocked(
        self, action: PendingAction, expected: PendingActionStatus
    ) -> bool:
        current = self._actions.get(action.pending_action_id)
        if current is None or current.status is not expected:
            return False
        trace_id = self._trace_ids[action.pending_action_id]
        if self._db is None:
            self._actions[action.pending_action_id] = action
            return True
        values = self._values(action, trace_id)
        updated = await self._db.run_in_transaction(
            lambda conn: conn.execute(
                "UPDATE pending_action SET tool_slug=?, prepare_action=?, submit_action=?, "
                "prepared_input=?, summary=?, status=?, idempotency_key=?, created_at=?, "
                "updated_at=?, submission_result=?, trace_id=? "
                "WHERE id=? AND status=?",
                values[2:] + (values[0], expected.value),
            ).rowcount
        )
        if updated != 1:
            return False
        self._actions[action.pending_action_id] = action
        return True

    async def clear(self) -> None:
        if self._db is not None:
            updated_at = utc_now().isoformat()

            def _clear_nonterminal(conn: Any) -> None:
                conn.execute(
                    "DELETE FROM pending_action WHERE status = ?",
                    ("pending_confirmation",),
                )
                conn.execute(
                    "UPDATE pending_action SET status = ?, updated_at = ? WHERE status = ?",
                    ("failed", updated_at, "confirmed"),
                )

            await self._db.run_in_transaction(_clear_nonterminal)
        for pending_id, action in tuple(self._actions.items()):
            if action.status.value == "pending_confirmation":
                self._actions.pop(pending_id, None)
                self._trace_ids.pop(pending_id, None)
                self._execution_inputs.pop(pending_id, None)
            elif action.status is PendingActionStatus.CONFIRMED:
                self._actions[pending_id] = action.model_copy(
                    update={"status": PendingActionStatus.FAILED, "updated_at": utc_now()}
                )

    def _load(self) -> None:
        assert self._db is not None
        cipher = self._db.state_cipher()
        rows = self._db.read_all_sync("SELECT * FROM pending_action ORDER BY created_at, id")
        for row in rows:
            submission = (
                ToolResult.model_validate(json.loads(_decrypt_text(cipher, row["submission_result"])))
                if row["submission_result"]
                else None
            )
            stored_input = json.loads(_decrypt_text(cipher, row["prepared_input"]))
            if isinstance(stored_input, dict) and "execution" in stored_input:
                execution_input = stored_input.get("execution")
                public_input = stored_input.get("public", {})
            else:
                execution_input = stored_input
                public_input = stored_input
            if not isinstance(execution_input, dict) or not isinstance(public_input, dict):
                raise RuntimeError("persisted action input is invalid")
            action = PendingAction(
                pending_action_id=UUID(row["id"]),
                conversation_id=UUID(row["conversation_id"]),
                tool_slug=row["tool_slug"],
                prepare_action=row["prepare_action"],
                submit_action=row["submit_action"],
                prepared_input=public_input,
                summary=_decrypt_text(cipher, row["summary"]),
                status=row["status"],
                idempotency_key=_decrypt_text(cipher, row["idempotency_key"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                submission_result=submission,
            )
            pending_id = action.pending_action_id
            self._actions[pending_id] = action
            self._trace_ids[pending_id] = UUID(row["trace_id"])
            self._execution_inputs[pending_id] = execution_input

    async def _persist(self, action: PendingAction, trace_id: UUID) -> None:
        values = self._values(action, trace_id)
        if self._db is None:
            return
        await self._db.run_in_transaction(
            lambda conn: conn.execute(
                "INSERT INTO pending_action "
                "(id, conversation_id, tool_slug, prepare_action, submit_action, "
                "prepared_input, summary, status, idempotency_key, created_at, "
                "updated_at, submission_result, trace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET conversation_id=excluded.conversation_id, "
                "tool_slug=excluded.tool_slug, prepare_action=excluded.prepare_action, "
                "submit_action=excluded.submit_action, prepared_input=excluded.prepared_input, "
                "summary=excluded.summary, status=excluded.status, "
                "idempotency_key=excluded.idempotency_key, created_at=excluded.created_at, "
                "updated_at=excluded.updated_at, submission_result=excluded.submission_result, "
                "trace_id=excluded.trace_id",
                values,
            )
        )

    def _values(self, action: PendingAction, trace_id: UUID) -> tuple[str, ...]:
        cipher = self._db.state_cipher() if self._db is not None else None
        values = (
            str(action.pending_action_id),
            str(action.conversation_id),
            action.tool_slug,
            action.prepare_action,
            action.submit_action,
            _encrypt_text(
                cipher,
                json.dumps(
                    {
                        "execution": _without_forbidden_persistence_fields(
                            self._execution_inputs.get(
                                action.pending_action_id, action.prepared_input
                            )
                        ),
                        "public": _without_forbidden_persistence_fields(
                            redact(action.prepared_input)
                        ),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            ) if cipher else json.dumps(action.prepared_input, ensure_ascii=False, default=str),
            _encrypt_text(cipher, action.summary) if cipher else action.summary,
            action.status.value,
            _encrypt_text(cipher, action.idempotency_key) if cipher else action.idempotency_key,
            action.created_at.isoformat(),
            action.updated_at.isoformat(),
            (
                json.dumps(
                    redact(action.submission_result.model_dump(by_alias=True, mode="json")),
                    ensure_ascii=False,
                    default=str,
                )
                if action.submission_result is not None
                else None
            ),
            str(trace_id),
        )
        if cipher and values[11] is not None:
            values = values[:11] + (_encrypt_text(cipher, values[11]),) + values[12:]
        return values


class TraceStore:
    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._events: dict[UUID, list[TraceEvent]] = {}
        if db is not None:
            self._load()

    async def append(
        self,
        trace_id: UUID,
        kind: TraceEventKind,
        data: dict[str, Any] | None = None,
        *,
        tool_slug: str | None = None,
        action: str | None = None,
        config_version: int | None = None,
        policy: str | None = None,
        channel: str | None = None,
    ) -> TraceEvent:
        redacted = redact(data or {})
        stored_tool_slug = tool_slug or _optional_text(redacted, "name")
        stored_action = action or _optional_text(redacted, "action")
        stored_channel = channel or _TRACE_CHANNEL.get()
        event_id = uuid4()
        at = utc_now()
        if self._db is None:
            sequence = len(self._events.setdefault(trace_id, [])) + 1
        else:
            cipher = self._db.state_cipher()
            def _write(conn: Any) -> int:
                row = conn.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM trace_event WHERE trace_id = ?",
                    (str(trace_id),),
                ).fetchone()
                sequence = int(row[0])
                conn.execute(
                    "INSERT INTO trace_event "
                    "(event_id, trace_id, sequence, at, kind, tool_slug, action, "
                    "config_version, policy, channel, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(event_id), str(trace_id), sequence, at.isoformat(), kind.value,
                        stored_tool_slug,
                        stored_action,
                        config_version,
                        policy,
                        stored_channel,
                        _encrypt_text(cipher, json.dumps(redacted, ensure_ascii=False, default=str)),
                    ),
                )
                return sequence

            sequence = await self._db.run_in_transaction(_write)
        event = TraceEvent(
            event_id=event_id,
            trace_id=trace_id,
            sequence=sequence,
            at=at,
            kind=kind,
            tool_slug=stored_tool_slug,
            action=stored_action,
            config_version=config_version,
            policy=policy,
            channel=stored_channel,
            data=redacted,
        )
        self._events.setdefault(trace_id, []).append(event)
        return event

    def get(self, trace_id: UUID) -> TraceResponse | None:
        events = self._events.get(trace_id)
        if events is None:
            return None
        return TraceResponse(trace_id=trace_id, events=tuple(sorted(events, key=lambda event: event.sequence)))

    def has_kind(
        self,
        trace_id: UUID,
        kind: TraceEventKind,
        *,
        pending_action_id: UUID | None = None,
    ) -> bool:
        """Check an audit event, optionally scoped to one pending action."""
        expected_pending_id = str(pending_action_id) if pending_action_id is not None else None
        return any(
            event.kind is kind
            and (
                expected_pending_id is None
                or event.data.get("pendingActionId") == expected_pending_id
            )
            for event in self._events.get(trace_id, ())
        )

    async def clear(self) -> None:
        """Keep trace history append-only; reset must not erase the audit trail."""
        return None

    def _load(self) -> None:
        assert self._db is not None
        rows = self._db.read_all_sync("SELECT * FROM trace_event ORDER BY trace_id, sequence")
        cipher = self._db.state_cipher()
        for row in rows:
            event = self._event_from_row(row, cipher)
            self._events.setdefault(event.trace_id, []).append(event)

    @staticmethod
    def _event_from_row(row: Any, cipher: Fernet) -> TraceEvent:
        return TraceEvent(
            event_id=UUID(row["event_id"]),
            trace_id=UUID(row["trace_id"]),
            sequence=row["sequence"],
            at=datetime.fromisoformat(row["at"]),
            kind=row["kind"],
            tool_slug=row["tool_slug"],
            action=row["action"],
            config_version=row["config_version"],
            policy=row["policy"],
            channel=row["channel"],
            data=json.loads(_decrypt_text(cipher, row["data"])),
        )


def _optional_text(data: Any, key: str) -> str | None:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _encrypt_text(cipher: Fernet | None, value: str) -> str:
    if cipher is None:
        return value
    return cipher.encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt_text(cipher: Fernet, value: str) -> str:
    try:
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("persisted state cannot be decrypted") from exc
