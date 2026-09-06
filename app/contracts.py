"""สัญญา transport และเครื่องมือ v1 แบบคงที่ โดยไม่มีการทำงานของฟีเจอร์อยู่ที่นี่"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_serializer,
    model_validator,
)


def to_camel(value: str) -> str:
    """ใช้รูปแบบการตั้งชื่อ JSON แบบเดียวกันที่ทุกจุดเชื่อมต่อภายนอก"""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class FrozenModel(BaseModel):
    """คลาสพื้นฐานสำหรับออบเจ็กต์ค่าที่ใช้ข้ามโมดูลทุกตัว"""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        alias_generator=to_camel,
    )


class AdminModel(BaseModel):
    """ฐานสัญญา request ของ admin API ใช้ alias camelCase และห้าม field ส่วนเกิน"""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=to_camel,
    )


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)


class AdminOperationInput(AdminModel):
    action: str = Field(min_length=1, max_length=64)
    policy: str = "plain_read"
    exposure: str = "llm"
    mode: str = "read"
    submit_action: str | None = None
    http_method: str | None = None
    url_template: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None
    client_context: dict[str, str] | None = None


class AdminToolDefinitionInput(AdminModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    auth_env_var: str | None = Field(default=None, min_length=1, max_length=128)
    # P1: รูปแบบ header ของ auth — header_name ต้องเป็น HTTP token; scheme ว่าง =
    # ส่งค่า secret ตรง ๆ (กรณี X-API-Key) ทั้งคู่ไม่ใช่ความลับ คืนกลับทาง GET ได้
    auth_header_name: str | None = Field(default=None, min_length=1, max_length=128)
    auth_scheme: str | None = Field(default=None, max_length=128)
    operations: list[AdminOperationInput] = Field(min_length=1)


class AdminToolEnabledInput(AdminModel):
    enabled: bool


class AdminTryOperationInput(AdminModel):
    http_method: str
    url_template: str = Field(min_length=1, max_length=2048)
    input: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    auth_env_var: str | None = Field(default=None, max_length=128)
    auth_header_name: str | None = Field(default=None, min_length=1, max_length=128)
    auth_scheme: str | None = Field(default=None, max_length=128)


class AdminPromptInput(AdminModel):
    content: str = Field(min_length=1, max_length=20_000)


class AdminApiKeyCreateInput(AdminModel):
    name: str = Field(min_length=1, max_length=100)


class ToolName(str, Enum):
    KNOWLEDGE = "knowledge_tool"
    VOC = "voc_tool"
    OMS = "oms_tool"


class ToolAction(str, Enum):
    KNOWLEDGE_SEARCH = "search"
    VOC_LIST_CATEGORIES = "list_categories"
    VOC_PREPARE_CASE = "prepare_case"
    VOC_SUBMIT_CASE = "submit_case"
    VOC_GET_CASE = "get_case"
    OMS_GET_OUTAGE_BY_CA = "get_outage_by_ca"
    OMS_PREPARE_OUTAGE_WITH_CA = "prepare_outage_with_ca"
    OMS_SUBMIT_OUTAGE_WITH_CA = "submit_outage_with_ca"
    OMS_PREPARE_ANONYMOUS_OUTAGE = "prepare_anonymous_outage"
    OMS_SUBMIT_ANONYMOUS_OUTAGE = "submit_anonymous_outage"


# D2.5: ยังเป็น dict กลางที่นี่โดยตั้งใจ — คงไว้เป็น alias สำหรับ 3 tool เดิม (voc/knowledge/
# oms) เท่านั้นในช่วง 3 วันนี้ ตามแผนเต็ม (docs/v2/TASKS.md T2.4) การย้ายเป็น "data ต่อ
# tool" จริงจะเกิดพร้อมกับตอนที่ ToolRegistry เริ่ม dispatch จาก ToolShape (D2.6/D2.7 เป็นต้นไป)
# ที่ tool ใหม่แต่ละตัวประกาศ action ของตัวเองอยู่แล้วโดยไม่ต้องพึ่ง dict นี้เลย
TOOL_ACTIONS: dict[ToolName, frozenset[ToolAction]] = {
    ToolName.KNOWLEDGE: frozenset({ToolAction.KNOWLEDGE_SEARCH}),
    ToolName.VOC: frozenset({
        ToolAction.VOC_LIST_CATEGORIES,
        ToolAction.VOC_PREPARE_CASE,
        ToolAction.VOC_SUBMIT_CASE,
        ToolAction.VOC_GET_CASE,
    }),
    ToolName.OMS: frozenset({
        ToolAction.OMS_GET_OUTAGE_BY_CA,
        ToolAction.OMS_PREPARE_OUTAGE_WITH_CA,
        ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
        ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE,
        ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE,
    }),
}

PREPARE_TO_SUBMIT: dict[ToolAction, ToolAction] = {
    ToolAction.VOC_PREPARE_CASE: ToolAction.VOC_SUBMIT_CASE,
    ToolAction.OMS_PREPARE_OUTAGE_WITH_CA: ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA,
    ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE: ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE,
}


class Citation(FrozenModel):
    source_id: str = Field(min_length=1, serialization_alias="sourceId")
    title: str = Field(min_length=1, max_length=500)
    uri: str = Field(min_length=1, max_length=2000)
    snippet: str = Field(min_length=1, max_length=1000)
    page: int | None = Field(default=None, ge=1)


class ToolErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INTERNAL = "internal"


class ToolError(FrozenModel):
    code: ToolErrorCode
    message: str = Field(min_length=1, max_length=500)


class ToolCall(FrozenModel):
    """D2.5: ``name``/``action`` เป็น string ล้วน (ไม่ผูกกับ ``ToolName``/``ToolAction`` enum อีกต่อไป)
    เพื่อให้ declarative tool ที่มี slug ใหม่ (ไม่ได้อยู่ใน enum เดิม) สร้าง ``ToolCall`` ได้โดยไม่ต้อง
    แก้ enum — enum เดิมยังส่งเข้ามาได้ตามปกติเพราะเป็น ``str`` subclass (ARCHITECTURE-V2.md §3.5)

    การตรวจว่า ``action`` เป็นของ ``name`` จริงย้ายไปตรวจตอน dispatch ที่ ``ToolRegistry`` แทน
    (CONTRACTS-V2 §3.5) เพราะที่นี่ไม่มีทางรู้ล่วงหน้าว่า tool ใหม่จาก DB มี action อะไรบ้าง

    ⚠️ ขอบเขตของ D2.5 คือชั้น *สัญญาข้อมูล* เท่านั้น — การสร้าง ``ToolCall`` ของ tool ใหม่ไม่ error
    แล้วก็จริง แต่ ``ToolRegistry`` ยังรู้จักเฉพาะ tool ที่เป็น Python plugin (``source: code``)
    เท่านั้น การ dispatch ไปหา declarative tool ที่มาจาก DB จริง ๆ ต้องรอ D2.6/D2.7 ที่เอา
    ``app.agent.tool_shape.ToolShape`` มาต่อเข้า ``ToolRegistry``
    """

    call_id: UUID = Field(serialization_alias="callId")
    name: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]


class ToolResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class ToolResult(FrozenModel):
    """D2.5: ``name``/``action`` เป็น string ล้วนเหมือน ``ToolCall`` — ดู docstring ที่นั่น"""

    call_id: UUID = Field(serialization_alias="callId")
    name: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=64)
    status: ToolResultStatus
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    citations: tuple[Citation, ...] = ()
    simulation: bool

    @model_validator(mode="after")
    def enforce_result_shape(self) -> "ToolResult":
        if self.status is ToolResultStatus.SUCCESS and (self.data is None or self.error is not None):
            raise ValueError("ผลลัพธ์ที่สำเร็จต้องมีข้อมูลและไม่มีข้อผิดพลาด")
        if self.status is ToolResultStatus.ERROR and (self.error is None or self.data is not None):
            raise ValueError("ผลลัพธ์ที่ผิดพลาดต้องมีข้อผิดพลาดและไม่มีข้อมูล")
        # เทียบด้วย == ไม่ใช่ is เพราะ self.name เป็น str ธรรมดาแล้ว (ไม่ใช่ enum instance เดิม)
        if self.name == ToolName.KNOWLEDGE and self.simulation:
            raise ValueError("ผลลัพธ์ความรู้ต้องไม่เป็นข้อมูลจำลอง")
        if self.name != ToolName.KNOWLEDGE and not self.simulation:
            raise ValueError("ผลลัพธ์เครื่องมือปฏิบัติการต้องเป็นข้อมูลจำลอง")
        # Citation ownership is an operation policy, not a tool-name property.  The
        # registry enforces that grounded_answer results include citations at runtime;
        # keeping this shape model name-agnostic lets declarative/plugin operations
        # participate without weakening that policy check.
        return self


class PendingActionStatus(str, Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    FAILED = "failed"


class PendingAction(FrozenModel):
    pending_action_id: UUID = Field(serialization_alias="pendingActionId")
    conversation_id: UUID = Field(serialization_alias="conversationId")
    tool_slug: str = Field(
        min_length=1,
        max_length=64,
        serialization_alias="toolSlug",
        validation_alias=AliasChoices("tool_name", "toolName", "tool_slug", "toolSlug"),
    )
    prepare_action: str = Field(min_length=1, max_length=64, serialization_alias="prepareAction")
    submit_action: str = Field(min_length=1, max_length=64, serialization_alias="submitAction")
    prepared_input: dict[str, Any] = Field(serialization_alias="preparedInput")
    summary: str = Field(min_length=1, max_length=500)
    status: PendingActionStatus
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    submission_result: ToolResult | None = Field(default=None, serialization_alias="submissionResult")

    @property
    def tool_name(self) -> str:
        """Compatibility accessor; the canonical contract field is ``tool_slug``."""
        return self.tool_slug

    @field_serializer("idempotency_key")
    def redact_idempotency_key(self, value: str) -> str:
        """ปกปิดคีย์ภายในระบบเสมอเมื่อออกจากขอบเขตแอปพลิเคชัน

        ผู้ใช้กำหนดข้อความของคำขอได้ คีย์นี้จึงอาจมีค่าที่ผู้ใช้แทรกมา เช่น payment token
        การส่งกลับตรง ๆ ทำให้ข้อมูลอ่อนไหวรั่วผ่าน API และ trace ได้ ค่าเดิมยังใช้ภายใน
        เพื่อกันการส่งซ้ำได้ตามปกติ
        """
        del value
        return "[redacted]"

    @model_validator(mode="after")
    def validate_action_pair(self) -> "PendingAction":
        expected_submit = PREPARE_TO_SUBMIT.get(self.prepare_action)
        if expected_submit is not None:
            if self.submit_action != expected_submit:
                raise ValueError("การกระทำสำหรับส่งรายการไม่ตรงกับการกระทำสำหรับจัดเตรียม")
        elif self.submit_action == self.prepare_action or not self.submit_action.strip():
            raise ValueError("การกระทำสำหรับส่งรายการไม่ถูกต้อง")
        if self.status is PendingActionStatus.SUBMITTED and self.submission_result is None:
            raise ValueError("การกระทำที่ส่งแล้วต้องมีผลลัพธ์การส่งรายการ")
        if self.status in {PendingActionStatus.PENDING_CONFIRMATION, PendingActionStatus.REJECTED} and self.submission_result is not None:
            raise ValueError("การกระทำที่ยังไม่ได้ส่งต้องไม่มีผลลัพธ์การส่งรายการ")
        return self


class TraceEventKind(str, Enum):
    CHAT_RECEIVED = "chat_received"
    LLM_REQUESTED = "llm_requested"
    LLM_RESPONDED = "llm_responded"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    ACTION_PREPARED = "action_prepared"
    ACTION_CONFIRMED = "action_confirmed"
    ACTION_REJECTED = "action_rejected"
    ACTION_SUBMITTED = "action_submitted"
    ERROR = "error"
    POLICY_REJECTED = "policy_rejected"
    RESPONSE_DEGRADED = "response_degraded"
    TOOL_DISABLED = "tool_disabled"


class TraceEvent(FrozenModel):
    event_id: UUID = Field(serialization_alias="eventId")
    trace_id: UUID = Field(serialization_alias="traceId")
    sequence: int = Field(ge=1)
    at: datetime
    kind: TraceEventKind
    tool_slug: str | None = Field(default=None, serialization_alias="toolSlug")
    action: str | None = None
    config_version: int | None = Field(default=None, serialization_alias="configVersion")
    policy: str | None = None
    channel: str | None = None
    data: dict[str, Any] = Field(max_length=20)


class ChatClientLocation(FrozenModel):
    """พิกัดโดยประมาณจาก IP ของผู้ใช้ (ipwho.is, ระดับอำเภอ/จังหวัด ไม่ใช่ GPS จริง
    — เลี่ยง navigator.geolocation เพราะพึ่ง OS Location Services ที่บางเครื่อง
    fail แม้ตั้งค่าถูก) — ใช้เป็น fallback
    เมื่อไม่มี CA ให้ค้นพิกัดจาก MST GIS ได้ (ดู OmsPrepareAnonymousOutageInput)"""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ChoiceOption(FrozenModel):
    """ตัวเลือกเดียวที่ผู้ใช้กดได้ โดย ``value`` ต้องมาจาก catalog ต้นทางเสมอ"""

    value: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ChoicePrompt(FrozenModel):
    """คำถามหนึ่งขั้นพร้อมตัวเลือกที่กำหนดไว้ล่วงหน้า

    ใช้แทนการให้ผู้ใช้พิมพ์รหัส taxonomy เอง ``prompt_id`` ระบุขั้นตอนที่กำลังถาม
    จึงปฏิเสธคำตอบที่ส่งกลับมาผิดขั้นได้
    """

    prompt_id: str = Field(min_length=1, max_length=64, serialization_alias="promptId")
    question: str = Field(min_length=1, max_length=500)
    options: tuple[ChoiceOption, ...] = Field(default=(), max_length=60)
    allow_free_text: bool = Field(default=False, serialization_alias="allowFreeText")

    @model_validator(mode="after")
    def validate_answerable(self) -> "ChoicePrompt":
        if not self.options and not self.allow_free_text:
            raise ValueError("คำถามต้องมีตัวเลือกอย่างน้อยหนึ่งข้อ หรืออนุญาตให้พิมพ์ตอบ")
        values = [option.value for option in self.options]
        if len(values) != len(set(values)):
            raise ValueError("ค่าตัวเลือกต้องไม่ซ้ำกัน")
        return self


class ChatRequest(FrozenModel):
    conversation_id: UUID | None = Field(default=None, serialization_alias="conversationId")
    message: str = Field(min_length=1, max_length=4000)
    request_id: UUID | None = Field(default=None, serialization_alias="requestId")
    # เสริมนอกสัญญาเดิม (optional, backward-compatible) — ไม่ผ่าน LLM เพราะเป็น
    # device state ไม่ใช่เนื้อหาการสนทนา ดู main_agent._inject_client_context
    client_location: ChatClientLocation | None = Field(default=None, serialization_alias="clientLocation")
    # ค่าที่ผู้ใช้กดเลือกจาก ChoicePrompt รอบก่อน ต้องตรวจกับ catalog เสมอ ห้ามเชื่อ client
    selected_prompt_id: str | None = Field(default=None, max_length=64, serialization_alias="selectedPromptId")
    selected_value: str | None = Field(default=None, max_length=64, serialization_alias="selectedValue")

    @model_validator(mode="after")
    def validate_selection_pair(self) -> "ChatRequest":
        if (self.selected_prompt_id is None) != (self.selected_value is None):
            raise ValueError("ต้องส่ง selectedPromptId และ selectedValue คู่กันเสมอ")
        return self


ActionKind = Literal["confirm", "reject", "pick", "link"]


class Action(FrozenModel):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=64)
    kind: ActionKind
    single_use: bool = Field(default=False, serialization_alias="singleUse")


class ChatResponse(FrozenModel):
    conversation_id: UUID = Field(serialization_alias="conversationId")
    trace_id: UUID = Field(serialization_alias="traceId")
    message: str
    citations: tuple[Citation, ...] = ()
    pending_action: PendingAction | None = Field(default=None, serialization_alias="pendingAction")
    tool_results: tuple[ToolResult, ...] = Field(default=(), serialization_alias="toolResults")
    choice_prompt: ChoicePrompt | None = Field(default=None, serialization_alias="choicePrompt")
    simulation: bool = False
    actions: tuple[Action, ...] = ()


class ConfirmActionRequest(FrozenModel):
    confirmation_note: str | None = Field(default=None, max_length=500, serialization_alias="confirmationNote")


class RejectActionRequest(FrozenModel):
    reason: str = Field(min_length=1, max_length=500)


class ActionDecisionResponse(FrozenModel):
    pending_action: PendingAction = Field(serialization_alias="pendingAction")
    tool_result: ToolResult | None = Field(default=None, serialization_alias="toolResult")
    trace_id: UUID = Field(serialization_alias="traceId")


class TraceResponse(FrozenModel):
    trace_id: UUID = Field(serialization_alias="traceId")
    events: tuple[TraceEvent, ...]


class ResetResponse(FrozenModel):
    reset: Literal[True] = True


class HealthResponse(FrozenModel):
    status: Literal["ok", "degraded"]


# สัญญาข้อมูลนำเข้าและผลลัพธ์เฉพาะแต่ละการกระทำ
class KnowledgeSearchInput(FrozenModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=3, ge=1, le=5, serialization_alias="maxResults")


class EmptyInput(FrozenModel):
    pass


class VocCategory(str, Enum):
    POWER_QUALITY = "power_quality"
    SERVICE = "service"
    COMPLIMENT = "compliment"
    TIP_OFF = "tip_off"
    OPERATIONS = "operations"
    STAKEHOLDER_FEEDBACK = "stakeholder_feedback"


class ContactChannel(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    NONE = "none"


class VocApiReporter(FrozenModel):
    prefix_code: str | None = Field(default=None, serialization_alias="prefixCode")
    first_name: str | None = Field(default=None, max_length=100, serialization_alias="firstName")
    last_name: str | None = Field(default=None, max_length=100, serialization_alias="lastName")
    phone: str | None = Field(default=None, serialization_alias="phone")
    email: str | None = None
    ca_number: str | None = Field(default=None, serialization_alias="caNumber")
    meter_number: str | None = Field(default=None, serialization_alias="meterNumber")


class VocApiIncident(FrozenModel):
    province_code: str = Field(min_length=1, serialization_alias="provinceCode")
    district_code: str = Field(min_length=1, serialization_alias="districtCode")
    subdistrict_code: str = Field(min_length=1, serialization_alias="subdistrictCode")
    pea_office_code: str = Field(min_length=1, serialization_alias="peaOfficeCode")
    location_text: str = Field(min_length=1, max_length=1000, serialization_alias="locationText")


class VocApiClassification(FrozenModel):
    request_type_code: str = Field(serialization_alias="requestTypeCode")
    topic_code: str = Field(serialization_alias="topicCode")
    issue_code: str = Field(serialization_alias="issueCode")
    sub_issue_code: str | None = Field(default=None, serialization_alias="subIssueCode")


class VocApiConsent(FrozenModel):
    accepted: Literal[True]
    notice_version: str = Field(min_length=1, serialization_alias="noticeVersion")
    accepted_at: datetime = Field(serialization_alias="acceptedAt")
    channel: Literal["CHAT", "VOICE"]


class VocExternalCasePayload(FrozenModel):
    """Canonical, user-supplied payload accepted by the VOC gateway."""

    journey_code: Literal[
        "POWER_QUALITY", "SERVICE_ISSUE", "PRAISE", "TIP_OFF",
        "STAKEHOLDER_ISSUE", "STAKEHOLDER_FEEDBACK",
    ] = Field(serialization_alias="journeyCode")
    reporter: VocApiReporter | None = None
    incident: VocApiIncident
    classification: VocApiClassification
    frequency_code: str | None = Field(default=None, serialization_alias="frequencyCode")
    severity_level: int | None = Field(default=None, ge=1, le=5, serialization_alias="severityLevel")
    detail: str = Field(min_length=1, max_length=2000)
    consent: VocApiConsent

    @model_validator(mode="after")
    def validate_journey_requirements(self) -> "VocExternalCasePayload":
        if self.journey_code != "TIP_OFF" and self.reporter is None:
            raise ValueError("reporter is required for this journey")
        if self.journey_code in {"POWER_QUALITY", "SERVICE_ISSUE"} and (self.frequency_code is None or self.severity_level is None):
            raise ValueError("frequency and severity are required for this journey")
        if self.journey_code in {"POWER_QUALITY", "SERVICE_ISSUE", "PRAISE"} and not self.classification.sub_issue_code:
            raise ValueError("subIssueCode is required for this journey")
        return self


class VocPrepareCaseInput(FrozenModel):
    category: VocCategory
    subject: str = Field(min_length=1, max_length=140)
    detail: str = Field(min_length=1, max_length=2000)
    contact_name: str = Field(min_length=1, max_length=100, serialization_alias="contactName")
    contact_phone: str = Field(min_length=1, max_length=32, serialization_alias="contactPhone")
    location: str = Field(min_length=1, max_length=500)
    contact_channel: ContactChannel = Field(serialization_alias="contactChannel")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")
    external_payload: VocExternalCasePayload | None = Field(default=None, serialization_alias="externalPayload")


class VocGetCaseInput(FrozenModel):
    voc_id: str = Field(min_length=1, max_length=64, serialization_alias="vocId")
    tracking_key: str = Field(min_length=1, max_length=64, serialization_alias="trackingKey")


class OmsGetOutageByCaInput(FrozenModel):
    ca_number: str = Field(pattern=r"^[0-9]{12}$", serialization_alias="caNumber")


class OmsPrepareOutageWithCaInput(FrozenModel):
    ca_number: str = Field(pattern=r"^[0-9]{12}$", serialization_alias="caNumber")
    description: str = Field(min_length=1, max_length=2000)
    contact_phone: str | None = Field(default=None, min_length=8, max_length=32, serialization_alias="contactPhone")
    location_note: str | None = Field(default=None, min_length=1, max_length=500, serialization_alias="locationNote")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


class OmsPrepareAnonymousOutageInput(FrozenModel):
    description: str = Field(min_length=1, max_length=2000)
    location: str = Field(min_length=1, max_length=1000)
    contact_phone: str = Field(min_length=8, max_length=32, serialization_alias="contactPhone")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")
    # ไม่มี CA จึงหา MST GIS ไม่ได้ — เติมจาก ChatRequest.clientLocation แทน
    # (main_agent._inject_client_context ตาม clientContext ที่ operation ประกาศ) ไม่ใช่ค่าที่ LLM สร้างเอง
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class SubmitPreparedActionInput(FrozenModel):
    pending_action_id: UUID = Field(serialization_alias="pendingActionId")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


class KnowledgeSearchOutput(FrozenModel):
    answer_context: str = Field(max_length=4000, serialization_alias="answerContext")
    result_count: int = Field(ge=0, le=5, serialization_alias="resultCount")


class VocCategoryItem(FrozenModel):
    code: VocCategory
    label: str = Field(min_length=1, max_length=100)


class VocCategoryListOutput(FrozenModel):
    categories: tuple[VocCategoryItem, ...] = Field(min_length=1, max_length=6)


class VocPrepareCaseOutput(FrozenModel):
    category: VocCategory
    subject: str = Field(min_length=1, max_length=140)
    summary: str = Field(min_length=1, max_length=500)


class VocCaseOutput(FrozenModel):
    case_id: str = Field(min_length=1, serialization_alias="caseId")
    voc_id: str = Field(min_length=1, serialization_alias="vocId")
    tracking_key: str = Field(min_length=1, max_length=64, serialization_alias="trackingKey")
    status: Literal["submitted"]
    category: VocCategory


class VocGetCaseOutput(FrozenModel):
    voc_id: str = Field(min_length=1, serialization_alias="vocId")
    status: Literal["submitted"]
    category: VocCategory
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class OmsEventLevel(str, Enum):
    METER = "METER"
    TRANSFORMER = "TRANSFORMER"
    FEEDER = "FEEDER"


class OmsOutageStatus(str, Enum):
    RECEIVED = "RECEIVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESTORED = "RESTORED"


class OmsRecommendedAction(str, Enum):
    INFORM_EXISTING_EVENT = "INFORM_EXISTING_EVENT"
    CREATE_METER_EVENT = "CREATE_METER_EVENT"


class OmsNetworkReference(FrozenModel):
    meter_id: str = Field(min_length=1, serialization_alias="meterId")
    transformer_id: str = Field(min_length=1, serialization_alias="transformerId")
    feeder_id: str = Field(min_length=1, serialization_alias="feederId")


class OmsGeoPoint(FrozenModel):
    """พิกัดโดยประมาณจาก GIS ของ OMS โดยแต่ละค่าเป็น null ได้เมื่อไม่พบข้อมูล"""

    lat: float | None
    lon: float | None
    gis_type: Literal["POINT", "AREA"] | None


class OmsActiveOutageEvent(FrozenModel):
    event_id: str = Field(min_length=1, serialization_alias="eventId")
    level: OmsEventLevel
    status: OmsOutageStatus
    message: str = Field(min_length=1, max_length=1000)
    started_at: datetime = Field(serialization_alias="startedAt")
    estimated_restore_at: datetime | None = Field(serialization_alias="estimatedRestoreAt")
    location: OmsGeoPoint | None


class OmsGetOutageByCaOutput(FrozenModel):
    ca_number: str = Field(pattern=r"^[0-9]{12}$", serialization_alias="caNumber")
    customer_found: Literal[True] = Field(serialization_alias="customerFound")
    network: OmsNetworkReference
    active_event: OmsActiveOutageEvent | None = Field(serialization_alias="activeEvent")
    recommended_action: OmsRecommendedAction = Field(serialization_alias="recommendedAction")


class OmsPrepareOutageOutput(FrozenModel):
    summary: str = Field(min_length=1, max_length=500)


class OmsCreateOutageWithCaOutput(FrozenModel):
    event_id: str = Field(min_length=1, serialization_alias="eventId")
    ca_number: str = Field(pattern=r"^[0-9]{12}$", serialization_alias="caNumber")
    level: Literal[OmsEventLevel.METER]
    status: OmsOutageStatus
    message: str = Field(min_length=1, max_length=1000)
    location: OmsGeoPoint | None


class OmsCreateAnonymousOutageOutput(FrozenModel):
    report_id: str = Field(min_length=1, serialization_alias="reportId")
    status: OmsOutageStatus
    message: str = Field(min_length=1, max_length=1000)
    location: OmsGeoPoint | None


INPUT_MODELS: ClassVar[dict[ToolAction, type[FrozenModel]]] = {
    ToolAction.KNOWLEDGE_SEARCH: KnowledgeSearchInput,
    ToolAction.VOC_LIST_CATEGORIES: EmptyInput,
    ToolAction.VOC_PREPARE_CASE: VocPrepareCaseInput,
    ToolAction.VOC_SUBMIT_CASE: SubmitPreparedActionInput,
    ToolAction.VOC_GET_CASE: VocGetCaseInput,
    ToolAction.OMS_GET_OUTAGE_BY_CA: OmsGetOutageByCaInput,
    ToolAction.OMS_PREPARE_OUTAGE_WITH_CA: OmsPrepareOutageWithCaInput,
    ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA: SubmitPreparedActionInput,
    ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE: OmsPrepareAnonymousOutageInput,
    ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE: SubmitPreparedActionInput,
}


OUTPUT_MODELS: ClassVar[dict[ToolAction, type[FrozenModel]]] = {
    ToolAction.KNOWLEDGE_SEARCH: KnowledgeSearchOutput,
    ToolAction.VOC_LIST_CATEGORIES: VocCategoryListOutput,
    ToolAction.VOC_PREPARE_CASE: VocPrepareCaseOutput,
    ToolAction.VOC_SUBMIT_CASE: VocCaseOutput,
    ToolAction.VOC_GET_CASE: VocGetCaseOutput,
    ToolAction.OMS_GET_OUTAGE_BY_CA: OmsGetOutageByCaOutput,
    ToolAction.OMS_PREPARE_OUTAGE_WITH_CA: OmsPrepareOutageOutput,
    ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA: OmsCreateOutageWithCaOutput,
    ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE: OmsPrepareOutageOutput,
    ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE: OmsCreateAnonymousOutageOutput,
}


def validate_tool_input(call: ToolCall) -> FrozenModel:
    """ตรวจสอบ payload ของ envelope แบบคงที่กับการกระทำที่ประกาศไว้"""
    return TypeAdapter(INPUT_MODELS[call.action]).validate_python(call.input)


def validate_tool_success_data(action: ToolAction, data: dict[str, Any]) -> FrozenModel:
    """ตรวจสอบข้อมูลเครื่องมือที่สำเร็จเฉพาะการกระทำก่อนห่อเป็น ToolResult"""
    return TypeAdapter(OUTPUT_MODELS[action]).validate_python(data)
