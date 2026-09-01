"""Deterministic per-conversation state for the simulated VOC intake flow.

The language model may identify that a user wants to open a complaint, but this
module owns the form-like progression.  It never calls a tool and never performs
a write; the MainAgent remains responsible for executing ``voc_tool`` actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from uuid import UUID

from app.contracts import ContactChannel, VocCategory, VocCategoryItem


class VocStep(str, Enum):
    CATEGORY = "category"
    SUBJECT = "subject"
    DETAIL = "detail"
    CONTACT_NAME = "contact_name"
    CONTACT_PHONE = "contact_phone"
    LOCATION = "location"
    READY = "ready"


_FIELD_ORDER = (
    VocStep.CATEGORY,
    VocStep.SUBJECT,
    VocStep.DETAIL,
    VocStep.CONTACT_NAME,
    VocStep.CONTACT_PHONE,
    VocStep.LOCATION,
)
_FIELD_LABELS = {
    VocStep.SUBJECT: ("subject", "หัวข้อ"),
    VocStep.DETAIL: ("detail", "รายละเอียด"),
    VocStep.CONTACT_NAME: ("contactName", "ชื่อผู้ร้องเรียน", "ชื่อผู้แจ้ง", "ชื่อ"),
    VocStep.CONTACT_PHONE: ("contactPhone", "เบอร์โทร", "โทรศัพท์"),
    VocStep.LOCATION: ("location", "สถานที่", "พื้นที่"),
}
_PROMPTS = {
    VocStep.SUBJECT: "รับทราบประเภทเรื่องแล้วครับ กรุณาระบุหัวข้อของเรื่องที่ต้องการแจ้งครับ",
    VocStep.DETAIL: "กรุณาระบุรายละเอียดของเรื่องที่ต้องการแจ้งครับ",
    VocStep.CONTACT_NAME: "กรุณาระบุชื่อผู้ร้องเรียนเพื่อให้ผมเตรียมเรื่องให้ครับ",
    VocStep.CONTACT_PHONE: "กรุณาระบุเบอร์โทรที่สะดวกให้เจ้าหน้าที่ติดต่อกลับครับ",
    VocStep.LOCATION: "กรุณาระบุสถานที่เกิดเหตุหรือพื้นที่ที่เกี่ยวข้องครับ",
}


@dataclass(frozen=True, slots=True)
class VocIntakeState:
    category: VocCategory | None = None
    subject: str | None = None
    detail: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    location: str | None = None
    step: VocStep = VocStep.CATEGORY

    @property
    def ready(self) -> bool:
        return self.step is VocStep.READY

    def prepare_input(self, idempotency_key: str) -> dict[str, str]:
        if not self.ready or self.category is None:
            raise ValueError("ข้อมูลเรื่องร้องเรียนยังไม่ครบ")
        assert self.subject and self.detail and self.contact_name and self.contact_phone and self.location
        return {
            "category": self.category.value,
            "subject": self.subject,
            "detail": self.detail,
            "contactName": self.contact_name,
            "contactPhone": self.contact_phone,
            "location": self.location,
            "contactChannel": ContactChannel.NONE.value,
            "idempotencyKey": idempotency_key,
        }


@dataclass(frozen=True, slots=True)
class VocWorkflowDecision:
    state: VocIntakeState
    prompt: str | None
    needs_categories: bool = False


class VocWorkflowStore:
    """In-process workflow state with the same reset semantics as demo stores."""

    def __init__(self) -> None:
        self._states: dict[UUID, VocIntakeState] = {}

    def get(self, conversation_id: UUID) -> VocIntakeState | None:
        return self._states.get(conversation_id)

    def put(self, conversation_id: UUID, state: VocIntakeState) -> None:
        self._states[conversation_id] = state

    def pop(self, conversation_id: UUID) -> VocIntakeState | None:
        return self._states.pop(conversation_id, None)

    def clear(self) -> None:
        self._states.clear()


class VocIntakeCoordinator:
    """Extract validated slot candidates and choose exactly one next step."""

    def start(
        self,
        message: str,
        categories: tuple[VocCategoryItem, ...],
    ) -> VocWorkflowDecision:
        return self.advance(VocIntakeState(), message, categories)

    def advance(
        self,
        state: VocIntakeState,
        message: str,
        categories: tuple[VocCategoryItem, ...],
    ) -> VocWorkflowDecision:
        text = " ".join(message.split()).strip()
        updates: dict[str, object] = {}

        category = state.category or _match_category(text, categories)
        if category is not None:
            updates["category"] = category

        for step, attribute in (
            (VocStep.SUBJECT, "subject"),
            (VocStep.DETAIL, "detail"),
            (VocStep.CONTACT_NAME, "contact_name"),
            (VocStep.CONTACT_PHONE, "contact_phone"),
            (VocStep.LOCATION, "location"),
        ):
            current = getattr(state, attribute)
            value = current or _labelled_value(text, _FIELD_LABELS[step])
            if value is None and state.step is step and ":" not in text and ";" not in text:
                value = text or None
            if value:
                updates[attribute] = value

        updated = replace(state, **updates)
        next_step = _next_step(updated)
        updated = replace(updated, step=next_step)
        if next_step is VocStep.CATEGORY:
            return VocWorkflowDecision(updated, None, needs_categories=True)
        if next_step is VocStep.READY:
            return VocWorkflowDecision(updated, None)
        return VocWorkflowDecision(updated, _PROMPTS[next_step])


def category_choices(categories: tuple[VocCategoryItem, ...]) -> str:
    choices = "\n".join(
        f"{index}. {item.label}" for index, item in enumerate(categories, start=1)
    )
    return (
        "กรุณาเลือกประเภทเรื่องที่ต้องการแจ้ง:\n"
        f"{choices}\n\n"
        "ตอบด้วยหมายเลขหรือชื่อประเภทเรื่องได้เลยครับ"
    )


def _next_step(state: VocIntakeState) -> VocStep:
    values = {
        VocStep.CATEGORY: state.category,
        VocStep.SUBJECT: state.subject,
        VocStep.DETAIL: state.detail,
        VocStep.CONTACT_NAME: state.contact_name,
        VocStep.CONTACT_PHONE: state.contact_phone,
        VocStep.LOCATION: state.location,
    }
    return next((step for step in _FIELD_ORDER if not values[step]), VocStep.READY)


def _match_category(
    text: str,
    categories: tuple[VocCategoryItem, ...],
) -> VocCategory | None:
    normalized = text.casefold().strip()
    numbered = re.match(r"^\s*([1-9])(?:\s*[.)-])?", normalized)
    if numbered:
        index = int(numbered.group(1)) - 1
        if 0 <= index < len(categories):
            return categories[index].code

    for item in sorted(categories, key=lambda candidate: len(candidate.label), reverse=True):
        if item.code.value in normalized or item.label.casefold() in normalized:
            return item.code

    keyword_groups = (
        (VocCategory.STAKEHOLDER_FEEDBACK, ("ผู้มีส่วนได้ส่วนเสีย", "เสนอแนะ", "ข้อคิดเห็น")),
        (VocCategory.COMPLIMENT, ("ชื่นชม", "ชมเชย")),
        (VocCategory.TIP_OFF, ("เบาะแส", "ทุจริต", "อันตราย")),
        (VocCategory.OPERATIONS, ("ดำเนินงาน", "คู่ค้า", "ผู้รับเหมา")),
        (VocCategory.POWER_QUALITY, ("คุณภาพไฟฟ้า", "คุณภาพของไฟฟ้า", "ไฟตก", "แรงดัน", "ไฟดับ")),
        (VocCategory.SERVICE, ("การให้บริการ", "ด้านบริการ", "บริการ")),
    )
    available = {item.code for item in categories}
    for category, keywords in keyword_groups:
        if category in available and any(keyword in normalized for keyword in keywords):
            return category
    return None


def _labelled_value(text: str, labels: tuple[str, ...]) -> str | None:
    pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:^|;)\s*(?:{pattern})\s*:\s*(.+?)(?=\s*(?:;|$))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = " ".join(match.group(1).split()).strip()
    return value or None
