"""ตัวประสานงาน webhook ของ LINE: event → bridge → ข้อความตอบกลับ

ความรับผิดชอบของโมดูลนี้ (ไม่มีนโยบายธุรกิจ):

- แยกเหตุการณ์จาก webhook ของ LINE (ข้อความ, postback, follow)
- เรียก LINE bridge ซึ่งเป็นสะพานเดียวไปยัง Main Agent
- จัดรูปแบบคำตอบเป็นข้อความ LINE พร้อม citation เป็นปุ่มลิงก์ ป้าย
  simulation ปุ่มยืนยัน/ยกเลิกแบบ postback สำหรับ pending action
  และปุ่มเริ่มบทสนทนาใหม่
- แสดง loading indicator ("...") ระหว่างที่ agent ประมวลผล
- ตอบกลับด้วย reply token เมื่อทำได้ และ fallback เป็น push เมื่อ
  token หมดอายุ (agent loop อาจนานเกิน 1 นาที)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.line.api_client import LineApiClient, LineApiError
from app.line.bridge import LineBridge, LineBridgeError

logger = get_logger(__name__)

# เพดานของ LINE: ข้อความ text ยาวได้ ~2,000 ตัวอักษร และ reply/push
# หนึ่งครั้งส่งได้มากสุด 5 ข้อความ
_MAX_TEXT_CHARS = 1900
_MAX_MESSAGES_PER_CALL = 5

_LOADING_SECONDS = 30
_SIMULATION_NOTICE = "ℹ️ รายการนี้ทำงานบนระบบจำลองเพื่อการสาธิต (ไม่ใช่ระบบ PEA จริง)"

_WELCOME_TEXT = (
    "สวัสดีครับ ผมคือ น้องทัชชี่ พร้อมให้บริการแล้วครับ📌"
)

_POSTBACK_CONFIRM = "action=confirm"
_POSTBACK_REJECT = "action=reject"
_POSTBACK_NEW_CHAT = "action=new_chat"
# ปุ่มเมนู rich menu ส่ง intent เป็นข้อความเข้า flow แชตเดิม เช่น
# "action=intent&text=%E0%B9%81%E0%B8%88%E0%B9%89%E0%B8%87%E0%B9%84%E0%B8%9F%E0%B8%94%E0%B8%B1%E0%B8%9A"
_POSTBACK_INTENT_PREFIX = "action=intent&text="

# เพดานของ LINE: ปุ่ม uri ใน template มีได้ 4 ปุ่ม และ label ยาวสุด 20 ตัวอักษร
_MAX_URI_BUTTONS = 3  # เผื่อปุ่มที่ 4 ไว้ให้ "เริ่มแชทใหม่"
_MAX_BUTTON_LABEL = 20


@dataclass(frozen=True)
class LineWebhookService:
    """บริการจัดการ webhook ของ LINE หนึ่งชุดต่อหนึ่ง channel"""

    secret: str
    client: LineApiClient
    bridge: LineBridge

    async def handle_events(self, events: list[dict[str, Any]]) -> None:
        """ประมวลผลทุก event ของ webhook หนึ่งครั้งตามลำดับ"""
        for event in events:
            try:
                await self._handle_event(event)
            except Exception:
                # บันทึกให้เห็นแต่ไม่ทำให้ event ถัดไปตายตาม
                logger.exception("ประมวลผล LINE event ไม่สำเร็จ")

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "message":
            await self._handle_message_event(event)
        elif event_type == "postback":
            await self._handle_postback_event(event)
        elif event_type == "follow":
            user_id = _user_id_of(event)
            if user_id:
                await self._reply_or_push(
                    user_id, _reply_token_of(event), _welcome_messages()
                )

    async def _handle_message_event(self, event: dict[str, Any]) -> None:
        user_id = _user_id_of(event)
        reply_token = _reply_token_of(event)
        if not user_id or not reply_token:
            return
        message = event.get("message") or {}
        if message.get("type") != "text":
            await self._reply_or_push(
                user_id, reply_token,
                [{"type": "text", "text": "ขออภัยครับ ตอนนี้ผมรับข้อความพิมพ์เท่านั้นครับ"}],
            )
            return
        text = str(message.get("text") or "").strip()
        if not text:
            return

        # ให้ผู้ใช้เห็น "..." ว่าระบบกำลังทำงานก่อนเริ่ม agent loop
        await self._show_loading_best_effort(user_id)

        try:
            response = await self.bridge.handle_chat(user_id, text)
        except LineBridgeError as exc:
            await self._reply_or_push(user_id, reply_token, [
                {"type": "text", "text": exc.message}
            ])
            return
        except Exception:
            logger.exception("LINE chat turn ล้มเหลว")
            await self._reply_or_push(user_id, reply_token, [
                {"type": "text", "text": "ขออภัยครับ เกิดข้อผิดพลาดภายในระบบ กรุณาลองอีกครั้งครับ"}
            ])
            return

        messages = format_chat_messages(response)
        await self._reply_or_push(user_id, reply_token, messages)

    async def _handle_postback_event(self, event: dict[str, Any]) -> None:
        user_id = _user_id_of(event)
        reply_token = _reply_token_of(event)
        if not user_id or not reply_token:
            return
        data = str((event.get("postback") or {}).get("data") or "")

        if data == _POSTBACK_NEW_CHAT:
            await self.bridge.start_new_chat(user_id)
            messages = [{"type": "text", "text": _WELCOME_TEXT}]
        elif data.startswith(_POSTBACK_INTENT_PREFIX):
            intent_text = data[len(_POSTBACK_INTENT_PREFIX):].strip()
            if not intent_text:
                messages = [{"type": "text", "text": "ไม่เข้าใจคำสั่งนี้ครับ กรุณาใช้ปุ่มในข้อความที่ระบบส่งให้ครับ"}]
            else:
                await self._show_loading_best_effort(user_id)
                try:
                    response = await self.bridge.handle_chat(user_id, intent_text)
                except LineBridgeError as exc:
                    await self._reply_or_push(user_id, reply_token, [
                        {"type": "text", "text": exc.message}
                    ])
                    return
                except Exception:
                    logger.exception("LINE intent postback ล้มเหลว")
                    await self._reply_or_push(user_id, reply_token, [
                        {"type": "text", "text": "ขออภัยครับ เกิดข้อผิดพลาดภายในระบบ กรุณาลองอีกครั้งครับ"}
                    ])
                    return
                messages = format_chat_messages(response)
        elif data == _POSTBACK_CONFIRM:
            await self._show_loading_best_effort(user_id)
            try:
                decision = await self.bridge.confirm_current(user_id)
            except LineBridgeError as exc:
                await self._reply_or_push(user_id, reply_token, [
                    {"type": "text", "text": exc.message}
                ])
                return
            except Exception:
                logger.exception("LINE confirm ล้มเหลว")
                await self._reply_or_push(user_id, reply_token, [
                    {"type": "text", "text": "ขออภัยครับ ยืนยันไม่สำเร็จ กรุณาลองอีกครั้งครับ"}
                ])
                return
            messages = format_confirm_result_messages(decision)
        elif data == _POSTBACK_REJECT:
            try:
                decision = await self.bridge.reject_current(user_id)
            except LineBridgeError as exc:
                await self._reply_or_push(user_id, reply_token, [
                    {"type": "text", "text": exc.message}
                ])
                return
            except Exception:
                logger.exception("LINE reject ล้มเหลว")
                await self._reply_or_push(user_id, reply_token, [
                    {"type": "text", "text": "ขออภัยครับ ยกเลิกไม่สำเร็จ กรุณาลองอีกครั้งครับ"}
                ])
                return
            messages = format_reject_result_messages(decision)
        else:
            # postback ที่ไม่รู้จัก: ปฏิเสธแบบ fail closed ไม่เดาเจตนา
            messages = [{"type": "text", "text": "ไม่เข้าใจคำสั่งนี้ครับ กรุณาใช้ปุ่มในข้อความที่ระบบส่งให้ครับ"}]

        await self._reply_or_push(user_id, reply_token, messages)

    async def _show_loading_best_effort(self, user_id: str) -> None:
        """แสดง "..." ก่อนเริ่มงานที่นาน ถ้าล้มเหลวไม่ถือว่าร้ายแรง"""
        try:
            await self.client.show_loading_indicator(user_id, _LOADING_SECONDS)
        except LineApiError:
            logger.warning("แสดง LINE loading indicator ไม่สำเร็จ")

    async def _reply_or_push(
        self,
        user_id: str,
        reply_token: str | None,
        messages: list[dict[str, Any]],
    ) -> None:
        """ตอบด้วย reply token ก่อน ถ้าใช้ไม่ได้แล้ว fallback เป็น push

        reply ใช้ได้ครั้งเดียวและส่งได้มากสุด 5 ข้อความ ส่วนเกินจึงไป
        ทาง push ต่อชุดละ 5 ข้อความ
        """
        first_batch, rest = (
            messages[:_MAX_MESSAGES_PER_CALL],
            messages[_MAX_MESSAGES_PER_CALL:],
        )
        try:
            if reply_token:
                await self.client.reply_message(reply_token, first_batch)
            else:
                await self.client.push_message(user_id, first_batch)
        except LineApiError as exc:
            # reply token หมดอายุ (agent นานเกิน 1 นาที) → push ทั้งชุดแทน
            logger.warning("LINE reply ล้มเหลว ใช้ push แทน", extra={"status_code": exc.status_code})
            await self.client.push_message(user_id, messages[:_MAX_MESSAGES_PER_CALL])
            rest = messages[_MAX_MESSAGES_PER_CALL:]

        for offset in range(0, len(rest), _MAX_MESSAGES_PER_CALL):
            await self.client.push_message(user_id, rest[offset:offset + _MAX_MESSAGES_PER_CALL])


def _welcome_messages() -> list[dict[str, Any]]:
    """ข้อความต้อนรับพร้อมปุ่มเริ่มบทสนทนาใหม่"""
    return [
        {"type": "text", "text": _WELCOME_TEXT},
        {
            "type": "template",
            "altText": "เริ่มบทสนทนาใหม่ได้จากปุ่มนี้",
            "template": {
                "type": "buttons",
                "text": "ต้องการเริ่มบทสนทนาใหม่หรือไม่ครับ",
                "actions": [
                    {"type": "postback", "label": "เริ่มแชทใหม่", "data": _POSTBACK_NEW_CHAT},
                ],
            },
        },
    ]


def format_chat_messages(response: dict[str, Any]) -> list[dict[str, Any]]:
    """แปลง ChatResponse (camelCase dict) เป็นข้อความ LINE

    องค์ประกอบตามลำดับ: คำตอบ (ตัดเป็นหลายข้อความถ้ายาว) → citation →
    ป้าย simulation → สรุป pending action + ปุ่มยืนยัน/ยกเลิกแบบ postback
    """
    messages: list[dict[str, Any]] = []
    text = str(response.get("message") or "").strip()
    if not text:
        text = "ไม่พบคำตอบสำหรับคำถามนี้ครับ"
    for part in _split_text(text):
        messages.append({"type": "text", "text": part})

    citations = response.get("citations") or []
    if citations:
        messages.extend(_citation_messages(citations))

    tool_results = response.get("toolResults") or []
    if any(tool_result.get("simulation") for tool_result in tool_results):
        messages.append({"type": "text", "text": _SIMULATION_NOTICE})

    pending_action = response.get("pendingAction")
    if pending_action is not None:
        messages.extend(_pending_action_messages(pending_action))

    messages = _attach_new_chat_quick_reply(messages)
    return messages


def _attach_new_chat_quick_reply(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """แนบ quickReply "เริ่มแชทใหม่" ท้ายข้อความ text สุดท้าย

    quickReply ไม่กินพื้นที่เพิ่มเป็นข้อความ ผู้ใช้จึงเริ่มบทสนทนาใหม่ได้
    ทุกรอบ แม้คำตอบไม่มี citation หรือปุ่มอื่น
    """
    for message in reversed(messages):
        if message.get("type") == "text":
            message["quickReply"] = {
                "items": [
                    {
                        "type": "action",
                        "action": {
                            "type": "postback",
                            "label": "เริ่มแชทใหม่",
                            "data": _POSTBACK_NEW_CHAT,
                        },
                    }
                ]
            }
            break
    return messages


def format_confirm_result_messages(decision: dict[str, Any]) -> list[dict[str, Any]]:
    """แปลงผลการยืนยันเป็นข้อความตอบกลับตามสถานะสิ้นสุด"""
    pending_action = decision.get("pendingAction") or {}
    summary = str(pending_action.get("summary") or "")
    status = str(pending_action.get("status") or "")
    if status == "submitted":
        return [{"type": "text", "text": f"✅ ยืนยันสำเร็จ ส่งรายการแล้ว (ระบบจำลอง)\n{summary}"}]
    if status == "failed":
        return [{"type": "text", "text": f"❌ การส่งรายการล้มเหลว กรุณาลองใหม่อีกครั้งครับ\n{summary}"}]
    return [{"type": "text", "text": f"รายการอยู่ในสถานะ {status} แล้วครับ"}]


def format_reject_result_messages(decision: dict[str, Any]) -> list[dict[str, Any]]:
    """แปลงผลการปฏิเสธเป็นข้อความตอบกลับ (เป็นสถานะสิ้นสุดเสมอ)"""
    return [{"type": "text", "text": "ยกเลิกรายการเรียบร้อยครับ ✋"}]


def _citation_messages(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """สร้างข้อความแหล่งอ้างอิง: บทสรุปข้อความ + ปุ่มเปิดเอกสาร (uri) + ปุ่มเริ่มแชทใหม่

    ปุ่ม uri ได้มากสุด 3 ปุ่ม (เผื่อช่องที่ 4 ให้ปุ่มเริ่มแชทใหม่) และ
    ไม่ฝังข้อมูลอื่นนอกจากลิงก์ที่ citation ระบุมาแล้ว
    """
    lines = ["แหล่งอ้างอิง:"]
    actions: list[dict[str, Any]] = []
    for citation in citations:
        title = str(citation.get("title") or "เอกสาร")
        page = citation.get("page")
        lines.append(f"• {title}" + (f" (หน้า {page})" if page else ""))
        uri = str(citation.get("uri") or "")
        if uri.startswith(("http://", "https://")) and len(actions) < _MAX_URI_BUTTONS:
            actions.append({
                "type": "uri",
                "label": _truncate_button_label(title),
                "uri": uri,
            })
    messages = [phase for part in _split_text("\n".join(lines)) for phase in [{"type": "text", "text": part}]]
    if actions:
        actions.append({
            "type": "postback",
            "label": "เริ่มแชทใหม่",
            "data": _POSTBACK_NEW_CHAT,
        })
        messages.append({
            "type": "template",
            "altText": "แหล่งอ้างอิง — กดปุ่มเพื่อเปิดเอกสาร หรือเริ่มบทสนทนาใหม่",
            "template": {
                "type": "buttons",
                "text": "เปิดเอกสารอ้างอิง หรือเริ่มบทสนทนาใหม่",
                "actions": actions,
            },
        })
    return messages


def _truncate_button_label(text: str) -> str:
    """ตัดป้ายปุ่มให้อยู่ในเพดาน 20 ตัวอักษรของ LINE"""
    return text if len(text) <= _MAX_BUTTON_LABEL else text[:_MAX_BUTTON_LABEL - 1] + "…"


def _pending_action_messages(pending_action: dict[str, Any]) -> list[dict[str, Any]]:
    """สร้างข้อความสรุปรายการ + ปุ่มยืนยัน/ยกเลิกแบบ confirm template

    ปุ่มส่ง postback เท่านั้น และไม่ฝัง pendingActionId ในข้อมูลปุ่ม
    เพราะ bridge ผูกรายการกับผู้ใช้อยู่แล้ว (fail closed เมื่อไม่มีรายการ)
    """
    summary = str(pending_action.get("summary") or "รายการที่รอการยืนยัน")
    summary_messages = [
        {"type": "text", "text": f"รายการที่รอการยืนยัน:\n{summary}\n\n{_SIMULATION_NOTICE}"},
    ]
    template = {
        "type": "template",
        "altText": "กรุณายืนยันหรือยกเลิกรายการ",
        "template": {
            "type": "confirm",
            "text": "ยืนยันการดำเนินการนี้หรือไม่ครับ",
            "actions": [
                {"type": "postback", "label": "ยืนยัน", "data": _POSTBACK_CONFIRM},
                {"type": "postback", "label": "ยกเลิก", "data": _POSTBACK_REJECT},
            ],
        },
    }
    return summary_messages + [template]


def _split_text(text: str, limit: int = _MAX_TEXT_CHARS) -> list[str]:
    """ตัดข้อความยาวให้อยู่ในเพดานต่อข้อความของ LINE

    พยายามตัดที่บรรทัดก่อน ถ้าบรรทัดเดียวยาวเกินจึงตัดหยาบ ๆ ตามความยาว
    """
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _user_id_of(event: dict[str, Any]) -> str | None:
    source = event.get("source") or {}
    user_id = source.get("userId")
    return str(user_id) if user_id else None


def _reply_token_of(event: dict[str, Any]) -> str | None:
    token = event.get("replyToken")
    return str(token) if token else None
