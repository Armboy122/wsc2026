"""สัญญา transport และเครื่องมือ v1 แบบคงที่ โดยไม่มีการทำงานของฟีเจอร์อยู่ที่นี่"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


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


class ToolName(str, Enum):
    KNOWLEDGE = "knowledge_tool"
    SABUY = "sabuy_tool"
    VOC = "voc_tool"
    OMS = "oms_tool"


class ToolAction(str, Enum):
    KNOWLEDGE_SEARCH = "search"
    SABUY_ACCOUNT_SUMMARY = "get_account_summary"
    SABUY_PREPARE_PAYMENT = "prepare_payment"
    SABUY_SUBMIT_PAYMENT = "submit_payment"
    VOC_LIST_CATEGORIES = "list_categories"
    VOC_PREPARE_CASE = "prepare_case"
    VOC_SUBMIT_CASE = "submit_case"
    VOC_GET_CASE = "get_case"
    OMS_OUTAGE_STATUS = "get_outage_status"
    OMS_PREPARE_OUTAGE_REPORT = "prepare_outage_report"
    OMS_SUBMIT_OUTAGE_REPORT = "submit_outage_report"


TOOL_ACTIONS: dict[ToolName, frozenset[ToolAction]] = {
    ToolName.KNOWLEDGE: frozenset({ToolAction.KNOWLEDGE_SEARCH}),
    ToolName.SABUY: frozenset({
        ToolAction.SABUY_ACCOUNT_SUMMARY,
        ToolAction.SABUY_PREPARE_PAYMENT,
        ToolAction.SABUY_SUBMIT_PAYMENT,
    }),
    ToolName.VOC: frozenset({
        ToolAction.VOC_LIST_CATEGORIES,
        ToolAction.VOC_PREPARE_CASE,
        ToolAction.VOC_SUBMIT_CASE,
        ToolAction.VOC_GET_CASE,
    }),
    ToolName.OMS: frozenset({
        ToolAction.OMS_OUTAGE_STATUS,
        ToolAction.OMS_PREPARE_OUTAGE_REPORT,
        ToolAction.OMS_SUBMIT_OUTAGE_REPORT,
    }),
}

PREPARE_TO_SUBMIT: dict[ToolAction, ToolAction] = {
    ToolAction.SABUY_PREPARE_PAYMENT: ToolAction.SABUY_SUBMIT_PAYMENT,
    ToolAction.VOC_PREPARE_CASE: ToolAction.VOC_SUBMIT_CASE,
    ToolAction.OMS_PREPARE_OUTAGE_REPORT: ToolAction.OMS_SUBMIT_OUTAGE_REPORT,
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
    INTERNAL = "internal"


class ToolError(FrozenModel):
    code: ToolErrorCode
    message: str = Field(min_length=1, max_length=500)


class ToolCall(FrozenModel):
    call_id: UUID = Field(serialization_alias="callId")
    name: ToolName
    action: ToolAction
    input: dict[str, Any]

    @model_validator(mode="after")
    def action_belongs_to_tool(self) -> "ToolCall":
        if self.action not in TOOL_ACTIONS[self.name]:
            raise ValueError(f"การกระทำ {self.action.value} ไม่ได้อยู่ภายใต้ {self.name.value}")
        return self


class ToolResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class ToolResult(FrozenModel):
    call_id: UUID = Field(serialization_alias="callId")
    name: ToolName
    action: ToolAction
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
        if self.name is ToolName.KNOWLEDGE and self.simulation:
            raise ValueError("ผลลัพธ์ความรู้ต้องไม่เป็นข้อมูลจำลอง")
        if self.name is not ToolName.KNOWLEDGE and not self.simulation:
            raise ValueError("ผลลัพธ์เครื่องมือปฏิบัติการต้องเป็นข้อมูลจำลอง")
        if self.name is not ToolName.KNOWLEDGE and self.citations:
            raise ValueError("เฉพาะผลลัพธ์ความรู้เท่านั้นที่มีแหล่งอ้างอิงได้")
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
    tool_name: Literal[ToolName.SABUY, ToolName.VOC, ToolName.OMS] = Field(serialization_alias="toolName")
    prepare_action: ToolAction = Field(serialization_alias="prepareAction")
    submit_action: ToolAction = Field(serialization_alias="submitAction")
    prepared_input: dict[str, Any] = Field(serialization_alias="preparedInput")
    summary: str = Field(min_length=1, max_length=500)
    status: PendingActionStatus
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    submission_result: ToolResult | None = Field(default=None, serialization_alias="submissionResult")

    @model_validator(mode="after")
    def validate_action_pair(self) -> "PendingAction":
        if PREPARE_TO_SUBMIT.get(self.prepare_action) is not self.submit_action:
            raise ValueError("การกระทำสำหรับส่งรายการไม่ตรงกับการกระทำสำหรับจัดเตรียม")
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


class TraceEvent(FrozenModel):
    event_id: UUID = Field(serialization_alias="eventId")
    trace_id: UUID = Field(serialization_alias="traceId")
    sequence: int = Field(ge=1)
    at: datetime
    kind: TraceEventKind
    data: dict[str, Any] = Field(max_length=20)


class ChatRequest(FrozenModel):
    conversation_id: UUID | None = Field(default=None, serialization_alias="conversationId")
    message: str = Field(min_length=1, max_length=4000)
    request_id: UUID | None = Field(default=None, serialization_alias="requestId")


class ChatResponse(FrozenModel):
    conversation_id: UUID = Field(serialization_alias="conversationId")
    trace_id: UUID = Field(serialization_alias="traceId")
    message: str
    citations: tuple[Citation, ...] = ()
    pending_action: PendingAction | None = Field(default=None, serialization_alias="pendingAction")
    tool_results: tuple[ToolResult, ...] = Field(default=(), serialization_alias="toolResults")


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
    llm_adapter: Literal["ready", "unavailable"] = Field(serialization_alias="llmAdapter")
    knowledge_backend: Literal["ready", "unavailable"] = Field(serialization_alias="knowledgeBackend")
    simulation_mode: Literal[True] = Field(True, serialization_alias="simulationMode")


# สัญญาข้อมูลนำเข้าและผลลัพธ์เฉพาะแต่ละการกระทำ
class KnowledgeSearchInput(FrozenModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=3, ge=1, le=5, serialization_alias="maxResults")


class SabuyAccountSummaryInput(FrozenModel):
    account_ref: str = Field(min_length=1, max_length=64, serialization_alias="accountRef")


class PaymentMethod(str, Enum):
    DEMO_CARD = "demo_card"
    DEMO_BANK = "demo_bank"


class SabuyPreparePaymentInput(FrozenModel):
    account_ref: str = Field(min_length=1, max_length=64, serialization_alias="accountRef")
    amount_thb: Decimal = Field(gt=0, serialization_alias="amountThb")
    payment_method: PaymentMethod = Field(serialization_alias="paymentMethod")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


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


class VocPrepareCaseInput(FrozenModel):
    category: VocCategory
    subject: str = Field(min_length=1, max_length=140)
    detail: str = Field(min_length=1, max_length=2000)
    contact_name: str = Field(min_length=1, max_length=100, serialization_alias="contactName")
    contact_phone: str = Field(min_length=1, max_length=32, serialization_alias="contactPhone")
    location: str = Field(min_length=1, max_length=500)
    contact_channel: ContactChannel = Field(serialization_alias="contactChannel")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


class VocGetCaseInput(FrozenModel):
    voc_id: str = Field(min_length=1, max_length=64, serialization_alias="vocId")
    tracking_key: str = Field(min_length=1, max_length=64, serialization_alias="trackingKey")


class OmsOutageStatusInput(FrozenModel):
    area_code: str = Field(min_length=1, max_length=32, serialization_alias="areaCode")


class OmsPrepareOutageReportInput(FrozenModel):
    area_code: str = Field(min_length=1, max_length=32, serialization_alias="areaCode")
    location_note: str = Field(min_length=1, max_length=500, serialization_alias="locationNote")
    symptoms: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


class SubmitPreparedActionInput(FrozenModel):
    pending_action_id: UUID = Field(serialization_alias="pendingActionId")
    idempotency_key: str = Field(min_length=1, max_length=128, serialization_alias="idempotencyKey")


class KnowledgeSearchOutput(FrozenModel):
    answer_context: str = Field(max_length=4000, serialization_alias="answerContext")
    result_count: int = Field(ge=0, le=5, serialization_alias="resultCount")


class PaymentStatus(str, Enum):
    CURRENT = "current"
    OVERDUE = "overdue"
    PAID = "paid"


class SabuyAccountSummaryOutput(FrozenModel):
    account_ref: str = Field(min_length=1, serialization_alias="accountRef")
    customer_display_name: str = Field(min_length=1, serialization_alias="customerDisplayName")
    outstanding_balance_thb: Decimal = Field(ge=0, serialization_alias="outstandingBalanceThb")
    due_date: date | None = Field(serialization_alias="dueDate")
    payment_status: PaymentStatus = Field(serialization_alias="paymentStatus")


class SabuyPreparePaymentOutput(FrozenModel):
    account_ref: str = Field(min_length=1, serialization_alias="accountRef")
    amount_thb: Decimal = Field(gt=0, serialization_alias="amountThb")
    payment_method: PaymentMethod = Field(serialization_alias="paymentMethod")
    summary: str = Field(min_length=1, max_length=500)


class SabuyPaymentReceiptOutput(FrozenModel):
    receipt_id: str = Field(min_length=1, serialization_alias="receiptId")
    account_ref: str = Field(min_length=1, serialization_alias="accountRef")
    amount_thb: Decimal = Field(gt=0, serialization_alias="amountThb")
    status: Literal["accepted"]


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


class OutageStatus(str, Enum):
    NORMAL = "normal"
    PLANNED = "planned_outage"
    UNPLANNED = "unplanned_outage"


class OmsOutageStatusOutput(FrozenModel):
    area_code: str = Field(min_length=1, serialization_alias="areaCode")
    status: OutageStatus
    updated_at: datetime = Field(serialization_alias="updatedAt")
    estimated_restore_at: datetime | None = Field(serialization_alias="estimatedRestoreAt")
    safety_message: str = Field(min_length=1, max_length=1000, serialization_alias="safetyMessage")


class OmsPrepareOutageReportOutput(FrozenModel):
    area_code: str = Field(min_length=1, serialization_alias="areaCode")
    summary: str = Field(min_length=1, max_length=500)
    safety_message: str = Field(min_length=1, max_length=1000, serialization_alias="safetyMessage")


class OmsOutageReportOutput(FrozenModel):
    report_id: str = Field(min_length=1, serialization_alias="reportId")
    status: Literal["submitted"]
    area_code: str = Field(min_length=1, serialization_alias="areaCode")


INPUT_MODELS: ClassVar[dict[ToolAction, type[FrozenModel]]] = {
    ToolAction.KNOWLEDGE_SEARCH: KnowledgeSearchInput,
    ToolAction.SABUY_ACCOUNT_SUMMARY: SabuyAccountSummaryInput,
    ToolAction.SABUY_PREPARE_PAYMENT: SabuyPreparePaymentInput,
    ToolAction.SABUY_SUBMIT_PAYMENT: SubmitPreparedActionInput,
    ToolAction.VOC_LIST_CATEGORIES: EmptyInput,
    ToolAction.VOC_PREPARE_CASE: VocPrepareCaseInput,
    ToolAction.VOC_SUBMIT_CASE: SubmitPreparedActionInput,
    ToolAction.VOC_GET_CASE: VocGetCaseInput,
    ToolAction.OMS_OUTAGE_STATUS: OmsOutageStatusInput,
    ToolAction.OMS_PREPARE_OUTAGE_REPORT: OmsPrepareOutageReportInput,
    ToolAction.OMS_SUBMIT_OUTAGE_REPORT: SubmitPreparedActionInput,
}


OUTPUT_MODELS: ClassVar[dict[ToolAction, type[FrozenModel]]] = {
    ToolAction.KNOWLEDGE_SEARCH: KnowledgeSearchOutput,
    ToolAction.SABUY_ACCOUNT_SUMMARY: SabuyAccountSummaryOutput,
    ToolAction.SABUY_PREPARE_PAYMENT: SabuyPreparePaymentOutput,
    ToolAction.SABUY_SUBMIT_PAYMENT: SabuyPaymentReceiptOutput,
    ToolAction.VOC_LIST_CATEGORIES: VocCategoryListOutput,
    ToolAction.VOC_PREPARE_CASE: VocPrepareCaseOutput,
    ToolAction.VOC_SUBMIT_CASE: VocCaseOutput,
    ToolAction.VOC_GET_CASE: VocGetCaseOutput,
    ToolAction.OMS_OUTAGE_STATUS: OmsOutageStatusOutput,
    ToolAction.OMS_PREPARE_OUTAGE_REPORT: OmsPrepareOutageReportOutput,
    ToolAction.OMS_SUBMIT_OUTAGE_REPORT: OmsOutageReportOutput,
}


def validate_tool_input(call: ToolCall) -> FrozenModel:
    """ตรวจสอบ payload ของ envelope แบบคงที่กับการกระทำที่ประกาศไว้"""
    return TypeAdapter(INPUT_MODELS[call.action]).validate_python(call.input)


def validate_tool_success_data(action: ToolAction, data: dict[str, Any]) -> FrozenModel:
    """ตรวจสอบข้อมูลเครื่องมือที่สำเร็จเฉพาะการกระทำก่อนห่อเป็น ToolResult"""
    return TypeAdapter(OUTPUT_MODELS[action]).validate_python(data)
