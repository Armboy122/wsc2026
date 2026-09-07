"""VOC guided intake flow: own the conversation while collecting a case."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from app.agent.guided_flow import GuidedTurn
from app.backends import BackendError
from app.contracts import ChoicePrompt, ToolAction, ToolName
from app.plugins.voc.intake import (
    CONSENT_ACCEPT,
    CA_SKIP,
    CONSENT_DECLINE,
    STEP_CONSENT,
    STEP_DETAIL,
    STEP_CA_NUMBER,
    STEP_JOURNEY,
    STEP_SUBJECT,
    IntakeError,
    VocIntakeFlow,
    VocIntakeState,
    extract_explicit_ca_number,
)
from app.plugins.voc.prefill import VocPrefiller

# ข้อความที่บ่งชี้ว่าผู้ใช้ต้องการเปิดเรื่องใหม่ ไม่ใช่ติดตามเรื่องเดิม
_START_PATTERNS = (
    "ร้องเรียน", "แจ้งเรื่อง", "แจ้งปัญหา", "ชื่นชม", "แจ้งเบาะแส",
    "เสนอแนะ", "ข้อคิดเห็น", "ติชม", "complaint", "complain",
)
_TRACKING_PATTERNS = ("ติดตาม", "สถานะเรื่อง", "เช็คเรื่อง", "ตรวจสอบเรื่อง")
# คำถามว่ามีอะไรบ้างคือการขอข้อมูล ไม่ใช่การเริ่มเปิดเรื่อง ต้องปล่อยให้เส้นทางปกติตอบ
_INQUIRY_PATTERNS = (
    "อะไรบ้าง", "มีกี่", "คืออะไร", "หมายถึงอะไร", "ต่างกันอย่างไร",
    "ดูประเภท", "ขอดู", "อยากรู้ว่า", "สอบถาม",
)
_CANCEL_PATTERNS = ("ยกเลิก", "ไม่เอาแล้ว", "หยุดก่อน", "เลิก", "cancel")
# คำตอบสั้น ๆ ที่แปลว่าข้ามขั้นตอนที่ไม่บังคับ เช่น หมายเลขผู้ใช้ไฟ
_SKIP_PATTERNS = ("ไม่มี", "ไม่ทราบ", "ข้าม", "ไม่รู้", "จำไม่ได้", "skip", "ไม่สะดวก")
# จำนวนครั้งที่ยอมให้ตอบขั้นเดิมไม่ผ่าน ก่อนข้ามขั้นที่ไม่บังคับให้อัตโนมัติ
_MAX_STEP_RETRIES = 3

_CANCELLED_MESSAGE = "ยกเลิกการแจ้งเรื่องแล้วครับ หากต้องการเริ่มใหม่แจ้งได้เสมอครับ"
_DECLINED_MESSAGE = (
    "เข้าใจครับ เมื่อไม่ได้รับความยินยอมระบบจะไม่เก็บข้อมูลและไม่ส่งเรื่องต่อ "
    "หากเปลี่ยนใจภายหลังแจ้งได้เสมอครับ"
)
_CATALOG_UNAVAILABLE_MESSAGE = (
    "ขณะนี้ระบบ VOC ไม่พร้อมให้บริการ จึงยังเปิดเรื่องใหม่ไม่ได้ครับ กรุณาลองใหม่อีกครั้งภายหลังครับ"
)


class VocGuidedFlow:
    """Drive VOC intake deterministically from the gateway catalog."""

    def __init__(
        self,
        tool: Any,
        *,
        consent_notice_version: str,
        prefiller: Any = None,
    ) -> None:
        self._tool = tool
        self._consent_notice_version = consent_notice_version
        # ตัวช่วยเติมคำตอบที่ผู้ใช้บอกมาแล้ว ทำงานได้เฉพาะกับตัวเลือกที่ catalog ให้มา
        self._prefiller = prefiller
        self._states: dict[UUID, VocIntakeState] = {}
        self._prompts: dict[UUID, ChoicePrompt] = {}
        self._retries: dict[UUID, int] = {}

    # ------------------------------------------------------------------ seam

    def is_active(self, conversation_id: UUID) -> bool:
        return conversation_id in self._states

    async def start(self, conversation_id: UUID, message: str) -> GuidedTurn | None:
        if self.is_active(conversation_id) or not _wants_new_case(message):
            return None
        try:
            flow = self._flow()
        except BackendError:
            # catalog อ่านไม่ได้แปลว่าเดินขั้นตอนโดยไม่เดารหัสไม่ได้ จึงไม่เปิด session ค้างไว้
            return GuidedTurn(message=_CATALOG_UNAVAILABLE_MESSAGE, finished=True)
        state = VocIntakeState()
        # ข้อความเปิดเรื่องมักระบุประเภทมาแล้ว เช่น "ร้องเรียนบริการ" จึงข้ามคำถามแรกให้
        if (journey := self._journey_from_text(flow, message)) is not None:
            state = state.with_answer(STEP_JOURNEY, journey)
        elif _is_generic_complaint(message) and any(
            item.get("code") == "SERVICE_ISSUE" for item in flow.journeys()
        ):
            state = state.with_answer(STEP_JOURNEY, "SERVICE_ISSUE")
        state = _retain_explicit_ca(flow, state, message)

        opening_narrative = _extract_opening_narrative(message)
        if (
            state.answers.get(STEP_JOURNEY) == "SERVICE_ISSUE"
            and opening_narrative is not None
            and len(opening_narrative) > 2000
        ):
            prompt = ChoicePrompt(
                prompt_id=STEP_DETAIL,
                question="รายละเอียดที่เล่ามายาวเกิน 2,000 อักขระครับ กรุณาย่อรายละเอียดให้สั้นลงแล้วส่งใหม่ครับ",
                allow_free_text=True,
            )
            self._states[conversation_id] = state
            self._prompts[conversation_id] = prompt
            return GuidedTurn(message=prompt.question, prompt=prompt)

        # ผู้ใช้มักเล่าอาการมาครบในประโยคแรก การถามซ้ำทั้งหมดทำให้รู้สึกเหมือนแบบฟอร์ม
        if self._prefiller is not None:
            state = await self._prefiller.prefill(flow, state, message)
        # Deterministic fallback ensures a provider failure cannot turn a
        # meaningful opening into a 140-character subject (or lose it).
        if state.answers.get(STEP_JOURNEY) == "SERVICE_ISSUE":
            narrative = _extract_opening_narrative(message)
            if narrative is not None and STEP_DETAIL not in state.answers:
                state = state.with_answer(STEP_DETAIL, narrative)
            if STEP_DETAIL in state.answers and STEP_SUBJECT not in state.answers:
                state = state.with_answer(STEP_SUBJECT, state.answers[STEP_DETAIL][:140])
        return self._continue(conversation_id, flow, state)

    async def advance(
        self,
        conversation_id: UUID,
        message: str,
        selected_prompt_id: str | None,
        selected_value: str | None,
    ) -> GuidedTurn | None:
        state = self._states.get(conversation_id)
        if state is None:
            return None
        if selected_value is None and _wants_cancel(message):
            self.cancel(conversation_id)
            return GuidedTurn(message=_CANCELLED_MESSAGE, finished=True)

        prompt = self._prompts.get(conversation_id)
        if prompt is None:  # pragma: no cover - state และ prompt ถูกเขียนคู่กันเสมอ
            self.cancel(conversation_id)
            return None
        if selected_prompt_id is not None and selected_prompt_id != prompt.prompt_id:
            # ผู้ใช้กดปุ่มของคำถามเก่า ตอบด้วยคำถามปัจจุบันแทนการรับค่าผิดขั้น
            return GuidedTurn(message=prompt.question, prompt=prompt)

        flow = self._flow()
        state = _retain_explicit_ca(flow, state, message)
        # One structured extraction may enrich several facts in this turn.  It
        # must be persisted even when the current choice remains unresolved;
        # otherwise the next request silently reverts to stale state.
        if selected_value is None and message.strip() and self._prefiller is not None:
            enriched = await self._prefiller.prefill(flow, state, message)
            resolved_state, resolved_prompt = flow.resolve(enriched)
            self._states[conversation_id] = resolved_state
            if resolved_prompt is not None:
                self._prompts[conversation_id] = resolved_prompt
            else:
                self._prompts.pop(conversation_id, None)
            if resolved_prompt is None:
                return self._continue(conversation_id, flow, resolved_state)
            if resolved_prompt.prompt_id != prompt.prompt_id:
                return GuidedTurn(message=resolved_prompt.question, prompt=resolved_prompt)
            state, prompt = resolved_state, resolved_prompt

        answer = selected_value if selected_value is not None else message
        if prompt.options and selected_value is None:
            # ปุ่มกดไม่ได้ในโหมดเสียงหรือสายโทรศัพท์ จึงจับคู่จากข้อความแบบกำหนดผลได้
            matched = _match_option(prompt, message)
            if matched is None:
                if prompt.allow_free_text:
                    # ขั้นที่พิมพ์ตอบได้ เช่น CA ให้ถือว่าเป็นคำตอบอิสระ ไม่ใช่การเลือกผิด
                    answer = message
                else:
                    # Enriched state/prompt was saved above before clarification.
                    return GuidedTurn(
                        message=f"ขออภัยครับ ยังจับคู่กับตัวเลือกไม่ได้\n{prompt.question}",
                        prompt=prompt,
                    )
            else:
                answer = matched

        if prompt.prompt_id == STEP_CONSENT and answer == CONSENT_DECLINE:
            self.cancel(conversation_id)
            return GuidedTurn(message=_DECLINED_MESSAGE, finished=True)
        try:
            state = flow.apply(state, prompt, answer)
        except IntakeError as error:
            # ถามซ้ำขั้นเดิมได้ไม่จำกัดจะกลายเป็นวนตัน ขั้นที่ข้ามได้จึงข้ามให้หลังพยายามพอสมควร
            attempts = self._retries.get(conversation_id, 0) + 1
            self._retries[conversation_id] = attempts
            if attempts >= _MAX_STEP_RETRIES and any(
                option.value == CA_SKIP for option in prompt.options
            ):
                state = flow.apply(state, prompt, CA_SKIP)
                self._retries.pop(conversation_id, None)
                return self._continue(conversation_id, flow, state)
            return GuidedTurn(message=f"{error}\n{prompt.question}", prompt=prompt)
        self._retries.pop(conversation_id, None)
        state = _retain_explicit_ca(flow, state, message)
        return self._continue(conversation_id, flow, state)

    def cancel(self, conversation_id: UUID) -> None:
        self._states.pop(conversation_id, None)
        self._prompts.pop(conversation_id, None)
        self._retries.pop(conversation_id, None)

    def reset(self) -> None:
        self._states.clear()
        self._prompts.clear()
        self._retries.clear()

    def attach_llm(self, llm_client: Any) -> None:
        """เปิดใช้การเติมคำตอบจากข้อความเดิมเมื่อ runtime มี LLM ให้ใช้"""
        if self._prefiller is None and llm_client is not None:
            self._prefiller = VocPrefiller(llm_client)

    # ------------------------------------------------------------------ internals

    def _flow(self) -> VocIntakeFlow:
        return VocIntakeFlow(
            self._tool.get_catalog(),
            consent_notice_version=self._consent_notice_version,
        )

    def _continue(self, conversation_id: UUID, flow: VocIntakeFlow, state: VocIntakeState) -> GuidedTurn:
        state, prompt = flow.resolve(state)
        if prompt is not None:
            self._states[conversation_id] = state
            self._prompts[conversation_id] = prompt
            return GuidedTurn(message=prompt.question, prompt=prompt)

        answers = state.answers
        payload = flow.build_external_payload(state)
        self.cancel(conversation_id)
        return GuidedTurn(
            message="ตรวจสอบรายละเอียดด้านล่างแล้วกดยืนยันเพื่อส่งเรื่องครับ",
            tool_name=ToolName.VOC,
            tool_action=ToolAction.VOC_PREPARE_CASE,
            tool_input={
                "category": _CATEGORY_BY_JOURNEY[answers[STEP_JOURNEY]],
                "subject": answers[STEP_SUBJECT],
                "detail": answers[STEP_DETAIL],
                "contactName": _reporter_field(payload, "firstName", "lastName") or "ไม่ระบุ",
                "contactPhone": _reporter_value(payload, "phone") or "ไม่ระบุ",
                "location": payload["incident"]["locationText"],
                "contactChannel": "phone" if _reporter_value(payload, "phone") else "none",
                "idempotencyKey": f"voc-{uuid4()}",
                "externalPayload": payload,
            },
            finished=True,
        )

    def _journey_from_text(self, flow: VocIntakeFlow, message: str) -> str | None:
        """จับคู่ข้อความเปิดเรื่องกับ label หรือวลีเจตนาที่กำหนดผลได้"""
        text = " ".join(message.casefold().split())
        if "ร้องเรียนบริการ" in text or "แจ้งปัญหาด้านบริการ" in text:
            if any(item.get("code") == "SERVICE_ISSUE" for item in flow.journeys()):
                return "SERVICE_ISSUE"
        matches = {
            item["code"]
            for item in flow.journeys()
            if isinstance(item.get("label"), str) and item["label"].casefold() in text
        }
        return next(iter(matches)) if len(matches) == 1 else None


# journeyCode ของ gateway จับคู่กับ VocCategory ในสัญญาภายในแบบหนึ่งต่อหนึ่ง
_CATEGORY_BY_JOURNEY = {
    "POWER_QUALITY": "power_quality",
    "SERVICE_ISSUE": "service",
    "PRAISE": "compliment",
    "TIP_OFF": "tip_off",
    "STAKEHOLDER_ISSUE": "operations",
    "STAKEHOLDER_FEEDBACK": "stakeholder_feedback",
}


def _wants_new_case(message: str) -> bool:
    text = " ".join(message.casefold().split())
    if any(term in text for term in _TRACKING_PATTERNS + _INQUIRY_PATTERNS):
        return False
    return any(term in text for term in _START_PATTERNS)


def _wants_cancel(message: str) -> bool:
    text = " ".join(message.casefold().split())
    return any(term in text for term in _CANCEL_PATTERNS)


def _retain_explicit_ca(flow: VocIntakeFlow, state: VocIntakeState, message: str) -> VocIntakeState:
    journey_code = state.answers.get(STEP_JOURNEY)
    supports_ca = journey_code is not None and any(
        item.get("code") == journey_code and item.get("supportsCaNumber") is True
        for item in flow.journeys()
    )
    if STEP_CA_NUMBER in state.answers:
        # Keep an early fact until journey selection resolves, but remove it
        # before an anonymous/unsupported journey can carry it to the payload.
        if journey_code is None or supports_ca:
            return state
        return VocIntakeState({key: value for key, value in state.answers.items() if key != STEP_CA_NUMBER})
    ca_number = extract_explicit_ca_number(message)
    if ca_number is None:
        return state
    # A labelled, validated CA is a user fact even before journey is known.
    return state.with_answer(STEP_CA_NUMBER, ca_number) if journey_code is None or supports_ca else state


def _is_generic_complaint(message: str) -> bool:
    text = " ".join(message.casefold().split())
    return "ร้องเรียน" in text and "บริการ" in text and _extract_opening_narrative(message) is None


def _extract_opening_narrative(message: str) -> str | None:
    """Keep meaningful opening text while dropping polite intent-only filler."""
    original = " ".join(message.split()).strip(" .,:-")
    if not original:
        return None
    lowered = original.casefold()
    for lead in ("ขอ", "อยาก", "ต้องการ", "ช่วย"):
        if lowered.startswith(lead):
            return _extract_opening_narrative(original[len(lead):].lstrip())
    markers = ("ร้องเรียนบริการ", "แจ้งปัญหาด้านบริการ", "แจ้งเรื่องร้องเรียน", "ร้องเรียน")
    for marker in markers:
        index = lowered.find(marker)
        if index < 0:
            continue
        before = original[:index].strip(" .,:-")
        after = original[index + len(marker):].strip(" .,:-")
        filler = ("หน่อย", "ครับ", "ค่ะ", "คะ", "นะ", "ที", "ได้ไหม", "ด้วย")
        after_words = after.split()
        while after_words and any(after_words[0].casefold().startswith(word) for word in filler):
            after_words.pop(0)
        after = " ".join(after_words).strip(" .,:-")
        # An intent phrase in the middle follows a meaningful narrative; keep
        # the complete opening rather than truncating it at the intent marker.
        # "อยากร้องเรียน ..." is intent-only lead-in, while a sentence such
        # as "พนักงานพูดไม่สุภาพ เลยอยากร้องเรียน ..." contains a narrative.
        before_intent_only = before.casefold().strip()
        for lead in ("อยาก", "ต้องการ", "ขอ", "เลย", "ช่วย", "ร้องเรียน", "แจ้งเรื่อง", "แจ้งปัญหา"):
            before_intent_only = before_intent_only.replace(lead, " ").strip()
        candidate = after if not before else original
        if candidate and (not before or before_intent_only):
            if not all(word.casefold() in filler for word in candidate.split()):
                return candidate
        if before and before_intent_only and not all(word.casefold() in filler for word in before.split()):
            return before
        return None
    return None


def _match_option(prompt: ChoicePrompt, message: str) -> str | None:
    text = " ".join(message.casefold().split())
    if not text:
        return None
    # Consent is an explicit response to the current notice.  Never accept a
    # substring such as "ยินยอมครับ" as consent.
    if prompt.prompt_id == STEP_CONSENT:
        exact = {
            option.value: option
            for option in prompt.options
            if option.value.casefold() == text or option.label.casefold() == text
        }
        return next(iter(exact), None) if len(exact) == 1 else None
    # ขั้นที่ข้ามได้ ผู้ใช้มักตอบสั้น ๆ ว่า "ไม่มี" ไม่ใช่อ่าน label เต็ม
    if any(option.value == CA_SKIP for option in prompt.options) and any(
        term in text for term in _SKIP_PATTERNS
    ):
        return CA_SKIP
    exact = [option.value for option in prompt.options if option.label.casefold() == text]
    if len(exact) == 1:
        return exact[0]
    # รองรับการตอบด้วยลำดับข้อ เช่น "2" หรือ "ข้อ 2"
    if (ordinal := re.fullmatch(r"(?:ข้อ\s*)?(\d{1,2})", text)) is not None:
        index = int(ordinal.group(1)) - 1
        if 0 <= index < len(prompt.options):
            return prompt.options[index].value
    contained = [option.value for option in prompt.options if option.label.casefold() in text]
    return contained[0] if len(contained) == 1 else None


def _reporter_value(payload: dict[str, Any], key: str) -> str | None:
    reporter = payload.get("reporter")
    if isinstance(reporter, dict) and isinstance(reporter.get(key), str):
        return reporter[key]
    return None


def _reporter_field(payload: dict[str, Any], *keys: str) -> str | None:
    parts = [value for key in keys if (value := _reporter_value(payload, key))]
    return " ".join(dict.fromkeys(parts)) if parts else None
