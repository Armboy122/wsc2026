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
from datetime import datetime, timezone
import re
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ValidationError

from app.agent.stores import trace_channel
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
_MAX_RETRIES = 3
_MAX_CORRECTIONS = 3

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

_FIELD_LABELS: dict[str, str] = {
    "ca_number": "หมายเลขผู้ใช้ไฟฟ้า",
    "caNumber": "หมายเลขผู้ใช้ไฟฟ้า",
    "phone": "เบอร์โทรศัพท์",
    "phone_number": "เบอร์โทรศัพท์",
    "phoneNumber": "เบอร์โทรศัพท์",
    "customer_name": "ชื่อผู้ติดต่อ",
    "customerName": "ชื่อผู้ติดต่อ",
    "name": "ชื่อผู้ติดต่อ",
    "description": "รายละเอียด",
    "detail": "รายละเอียด",
    "location": "สถานที่",
    "address": "ที่อยู่",
    "remark": "หมายเหตุ",
    "category": "หมวดหมู่",
    "service_type": "ประเภทบริการ",
    "serviceType": "ประเภทบริการ",
    "amount": "จำนวนเงิน",
    "meter_id": "รหัสมิเตอร์",
    "meterId": "รหัสมิเตอร์",
}

# T6.1 & CONTRACTS-V2 §6.3:
# ปฏิเสธ: ยกเลิก · ไม่ใช่ · ไม่เอา · ผิด · แก้ไข (+ ไม่เอาแล้ว, ไม่ต้องแล้ว, ไม่ต้อง, ขอยกเลิก, หยุดก่อน, ไม่ทำแล้ว, เลิกทำ, cancel)
_REFUSAL_PHRASES: tuple[str, ...] = (
    "ไม่ใช่", "ไม่เอาแล้ว", "ไม่เอา", "ไม่ต้องแล้ว", "ไม่ต้อง",
    "ขอยกเลิก", "หยุดก่อน", "ไม่ทำแล้ว", "เลิกทำ", "cancel",
    "ยกเลิก", "ผิด", "แก้ไข", "แก้", "ไม่ถูกต้อง", "ไม่ยืนยัน", "ไม่ตกลง",
)
_CANCEL_REASON = "ผู้ใช้ปฏิเสธรายการด้วยเสียง"

# ยืนยัน: ยืนยัน · ตกลง · ใช่ (+ครับ/ค่ะ) · ถูกต้อง · เอาเลย
# สังเกต negative lookbehind (?<!ไม่) เพื่อป้องกันกรณี "ไม่ใช่" หลุดมาเข้า confirm
_CONFIRM_PATTERN = re.compile(r"(?<!ไม่)(?:ยืนยัน|ตกลง|ถูกต้อง|เอาเลย|ใช่)")


def match_voice_intent(text: str) -> str:
    """Deterministic refusal-first matching:
    คืนค่า 'refusal' | 'confirm' | 'unrecognized'
    🔒 กติกาความปลอดภัย T6.1: ต้องตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ
    """
    normalized = " ".join(text.casefold().split())
    if not normalized or len(normalized) > 40:
        return "unrecognized"
    # 1. ตรวจชุดปฏิเสธก่อนเสมอ!
    if any(phrase in normalized for phrase in _REFUSAL_PHRASES):
        return "refusal"
    # 2. ตรวจชุดยืนยัน
    if _CONFIRM_PATTERN.search(normalized):
        return "confirm"
    return "unrecognized"


def build_read_back_text(
    pending_action: Any,
    schema_properties: Mapping[str, Any] | None = None,
) -> str:
    """อ่านทวนทุก field ที่จะบันทึกก่อนถามยืนยัน (T6.1)"""
    prepared = getattr(pending_action, "prepared_input", None) or {}
    items: list[str] = []
    for key, val in prepared.items():
        if key.startswith("_") or key in {"idempotency_key", "idempotencyKey", "token", "trace_id", "channel"}:
            continue
        label = None
        if schema_properties and key in schema_properties:
            label = schema_properties[key].get("title")
        if not label:
            label = _FIELD_LABELS.get(key, key.replace("_", " "))
        items.append(f"{label} คือ {val}")
    if items:
        fields_text = " และ ".join(items) if len(items) == 2 else " ".join(items)
        return f"ขออ่านทวนข้อมูลที่จะบันทึกครับ: {fields_text} ข้อมูลถูกต้องหรือไม่ครับ กรุณาตอบ ยืนยัน หรือแจ้งแก้ไขครับ"
    summary = getattr(pending_action, "summary", "รายการรอดำเนินการ")
    return f"ขออ่านทวนข้อมูลที่จะบันทึกครับ: {summary} ข้อมูลถูกต้องหรือไม่ครับ กรุณาตอบ ยืนยัน หรือแจ้งแก้ไขครับ"


def sanitize_confirmation_evidence(text: str) -> str:
    """ขัดเกลาข้อความหลักฐานการยืนยัน ป้องกันข้อมูลอ่อนไหวรั่วไหล (T6.4)"""
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"\b\d{13}\b", "[redacted-id]", cleaned)
    cleaned = re.sub(r"\b\d{16}\b", "[redacted-card]", cleaned)
    cleaned = re.sub(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "[redacted-token]", cleaned)
    if len(cleaned) > 500:
        cleaned = cleaned[:500] + "..."
    return cleaned


def strip_voice_citations(text: str) -> str:
    """ตัด citation markers และ URLs สำหรับช่องทางเสียงตาม T6.3"""
    if not text:
        return ""
    cleaned = re.sub(r"\[\d+\]", "", text)
    cleaned = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    return " ".join(cleaned.split())


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

    def __init__(self, message: str = "รายการนี้ไม่สามารถดำเนินการได้ในสถานะปัจจุบันครับ") -> None:
        super().__init__("action_conflict", message)


class VoiceBridge:
    """bridge แบบผูกกับเซสชันที่ส่งต่อข้อความและคำตัดสินไปยัง Main Agent

    อาร์กิวเมนต์ ``agent`` ต้องเป็นไปตาม ``MainAgentGateway`` ซึ่งคลาส
    ``MainAgent`` จริงมีคุณสมบัติครบ (ไม่ต้องมี wrapper เพิ่มเติม)
    """

    def __init__(self, agent: MainAgentGateway, *, has_display: bool = True) -> None:
        self._agent = agent
        # โหมดเว็บมีจอแสดงการ์ด เสียงจึงไม่ต้องอ่านตัวเลือกซ้ำ
        # ช่องทางที่ไม่มีจอ เช่น สายโทรศัพท์ 1129 ต้องได้ยินตัวเลือกครบทุกข้อ
        self._has_display = has_display
        self._conversation_id: UUID | None = None
        self._pending_action_id: UUID | None = None
        self._current_pending_action: Any | None = None
        self._read_back_text: str | None = None
        self._read_back_completed: bool = False
        self._voice_confirm_allowed: bool = True
        self._consent_granted: bool = False
        self._transcribed_consent: str | None = None
        self._retry_count: int = 0
        self._in_correction_mode: bool = False
        self._correction_count: int = 0
        self._last_rejected_action_id: UUID | None = None
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

    @property
    def read_back_completed(self) -> bool:
        """True เมื่อได้อ่านทวนรายการทั้งหมดแล้ว"""
        return self._read_back_completed

    @property
    def read_back_text(self) -> str | None:
        """ข้อความอ่านทวนรายการปัจจุบันที่เตรียมไว้"""
        return self._read_back_text

    @property
    def in_correction_mode(self) -> bool:
        """True เมื่ออยู่ในโหมดแก้ไขรายการ (T6.2)"""
        return self._in_correction_mode

    @property
    def correction_count(self) -> int:
        return self._correction_count

    @property
    def retry_count(self) -> int:
        return self._retry_count

    def _get_operation_schema(self, tool_slug: str, action: str) -> dict[str, Any] | None:
        fn = getattr(self._agent, "get_operation_schema", None)
        if callable(fn):
            return fn(tool_slug, action)
        return None

    def _get_operation_spec(self, tool_slug: str, action: str) -> Any:
        fn = getattr(self._agent, "get_operation_spec", None)
        if callable(fn):
            return fn(tool_slug, action)
        return None

    async def process_user_transcription(self, text: str) -> None:
        """ประมวลผลข้อความถอดเสียงจริงของผู้ใช้แบบ deterministic matching (T6.1)

        🔒 ข้อกำหนดความปลอดภัย:
        - LLM ไม่มีทางตัดสินคำยินยอม
        - คำยินยอมต้องมาจากเสียงจริงของผู้ใช้เท่านั้น
        - ตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ
        """
        async with self._lock:
            if self._pending_action_id is None:
                return

            intent = match_voice_intent(text)
            if intent == "refusal":
                # Spoken refusal terminates old action immediately
                await self._handle_refusal_locked()
            elif intent == "confirm":
                if self._read_back_completed and self._voice_confirm_allowed:
                    self._consent_granted = True
                    self._transcribed_consent = sanitize_confirmation_evidence(text)
                else:
                    self._consent_granted = False
            else:
                # Ambiguous / unrecognized speech
                if not self._in_correction_mode:
                    self._retry_count += 1
                    if self._retry_count > _MAX_RETRIES:
                        await self._reject_locked("ถามซ้ำเกินกำหนด 3 ครั้ง ยกเลิกรายการ")
                        self._retry_count = 0

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

            # 1. ถ้ามี pending action และไม่ได้อยู่ในโหมดแก้ไข
            if self._pending_action_id is not None and not self._in_correction_mode:
                intent = match_voice_intent(text)
                if intent == "refusal":
                    return await self._handle_refusal_locked()
                elif intent == "confirm":
                    if self._read_back_completed and self._voice_confirm_allowed:
                        self._consent_granted = True
                        self._transcribed_consent = sanitize_confirmation_evidence(text)

            # 2. ถ้าอยู่ในโหมดแก้ไข (T6.2)
            if self._in_correction_mode:
                if self._correction_count > _MAX_CORRECTIONS:
                    self._in_correction_mode = False
                    return {
                        "message": "ขออภัยครับ มีการแก้ไขข้อมูลเกินเพดาน 3 ครั้งแล้ว กรุณาติดต่อสายด่วน 1129 หรือทำรายการใหม่ภายหลังครับ",
                        "conversationId": self.conversation_id,
                        "inCorrectionMode": False,
                        "voiceGuidance": "แจ้งผู้ใช้ว่าแก้ไขเกินเพดาน 3 ครั้ง และแนะนำให้ติดต่อสายด่วน 1129",
                    }

            # 3. ส่งข้อความเข้า MainAgent
            try:
                request = ChatRequest(conversation_id=self._conversation_id, message=text)
            except ValidationError as exc:
                raise InvalidTextError(
                    f"ข้อความยาวเกินกำหนด (สูงสุด {_MAX_MESSAGE_LENGTH} ตัวอักษร) กรุณาลองอีกครั้งครับ"
                ) from exc

            with trace_channel("voice"):
                response = await self._agent.handle_chat(request)

            self._conversation_id = response.conversation_id

            # ถ้าได้ pending_action ใหม่
            if response.pending_action is not None:
                # ตรวจสอบว่าไม่ใช่ action เดิมที่ถูก reject ไปแล้ว
                if self._last_rejected_action_id is not None:
                    if response.pending_action.pending_action_id == self._last_rejected_action_id:
                        raise ActionConflictError("ห้ามปลุก pending action เดิมที่ถูกปฏิเสธแล้ว")

                self._pending_action_id = response.pending_action.pending_action_id
                self._current_pending_action = response.pending_action
                self._in_correction_mode = False
                self._retry_count = 0
                self._consent_granted = False
                self._transcribed_consent = None

                # ตรวจ voiceConfirm
                spec = self._get_operation_spec(
                    response.pending_action.tool_slug,
                    response.pending_action.prepare_action,
                )
                self._voice_confirm_allowed = getattr(spec, "voice_confirm", True)

                # สร้าง read-back text
                schema = self._get_operation_schema(
                    response.pending_action.tool_slug,
                    response.pending_action.prepare_action,
                )
                props = schema.get("properties", {}) if schema else {}
                self._read_back_text = build_read_back_text(response.pending_action, props)
                self._read_back_completed = True

            payload = response.model_dump(mode="json", by_alias=True)
            payload["voiceGuidance"] = self._voice_guidance(response)
            return payload

    async def _handle_refusal_locked(self) -> dict[str, Any]:
        """ผู้ใช้ปฏิเสธรายการด้วยเสียง -> reject action เดิม และเข้าสู่โหมดแก้ไข (T6.2)"""
        last_action = self._current_pending_action
        rejected_resp = await self._reject_locked(_CANCEL_REASON)
        self._consent_granted = False
        self._transcribed_consent = None
        self._read_back_completed = False
        self._read_back_text = None

        self._correction_count += 1
        if self._correction_count > _MAX_CORRECTIONS:
            self._in_correction_mode = False
            payload = dict(rejected_resp)
            payload.update({
                "message": "ขออภัยครับ มีการแก้ไขข้อมูลเกินเพดาน 3 ครั้งแล้ว กรุณาติดต่อสายด่วน 1129 หรือทำรายการใหม่ภายหลังครับ",
                "conversationId": self.conversation_id,
                "inCorrectionMode": False,
                "voiceGuidance": "แจ้งผู้ใช้ว่าแก้ไขเกินเพดาน 3 ครั้ง และแนะนำให้ติดต่อสายด่วน 1129",
            })
            return payload

        self._in_correction_mode = True
        schema = None
        if last_action:
            schema = self._get_operation_schema(last_action.tool_slug, last_action.prepare_action)
        props = schema.get("properties", {}) if schema else {}
        field_names = [
            prop.get("title", k)
            for k, prop in props.items()
            if not k.startswith("_") and k not in {"idempotency_key", "idempotencyKey", "token"}
        ]
        if not field_names and last_action and getattr(last_action, "prepared_input", None):
            field_names = [
                _FIELD_LABELS.get(k, k)
                for k in last_action.prepared_input.keys()
                if not k.startswith("_")
            ]
        fields_str = " / ".join(field_names) if field_names else "ข้อมูลที่ต้องการแก้ไข"
        prompt = (
            f"รับทราบครับ ยกเลิกรายการเดิมเรียบร้อยแล้ว ท่านต้องการแก้ไขส่วนไหนครับ "
            f"สามารถแก้ไขได้ดังนี้: {fields_str} หรือแจ้งว่า 'ทั้งหมด' ได้ครับ"
        )
        payload = dict(rejected_resp)
        payload.update({
            "message": prompt,
            "conversationId": self.conversation_id,
            "inCorrectionMode": True,
            "voiceGuidance": f"ถามผู้ใช้ว่าต้องการแก้ไขส่วนไหนจากรายการ: {fields_str} หรือทั้งหมด",
        })
        return payload

    def _voice_guidance(self, response: Any) -> str | None:
        """บอกเสียงว่าต้องพูดอย่างไรกับตัวเลือกและลิงก์ในคำตอบรอบนี้"""
        guidance_parts: list[str] = []
        if getattr(response, "pending_action", None) is not None and self._read_back_text:
            if not self._voice_confirm_allowed:
                guidance_parts.append(
                    f"อ่านทวนข้อมูลให้ผู้ใช้ฟัง: {self._read_back_text} "
                    "และแจ้งผู้ใช้ว่ารายการนี้ไม่อนุญาตให้ยืนยันด้วยเสียง ต้องยืนยันผ่านช่องทางอื่น"
                )
            else:
                guidance_parts.append(f"อ่านทวนข้อมูลให้ผู้ใช้ฟังอย่างชัดเจน: {self._read_back_text}")

        choice = self._choice_guidance(response)
        if choice:
            guidance_parts.append(choice)
        link = self._link_guidance(response)
        if link:
            guidance_parts.append(link)

        # T6.3 citation degradation instruction
        if getattr(response, "citations", None):
            guidance_parts.append("ห้ามอ่านหมายเลข citation หรือ URL อ้างอิงในเสียงตอบกลับ")

        return " ".join(guidance_parts) if guidance_parts else None

    def _choice_guidance(self, response: Any) -> str | None:
        prompt = getattr(response, "choice_prompt", None)
        if prompt is None or not prompt.options:
            return None
        if self._has_display:
            return (
                f"ถามผู้ใช้ว่า: {prompt.question} "
                "แจ้งสั้น ๆ ว่ามีตัวเลือกแสดงบนหน้าจอให้กดเลือก หรือจะพูดตอบก็ได้ "
                "ห้ามอ่านรายการตัวเลือกทั้งหมด"
            )
        options = " / ".join(option.label for option in prompt.options)
        return (
            f"ถามผู้ใช้ว่า: {prompt.question} "
            f"อ่านตัวเลือกให้ครบทุกข้อ: {options} "
            "แล้วส่งคำตอบของผู้ใช้ต่อด้วย pea_agent_chat ตามคำพูดเดิม"
        )

    def _link_guidance(self, response: Any) -> str | None:
        """คำตอบรอบนี้มีลิงก์บริการแล้ว เสียงจึงต้องไม่รับปากว่าจะส่งให้ทีหลัง"""
        hosts = _service_hosts(getattr(response, "message", None))
        if not hosts:
            return None
        if self._has_display:
            return (
                "คำตอบรอบนี้มีลิงก์บริการแสดงเป็นลิงก์กดได้บนหน้าจอแล้ว "
                "ให้บอกสั้น ๆ ว่าลิงก์อยู่บนหน้าจอและกดเปิดได้เลย "
                "ห้ามอ่าน URL เต็ม และห้ามรับปากว่าจะส่งลิงก์ให้ภายหลัง"
            )
        spoken = " และ ".join(hosts)
        return (
            f"ช่องทางนี้ไม่มีหน้าจอ ให้บอกชื่อเว็บไซต์ด้วยเสียงว่า {spoken} "
            "พูดช้า ๆ ให้ผู้ใช้จดตามได้ และเสนอให้จดหรือทวนซ้ำได้ "
            "ห้ามอ่านเส้นทางหลังชื่อเว็บไซต์ และห้ามรับปากว่าจะส่งลิงก์ให้ภายหลัง"
        )

    async def confirm_current(self, confirmation_note: str | None = None) -> dict[str, Any]:
        """ยืนยัน pending action ปัจจุบันของเซสชัน (ไม่รับ id จากโมเดล)

        เรียก ``MainAgent.confirm_pending_action`` ด้วย id ที่เก็บไว้ภายใน
        เมื่อผลเป็นสถานะสิ้นสุดจะล้าง id ทันที หากไม่มี pending action
        จะ fail closed ด้วย ``NoPendingActionError``
        """
        async with self._lock:
            return await self._confirm_locked(confirmation_note)

    async def _confirm_locked(self, confirmation_note: str | None = None) -> dict[str, Any]:
        pending_action_id = self._require_pending()

        # 🔒 T6.3 voiceConfirm gating: fail closed if voiceConfirm is false
        if not self._voice_confirm_allowed:
            raise VoiceBridgeError("voice_confirm_disabled", "รายการนี้ไม่อนุญาตให้ยืนยันด้วยเสียง (voiceConfirm: false)")

        # 🔒 T6.1 Structural safety: read-back must have been completed
        if not self._read_back_completed:
            raise ActionConflictError("ยังไม่ได้อ่านทวนรายการทั้งหมดให้ผู้ใช้ฟัง กรุณาอ่านทวนก่อนยืนยัน")

        # 🔒 T6.1 Structural safety: LLM call cannot constitute consent; genuine speech consent is required
        if not self._consent_granted:
            raise VoiceBridgeError("consent_required", "ยังไม่ได้รับคำยินยอมที่ชัดเจนจากเสียงของผู้ใช้")

        note = self._normalize_optional_text(confirmation_note, _MAX_NOTE_LENGTH, "confirmationNote")

        # 🔒 T6.4 Confirmation evidence
        evidence = {
            "readBackText": sanitize_confirmation_evidence(self._read_back_text or ""),
            "transcription": sanitize_confirmation_evidence(self._transcribed_consent or "ยืนยัน"),
            "confirmedAt": datetime.now(timezone.utc).isoformat(),
            "channel": "voice",
        }

        try:
            with trace_channel("voice"):
                try:
                    decision = await self._agent.confirm_pending_action(
                        pending_action_id,
                        confirmation_note=note,
                        evidence=evidence,
                    )
                except TypeError:
                    decision = await self._agent.confirm_pending_action(
                        pending_action_id,
                        confirmation_note=note,
                    )
        except LookupError as exc:
            self._pending_action_id = None
            raise NoPendingActionError() from exc
        except RuntimeError as exc:
            raise ActionConflictError() from exc

        # Reset consent and read-back state
        self._consent_granted = False
        self._transcribed_consent = None
        self._read_back_completed = False
        self._read_back_text = None
        self._clear_if_terminal(decision)
        return decision.model_dump(mode="json", by_alias=True)

    async def reject_current(self, reason: str) -> dict[str, Any]:
        """ปฏิเสธ pending action ปัจจุบันของเซสชัน (ไม่รับ id จากโมเดล)

        เรียก ``MainAgent.reject_pending_action`` ด้วย id ที่เก็บไว้ภายใน
        และเหตุผลที่ผ่านการตรวจสอบ เมื่อผลเป็นสถานะสิ้นสุดจะล้าง id ทันที
        หากไม่มี pending action จะ fail closed ด้วย ``NoPendingActionError``
        """
        async with self._lock:
            return await self._reject_locked(reason)

    async def _reject_locked(self, reason: str) -> dict[str, Any]:
        """ตัวปฏิเสธจริง ผู้เรียกต้องถือ ``self._lock`` อยู่แล้ว"""
        pending_action_id = self._require_pending()
        normalized_reason = self._normalize_optional_text(reason, _MAX_REASON_LENGTH, "reason")
        if not normalized_reason:
            raise InvalidTextError("ไม่ได้รับเหตุผลการปฏิเสธที่ชัดเจน กรุณาลองอีกครั้งครับ")
        try:
            with trace_channel("voice"):
                decision = await self._agent.reject_pending_action(
                    pending_action_id,
                    reason=normalized_reason,
                )
        except LookupError as exc:
            self._pending_action_id = None
            raise NoPendingActionError() from exc
        except RuntimeError as exc:
            raise ActionConflictError() from exc
        self._last_rejected_action_id = pending_action_id
        self._consent_granted = False
        self._transcribed_consent = None
        self._read_back_completed = False
        self._read_back_text = None
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
            self._current_pending_action = None

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


def _is_cancellation(text: str) -> bool:
    """True เมื่อผู้ใช้ปฏิเสธรายการที่รอยืนยันอย่างชัดเจน

    จำกัดที่ข้อความสั้นเท่านั้น เพื่อไม่ให้ประโยคยาวที่บังเอิญมีคำว่า
    ``ไม่ต้อง`` เช่น การถามข้อมูลเพิ่ม ถูกตีความเป็นการยกเลิกรายการ
    """
    normalized = " ".join(text.casefold().split())
    if len(normalized) > 40:
        return False
    return any(phrase in normalized for phrase in _CANCEL_PHRASES)


def _service_hosts(message: Any) -> tuple[str, ...]:
    """ชื่อโฮสต์ตามลำดับที่ปรากฏในคำตอบ ใช้บอกเว็บไซต์ด้วยเสียงเมื่อไม่มีจอ

    คืนเฉพาะโฮสต์ที่อ่านออกเสียงได้ ตัด ``www.`` ทิ้งเพื่อไม่ให้เสียงยาวเกิน
    และไม่ส่งเส้นทางหลังโฮสต์ เพราะผู้ใช้ทางโทรศัพท์จดตามไม่ทัน
    """
    if not isinstance(message, str) or not message:
        return ()
    hosts: list[str] = []
    for url in _URL_PATTERN.findall(message):
        hostname = urlparse(url.rstrip(".,)")).hostname
        if not hostname:
            continue
        spoken = hostname.removeprefix("www.")
        if spoken and spoken not in hosts:
            hosts.append(spoken)
    return tuple(hosts)
