"""Extract user-stated VOC facts with strict evidence checks.

The model is called once for a turn and can only suggest catalog values or
free-text spans that the user actually supplied.  Consent, CA, and area codes
are deterministic user/system facts and are never accepted from model output.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

from app.llm.models import LLMMessage, LLMRequest
from app.plugins.voc.intake import (
    STEP_CA_NUMBER,
    STEP_CONSENT,
    STEP_DETAIL,
    STEP_DISTRICT,
    STEP_FREQUENCY,
    STEP_ISSUE,
    STEP_JOURNEY,
    STEP_LOCATION_TEXT,
    STEP_OFFICE,
    STEP_PREFIX,
    STEP_PROVINCE,
    STEP_REPORTER_NAME,
    STEP_REPORTER_PHONE,
    STEP_REQUEST_TYPE,
    STEP_SEVERITY,
    STEP_SUBDISTRICT,
    STEP_SUBJECT,
    STEP_SUB_ISSUE,
    STEP_TOPIC,
    VocIntakeFlow,
    VocIntakeState,
    extract_explicit_ca_number,
)

logger = logging.getLogger(__name__)

_NEVER_PREFILL = frozenset({STEP_CONSENT, STEP_CA_NUMBER})
_FREE_TEXT_FIELDS = frozenset({
    STEP_DETAIL, STEP_SUBJECT, STEP_LOCATION_TEXT, STEP_REPORTER_NAME, STEP_REPORTER_PHONE,
})
_FIELD_ALIASES = {
    "journey": STEP_JOURNEY,
    "requestType": STEP_REQUEST_TYPE,
    "topic": STEP_TOPIC,
    "issue": STEP_ISSUE,
    "subIssue": STEP_SUB_ISSUE,
    "frequency": STEP_FREQUENCY,
    "severity": STEP_SEVERITY,
    "subject": STEP_SUBJECT,
    "detail": STEP_DETAIL,
    "reporterName": STEP_REPORTER_NAME,
    "reporterPhone": STEP_REPORTER_PHONE,
    "location": STEP_LOCATION_TEXT,
    "locationText": STEP_LOCATION_TEXT,
    "prefix": STEP_PREFIX,
}
_FIELD_ORDER = (
    STEP_JOURNEY, STEP_REQUEST_TYPE, STEP_TOPIC, STEP_ISSUE, STEP_SUB_ISSUE,
    STEP_FREQUENCY, STEP_SEVERITY, STEP_DETAIL, STEP_SUBJECT, STEP_LOCATION_TEXT,
    STEP_PREFIX, STEP_REPORTER_NAME, STEP_REPORTER_PHONE,
)
_CORRECTION_MARKERS = ("แก้ไข", "ขอแก้", "แก้", "เปลี่ยน", "ข้อมูลใหม่", "แทนค่าเดิม")
_PROMPT = """ไม่ต้องเรียก tool ใด ๆ ให้ตอบด้วย toolCalls เป็น [] และ directResponse เป็น null
ใส่ JSON ของงานนี้เป็นสตริงใน field message ของ planner envelope

งาน: สกัดข้อมูลที่ผู้ใช้ระบุจริงจากข้อความสำหรับแบบฟอร์มร้องเรียนการไฟฟ้า
ข้อความผู้ใช้:
{message}

รายการ catalog ที่อนุญาต (ใช้ตรวจรหัสและลำดับชั้นเท่านั้น):
{catalog}

คืนรูปแบบนี้เท่านั้น:
{{"fields": {{"fieldName": {{"value": "...", "evidence": "ข้อความช่วงที่ผู้ใช้ระบุจริง", "explicitCorrection": false}}}}}}
fieldName ใช้ได้เฉพาะ journey, requestType, topic, issue, subIssue, frequency,
severity, subject, detail, reporterName, reporterPhone, location, prefix
ใส่เฉพาะค่าที่มีหลักฐานอยู่ในข้อความนี้ ห้ามเดา ห้ามใส่ consent, caNumber,
province, district, subdistrict หรือ office
value ของ taxonomy ต้องเป็น code ที่อยู่ใน catalog และ evidence ต้องเป็นข้อความจริง
จากผู้ใช้ ส่วน free-text value ต้องเป็นข้อความช่วงเดียวกับที่ผู้ใช้พิมพ์จริง
explicitCorrection เป็นข้อมูลประกอบเท่านั้น ไม่ใช่สิทธิ์เขียนทับค่าที่รู้แล้ว
ถ้าไม่มีข้อมูลให้คืน fields เป็น {{}}"""


class VocPrefiller:
    """Extract all safely retainable facts from one user message."""

    def __init__(self, llm_client: Any) -> None:
        self._llm = llm_client

    async def prefill(
        self,
        flow: VocIntakeFlow,
        state: VocIntakeState,
        message: str,
    ) -> VocIntakeState:
        text = message.strip()
        if not text:
            return state

        # This is deterministic and deliberately happens outside the model
        # fields contract.  It lets a CA supplied in the opening turn skip the
        # optional question without allowing the model to invent one.
        state = _retain_explicit_ca(flow, state, text)
        if self._llm is None:
            return state
        extracted = await self._extract(text, flow)
        if extracted is None:
            return state

        for field in _FIELD_ORDER:
            fact = extracted.get(field)
            if not isinstance(fact, dict):
                continue
            value = fact.get("value")
            evidence = fact.get("evidence")
            if not isinstance(value, (str, int)) or not isinstance(evidence, str):
                continue
            value_text = str(value).strip()
            evidence_text = evidence.strip()
            if not value_text or not _evidence_in_message(evidence_text, text):
                continue
            if field in _FREE_TEXT_FIELDS:
                if not _value_in_message(value_text, text, field):
                    continue
            elif not _catalog_value_matches_evidence(flow, field, value_text, evidence_text):
                continue
            previous = state.answers.get(field)
            if previous is not None and previous != value_text:
                # The model's explicitCorrection flag is intentionally ignored.
                # Only an actual correction phrase in this same user message
                # can authorize replacing a known answer.
                if not _deterministic_correction(text, field, value_text):
                    continue
            if previous == value_text:
                continue
            try:
                state = flow.apply_prefilled(state, field, value_text)
            except Exception:  # noqa: BLE001 - invalid suggestions fail closed
                logger.info("voc_prefill_rejected", extra={"promptId": field})

        # The model may have established the journey after the first
        # deterministic CA check; repeat the same deterministic check, never a
        # model check, so an explicitly labelled CA in an opening is retained.
        state = _retain_explicit_ca(flow, state, text)

        # A narrative is authoritative detail; subject is only its bounded
        # derivative and cannot replace or shorten the detail.
        if STEP_DETAIL in state.answers and STEP_SUBJECT not in state.answers:
            detail = state.answers[STEP_DETAIL]
            if isinstance(detail, str):
                state = state.with_answer(STEP_SUBJECT, detail[:140])
        return state

    async def _extract(self, message: str, flow: VocIntakeFlow) -> dict[str, dict[str, Any]] | None:
        instruction = _PROMPT.format(
            message=message,
            catalog=json.dumps(flow.catalog_for_prefill(), ensure_ascii=False),
        )
        try:
            response = await self._llm.complete(
                LLMRequest((LLMMessage("user", instruction),), (), uuid4(), None, ())
            )
        except Exception:  # noqa: BLE001 - provider failure must retain state
            logger.warning("voc_prefill_llm_unavailable")
            return None
        payload = _parse_extraction(response.text)
        if payload is None:
            logger.info("voc_prefill_malformed_output")
            return None
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            # Value-only/legacy responses are intentionally not interpreted.
            return None
        result: dict[str, dict[str, Any]] = {}
        for name, fact in fields.items():
            step = _FIELD_ALIASES.get(name)
            if step is not None and step not in _NEVER_PREFILL and isinstance(fact, dict):
                result[step] = fact
        return result


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _evidence_in_message(evidence: str, message: str) -> bool:
    evidence_text = _normalise(evidence)
    return bool(evidence_text) and evidence_text in _normalise(message)


def _catalog_value_matches_evidence(
    flow: VocIntakeFlow, field: str, value: str, evidence: str
) -> bool:
    """Require catalog-backed evidence to describe the selected option.

    Codes are not usually literal Thai spans.  Their only accepted
    transformation is selecting the catalog row whose label/name is the
    supplied evidence; this prevents an unrelated name from authorizing a
    guessed code.
    """
    catalog = flow.catalog_for_prefill()
    rows: list[dict[str, Any]] = []
    if field == STEP_JOURNEY:
        rows = flow.journeys()
    elif field == STEP_REQUEST_TYPE:
        rows = [row for row in catalog.get("requestTypes", []) if isinstance(row, dict)]
    elif field == STEP_TOPIC:
        for request in catalog.get("requestTypes", []):
            if isinstance(request, dict):
                rows.extend(row for row in request.get("topics", []) if isinstance(row, dict))
    elif field == STEP_ISSUE:
        for request in catalog.get("requestTypes", []):
            if isinstance(request, dict):
                for topic in request.get("topics", []):
                    if isinstance(topic, dict):
                        rows.extend(row for row in topic.get("issues", []) if isinstance(row, dict))
    elif field == STEP_SUB_ISSUE:
        for request in catalog.get("requestTypes", []):
            if isinstance(request, dict):
                for topic in request.get("topics", []):
                    if isinstance(topic, dict):
                        for issue in topic.get("issues", []):
                            if isinstance(issue, dict):
                                rows.extend(row for row in issue.get("subIssues", []) if isinstance(row, dict))
    elif field == STEP_FREQUENCY:
        rows = [row for row in catalog.get("incidentFrequencies", []) if isinstance(row, dict)]
    elif field == STEP_SEVERITY:
        rows = [row for row in catalog.get("severityLevels", []) if isinstance(row, dict)]
    elif field == STEP_PREFIX:
        rows = [row for row in catalog.get("titlePrefixes", []) if isinstance(row, dict)]
    else:
        return False
    evidence_text = _normalise(evidence)
    if not evidence_text:
        return False

    # Evidence must identify one complete catalog entry.  A shared fragment
    # such as "บริการ" is not enough to distinguish labels such as
    # "บริการล่าช้า" and "บริการไม่ดี".
    matching_rows = []
    for row in rows:
        code = str(row.get("code", row.get("level", "")))
        catalog_terms = [code, *(row.get(key) for key in ("label", "name", "description"))]
        if any(isinstance(term, str) and evidence_text == _normalise(term) for term in catalog_terms):
            matching_rows.append(row)
    if len(matching_rows) != 1:
        return False
    row = matching_rows[0]
    return str(row.get("code", row.get("level", ""))) == value


def _value_in_message(value: str, message: str, field: str) -> bool:
    value_text = _normalise(value)
    message_text = _normalise(message)
    if value_text and value_text in message_text:
        return True
    # Phone punctuation is a deterministic presentation transformation, not a
    # model-authorized change: all digits must occur contiguously in the source.
    if field == STEP_REPORTER_PHONE:
        digits = re.sub(r"[^0-9]", "", value)
        source_digits = re.sub(r"[^0-9]", "", message)
        return bool(digits) and digits in source_digits
    return False


def _deterministic_correction(message: str, field: str, value: str) -> bool:
    text = _normalise(message)
    if not any(marker in text for marker in _CORRECTION_MARKERS):
        return False
    if not _value_in_message(value, message, field):
        return False
    # Require a target word so a generic "เปลี่ยน" elsewhere cannot overwrite
    # an unrelated known field.
    targets = {
        STEP_DETAIL: ("รายละเอียด", "เรื่อง"),
        STEP_SUBJECT: ("หัวข้อ", "เรื่อง"),
        STEP_LOCATION_TEXT: ("สถานที่", "ที่เกิดเหตุ", "ที่อยู่"),
        STEP_REPORTER_NAME: ("ชื่อ",),
        STEP_REPORTER_PHONE: ("เบอร์", "โทรศัพท์", "โทร"),
    }
    return field not in targets or any(target in text for target in targets[field])


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


def _parse_extraction(raw: str) -> dict[str, Any] | None:
    payload = _parse_json(raw)
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if isinstance(message, str):
        nested = _parse_json(message)
        return nested if isinstance(nested, dict) else None
    return payload if isinstance(payload.get("fields"), dict) else None


def _parse_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        if lines and lines[0].strip().casefold() in {"json", "jsonc"}:
            lines = lines[1:]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
