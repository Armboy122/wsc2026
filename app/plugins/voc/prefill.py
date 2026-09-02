"""Map what the user already said onto catalog answers before asking anything.

The intake flow must never invent a taxonomy code, but re-asking for facts the
user already gave makes the assistant feel like a form.  This module closes that
gap: the model only ever *chooses among options the catalog already produced*,
and every returned value is verified against that same option list before it is
accepted.  A wrong or hallucinated choice is dropped, so the worst case is an
extra question rather than a fabricated code.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from uuid import uuid4

from app.contracts import ChoicePrompt
from app.llm.models import LLMMessage, LLMRequest
from app.plugins.voc.intake import (
    STEP_CA_NUMBER,
    STEP_CONSENT,
    VocIntakeFlow,
    VocIntakeState,
)

logger = logging.getLogger(__name__)

# ความยินยอมและ CA ต้องมาจากการกระทำของผู้ใช้เท่านั้น ห้ามให้โมเดลเติมให้เด็ดขาด
_NEVER_PREFILL = frozenset({STEP_CONSENT, STEP_CA_NUMBER})

# adapter ของ Main Agent บังคับ system prompt ของ planner กับทุกคำขอ คำตอบจึงกลับมาเป็น
# planner envelope เสมอ ที่นี่จึงสั่งให้ใส่คำตอบไว้ใน field `message` ของ envelope นั้น
# แล้วอ่านค่าออกมาทีหลัง แทนการฝืนขอรูปแบบที่ adapter ไม่อนุญาต
_PROMPT = """งานนี้ไม่ต้องเรียก tool ใด ๆ ให้ตอบด้วย toolCalls เป็น [] และ directResponse เป็น null
โดยใส่คำตอบของงานด้านล่างเป็นสตริงใน field message

งาน: เลือกตัวเลือกที่ตรงกับสิ่งที่ผู้ใช้บอกมาแล้ว สำหรับแบบฟอร์มร้องเรียนของการไฟฟ้าส่วนภูมิภาค

ข้อความของผู้ใช้:
{message}

คำถามปัจจุบัน: {question}
ตัวเลือกที่เลือกได้:
{options}

ค่าใน message ต้องเป็น value ของตัวเลือกที่เลือก หรือคำว่า NONE เมื่อไม่แน่ใจ
เลือกเฉพาะเมื่อข้อความของผู้ใช้ระบุชัดเจนพอ ห้ามสร้าง value ใหม่ที่ไม่อยู่ในรายการ
ห้ามใส่คำอธิบายอื่นใน message นอกจาก value หรือ NONE"""


class VocPrefiller:
    """Fill catalog-backed answers the user already stated, one question at a time."""

    def __init__(self, llm_client: Any, *, max_steps: int = 6) -> None:
        self._llm = llm_client
        self._max_steps = max_steps

    async def prefill(
        self,
        flow: VocIntakeFlow,
        state: VocIntakeState,
        message: str,
    ) -> VocIntakeState:
        """เดินคำถามที่ตอบได้จากข้อความเดิม แล้วหยุดทันทีที่โมเดลไม่มั่นใจ"""
        text = " ".join(message.split())
        if not text or self._llm is None:
            return state

        for _ in range(self._max_steps):
            state, prompt = flow.resolve(state)
            if prompt is None or not prompt.options or prompt.prompt_id in _NEVER_PREFILL:
                return state
            value = await self.choose(prompt, text)
            if value is None:
                return state
            try:
                state = flow.apply(state, prompt, value)
            except Exception:  # noqa: BLE001 - ค่าที่ไม่ผ่านการตรวจให้ถามผู้ใช้ตามปกติ
                logger.info("voc_prefill_rejected", extra={"promptId": prompt.prompt_id})
                return state
        return state

    async def choose(self, prompt: ChoicePrompt, message: str) -> str | None:
        """เลือกหนึ่งตัวเลือกจากข้อความอิสระ คืน None เมื่อไม่มั่นใจหรือค่าไม่อยู่ใน catalog"""
        options = "\n".join(
            f"- {option.value}: {option.label}"
            + (f" ({option.description})" if option.description else "")
            for option in prompt.options
        )
        instruction = _PROMPT.format(message=message, question=prompt.question, options=options)
        try:
            response = await self._llm.complete(
                LLMRequest(
                    (LLMMessage("user", instruction),),
                    (),
                    uuid4(),
                    None,
                    (),
                )
            )
        except Exception:  # noqa: BLE001 - provider ล่มต้องไม่ทำให้การแจ้งเรื่องล้ม
            logger.warning("voc_prefill_llm_unavailable", extra={"promptId": prompt.prompt_id})
            return None

        value = _parse_value(response.text)
        if value is None or value.upper() in {"NONE", "NULL"}:
            return None
        # เชื่อเฉพาะค่าที่อยู่ในรายการของ catalog รอบนี้เท่านั้น
        allowed = {option.value for option in prompt.options}
        if value not in allowed:
            logger.info("voc_prefill_out_of_catalog", extra={"promptId": prompt.prompt_id})
            return None
        return value


def _parse_value(raw: str) -> str | None:
    """อ่านค่าที่เลือกจากคำตอบของโมเดล รองรับทั้ง planner envelope และ JSON ตรง"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # โมเดลบางครั้งตอบ value ล้วนโดยไม่ห่อ JSON
        return text or None
    if not isinstance(payload, dict):
        return None
    # planner envelope ใส่คำตอบไว้ใน message ส่วนรูปแบบตรงใช้ key value
    for key in ("value", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
