"""LINE bridge แบบผูกกับผู้ใช้: สะพานระหว่าง webhook ของ LINE และ Main Agent

ข้อกำหนดด้านความปลอดภัย (เหมือน voice bridge ทุกข้อ):

- เรียก Main Agent ได้เฉพาะ ``handle_chat`` / ``confirm_pending_action`` /
  ``reject_pending_action`` ผ่านโปรโตคอล ``MainAgentGateway`` เท่านั้น
- **ไม่รับ pending action id จากผู้ใช้หรือข้อความแชต**: การยืนยัน/ปฏิเสธ
  ใช้เฉพาะ id ที่ bridge เก็บไว้ต่อ LINE user (เก็บเฉพาะรายการล่าสุด)
- **Fail closed**: ไม่มี pending action → ยก ``NoPendingActionError`` พร้อม
  ข้อความปลอดภัยต่อผู้ใช้
- **ล้างสถานะสิ้นสุดทันที**: submitted/rejected/failed → ล้าง id ทันที
  ทำให้การกดปุ่มซ้ำ fail closed
- คง ``conversation_id`` เดียวกันต่อ LINE user ตลอดอายุของ process

สถานะเป็น in-process เหมือน TraceStore/PendingActionStore: restart แล้ว
เริ่มบทสนทนาใหม่ (เป็นข้อจำกัดระดับเดโมที่ PRD ประกาศไว้แล้ว)
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.contracts import ActionDecisionResponse, ChatRequest, PendingActionStatus
from app.live.models import MainAgentGateway

_TERMINAL_STATUSES = frozenset({
    PendingActionStatus.SUBMITTED,
    PendingActionStatus.REJECTED,
    PendingActionStatus.FAILED,
})

_MAX_MESSAGE_LENGTH = 4000
_MAX_NOTE_LENGTH = 500
_MAX_REASON_LENGTH = 500

# เหตุผลเริ่มต้นเมื่อผู้ใช้กดปุ่มยกเลิก (reject ต้องมีเหตุผลตามสัญญา)
_DEFAULT_REJECT_REASON = "ผู้ใช้ยกเลิกผ่านปุ่มใน LINE"


class LineBridgeError(RuntimeError):
    """ข้อผิดพลาด fail-closed ของ LINE bridge พร้อมข้อความปลอดภัยต่อผู้ใช้"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NoPendingActionError(LineBridgeError):
    """ไม่มีรายการที่รอการยืนยันสำหรับผู้ใช้รายนี้"""

    def __init__(self) -> None:
        super().__init__(
            "no_pending_action",
            "ยังไม่มีรายการที่รอการยืนยันสำหรับคุณครับ",
        )


class InvalidTextError(LineBridgeError):
    """ข้อความหรืออาร์กิวเมนต์ไม่ถูกต้องตามสัญญา"""

    def __init__(self, message: str = "ไม่ได้รับข้อความที่ชัดเจน กรุณาลองอีกครั้งครับ") -> None:
        super().__init__("invalid_input", message)


class ActionConflictError(LineBridgeError):
    """สถานะปัจจุบันไม่อนุญาตให้ยืนยันหรือปฏิเสธรายการนี้"""

    def __init__(self) -> None:
        super().__init__(
            "action_conflict",
            "รายการนี้ไม่สามารถดำเนินการได้ในสถานะปัจจุบันครับ",
        )


class LineBridge:
    """สะพานสถานะรายผู้ใช้ที่ส่งต่อข้อความและคำตัดสินไปยัง Main Agent

    หนึ่งอินสแตนซ์ให้บริการผู้ใช้ LINE ทุกคนใน process เดียว โดยแยก lock
    ต่อผู้ใช้เพื่อไม่ให้ข้อความของคนละคนบล็อกกันเอง
    """

    def __init__(self, agent: MainAgentGateway) -> None:
        self._agent = agent
        self._conversation_ids: dict[str, UUID] = {}
        self._pending_action_ids: dict[str, UUID] = {}
        self._user_locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def handle_chat(self, user_id: str, message: str) -> dict[str, Any]:
        """ส่งข้อความหนึ่งรอบไปยัง Main Agent แล้วคืน ChatResponse แบบ camelCase

        ถ้ารอบนี้มี ``pendingAction`` ใหม่จะแทนที่ id ของผู้ใช้คนนั้น
        (เก็บเฉพาะ id ของรายการปัจจุบันเท่านั้น)
        """
        async with await self._lock_for(user_id):
            text = message.strip() if isinstance(message, str) else ""
            if not text:
                raise InvalidTextError()
            conversation_id = self._conversation_ids.get(user_id)
            try:
                request = ChatRequest(conversation_id=conversation_id, message=text)
            except ValidationError as exc:
                raise InvalidTextError(
                    f"ข้อความยาวเกินกำหนด (สูงสุด {_MAX_MESSAGE_LENGTH} ตัวอักษร) กรุณาลองอีกครั้งครับ"
                ) from exc
            response = await self._agent.handle_chat(request)
            self._conversation_ids[user_id] = response.conversation_id
            if response.pending_action is not None:
                self._pending_action_ids[user_id] = response.pending_action.pending_action_id
            return response.model_dump(mode="json", by_alias=True)

    async def confirm_current(self, user_id: str, confirmation_note: str | None = None) -> dict[str, Any]:
        """ยืนยัน pending action ปัจจุบันของผู้ใช้รายนี้ (ไม่รับ id จากผู้ใช้)"""
        async with await self._lock_for(user_id):
            pending_action_id = self._require_pending(user_id)
            note = self._normalize_optional_text(confirmation_note, _MAX_NOTE_LENGTH, "confirmationNote")
            try:
                decision = await self._agent.confirm_pending_action(
                    pending_action_id,
                    confirmation_note=note,
                )
            except LookupError as exc:
                self._pending_action_ids.pop(user_id, None)
                raise NoPendingActionError() from exc
            except RuntimeError as exc:
                raise ActionConflictError() from exc
            self._clear_if_terminal(user_id, decision)
            return decision.model_dump(mode="json", by_alias=True)

    async def reject_current(self, user_id: str, reason: str | None = None) -> dict[str, Any]:
        """ปฏิเสธ pending action ปัจจุบันของผู้ใช้รายนี้ (ไม่รับ id จากผู้ใช้)"""
        async with await self._lock_for(user_id):
            pending_action_id = self._require_pending(user_id)
            normalized_reason = self._normalize_optional_text(reason, _MAX_REASON_LENGTH, "reason")
            if not normalized_reason:
                normalized_reason = _DEFAULT_REJECT_REASON
            try:
                decision = await self._agent.reject_pending_action(
                    pending_action_id,
                    reason=normalized_reason,
                )
            except LookupError as exc:
                self._pending_action_ids.pop(user_id, None)
                raise NoPendingActionError() from exc
            except RuntimeError as exc:
                raise ActionConflictError() from exc
            self._clear_if_terminal(user_id, decision)
            return decision.model_dump(mode="json", by_alias=True)

    async def _lock_for(self, user_id: str) -> asyncio.Lock:
        """คืน lock ของผู้ใช้รายนั้น สร้างใหม่พร้อมกันได้อย่างปลอดภัย"""
        async with self._registry_lock:
            lock = self._user_locks.get(user_id)
            if lock is None:
                lock = asyncio.Lock()
                self._user_locks[user_id] = lock
            return lock

    def _require_pending(self, user_id: str) -> UUID:
        pending_action_id = self._pending_action_ids.get(user_id)
        if pending_action_id is None:
            raise NoPendingActionError()
        return pending_action_id

    def _clear_if_terminal(self, user_id: str, decision: ActionDecisionResponse) -> None:
        """ล้าง id ทันทีที่สถานะสิ้นสุด เพื่อให้การกดปุ่มซ้ำ fail closed"""
        if decision.pending_action.status in _TERMINAL_STATUSES:
            self._pending_action_ids.pop(user_id, None)

    @staticmethod
    def _normalize_optional_text(
        value: str | None,
        max_length: int,
        field_name: str,
    ) -> str | None:
        """ตัดช่องว่างและจำกัดความยาวของอาร์กิวเมนต์ข้อความเสริม"""
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidTextError(f"รูปแบบของ {field_name} ไม่ถูกต้อง กรุณาลองอีกครั้งครับ")
        normalized = value.strip()
        if len(normalized) > max_length:
            raise InvalidTextError(
                f"{field_name} ยาวเกินกำหนด (สูงสุด {max_length} ตัวอักษร) กรุณาลองอีกครั้งครับ"
            )
        return normalized or None
