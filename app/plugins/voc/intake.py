"""Catalog-driven VOC intake: ask one answerable question at a time.

The VOC gateway accepts a case only with a canonical ``externalPayload`` full of
taxonomy codes (journey, request type, topic, issue, sub-issue, frequency,
severity, province/district/subdistrict/PEA office).  A language model cannot
invent those codes, so letting it drive intake produces guessed values or an
endless clarification loop.

This module derives every step from the live catalog instead.  Each step offers
the exact options the catalog declares, and the next step is computed from the
selected journey's own requirement flags, so a catalog that gains a journey or
an issue changes the conversation without a code change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.contracts import ChoiceOption, ChoicePrompt

# ขั้นตอนที่ต้องพิมพ์ตอบ ไม่ใช่การกดเลือกจาก catalog
STEP_DETAIL = "voc_detail"
STEP_SUBJECT = "voc_subject"
STEP_REPORTER_NAME = "voc_reporter_name"
STEP_REPORTER_PHONE = "voc_reporter_phone"
STEP_LOCATION_TEXT = "voc_location_text"

STEP_CA_NUMBER = "voc_ca_number"

STEP_JOURNEY = "voc_journey"
STEP_REQUEST_TYPE = "voc_request_type"
STEP_TOPIC = "voc_topic"
STEP_ISSUE = "voc_issue"
STEP_SUB_ISSUE = "voc_sub_issue"
STEP_FREQUENCY = "voc_frequency"
STEP_SEVERITY = "voc_severity"
STEP_PREFIX = "voc_prefix"
STEP_PROVINCE = "voc_province"
STEP_DISTRICT = "voc_district"
STEP_SUBDISTRICT = "voc_subdistrict"
STEP_OFFICE = "voc_office"
STEP_CONSENT = "voc_consent"

CONSENT_ACCEPT = "accept"
CONSENT_DECLINE = "decline"
CA_SKIP = "skip"

_CONSENT_QUESTION = (
    "เพื่อส่งเรื่องให้ PEA ระบบต้องเก็บและใช้ชื่อ เบอร์ติดต่อ และรายละเอียดที่ท่านให้ไว้ "
    "เพื่อดำเนินการและติดต่อกลับเท่านั้น ท่านยินยอมหรือไม่ครับ"
)

_MAX_TEXT = {
    STEP_SUBJECT: 140,
    STEP_DETAIL: 2000,
    STEP_REPORTER_NAME: 100,
    STEP_REPORTER_PHONE: 32,
    STEP_LOCATION_TEXT: 500,
    STEP_CA_NUMBER: 32,
}

# รหัสพื้นที่ที่ใช้เมื่อจับคู่ข้อความของผู้ใช้กับ catalog ไม่ได้
# VOC ปลายทาง map พื้นที่จาก locationText เองอยู่แล้ว จึงไม่ควรบล็อกผู้ใช้ที่อยู่นอกข้อมูลตัวอย่าง
_UNRESOLVED_AREA_CODE = "UNSPECIFIED"

# CA บนใบแจ้งค่าไฟเป็นตัวเลข 12 หลักตามสัญญาของ OMS
_CA_PATTERN = re.compile(r"^[0-9]{12}$")


class IntakeError(RuntimeError):
    """ผู้ใช้ตอบไม่ตรงกับตัวเลือกที่ catalog ประกาศไว้"""


@dataclass(frozen=True, slots=True)
class VocIntakeState:
    """คำตอบที่ยืนยันแล้วของบทสนทนาหนึ่ง ทุกค่ามาจาก catalog หรือข้อความผู้ใช้จริง"""

    answers: dict[str, Any] = field(default_factory=dict)

    def with_answer(self, step: str, value: Any) -> "VocIntakeState":
        merged = dict(self.answers)
        merged[step] = value
        # การย้อนไปแก้ขั้นต้นทางต้องล้างคำตอบปลายทางที่ขึ้นกับมัน มิฉะนั้นรหัสจะไม่สอดคล้องกัน
        for dependent in _DEPENDENTS.get(step, ()):
            merged.pop(dependent, None)
        return VocIntakeState(merged)


# ลำดับการพึ่งพา: เปลี่ยนคำตอบต้นทางแล้วคำตอบปลายทางใช้ไม่ได้อีก
_DEPENDENTS: dict[str, tuple[str, ...]] = {
    STEP_JOURNEY: (
        STEP_REQUEST_TYPE, STEP_TOPIC, STEP_ISSUE, STEP_SUB_ISSUE,
        STEP_FREQUENCY, STEP_SEVERITY,
    ),
    STEP_REQUEST_TYPE: (STEP_TOPIC, STEP_ISSUE, STEP_SUB_ISSUE),
    STEP_TOPIC: (STEP_ISSUE, STEP_SUB_ISSUE),
    STEP_ISSUE: (STEP_SUB_ISSUE,),
    STEP_PROVINCE: (STEP_DISTRICT, STEP_SUBDISTRICT, STEP_OFFICE),
    STEP_DISTRICT: (STEP_SUBDISTRICT, STEP_OFFICE),
    STEP_SUBDISTRICT: (STEP_OFFICE,),
}


class VocIntakeFlow:
    """อ่าน catalog แล้วสร้างคำถามถัดไปและ payload สุดท้ายแบบกำหนดผลได้

    ไม่เก็บสถานะเอง ผู้เรียกส่ง ``VocIntakeState`` เข้ามาทุกครั้ง จึงทดสอบได้ตรงไปตรงมา
    """

    def __init__(self, catalog: dict[str, Any], *, consent_notice_version: str) -> None:
        self._catalog = catalog
        self._consent_notice_version = consent_notice_version

    # ------------------------------------------------------------------ catalog

    def journeys(self) -> list[dict[str, Any]]:
        """ประเภทเรื่องทั้งหมดที่ catalog ประกาศ"""
        return [item for item in self._catalog.get("journeys", []) if isinstance(item, dict)]

    def _journey(self, code: str) -> dict[str, Any]:
        for item in self.journeys():
            if item.get("code") == code:
                return item
        raise IntakeError(f"ไม่พบประเภทเรื่อง {code} ใน catalog")

    def _request_types(self, journey_code: str) -> list[dict[str, Any]]:
        roots = self._journey(journey_code).get("classificationRootCodes", [])
        return [
            item
            for item in self._catalog.get("requestTypes", [])
            if isinstance(item, dict) and item.get("code") in roots
        ]

    def _request_type(self, journey_code: str, code: str) -> dict[str, Any]:
        for item in self._request_types(journey_code):
            if item.get("code") == code:
                return item
        raise IntakeError(f"ไม่พบประเภทคำร้อง {code} ใน catalog")

    def _topic(self, journey_code: str, request_code: str, code: str) -> dict[str, Any]:
        for item in self._request_type(journey_code, request_code).get("topics", []):
            if isinstance(item, dict) and item.get("code") == code:
                return item
        raise IntakeError(f"ไม่พบหมวด {code} ใน catalog")

    def _issue(self, journey_code: str, request_code: str, topic_code: str, code: str) -> dict[str, Any]:
        for item in self._topic(journey_code, request_code, topic_code).get("issues", []):
            if isinstance(item, dict) and item.get("code") == code:
                return item
        raise IntakeError(f"ไม่พบประเด็น {code} ใน catalog")

    def _service_areas(self) -> list[dict[str, Any]]:
        return [item for item in self._catalog.get("serviceAreas", []) if isinstance(item, dict)]

    # ------------------------------------------------------------------ stepping

    def next_prompt(self, state: VocIntakeState) -> ChoicePrompt | None:
        """คำถามถัดไปที่ยังขาด หรือ ``None`` เมื่อข้อมูลครบพอจะเตรียมเรื่องแล้ว"""
        return self.resolve(state)[1]

    def resolve(self, state: VocIntakeState) -> tuple[VocIntakeState, ChoicePrompt | None]:
        """เดินลำดับคำถามจนถึงขั้นที่ต้องให้ผู้ใช้ตอบจริง

        คืน state ที่รวมคำตอบซึ่งมีทางเลือกเดียวไว้แล้ว เพื่อไม่ถามคำถามที่ไม่มีทางเลือก
        และเพื่อให้ payload สุดท้ายมีรหัสครบตามที่ catalog กำหนด
        """
        answers = state.answers

        if STEP_JOURNEY not in answers:
            return state, _prompt(
                STEP_JOURNEY,
                "ท่านต้องการแจ้งเรื่องประเภทใดครับ",
                [
                    ChoiceOption(
                        value=item["code"],
                        label=item.get("label", item["code"]),
                        description=item.get("description"),
                    )
                    for item in self.journeys()
                ],
            )

        journey_code = answers[STEP_JOURNEY]
        journey = self._journey(journey_code)

        if STEP_REQUEST_TYPE not in answers:
            options = self._request_types(journey_code)
            if len(options) == 1:
                return self.resolve(state.with_answer(STEP_REQUEST_TYPE, options[0]["code"]))
            return state, _prompt(
                STEP_REQUEST_TYPE,
                "ขอทราบลักษณะของเรื่องที่ต้องการแจ้งครับ",
                [ChoiceOption(value=item["code"], label=item.get("name", item["code"])) for item in options],
            )

        request_code = answers[STEP_REQUEST_TYPE]

        if STEP_TOPIC not in answers:
            topics = [t for t in self._request_type(journey_code, request_code).get("topics", []) if isinstance(t, dict)]
            if len(topics) == 1:
                return self.resolve(state.with_answer(STEP_TOPIC, topics[0]["code"]))
            return state, _prompt(
                STEP_TOPIC,
                "เรื่องนี้เกี่ยวข้องกับหมวดใดครับ",
                [ChoiceOption(value=t["code"], label=t.get("name", t["code"])) for t in topics],
            )

        topic_code = answers[STEP_TOPIC]

        if STEP_ISSUE not in answers:
            issues = [i for i in self._topic(journey_code, request_code, topic_code).get("issues", []) if isinstance(i, dict)]
            if len(issues) == 1:
                return self.resolve(state.with_answer(STEP_ISSUE, issues[0]["code"]))
            return state, _prompt(
                STEP_ISSUE,
                "ขอทราบประเด็นที่ตรงที่สุดครับ",
                [ChoiceOption(value=i["code"], label=i.get("name", i["code"])) for i in issues],
            )

        issue_code = answers[STEP_ISSUE]

        if journey.get("requiresSubIssue") and STEP_SUB_ISSUE not in answers:
            subs = [
                s
                for s in self._issue(journey_code, request_code, topic_code, issue_code).get("subIssues", [])
                if isinstance(s, dict)
            ]
            if subs:
                if len(subs) == 1:
                    return self.resolve(state.with_answer(STEP_SUB_ISSUE, subs[0]["code"]))
                return state, _prompt(
                    STEP_SUB_ISSUE,
                    "ขอทราบรายละเอียดย่อยของประเด็นครับ",
                    [ChoiceOption(value=s["code"], label=s.get("name", s["code"])) for s in subs],
                )

        if journey.get("requiresFrequency") and STEP_FREQUENCY not in answers:
            return state, _prompt(
                STEP_FREQUENCY,
                "เหตุการณ์นี้เกิดบ่อยเพียงใดครับ",
                [
                    ChoiceOption(value=f["code"], label=f.get("name", f["code"]))
                    for f in self._catalog.get("incidentFrequencies", [])
                    if isinstance(f, dict)
                ],
            )

        if journey.get("requiresSeverity") and STEP_SEVERITY not in answers:
            return state, _prompt(
                STEP_SEVERITY,
                "เหตุการณ์นี้ส่งผลกระทบระดับใดครับ",
                [
                    ChoiceOption(value=str(s["level"]), label=s.get("name", str(s["level"])))
                    for s in self._catalog.get("severityLevels", [])
                    if isinstance(s, dict)
                ],
            )

        if journey.get("requiresIncidentLocation", True):
            location_state, location_prompt = self._location_step(state)
            if location_prompt is not None:
                return state, location_prompt
            if location_state is not state:
                return self.resolve(location_state)

        if STEP_SUBJECT not in answers:
            return state, _text_prompt(STEP_SUBJECT, "ขอหัวข้อเรื่องสั้น ๆ ของเรื่องที่ต้องการแจ้งครับ")
        if STEP_DETAIL not in answers:
            return state, _text_prompt(STEP_DETAIL, "ขอรายละเอียดของเรื่องครับ ยิ่งละเอียดยิ่งช่วยให้ตรวจสอบได้เร็วขึ้น")

        # TIP_OFF แจ้งแบบไม่ระบุตัวตนได้ ตาม reporterMode ที่ catalog ประกาศ
        if journey.get("reporterMode") == "REQUIRED":
            if STEP_PREFIX not in answers:
                return state, _prompt(
                    STEP_PREFIX,
                    "ขอคำนำหน้าชื่อของท่านครับ",
                    [
                        ChoiceOption(value=p["code"], label=p.get("label", p["code"]))
                        for p in self._catalog.get("titlePrefixes", [])
                        if isinstance(p, dict)
                    ],
                )
            if STEP_REPORTER_NAME not in answers:
                return state, _text_prompt(STEP_REPORTER_NAME, "ขอชื่อและนามสกุลของท่านครับ")
            if STEP_REPORTER_PHONE not in answers:
                return state, _text_prompt(STEP_REPORTER_PHONE, "ขอเบอร์โทรที่สะดวกให้เจ้าหน้าที่ติดต่อกลับครับ")

        # CA ช่วยให้ PEA ระบุจุดใช้ไฟได้แม่นขึ้น แต่ catalog ระบุว่า "supports" ไม่ใช่ required
        # จึงต้องข้ามได้เสมอ ไม่ใช่เงื่อนไขกั้นการแจ้งเรื่อง
        if journey.get("supportsCaNumber") and STEP_CA_NUMBER not in answers:
            return state, ChoicePrompt(
                prompt_id=STEP_CA_NUMBER,
                question=(
                    "หากมีหมายเลขผู้ใช้ไฟ (CA) 12 หลักบนใบแจ้งค่าไฟ พิมพ์ได้เลยครับ "
                    "ถ้าไม่มีหรือไม่สะดวก กดข้ามได้ครับ"
                ),
                options=(ChoiceOption(value=CA_SKIP, label="ไม่มี / ข้ามขั้นตอนนี้"),),
                allow_free_text=True,
            )

        if STEP_CONSENT not in answers:
            return state, _prompt(
                STEP_CONSENT,
                _CONSENT_QUESTION,
                [
                    ChoiceOption(value=CONSENT_ACCEPT, label="ยินยอม"),
                    ChoiceOption(value=CONSENT_DECLINE, label="ไม่ยินยอม"),
                ],
            )
        return state, None

    def _location_step(self, state: VocIntakeState) -> tuple[VocIntakeState, ChoicePrompt | None]:
        """ถามสถานที่เป็นข้อความอิสระ แล้วจับคู่กับ catalog เท่าที่จับได้

        พื้นที่เป็นข้อมูลอ้างอิงเปิดที่ผู้ใช้รู้ดีกว่าระบบ และ catalog ตัวอย่างครอบคลุมไม่ครบทุกจังหวัด
        การบังคับเลือกจากรายการจึงกันผู้ใช้จริงออกจากบริการ ที่นี่จึงเก็บข้อความไว้เสมอ
        และเติมรหัสพื้นที่ให้เมื่อจับคู่ได้เท่านั้น
        """
        answers = state.answers
        if STEP_LOCATION_TEXT not in answers:
            return state, _text_prompt(
                STEP_LOCATION_TEXT,
                "เหตุเกิดที่ใดครับ ระบุจังหวัด อำเภอ และจุดสังเกตได้เลย",
            )
        if STEP_PROVINCE not in answers:
            return self._resolve_area(state, answers[STEP_LOCATION_TEXT]), None
        return state, None

    def _resolve_area(self, state: VocIntakeState, location_text: str) -> VocIntakeState:
        """เติมรหัสพื้นที่จากข้อความ โดยเลือกได้เฉพาะแถวที่มีอยู่จริงใน catalog"""
        matched = self._match_service_area(location_text)
        if matched is None:
            # ส่ง locationText ให้ VOC map เอง ดีกว่าปฏิเสธผู้ใช้ที่อยู่นอกข้อมูลตัวอย่าง
            return (
                state.with_answer(STEP_PROVINCE, _UNRESOLVED_AREA_CODE)
                .with_answer(STEP_DISTRICT, _UNRESOLVED_AREA_CODE)
                .with_answer(STEP_SUBDISTRICT, _UNRESOLVED_AREA_CODE)
                .with_answer(STEP_OFFICE, _UNRESOLVED_AREA_CODE)
            )
        return (
            state.with_answer(STEP_PROVINCE, matched["provinceCode"])
            .with_answer(STEP_DISTRICT, matched["districtCode"])
            .with_answer(STEP_SUBDISTRICT, matched["subdistrictCode"])
            .with_answer(STEP_OFFICE, matched["peaOfficeCode"])
        )

    def _match_service_area(self, location_text: str) -> dict[str, Any] | None:
        """จับคู่ข้อความกับ serviceAreas โดยให้แถวที่ตรงละเอียดที่สุดชนะ"""
        text = " ".join(location_text.casefold().split())
        best: tuple[int, dict[str, Any]] | None = None
        for area in self._service_areas():
            score = sum(
                1
                for key in ("subdistrictName", "districtName", "provinceName")
                if isinstance(area.get(key), str) and area[key].casefold() in text
            )
            if score and (best is None or score > best[0]):
                best = (score, area)
        return best[1] if best is not None else None

    # ------------------------------------------------------------------ answering

    def apply(self, state: VocIntakeState, prompt: ChoicePrompt, raw_value: str) -> VocIntakeState:
        """รับคำตอบหนึ่งขั้นหลังตรวจกับตัวเลือกจริง ป้องกันค่าปลอมจาก client"""
        value = raw_value.strip()
        if not value:
            raise IntakeError("กรุณาระบุข้อมูลครับ")
        allowed = {option.value for option in prompt.options}
        if allowed and value not in allowed and not prompt.allow_free_text:
            raise IntakeError("กรุณาเลือกจากตัวเลือกที่ระบบเสนอครับ")
        if value not in allowed:
            limit = _MAX_TEXT.get(prompt.prompt_id, 500)
            if len(value) > limit:
                raise IntakeError(f"ข้อความยาวเกิน {limit} ตัวอักษรครับ")
            if prompt.prompt_id == STEP_CA_NUMBER and not _CA_PATTERN.fullmatch(value):
                raise IntakeError(
                    "หมายเลขผู้ใช้ไฟต้องเป็นตัวเลข 12 หลักครับ หากไม่มีให้กดข้ามได้"
                )
        return state.with_answer(prompt.prompt_id, value)

    # ------------------------------------------------------------------ payload

    def is_complete(self, state: VocIntakeState) -> bool:
        return (
            self.next_prompt(state) is None
            and state.answers.get(STEP_CONSENT) == CONSENT_ACCEPT
        )

    def build_external_payload(self, state: VocIntakeState, *, accepted_at: datetime | None = None) -> dict[str, Any]:
        """ประกอบ payload ตาม catalog ที่ผู้ใช้เลือกจริง โดยไม่เติมค่าที่ไม่ได้ตอบ"""
        answers = state.answers
        if answers.get(STEP_CONSENT) != CONSENT_ACCEPT:
            raise IntakeError("ต้องได้รับความยินยอมก่อนเตรียมเรื่องครับ")
        journey_code = answers[STEP_JOURNEY]
        journey = self._journey(journey_code)

        classification: dict[str, Any] = {
            "requestTypeCode": answers[STEP_REQUEST_TYPE],
            "topicCode": answers[STEP_TOPIC],
            "issueCode": answers[STEP_ISSUE],
        }
        if STEP_SUB_ISSUE in answers:
            classification["subIssueCode"] = answers[STEP_SUB_ISSUE]

        payload: dict[str, Any] = {
            "journeyCode": journey_code,
            "incident": {
                "provinceCode": answers[STEP_PROVINCE],
                "districtCode": answers[STEP_DISTRICT],
                "subdistrictCode": answers[STEP_SUBDISTRICT],
                "peaOfficeCode": answers[STEP_OFFICE],
                "locationText": answers[STEP_LOCATION_TEXT],
            },
            "classification": classification,
            "detail": answers[STEP_DETAIL],
            "consent": {
                "accepted": True,
                "noticeVersion": self._consent_notice_version,
                "acceptedAt": (accepted_at or datetime.now(UTC)).isoformat(),
                "channel": "CHAT",
            },
        }
        ca_number = answers.get(STEP_CA_NUMBER)
        if ca_number == CA_SKIP:
            ca_number = None
        if journey.get("reporterMode") == "REQUIRED":
            first_name, _, last_name = answers[STEP_REPORTER_NAME].partition(" ")
            payload["reporter"] = {
                "prefixCode": answers[STEP_PREFIX],
                "firstName": first_name,
                "lastName": last_name.strip() or first_name,
                "phone": answers[STEP_REPORTER_PHONE],
            }
            if ca_number:
                payload["reporter"]["caNumber"] = ca_number
        elif ca_number:
            # journey แบบไม่ระบุตัวตนยังแนบ CA ได้ถ้าผู้ใช้ให้มาเอง
            payload["reporter"] = {"caNumber": ca_number}
        if STEP_FREQUENCY in answers:
            payload["frequencyCode"] = answers[STEP_FREQUENCY]
        if STEP_SEVERITY in answers:
            payload["severityLevel"] = int(answers[STEP_SEVERITY])
        return payload

    def journey_label(self, state: VocIntakeState) -> str:
        journey = self._journey(state.answers[STEP_JOURNEY])
        return journey.get("label", journey["code"])


def _prompt(prompt_id: str, question: str, options: list[ChoiceOption]) -> ChoicePrompt:
    if not options:
        raise IntakeError(f"catalog ไม่มีตัวเลือกสำหรับขั้นตอน {prompt_id}")
    return ChoicePrompt(prompt_id=prompt_id, question=question, options=tuple(options))


def _text_prompt(prompt_id: str, question: str) -> ChoicePrompt:
    return ChoicePrompt(prompt_id=prompt_id, question=question, options=(), allow_free_text=True)


def _unique_options(rows: list[dict[str, Any]], code_key: str, name_key: str) -> list[ChoiceOption]:
    seen: dict[str, str] = {}
    for row in rows:
        code, name = row.get(code_key), row.get(name_key)
        if isinstance(code, str) and code and code not in seen:
            seen[code] = name if isinstance(name, str) and name else code
    return [ChoiceOption(value=code, label=label) for code, label in seen.items()]
