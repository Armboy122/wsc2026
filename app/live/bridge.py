"""Voice bridge แบบผูกกับเซสชัน: ตัวกลางบาง ๆ ระหว่าง Gemini Live และ Main Agent

ข้อกำหนดด้านความปลอดภัยของ bridge นี้:

- เรียก Main Agent ได้เพียง ``handle_chat`` / ``confirm_pending_action`` /
  ``reject_pending_action`` เท่านั้น ไม่มีการแตะ ToolRegistry หรือ backend ธุรกิจ
- **ไม่รับ pending action id จากโมเดล**: การยืนยัน/ปฏิเสธไม่รับ id เป็น
  อาร์กิวเมนต์ ใช้เฉพาะ id ที่ bridge เก็บไว้ภายใน (เก็บแค่ id ของรายการ
  ปัจจุบันเท่านั้น และแทนที่เมื่อมีรายการใหม่)
- **Fail closed**: เมื่อไม่มี pending action ในเซสชัน การยืนยัน/ปฏิเสธ
  จะยก ``NoPendingActionError`` ที่มีข้อความปลอดภัยต่อผู้ใช้แทนการส่งต่อ id
- **ล้างสถานะสิ้นสุด**: ทันทีที่ยืนยันหรือปฏิเสธเสร็จ (submitted / rejected /
  failed) bridge จะล้าง id ที่เก็บไว้ ทำให้การยืนยันซ้ำ fail closed
- คง ``conversation_id`` เดียวกันตลอดอายุของเซสชัน WebSocket หนึ่งครั้ง

หนึ่งอินสแตนซ์ให้บริการหนึ่ง WebSocket session เท่านั้น และ caller ต้องไม่
เรียกเมทอดของ bridge พร้อมกัน (การทำงานเป็น ``async`` และมี lock ภายใน)
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.contracts import ActionDecisionResponse, ChatRequest, PendingActionStatus
from app.live.models import ChatTurnResult, MainAgentGateway

_TERMINAL_STATUSES = frozenset({
    PendingActionStatus.SUBMITTED,
    PendingActionStatus.REJECTED,
    PendingActionStatus.FAILED,
})

_MAX_MESSAGE_LENGTH = 4000
_MAX_NOTE_LENGTH = 500
_MAX_REASON_LENGTH = 500


class VoiceBridgeError(RuntimeError):
    """ข้อผิดพลาด fail-closed ของ voice bridge พร้อมข้อความที่ปลอดภัยต่อผู้ใช้"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        """รูป JSON ที่ voice backend ส่งกลับไปหาโมเดล/ไคลเอนต์ได้ทันที"""
        return {"error": {"code": self.code, "message": self.message}}


class NoPendingActionError(VoiceBridgeError):
    """ไม่มีรายการที่รอการยืนยันในเซสชันนี้"""

    def __init__(self) -> None:
        super().__init__(
            "no_pending_action",
            "ยังไม่มีรายการที่รอการยืนยันในเซสชันนี้ครับ",
        )


class InvalidTextError(VoiceBridgeError):
    """ข้อความเสียง/พิมพ์หรืออาร์กิวเมนต์ไม่ถูกต้องตามสัญญา"""

    def __init__(self, message: str = "ไม่ได้รับข้อความที่ชัดเจน กรุณาลองอีกครั้งครับ") -> None:
        super().__init__("invalid_input", message)


class ActionConflictError(VoiceBridgeError):
    """สถานะปัจจุบันไม่อนุญาตให้ยืนยันหรือปฏิเสธรายการนี้"""

    def __init__(self) -> None:
        super().__init__(
            "action_conflict",
            "รายการนี้ไม่สามารถดำเนินการได้ในสถานะปัจจุบันครับ",
        )


class VoiceBridge:
    """bridge แบบผูกกับเซสชันที่ส่งต่อข้อความและคำตัดสินไปยัง Main Agent

    อาร์กิวเมนต์ ``agent`` ต้องเป็นไปตาม ``MainAgentGateway`` ซึ่งคลาส
    ``MainAgent`` จริงมีคุณสมบัติครบ (ไม่ต้องมี wrapper เพิ่มเติม)
    """

    def __init__(self, agent: MainAgentGateway) -> None:
        self._agent = agent
        self._conversation_id: UUID | None = None
        self._pending_action_id: UUID | None = None
        self._lock = asyncio.Lock()

    @property
    def conversation_id(self) -> str | None:
        """conversation_id ของเซสชันนี้ (สร้างครั้งแรกที่เรียก ``handle_text``)"""
        return str(self._conversation_id) if self._conversation_id is not None else None

    @property
    def pending_action_id(self) -> str | None:
        """id ของ pending action ปัจจุบันที่ bridge เก็บไว้ หรือ None"""
        return str(self._pending_action_id) if self._pending_action_id is not None else None

    @property
    def has_pending_action(self) -> bool:
        """True เมื่อมีรายการที่รอการยืนยันในเซสชันนี้"""
        return self._pending_action_id is not None

    async def handle_text(self, message: str) -> dict[str, Any]:
        """ส่งข้อความเสียง/พิมพ์หนึ่งรอบไปยัง Main Agent

        คืนค่า ``ChatTurnResult`` แบบ camelCase ที่ปลอดภัยต่อ JSON
        ถ้ารอบนี้มี ``pendingAction`` ใหม่จะแทนที่ id ที่เก็บไว้
        (เก็บเฉพาะ id ของรายการปัจจุบันเท่านั้น)
        """
        async with self._lock:
            text = message.strip() if isinstance(message, str) else ""
            if not text:
                raise InvalidTextError()
            try:
                request = ChatRequest(conversation_id=self._conversation_id, message=text)
            except ValidationError as exc:
                raise InvalidTextError(
                    f"ข้อความยาวเกินกำหนด (สูงสุด {_MAX_MESSAGE_LENGTH} ตัวอักษร) กรุณาลองอีกครั้งครับ"
                ) from exc
            response = await self._agent.handle_chat(request)
            self._conversation_id = response.conversation_id
            if response.pending_action is not None:
                self._pending_action_id = response.pending_action.pending_action_id
            return response.model_dump(mode="json", by_alias=True)

    async def confirm_current(self, confirmation_note: str | None = None) -> dict[str, Any]:
        """ยืนยัน pending action ปัจจุบันของเซสชัน (ไม่รับ id จากโมเดล)

        เรียก ``MainAgent.confirm_pending_action`` ด้วย id ที่เก็บไว้ภายใน
        เมื่อผลเป็นสถานะสิ้นสุดจะล้าง id ทันที หากไม่มี pending action
        จะ fail closed ด้วย ``NoPendingActionError``
        """
        async with self._lock:
            pending_action_id = self._require_pending()
            note = self._normalize_optional_text(confirmation_note, _MAX_NOTE_LENGTH, "confirmationNote")
            try:
                decision = await self._agent.confirm_pending_action(
                    pending_action_id,
                    confirmation_note=note,
                )
            except LookupError as exc:
                self._pending_action_id = None
                raise NoPendingActionError() from exc
            except RuntimeError as exc:
                raise ActionConflictError() from exc
            self._clear_if_terminal(decision)
            return decision.model_dump(mode="json", by_alias=True)

    async def reject_current(self, reason: str) -> dict[str, Any]:
        """ปฏิเสธ pending action ปัจจุบันของเซสชัน (ไม่รับ id จากโมเดล)

        เรียก ``MainAgent.reject_pending_action`` ด้วย id ที่เก็บไว้ภายใน
        และเหตุผลที่ผ่านการตรวจสอบ เมื่อผลเป็นสถานะสิ้นสุดจะล้าง id ทันที
        หากไม่มี pending action จะ fail closed ด้วย ``NoPendingActionError``
        """
        async with self._lock:
            pending_action_id = self._require_pending()
            normalized_reason = self._normalize_optional_text(reason, _MAX_REASON_LENGTH, "reason")
            if not normalized_reason:
                raise InvalidTextError("ไม่ได้รับเหตุผลการปฏิเสธที่ชัดเจน กรุณาลองอีกครั้งครับ")
            try:
                decision = await self._agent.reject_pending_action(
                    pending_action_id,
                    reason=normalized_reason,
                )
            except LookupError as exc:
                self._pending_action_id = None
                raise NoPendingActionError() from exc
            except RuntimeError as exc:
                raise ActionConflictError() from exc
            self._clear_if_terminal(decision)
            return decision.model_dump(mode="json", by_alias=True)

    def _require_pending(self) -> UUID:
        if self._pending_action_id is None:
            raise NoPendingActionError()
        return self._pending_action_id

    def _clear_if_terminal(self, decision: ActionDecisionResponse) -> None:
        """ล้าง id ที่เก็บไว้ทันทีที่สถานะสิ้นสุด เพื่อให้การยืนยันซ้ำ fail closed"""
        if decision.pending_action.status in _TERMINAL_STATUSES:
            self._pending_action_id = None

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
