"""สถานะภายใน process ที่รีเซ็ตได้สำหรับเดโมสองวัน"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.contracts import PendingAction, TraceEvent, TraceEventKind, TraceResponse
from app.llm.models import LLMMessage

_SENSITIVE_KEYS = frozenset({"token", "paymenttoken", "authorization", "password", "secret", "detail", "locationnote", "symptoms"})


def utc_now() -> datetime:
    return datetime.now(UTC)


def redact(value: Any, *, key: str = "") -> Any:
    """เก็บข้อมูลวินิจฉัย trace ให้มีประโยชน์โดยไม่เก็บข้อความหรือ payload ที่ละเอียดอ่อน"""
    if key.lower().replace("_", "") in _SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, key=str(item_key)) for item_key, item_value in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 200:
        return "[redacted]"
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
    def __init__(self) -> None:
        self._actions: dict[UUID, PendingAction] = {}
        self._trace_ids: dict[UUID, UUID] = {}

    def put(self, action: PendingAction, trace_id: UUID) -> None:
        self._actions[action.pending_action_id] = action
        self._trace_ids[action.pending_action_id] = trace_id

    def get(self, pending_action_id: UUID) -> PendingAction | None:
        return self._actions.get(pending_action_id)

    def trace_id_for(self, pending_action_id: UUID) -> UUID | None:
        return self._trace_ids.get(pending_action_id)

    def update(self, action: PendingAction) -> None:
        self._actions[action.pending_action_id] = action

    def clear(self) -> None:
        self._actions.clear()
        self._trace_ids.clear()


class TraceStore:
    def __init__(self) -> None:
        self._events: dict[UUID, list[TraceEvent]] = {}

    def append(self, trace_id: UUID, kind: TraceEventKind, data: dict[str, Any] | None = None) -> TraceEvent:
        event = TraceEvent(
            event_id=uuid4(),
            trace_id=trace_id,
            sequence=len(self._events.setdefault(trace_id, [])) + 1,
            at=utc_now(),
            kind=kind,
            data=redact(data or {}),
        )
        self._events[trace_id].append(event)
        return event

    def get(self, trace_id: UUID) -> TraceResponse | None:
        events = self._events.get(trace_id)
        if events is None:
            return None
        return TraceResponse(trace_id=trace_id, events=tuple(events))

    def clear(self) -> None:
        self._events.clear()
