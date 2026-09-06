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
_POLITE_PARTICLES_REGEX = re.compile(
    r"(?:ครับ|ค่ะ|คะ|จ้ะ|จ้า|นะครับ|นะคะ|นะ|หน่อย|ด้วย|สิ|เลย|แล้ว|ก่อน)+$"
)

_QUESTION_WORDS = (
    "ไหม", "มั้ย", "หรือไม่", "หรือเปล่า", "หรือยัง", "หรือ", "ทำไม",
    "อะไร", "ใคร", "ที่ไหน", "เมื่อไหร่", "ยังไง", "อย่างไร", "เท่าไหร่",
    "กี่", "ดีไหม", "เหรอ", "หรอ", "?", "what", "why", "how", "when", "where", "who",
)

_REFUSAL_EXACT = frozenset({
    "ไม่ใช่", "ไม่", "ไม่เอา", "ไม่เอาแล้ว", "ไม่ต้อง", "ไม่ต้องแล้ว",
    "ขอยกเลิก", "ยกเลิก", "ไม่ทำแล้ว", "เลิกทำ", "หยุดก่อน",
    "ข้อมูลผิด", "ผิด", "ไม่ถูกต้อง", "ข้อมูลไม่ถูกต้อง", "ข้อมูลไม่ถูก",
    "ขอแก้ไข", "ขอแก้ไขข้อมูล", "แก้ไข", "แก้ไขข้อมูล", "แก้", "แก้ข้อมูล", "เปลี่ยน", "ขอเปลี่ยน",
    "ไม่ยืนยัน", "ไม่ตกลง", "ยังไม่พร้อม", "ยังไม่พร้อมยืนยัน", "ยังไม่ยืนยัน", "ยังไม่ตกลง",
    "cancel", "no", "reject",
})

_CONFIRM_EXACT = frozenset({
    "ยืนยัน", "ตกลง", "ถูกต้อง", "ถูกต้องแล้ว", "ใช่", "เอาเลย", "ตามนั้น", "ดำเนินการเลย",
    "yes", "confirm", "ok", "okay",
})

_CANCEL_REASON = "ผู้ใช้ปฏิเสธรายการด้วยเสียง"


def match_voice_intent(text: str) -> str:
    """Deterministic refusal-first matching with closed allowlist normalization:
    คืนค่า 'refusal' | 'confirm' | 'unrecognized'
    🔒 กติกาความปลอดภัย T6.1:
    - ตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ
    - ข้อความคำถาม / ข้อความกำกวม / มีคำปฏิเสธ ต้องไม่ผ่านเป็นยืนยันเด็ดขาด
    """
    if not isinstance(text, str):
        return "unrecognized"
    s = " ".join(text.casefold().strip().split())
    # ตัดเครื่องหมายวรรคตอน
    s = re.sub(r"[?!.,:;]+", " ", s).strip()
    s = " ".join(s.split())
    if not s or len(s) > 40:
        return "unrecognized"

    # 1. ข้อความที่เป็นคำถาม ห้ามเป็นคำยืนยันโดยเด็ดขาด (เช่น "ต้องยืนยันไหมครับ", "ยืนยันทำไม")
    if any(q in s for q in _QUESTION_WORDS):
        return "unrecognized"

    # ตัดคำลงท้ายสุภาพเพื่อเทียบคำศัพท์แก่น
    stripped = _POLITE_PARTICLES_REGEX.sub("", s).strip()
    stripped = " ".join(stripped.split())
    if not stripped:
        stripped = s

    # 2. ตรวจชุดปฏิเสธก่อนเสมอ (refusal-first)
    if stripped in _REFUSAL_EXACT or s in _REFUSAL_EXACT:
        return "refusal"
    if any(phrase in s for phrase in ("ยังไม่พร้อม", "ไม่ยืนยัน", "ไม่ตกลง", "ขอยกเลิก", "ไม่เอาแล้ว", "ไม่ต้องแล้ว", "ไม่ใช่", "ข้อมูลผิด", "ขอแก้ไข", "แก้ไขข้อมูล")):
        return "refusal"
    if s.startswith("ไม่") or s.startswith("ยังไม่"):
        return "refusal"

    # 3. ตรวจคำปฏิเสธอื่น ๆ ที่ยังหลงเหลือ — ถ้ามี ห้ามเป็น confirm เด็ดขาด
    if any(neg in s for neg in ("ไม่", "ยังไม่", "อย่า", "ห้าม", "มิ", "no", "not")):
        return "unrecognized"

    # 4. ตรวจชุดยืนยันแบบ closed allowlist เท่านั้น
    if stripped in _CONFIRM_EXACT or s in _CONFIRM_EXACT:
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
    cleaned = re.sub(r"\b\d{12}\b", "[redacted-ca]", cleaned)
    cleaned = re.sub(r"\b\d{16}\b", "[redacted-card]", cleaned)
    cleaned = re.sub(r"\b0\d{8,9}\b", "[redacted-phone]", cleaned)
    cleaned = re.sub(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer [redacted-token]", cleaned)
    if len(cleaned) > 200:
        cleaned = cleaned[:197] + "..."
    return cleaned


def build_confirmation_evidence(
    *,
    pending_action: Any,
    transcription: str,
    channel: str = "voice",
) -> dict[str, Any]:
    """สร้าง confirmation evidence ที่ปลอดภัยต่อ trace โดยไม่ทำให้ trace redaction เสียหาย (T6.4)"""
    prepared = getattr(pending_action, "prepared_input", None) or {}
    sanitized_fields: dict[str, Any] = {}
    for k, v in prepared.items():
        if k.startswith("_") or k in {"idempotency_key", "idempotencyKey", "token"}:
            continue
        norm_k = "".join(c for c in k.casefold() if c.isalnum())
        if norm_k in {"phone", "contactphone", "canumber", "citizenid", "nationalid", "idcard"}:
            sanitized_fields[k] = sanitize_confirmation_evidence(str(v))
        elif isinstance(v, str):
            sanitized_fields[k] = sanitize_confirmation_evidence(v)
        else:
            sanitized_fields[k] = v

    summary = getattr(pending_action, "summary", "รายการรอดำเนินการ")
    clean_summary = sanitize_confirmation_evidence(summary)
    if len(clean_summary) > 100:
        clean_summary = clean_summary[:97] + "..."

    return {
        "channel": channel,
        "transcription": sanitize_confirmation_evidence(transcription),
        "confirmedAt": datetime.now(timezone.utc).isoformat(),
        "readBackSummary": clean_summary,
        "readBackFields": sanitized_fields,
    }


def extract_field_correction(
    text: str,
    last_input: Mapping[str, Any],
    schema_properties: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """แกะฟิลด์ที่ผู้ใช้ระบุแก้ไขในโหมด schema-driven correction (T6.2)"""
    if not text or not last_input:
        return None
    normalized = text.strip()
    if normalized in {"ทั้งหมด", "เริ่มใหม่", "ทำใหม่", "ยกเลิกทั้งหมด"}:
        return None

    updated = dict(last_input)
    matched = False

    # 1. Phone number (0812345678 / 0899999999)
    phone_match = re.search(r"\b0\d{8,9}\b", normalized)
    if phone_match:
        phone_key = next((k for k in updated if "phone" in k.lower() or "contact" in k.lower()), None)
        if phone_key:
            updated[phone_key] = phone_match.group(0)
            matched = True

    # 2. CA number (12 digits)
    ca_match = re.search(r"\b\d{12}\b", normalized)
    if ca_match:
        ca_key = next((k for k in updated if "ca" in k.lower()), None)
        if ca_key:
            updated[ca_key] = ca_match.group(0)
            matched = True

    # 3. Label/Key pattern: (?:แก้|เปลี่ยน)? <label|key> (?:เป็น|คือ|:)? <val>
    for key in list(updated.keys()):
        if key.startswith("_") or key in {"idempotency_key", "idempotencyKey", "token"}:
            continue
        label = _FIELD_LABELS.get(key, key)
        pattern = rf"(?:แก้|เปลี่ยน)?\s*(?:{re.escape(label)}|{re.escape(key)})\s*(?:เป็น|คือ|:|=)?\s*([^\s;,]+)"
        m = re.search(pattern, normalized)
        if m:
            val = m.group(1).strip()
            if val:
                updated[key] = val
                matched = True

    return updated if matched else None


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
        self._last_rejected_action_id: UUID | None = None
        self._last_rejected_input: dict[str, Any] | None = None
        self._last_rejected_tool_slug: str | None = None
        self._last_rejected_prepare_action: str | None = None
        self._last_rejected_summary: str | None = None
        self._read_back_text: str | None = None
        self._read_back_generation: int = 0
        self._read_back_delivered: bool = False
        self._voice_confirm_allowed: bool = True
        self._consent_granted: bool = False
        self._transcribed_consent: str | None = None
        self._consent_pending_action_id: UUID | None = None
        self._consent_generation: int = 0
        self._retry_count: int = 0
        self._in_correction_mode: bool = False
        self._correction_count: int = 0
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
        """True เมื่อการอ่านทวนข้อมูลเสร็จสิ้นและส่งถึงผู้ใช้เรียบร้อยแล้วโดยไม่ถูกขัดจังหวะ"""
        return self._read_back_delivered

    def mark_read_back_delivered(
        self, pending_action_id: UUID | None = None, generation: int | None = None
    ) -> None:
        """เรียกเมื่อการส่งออกเสียงอ่านทวนถึงผู้ใช้เรียบร้อยแล้วโดยไม่ถูกขัดจังหวะ (T6.1 / T6.3)"""
        if pending_action_id is not None and self._pending_action_id != pending_action_id:
            return
        if generation is not None and self._read_back_generation != generation:
            return
        self._read_back_delivered = True

    def mark_interrupted(self) -> None:
        """เรียกเมื่อผู้ใช้พูดแทรกระหว่างที่ผู้ช่วยกำลังพูด (audio.interrupted) (T6.1 / T6.3)"""
        self._read_back_delivered = False
        self._consent_granted = False
        self._transcribed_consent = None
        self._consent_pending_action_id = None

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

    async def process_user_transcription(self, text: str) -> dict[str, Any] | None:
        """ประมวลผลข้อความถอดเสียงจริงของผู้ใช้แบบ deterministic matching (T6.1)

        🔒 ข้อกำหนดความปลอดภัย:
        - LLM ไม่มีทางตัดสินคำยินยอม
        - คำยินยอมต้องมาจากเสียงจริงของผู้ใช้เท่านั้น
        - ตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ
        """
        async with self._lock:
            cleaned = text.strip() if isinstance(text, str) else ""
            if not cleaned:
                return None

            if self._pending_action_id is None:
                return None

            intent = match_voice_intent(cleaned)

            # 1. ผู้ใช้พูดปฏิเสธ -> ยุติรายการเดิม และเข้าสู่โหมดแก้ไข
            if intent == "refusal":
                self._consent_granted = False
                self._transcribed_consent = None
                self._consent_pending_action_id = None
                return await self._handle_refusal_locked()

            # 2. ผู้ใช้พูดยืนยัน
            if intent == "confirm":
                if not self._voice_confirm_allowed:
                    self._consent_granted = False
                    return {
                        "operation": "reject",
                        "response": {
                            "error": {
                                "code": "voice_confirm_disabled",
                                "message": "รายการนี้ไม่อนุญาตให้ยืนยันด้วยเสียง กรุณายืนยันผ่านหน้าจอครับ",
                            }
                        },
                    }
                if not self._read_back_delivered or not self._read_back_text:
                    self._consent_granted = False
                    return {
                        "operation": "reject",
                        "response": {
                            "error": {
                                "code": "read_back_incomplete",
                                "message": "ยังอ่านทวนข้อมูลไม่เสร็จสิ้น หรือถูกขัดจังหวะ กรุณาฟังการอ่านทวนก่อนยืนยันครับ",
                            }
                        },
                    }
                self._consent_granted = True
                self._transcribed_consent = sanitize_confirmation_evidence(cleaned)
                self._consent_pending_action_id = self._pending_action_id
                self._consent_generation = self._read_back_generation
                return {
                    "operation": "chat",
                    "response": {
                        "message": "รับทราบคำยืนยันครับ ระบบกำลังดำเนินการ",
                        "voiceGuidance": "แจ้งผู้ใช้ว่ารับทราบคำยืนยันแล้ว และกำลังดำเนินการส่งรายการ",
                    },
                }

            # 3. คำพูดกำกวม หรือคำถามนอกเรื่อง -> unrecognized
            self._consent_granted = False
            self._transcribed_consent = None
            self._consent_pending_action_id = None
            if not self._in_correction_mode:
                self._retry_count += 1
                if self._retry_count > _MAX_RETRIES:
                    decision = await self._reject_internal_locked("speech_unrecognized_exceeded_retries")
                    self._in_correction_mode = False
                    return {
                        "operation": "reject",
                        "response": {
                            "pendingAction": decision.get("pendingAction"),
                            "message": "ขออภัยครับ ไม่สามารถจับใจความคำยืนยันได้ครบ 3 ครั้ง ระบบขอยกเลิกรายการนี้เพื่อความปลอดภัยครับ",
                            "voiceGuidance": "แจ้งผู้ใช้ว่าขอยกเลิกรายการเนื่องจากไม่สามารถจับใจความได้ครบ 3 ครั้ง",
                        },
                    }

                return {
                    "operation": "chat",
                    "response": {
                        "message": f"ขออภัยครับ ฟังไม่ชัดเจน กรุณาตอบ ยืนยัน หรือแจ้งแก้ไขครับ (ครั้งที่ {self._retry_count}/3)",
                        "voiceGuidance": f"ถามผู้ใช้อีกครั้งอย่างสุภาพ: ขออภัยครับ ฟังไม่ชัดเจน กรุณาตอบ ยืนยัน หรือแจ้งแก้ไขครับ (ครั้งที่ {self._retry_count} จาก 3 ครั้ง)",
                    },
                }

            return None

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

            # 🔒 T6.1: handle_text เป็นคำสั่งผ่าน LLM (pea_agent_chat)
            # จึงต้องไม่ให้คำยินยอมหรือตัดสินใจปฏิเสธแทนผู้ใช้โดยเด็ดขาด!
            # คำยินยอมและคำปฏิเสธจะถูกประมวลผลผ่าน process_user_transcription เท่านั้น

            # 1. ถ้าอยู่ในโหมดแก้ไข (T6.2)
            if self._in_correction_mode:
                if self._correction_count > _MAX_CORRECTIONS:
                    self._in_correction_mode = False
                    return {
                        "message": "ขออภัยครับ มีการแก้ไขข้อมูลเกินเพดาน 3 ครั้งแล้ว กรุณาติดต่อสายด่วน 1129 หรือทำรายการใหม่ภายหลังครับ",
                        "conversationId": self.conversation_id,
                        "inCorrectionMode": False,
                        "voiceGuidance": "แจ้งผู้ใช้ว่าแก้ไขเกินเพดาน 3 ครั้ง และแนะนำให้ติดต่อสายด่วน 1129",
                    }

            # 2. ผสานการแก้ไขฟิลด์ข้อมูลเข้ากับ input เดิม หากอยู่ในโหมดแก้ไข
            message_to_send = text
            if self._in_correction_mode and self._last_rejected_input:
                schema = None
                if self._last_rejected_tool_slug and self._last_rejected_prepare_action:
                    schema = self._get_operation_schema(
                        self._last_rejected_tool_slug, self._last_rejected_prepare_action
                    )
                props = schema.get("properties", {}) if schema else {}
                corrected_input = extract_field_correction(text, self._last_rejected_input, props)
                if corrected_input:
                    field_parts = [
                        f"{k}: {v}"
                        for k, v in corrected_input.items()
                        if not k.startswith("_") and k not in {"idempotency_key", "idempotencyKey", "token"}
                    ]
                    prefix = "แจ้งเหตุไฟดับ"
                    if self._last_rejected_summary and not self._last_rejected_summary.startswith("รายการ"):
                        prefix = self._last_rejected_summary
                    message_to_send = f"{prefix}; " + "; ".join(field_parts)

            # 3. ส่งข้อความเข้า MainAgent
            try:
                request = ChatRequest(conversation_id=self._conversation_id, message=message_to_send)
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
                self._consent_pending_action_id = None
                self._consent_generation = 0
                self._read_back_generation += 1
                self._read_back_delivered = False  # 🔒 T6.1 & T6.3: ยังไม่ได้ส่งมอบเสียงถึงผู้ใช้จริง!

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

            payload = response.model_dump(mode="json", by_alias=True)
            payload["voiceGuidance"] = self._voice_guidance(response)
            return payload

    async def _handle_refusal_locked(self) -> dict[str, Any]:
        """ผู้ใช้ปฏิเสธรายการด้วยเสียง -> reject action เดิม และเข้าสู่โหมดแก้ไข (T6.2)"""
        last_action = self._current_pending_action
        if last_action:
            self._last_rejected_input = dict(getattr(last_action, "prepared_input", None) or {})
            self._last_rejected_tool_slug = getattr(last_action, "tool_slug", None)
            self._last_rejected_prepare_action = getattr(last_action, "prepare_action", None)
            self._last_rejected_summary = getattr(last_action, "summary", None)
        rejected_resp = await self._reject_internal_locked(_CANCEL_REASON)
        self._consent_granted = False
        self._transcribed_consent = None
        self._consent_pending_action_id = None
        self._read_back_delivered = False
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
            return {"operation": "reject", "response": payload}

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
        return {"operation": "reject", "response": payload}

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

        # 🔒 T6.1 & T6.3 Structural safety: read-back delivery must have been completed without interrupt
        if not self._read_back_delivered or not self._read_back_text:
            raise ActionConflictError("ยังไม่ได้อ่านทวนรายการทั้งหมดให้ผู้ใช้ฟัง หรือถูกขัดจังหวะ กรุณาอ่านทวนใหม่ก่อนยืนยัน")

        # 🔒 T6.1 Structural safety: LLM call cannot constitute consent; genuine speech consent is required
        if (
            not self._consent_granted
            or self._consent_pending_action_id != pending_action_id
            or self._consent_generation != self._read_back_generation
        ):
            raise VoiceBridgeError("consent_required", "ยังไม่ได้รับคำยินยอมที่ชัดเจนจากเสียงของผู้ใช้")

        note = self._normalize_optional_text(confirmation_note, _MAX_NOTE_LENGTH, "confirmationNote")

        # 🔒 T6.4 Confirmation evidence safely structured without leaking raw customer fields
        evidence = build_confirmation_evidence(
            pending_action=self._current_pending_action,
            transcription=self._transcribed_consent or "ยืนยัน",
            channel="voice",
        )

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
        self._consent_pending_action_id = None
        self._read_back_delivered = False
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
        self._consent_pending_action_id = None
        self._read_back_delivered = False
        self._read_back_text = None
        self._clear_if_terminal(decision)
        return decision.model_dump(mode="json", by_alias=True)

    _reject_internal_locked = _reject_locked

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
