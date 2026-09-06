"""สะพานเชื่อมระหว่าง Telegram กับ Main Agent

ทำหน้าที่เดียวกับ LineBridge:
- จัดการความปลอดภัยระดับ transport และความสอดคล้องของการทำงานพร้อมกันต่อ chat
- ผูก conversationId และ pendingActionId กับ Telegram chat_id
- รองรับการย้ายกลุ่ม chat จาก group เป็น supergroup ผ่าน migrate_chat
- เรียก agent ภายใต้ trace_channel("telegram")
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agent.main_agent import InvalidActionStateError, NotFoundError
from app.agent.stores import trace_channel
from app.contracts import ChatRequest

_MAX_MESSAGE_LENGTH = 4000
_MAX_NOTE_LENGTH = 500


class TelegramBridgeError(RuntimeError):
    """ข้อผิดพลาดที่แปลงเป็นข้อความปลอดภัยสำหรับตอบกลับผู้ใช้ Telegram แล้ว"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidTextError(TelegramBridgeError):
    def __init__(
        self,
        message: str = "ขออภัยครับ ตอนนี้ผมรับข้อความพิมพ์เท่านั้นครับ",
    ) -> None:
        super().__init__(message)


class TelegramBridge:
    """สะพานประสานงานระหว่าง Telegram chat กับ Main Agent

    ผูก conversationId และ pendingActionId ด้วยคู่ (chat_id, user_id)
    เพื่อป้องกันการกดยืนยันข้ามผู้ใช้ (cross-user) ในกลุ่ม และตรวจสอบ
    pending_action_id เพื่อป้องกันการกดยืนยันผิดรายการ / รายการที่ถูกแทนที่ (stale)
    """

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self._conversation_ids: dict[str, UUID] = {}
        self._pending_action_ids: dict[str, UUID] = {}
        self._active_prompt_ids: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    def _key(self, chat_id: int | str, user_id: int | str | None = None) -> str:
        """สร้าง key สำหรับระบุสถานะของผู้ใช้ในห้องแชตหนึ่ง ๆ"""
        if user_id is None or str(user_id) == str(chat_id):
            return str(chat_id)
        return f"{chat_id}:{user_id}"

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def migrate_chat(self, old_chat_id: int | str, new_chat_id: int | str) -> None:
        """ย้ายสถานะบทสนทนาและรายการรอยืนยันเมื่อกลุ่มอัปเกรดเป็น supergroup (migrate_to_chat_id)

        รักษาอัตลักษณ์ของผู้ใช้แต่ละคนอย่างเคร่งครัด ไม่รวม (merge) ข้อมูลของผู้ใช้ต่างคนเข้าด้วยกัน
        """
        old_prefix = f"{old_chat_id}:"
        new_prefix = f"{new_chat_id}:"

        for store in (self._conversation_ids, self._pending_action_ids, self._active_prompt_ids, self._locks):
            keys = [k for k in store if k.startswith(old_prefix)]
            for k in keys:
                new_k = new_prefix + k[len(old_prefix):]
                store[new_k] = store.pop(k)

            # รองรับกรณี key เก่าที่เป็น chat_id เดี่ยว ๆ
            old_single = str(old_chat_id)
            if old_single in store:
                store[str(new_chat_id)] = store.pop(old_single)

    async def handle_chat(
        self,
        chat_id: int | str,
        message: str,
        user_id: int | str | None = None,
    ) -> dict[str, Any]:
        """ส่งข้อความหนึ่งรอบไปยัง Main Agent แล้วคืนผลลัพธ์แบบ camelCase dict"""
        key = self._key(chat_id, user_id)
        async with await self._lock_for(key):
            text = message.strip() if isinstance(message, str) else ""
            if not text:
                raise InvalidTextError()
            conversation_id = self._conversation_ids.get(key)
            try:
                request = ChatRequest(conversation_id=conversation_id, message=text)
            except ValidationError as exc:
                raise InvalidTextError(
                    f"ข้อความยาวเกินกำหนด (สูงสุด {_MAX_MESSAGE_LENGTH} ตัวอักษร) กรุณาลองอีกครั้งครับ"
                ) from exc

            with trace_channel("telegram"):
                response = await self._agent.handle_chat(request)

            self._conversation_ids[key] = response.conversation_id
            if response.pending_action is not None:
                self._pending_action_ids[key] = response.pending_action.pending_action_id
            if response.choice_prompt is not None:
                self._active_prompt_ids[key] = response.choice_prompt.prompt_id
            return response.model_dump(mode="json", by_alias=True)

    async def start_new_chat(
        self,
        chat_id: int | str,
        user_id: int | str | None = None,
    ) -> None:
        """เริ่มบทสนทนาใหม่: ล้าง conversation และ pending action ของผู้ใช้ใน chat นี้"""
        key = self._key(chat_id, user_id)
        async with await self._lock_for(key):
            self._conversation_ids.pop(key, None)
            self._pending_action_ids.pop(key, None)
            self._active_prompt_ids.pop(key, None)

    async def confirm_action(
        self,
        chat_id: int | str,
        user_id: int | str | None = None,
        pending_action_id: UUID | None = None,
        confirmation_note: str | None = None,
    ) -> dict[str, Any]:
        """ยืนยัน pending action ของผู้ใช้ใน chat นี้

        ตรวจสอบความสอดคล้องของ pending_action_id เพื่อป้องกันการกดยืนยันรายการเก่าที่ถูกแทนที่แล้ว
        """
        key = self._key(chat_id, user_id)
        async with await self._lock_for(key):
            current_pending_id = self._pending_action_ids.get(key)
            if current_pending_id is None:
                raise TelegramBridgeError("ไม่มีรายการที่รอการยืนยันในขณะนี้ครับ")

            if pending_action_id is not None and current_pending_id != pending_action_id:
                raise TelegramBridgeError("รายการนี้ถูกแทนที่หรือหมดอายุแล้วครับ")

            note = confirmation_note.strip() if confirmation_note else None
            if note and len(note) > _MAX_NOTE_LENGTH:
                note = note[:_MAX_NOTE_LENGTH]

            try:
                with trace_channel("telegram"):
                    decision = await self._agent.confirm_pending_action(
                        current_pending_id,
                        confirmation_note=note,
                    )
            except NotFoundError as exc:
                self._pending_action_ids.pop(key, None)
                raise TelegramBridgeError("ไม่พบรายการที่ต้องการยืนยัน อาจหมดอายุแล้วครับ") from exc
            except InvalidActionStateError as exc:
                raise TelegramBridgeError(str(exc)) from exc

            pending = decision.pending_action
            if pending.status.value in {"submitted", "failed", "rejected"}:
                self._pending_action_ids.pop(key, None)
                self._active_prompt_ids.pop(key, None)
            return decision.model_dump(mode="json", by_alias=True)

    async def confirm_current(
        self,
        chat_id: int | str,
        confirmation_note: str | None = None,
        user_id: int | str | None = None,
    ) -> dict[str, Any]:
        """ยืนยันรายการปัจจุบัน (alias เพื่อความเข้ากันได้แบบเดิม)"""
        return await self.confirm_action(
            chat_id=chat_id,
            user_id=user_id,
            pending_action_id=None,
            confirmation_note=confirmation_note,
        )

    async def reject_action(
        self,
        chat_id: int | str,
        user_id: int | str | None = None,
        pending_action_id: UUID | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """ยกเลิก pending action ของผู้ใช้ใน chat นี้"""
        key = self._key(chat_id, user_id)
        async with await self._lock_for(key):
            current_pending_id = self._pending_action_ids.get(key)
            if current_pending_id is None:
                raise TelegramBridgeError("ไม่มีรายการที่รอการยกเลิกในขณะนี้ครับ")

            if pending_action_id is not None and current_pending_id != pending_action_id:
                raise TelegramBridgeError("รายการนี้ถูกแทนที่หรือหมดอายุแล้วครับ")

            safe_reason = reason.strip() if reason else "ผู้ใช้กดยกเลิกผ่าน Telegram"
            try:
                with trace_channel("telegram"):
                    decision = await self._agent.reject_pending_action(
                        current_pending_id,
                        reason=safe_reason,
                    )
            except NotFoundError as exc:
                self._pending_action_ids.pop(key, None)
                raise TelegramBridgeError("ไม่พบรายการที่ต้องการยกเลิก อาจหมดอายุแล้วครับ") from exc
            except InvalidActionStateError as exc:
                raise TelegramBridgeError(str(exc)) from exc

            self._pending_action_ids.pop(key, None)
            self._active_prompt_ids.pop(key, None)
            return decision.model_dump(mode="json", by_alias=True)

    async def reject_current(
        self,
        chat_id: int | str,
        reason: str | None = None,
        user_id: int | str | None = None,
    ) -> dict[str, Any]:
        """ยกเลิกรายการปัจจุบัน (alias เพื่อความเข้ากันได้แบบเดิม)"""
        return await self.reject_action(
            chat_id=chat_id,
            user_id=user_id,
            pending_action_id=None,
            reason=reason,
        )

    async def handle_choice(
        self,
        chat_id: int | str,
        prompt_id: str | None,
        value: str,
        user_id: int | str | None = None,
    ) -> dict[str, Any]:
        """ส่งการเลือกคำตอบจาก ChoicePrompt ไปยัง Main Agent"""
        key = self._key(chat_id, user_id)
        async with await self._lock_for(key):
            active_prompt = self._active_prompt_ids.get(key)
            if prompt_id is not None and active_prompt is not None and active_prompt != prompt_id:
                raise TelegramBridgeError("ตัวเลือกนี้หมดอายุแล้วครับ กรุณาตอบคำถามล่าสุดครับ")

            conversation_id = self._conversation_ids.get(key)
            try:
                request = ChatRequest(
                    conversation_id=conversation_id,
                    message=value,
                    selected_prompt_id=prompt_id,
                    selected_value=value,
                )
            except ValidationError as exc:
                raise InvalidTextError("ข้อมูลตัวเลือกไม่ถูกต้อง กรุณาลองใหม่ครับ") from exc

            with trace_channel("telegram"):
                response = await self._agent.handle_chat(request)

            self._conversation_ids[key] = response.conversation_id
            if response.pending_action is not None:
                self._pending_action_ids[key] = response.pending_action.pending_action_id
            if response.choice_prompt is not None:
                self._active_prompt_ids[key] = response.choice_prompt.prompt_id
            else:
                self._active_prompt_ids.pop(key, None)
            return response.model_dump(mode="json", by_alias=True)

    def _require_pending(self, key: str) -> UUID:
        pending_id = self._pending_action_ids.get(key)
        if pending_id is None:
            raise TelegramBridgeError("ไม่มีรายการที่รอการยืนยันในขณะนี้ครับ")
        return pending_id
