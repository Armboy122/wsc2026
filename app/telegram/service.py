"""ตัวประสานงาน webhook ของ Telegram Bot: update → bridge → ข้อความตอบกลับ

ตามข้อกำหนด V2 T4.4:
- ตรวจ inline keyboard · callback_data <= 64 bytes (ยาวเกิน = ไม่ส่ง)
- เรียก answerCallbackQuery ทุกครั้ง
- editMessageReplyMarkup ปิดปุ่มหลังกดสำหรับ single-use
- รองรับ migrate_to_chat_id เมื่อกลุ่มอัปเกรด
- ยิง httpx ตรงผ่าน TelegramApiClient
"""

from __future__ import annotations

from dataclasses import dataclass, field
import secrets
import threading
import time
from typing import Any
from uuid import UUID

from app.channel import (
    ACTION_NEW_CHAT,
    SIMULATION_NOTICE,
    WELCOME_TEXT,
    format_citations_text,
    split_text,
    truncate_button_label,
)
from app.contracts import Action
from app.core.logging import get_logger
from app.telegram.api_client import TelegramApiClient, TelegramApiError
from app.telegram.bridge import TelegramBridge, TelegramBridgeError

logger = get_logger(__name__)

_TELEGRAM_MAX_TEXT_LENGTH = 4096
_MAX_CALLBACK_DATA_BYTES = 64
_MAX_URI_BUTTONS = 3


@dataclass
class TelegramActionEntry:
    token: str
    chat_id: str
    user_id: str
    kind: str  # "confirm" | "reject" | "pick"
    pending_action_id: UUID | None = None
    prompt_id: str | None = None
    value: str | None = None
    is_used: bool = False
    created_at: float = field(default_factory=time.monotonic)


class TelegramActionRegistry:
    """ตารางจัดเก็บ action callback ที่ผูกกับ sender (user_id), chat_id, และ pendingActionId อย่างแน่นหนา"""

    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: dict[str, TelegramActionEntry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def register(
        self,
        chat_id: int | str,
        user_id: int | str,
        kind: str,
        pending_action_id: UUID | None = None,
        prompt_id: str | None = None,
        value: str | None = None,
    ) -> str:
        """ออก callback token สั้น (act:...) และบันทึกข้อมูลความเป็นเจ้าของ"""
        token = secrets.token_hex(8)
        entry = TelegramActionEntry(
            token=token,
            chat_id=str(chat_id),
            user_id=str(user_id),
            kind=kind,
            pending_action_id=pending_action_id,
            prompt_id=prompt_id,
            value=value,
        )
        with self._lock:
            if len(self._entries) >= self._max_entries:
                keys_to_remove = list(self._entries.keys())[: self._max_entries // 2]
                for k in keys_to_remove:
                    self._entries.pop(k, None)
            self._entries[token] = entry
        return f"act:{token}"

    def get(self, token: str) -> TelegramActionEntry | None:
        with self._lock:
            return self._entries.get(token)

    def mark_used(self, token: str) -> bool:
        """ทำเครื่องหมายว่าถูกใช้งานแล้ว (ป้องกัน replay) คืน True หากสำเร็จ คืน False หากเคยใช้แล้ว"""
        with self._lock:
            entry = self._entries.get(token)
            if entry is None or entry.is_used:
                return False
            entry.is_used = True
            return True

    def migrate_chat(self, old_chat_id: int | str, new_chat_id: int | str) -> None:
        """ปรับปรุง chat_id ของ entries ทั้งหมดเมื่อกลุ่มอัปเกรดเป็น supergroup โดยไม่รวม user identities"""
        old_s = str(old_chat_id)
        new_s = str(new_chat_id)
        with self._lock:
            for entry in self._entries.values():
                if entry.chat_id == old_s:
                    entry.chat_id = new_s


@dataclass
class TelegramWebhookService:
    """บริการจัดการ Telegram webhook หนึ่งชุดต่อหนึ่ง bot"""

    secret: str
    client: TelegramApiClient
    bridge: TelegramBridge
    registry: TelegramActionRegistry = field(default_factory=TelegramActionRegistry)

    async def handle_update(self, update: dict[str, Any]) -> None:
        """ประมวลผล Update object จาก Telegram webhook"""
        try:
            if "message" in update:
                await self._handle_message(update["message"])
            elif "callback_query" in update:
                await self._handle_callback_query(update["callback_query"])
        except Exception:
            logger.exception("ประมวลผล Telegram update ล้มเหลว")

    async def _handle_message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not chat_id:
            return

        from_user = message.get("from") or {}
        user_id = from_user.get("id") or chat_id

        # ตรวจสอบการย้าย chat_id (group -> supergroup migration)
        migrate_to = message.get("migrate_to_chat_id")
        if migrate_to is not None:
            self.bridge.migrate_chat(chat_id, migrate_to)
            self.registry.migrate_chat(chat_id, migrate_to)
            logger.info(
                "ย้าย Telegram chat_id สำเร็จ",
                extra={"old_chat_id": chat_id, "new_chat_id": migrate_to},
            )
            return

        text = str(message.get("text") or "").strip()
        if not text:
            await self.client.send_message(
                chat_id, "ขออภัยครับ ตอนนี้ผมรับข้อความพิมพ์เท่านั้นครับ"
            )
            return

        if text in {"/start", "/new", "เริ่มแชทใหม่"}:
            await self.bridge.start_new_chat(chat_id, user_id=user_id)
            await self.client.send_message(chat_id, WELCOME_TEXT)
            return

        # ส่ง typing indicator แบบ best effort
        await self.client.send_chat_action(chat_id, "typing")

        try:
            response = await self.bridge.handle_chat(chat_id, text, user_id=user_id)
        except TelegramBridgeError as exc:
            await self.client.send_message(chat_id, exc.message)
            return
        except Exception:
            logger.exception("Telegram chat turn ล้มเหลว")
            await self.client.send_message(
                chat_id, "ขออภัยครับ เกิดข้อผิดพลาดภายในระบบ กรุณาลองอีกครั้งครับ"
            )
            return

        parts, reply_markup = format_telegram_chat_messages(
            response,
            chat_id=chat_id,
            user_id=user_id,
            registry=self.registry,
        )
        for i, part in enumerate(parts):
            # แนบ reply_markup ไว้กับข้อความท่อนสุดท้าย
            markup = reply_markup if i == len(parts) - 1 else None
            await self.client.send_message(chat_id, part, reply_markup=markup)

    async def _handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        query_id = str(callback_query.get("id") or "")
        data = str(callback_query.get("data") or "")
        caller_user = callback_query.get("from") or {}
        caller_user_id = caller_user.get("id")

        msg = callback_query.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id") or caller_user_id
        message_id = msg.get("message_id")

        answered = False
        try:
            if data.startswith("act:"):
                token = data[len("act:"):]
                entry = self.registry.get(token)
                if entry is None:
                    await self.client.answer_callback_query(
                        query_id, text="คำสั่งนี้ไม่รองรับหรือหมดอายุแล้วครับ", show_alert=True
                    )
                    answered = True
                    return

                # ตรวจสอบ chat_id
                if str(chat_id) != str(entry.chat_id):
                    await self.client.answer_callback_query(
                        query_id, text="คำสั่งนี้ไม่ถูกต้องสำหรับห้องแชตนี้ครับ", show_alert=True
                    )
                    answered = True
                    return

                # 🔒 ตรวจสอบ sender (ป้องกัน cross-user confirmation)
                if str(caller_user_id) != str(entry.user_id):
                    await self.client.answer_callback_query(
                        query_id,
                        text="คุณไม่มีสิทธิ์ทำรายการนี้ครับ (ไม่ใช่เจ้าของคำขอ)",
                        show_alert=True,
                    )
                    answered = True
                    return

                # 🔒 ตรวจสอบ replay
                if not self.registry.mark_used(token):
                    await self.client.answer_callback_query(
                        query_id, text="ปุ่มนี้ถูกใช้งานไปแล้วครับ", show_alert=True
                    )
                    answered = True
                    return

                # ลบปุ่มเดิมออกทันทีหลังกดเพื่อแสดงว่าเป็น single-use
                if chat_id and message_id:
                    try:
                        await self.client.edit_message_reply_markup(
                            chat_id, message_id, reply_markup=None
                        )
                    except TelegramApiError:
                        logger.warning("editMessageReplyMarkup ล้มเหลว")


                if entry.kind == "confirm":
                    decision = await self.bridge.confirm_action(
                        chat_id=entry.chat_id,
                        user_id=entry.user_id,
                        pending_action_id=entry.pending_action_id,
                    )
                    await self.client.answer_callback_query(query_id, text="ยืนยันสำเร็จ")
                    answered = True
                    result_text = _format_confirm_result(decision)
                    await self.client.send_message(chat_id, result_text)
                elif entry.kind == "reject":
                    decision = await self.bridge.reject_action(
                        chat_id=entry.chat_id,
                        user_id=entry.user_id,
                        pending_action_id=entry.pending_action_id,
                    )
                    await self.client.answer_callback_query(
                        query_id, text="ยกเลิกรายการเรียบร้อย"
                    )
                    answered = True
                    await self.client.send_message(chat_id, "ยกเลิกรายการเรียบร้อยครับ ✋")
                elif entry.kind == "pick":
                    response = await self.bridge.handle_choice(
                        chat_id=entry.chat_id,
                        prompt_id=entry.prompt_id,
                        value=entry.value or "",
                        user_id=entry.user_id,
                    )
                    await self.client.answer_callback_query(query_id)
                    answered = True
                    parts, reply_markup = format_telegram_chat_messages(
                        response,
                        chat_id=entry.chat_id,
                        user_id=entry.user_id,
                        registry=self.registry,
                    )
                    for i, part in enumerate(parts):
                        markup = reply_markup if i == len(parts) - 1 else None
                        await self.client.send_message(chat_id, part, reply_markup=markup)
            elif data == ACTION_NEW_CHAT:
                if chat_id and message_id:
                    try:
                        await self.client.edit_message_reply_markup(
                            chat_id, message_id, reply_markup=None
                        )
                    except TelegramApiError:
                        pass
                await self.bridge.start_new_chat(chat_id, user_id=caller_user_id)
                await self.client.answer_callback_query(query_id, text="เริ่มแชทใหม่เรียบร้อย")
                answered = True
                await self.client.send_message(chat_id, WELCOME_TEXT)
            else:
                # 🔒 ปฏิเสธ callback แปลกปลอมหรือไม่มีการลงทะเบียน (forged callback fail-closed)
                await self.client.answer_callback_query(
                    query_id, text="คำสั่งนี้ไม่รองรับหรือหมดอายุแล้วครับ", show_alert=True
                )
                answered = True
        except TelegramBridgeError as exc:
            if not answered:
                await self.client.answer_callback_query(
                    query_id, text=exc.message, show_alert=True
                )
                answered = True
            await self.client.send_message(chat_id, exc.message)
        except Exception:
            logger.exception("ประมวลผล Telegram callback query ล้มเหลว")
            if not answered:
                await self.client.answer_callback_query(
                    query_id, text="เกิดข้อผิดพลาดในการประมวลผลครับ", show_alert=True
                )
                answered = True
        finally:
            # ต้องเรียก answerCallbackQuery ทุกครั้งอย่างแน่นอนตามกฎ 🔒
            if not answered and query_id:
                try:
                    await self.client.answer_callback_query(query_id)
                except Exception:
                    pass


def format_telegram_chat_messages(
    response: dict[str, Any],
    chat_id: int | str | None = None,
    user_id: int | str | None = None,
    registry: TelegramActionRegistry | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    """จัดรูปแบบคำตอบสำหรับ Telegram: ข้อความตัวอักษร + InlineKeyboardMarkup"""
    text_blocks: list[str] = []
    message_text = str(response.get("message") or "").strip()
    if not message_text:
        message_text = "ไม่พบคำตอบสำหรับคำถามนี้ครับ"
    text_blocks.append(message_text)

    citations = response.get("citations") or []
    if citations:
        text_blocks.append(format_citations_text(citations))

    tool_results = response.get("toolResults") or []
    is_simulated = bool(response.get("simulation")) or any(
        tool_result.get("simulation") for tool_result in tool_results
    )
    if is_simulated:
        text_blocks.append(SIMULATION_NOTICE)

    pending_action = response.get("pendingAction")
    if pending_action is not None:
        summary = str(pending_action.get("summary") or "รายการที่รอการยืนยัน")
        text_blocks.append(f"รายการที่รอการยืนยัน:\n{summary}")

    full_text = "\n\n".join(text_blocks)
    parts = split_text(full_text, _TELEGRAM_MAX_TEXT_LENGTH)

    actions_to_render: list[Action] = []
    if chat_id is not None and user_id is not None and registry is not None:
        # ผูก action กับ sender (user_id), chat_id, และ pendingActionId
        if pending_action is not None:
            raw_pa_id = pending_action.get("pending_action_id") or pending_action.get("pendingActionId")
            pa_id = UUID(str(raw_pa_id)) if raw_pa_id else None
            confirm_cb = registry.register(
                chat_id=chat_id,
                user_id=user_id,
                kind="confirm",
                pending_action_id=pa_id,
            )
            reject_cb = registry.register(
                chat_id=chat_id,
                user_id=user_id,
                kind="reject",
                pending_action_id=pa_id,
            )
            actions_to_render.append(
                Action(label="ยืนยัน", value=confirm_cb, kind="confirm", single_use=True)
            )
            actions_to_render.append(
                Action(label="ยกเลิก", value=reject_cb, kind="reject", single_use=True)
            )

        choice_prompt = response.get("choicePrompt")
        if choice_prompt is not None:
            prompt_id = choice_prompt.get("promptId") or choice_prompt.get("prompt_id")
            options = choice_prompt.get("options") or ()
            for opt in options:
                opt_label = str(opt.get("label") or opt.get("value") or "")
                opt_val = str(opt.get("value") or "")
                pick_cb = registry.register(
                    chat_id=chat_id,
                    user_id=user_id,
                    kind="pick",
                    prompt_id=prompt_id,
                    value=opt_val,
                )
                actions_to_render.append(
                    Action(label=opt_label, value=pick_cb, kind="pick", single_use=True)
                )
    else:
        # Fallback กรณีไม่มี context ของห้องแชต/ผู้ใช้
        actions_to_render = list(response.get("actions") or ())

    reply_markup = build_inline_keyboard(
        actions=actions_to_render,
        citations=citations,
    )
    return parts, reply_markup


def build_inline_keyboard(
    actions: Any = (),
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """สร้าง InlineKeyboardMarkup โดยกรอง callback_data ไม่ให้เกิน 64 bytes"""
    rows: list[list[dict[str, Any]]] = []

    action_buttons: list[dict[str, Any]] = []
    for action in actions:
        if isinstance(action, dict):
            label = str(action.get("label") or "")
            val = str(action.get("value") or "")
            kind = action.get("kind")
        else:
            label = str(getattr(action, "label", "") or "")
            val = str(getattr(action, "value", "") or "")
            kind = getattr(action, "kind", None)

        if kind == "link":
            if val.startswith(("http://", "https://")):
                action_buttons.append({
                    "text": truncate_button_label(label, 30),
                    "url": val,
                })
        else:
            # ตรวจสอบกฎ 🔒: callback_data ยาวเกิน 64 bytes = ไม่ส่ง
            if len(val.encode("utf-8")) > _MAX_CALLBACK_DATA_BYTES:
                continue
            action_buttons.append({
                "text": truncate_button_label(label, 30),
                "callback_data": val,
            })

    if action_buttons:
        if len(action_buttons) == 2:
            rows.append(action_buttons)
        else:
            for btn in action_buttons:
                rows.append([btn])

    if citations:
        citation_buttons: list[dict[str, Any]] = []
        for citation in citations:
            uri = str(citation.get("uri") or "")
            title = str(citation.get("title") or "เอกสาร")
            if uri.startswith(("http://", "https://")) and len(citation_buttons) < _MAX_URI_BUTTONS:
                citation_buttons.append({
                    "text": truncate_button_label(title, 25),
                    "url": uri,
                })
        for btn in citation_buttons:
            rows.append([btn])

    if not rows:
        return None
    return {"inline_keyboard": rows}


def _format_confirm_result(decision: dict[str, Any]) -> str:
    pending = decision.get("pendingAction") or {}
    status = str(pending.get("status") or "")
    summary = str(pending.get("summary") or "")
    if status == "submitted":
        return f"✅ ยืนยันสำเร็จ ส่งรายการแล้ว (ระบบจำลอง)\n{summary}"
    if status == "failed":
        tool_result = decision.get("toolResult") or {}
        error = tool_result.get("error") or {}
        safe_error = str(error.get("message") or "กรุณาลองใหม่อีกครั้งครับ")
        return f"❌ การส่งรายการล้มเหลว\n{safe_error}\n{summary}"
    return f"รายการอยู่ในสถานะ {status} แล้วครับ"

