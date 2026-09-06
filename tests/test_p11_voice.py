"""P11 Voice read-back, deterministic confirmation, schema correction, and evidence tests.

V2 Phase 6 (T6.1–T6.4) comprehensive tests:
- T6.1: All-field read-back, deterministic refusal-first matching, bounded retries
- T6.2: Rejection into schema-driven correction, brand NEW pending action, old action stays terminal
- T6.3: voiceConfirm gating (fail-closed) and citation degradation (RESPONSE_DEGRADED)
- T6.4: Redacted confirmation evidence (readBackText + transcription, no audio stored)
- Structural safety: LLM tool calls cannot decide confirmation; genuine speech consent required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.operation_policy import OperationPolicy, OperationSpec
from app.agent.registry import ToolRegistry
from app.agent.stores import trace_channel
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import (
    ActionDecisionResponse,
    ChatRequest,
    ChatResponse,
    PendingAction,
    PendingActionStatus,
    ToolCall,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
    TraceEventKind,
)
from app.core.config import Settings
from app.db import Database
from app.llm import LLMClient
from app.live.bridge import (
    ActionConflictError,
    NoPendingActionError,
    VoiceBridge,
    VoiceBridgeError,
    build_read_back_text,
    match_voice_intent,
    sanitize_confirmation_evidence,
    strip_voice_citations,
)
from app.live.gemini_live import GeminiLiveSession
from app.tools.knowledge_tool import KnowledgeTool


# ===========================================================================
# 1. Deterministic Refusal-First Matching Tests (T6.1 🔒)
# ===========================================================================

def test_refusal_checked_before_confirmation_thai_edge_cases() -> None:
    """🔒 กติกาบังคับ: "ไม่ใช่ครับ" ต้องไม่ถูกนับเป็นยืนยัน
    ต้องตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ เพราะ "ไม่ใช่" มีคำว่า "ใช่" อยู่ข้างใน
    """
    # Refusal utterances MUST be classified as "refusal", NEVER "confirm"
    refusal_phrases = [
        "ไม่ใช่ครับ",
        "ไม่ใช่ค่ะ",
        "ไม่ใช่",
        "ไม่เอาครับ",
        "ไม่เอาแล้ว",
        "ไม่ต้องแล้วครับ",
        "ยกเลิกครับ",
        "ขอยกเลิก",
        "ข้อมูลผิดครับ",
        "ผิดครับ",
        "ขอแก้ไขข้อมูล",
        "แก้ไขครับ",
        "ไม่ถูกต้อง",
        "ไม่ยืนยันครับ",
        "ไม่ตกลง",
        "cancel",
    ]
    for phrase in refusal_phrases:
        assert match_voice_intent(phrase) == "refusal", f"Expected refusal for {phrase}"

    # Confirmation utterances MUST be classified as "confirm"
    confirm_phrases = [
        "ยืนยันครับ",
        "ยืนยันค่ะ",
        "ตกลงครับ",
        "ตกลงค่ะ",
        "ใช่ครับ",
        "ใช่ค่ะ",
        "ถูกต้องครับ",
        "ถูกต้องแล้ว",
        "เอาเลย",
    ]
    for phrase in confirm_phrases:
        assert match_voice_intent(phrase) == "confirm", f"Expected confirm for {phrase}"

    # Ambiguous or questions MUST be classified as "unrecognized"
    ambiguous_phrases = [
        "ขอคิดดูก่อนนะ",
        "อะไรนะครับ",
        "ฮัลโหล",
        "ขอถามเพิ่มว่าไม่ต้องใช้ทะเบียนบ้านก็ได้ใช่ไหมครับ แล้วต้องเตรียมอะไรอีกบ้าง",
    ]
    for phrase in ambiguous_phrases:
        assert match_voice_intent(phrase) == "unrecognized", f"Expected unrecognized for {phrase}"


# ===========================================================================
# 2. All-Field Read-Back Tests (T6.1)
# ===========================================================================

def test_read_back_formats_all_fields_to_be_saved() -> None:
    """อ่านทวนทุก field ที่จะบันทึกจาก prepared_input พร้อมแปลงชื่อภาษาไทยที่เข้าใจง่าย"""
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={
            "ca_number": "12345678901",
            "phone": "0812345678",
            "description": "ไฟดับทั้งซอย",
            "location": "หมู่บ้านทดสอบ",
            "idempotency_key": "secret-key-123",  # ต้องถูกข้าม
            "_internal_token": "xyz",             # ต้องถูกข้าม
        },
        summary="แจ้งเหตุไฟดับ CA 12345678901",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    read_back = build_read_back_text(pending)
    assert "ขออ่านทวนข้อมูลที่จะบันทึกครับ" in read_back
    assert "หมายเลขผู้ใช้ไฟฟ้า คือ 12345678901" in read_back
    assert "เบอร์โทรศัพท์ คือ 0812345678" in read_back
    assert "รายละเอียด คือ ไฟดับทั้งซอย" in read_back
    assert "สถานที่ คือ หมู่บ้านทดสอบ" in read_back
    assert "secret-key-123" not in read_back
    assert "_internal_token" not in read_back
    assert "ถูกต้องหรือไม่ครับ กรุณาตอบ ยืนยัน หรือแจ้งแก้ไขครับ" in read_back


# ===========================================================================
# 3. Structural Safety: LLM Cannot Decide Confirmation (T6.1 🔒)
# ===========================================================================

class StubVoiceGateway:
    def __init__(self, pending: PendingAction) -> None:
        self.pending = pending
        self.chat_calls: list[str] = []
        self.confirm_calls: list[tuple[UUID, str | None, dict[str, Any] | None]] = []
        self.reject_calls: list[tuple[UUID, str]] = []
        self.all_actions: dict[UUID, PendingAction] = {pending.pending_action_id: pending}

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        self.chat_calls.append(request.message)
        if (
            self.pending.pending_action_id in self.all_actions
            and self.all_actions[self.pending.pending_action_id].status is not PendingActionStatus.PENDING_CONFIRMATION
        ):
            new_id = uuid4()
            new_pending = self.pending.model_copy(
                update={"pending_action_id": new_id, "status": PendingActionStatus.PENDING_CONFIRMATION}
            )
            self.pending = new_pending
            self.all_actions[new_id] = new_pending
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            trace_id=uuid4(),
            message="บันทึกข้อมูลเรียบร้อย",
            pending_action=self.pending,
        )

    async def confirm_pending_action(
        self,
        pending_action_id: UUID,
        confirmation_note: str | None = None,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> ActionDecisionResponse:
        self.confirm_calls.append((pending_action_id, confirmation_note, evidence))
        action = self.all_actions[pending_action_id]
        if action.status is PendingActionStatus.REJECTED:
            raise RuntimeError("ไม่สามารถยืนยันรายการในสถานะปัจจุบันได้")
        result = ToolResult(
            call_id=uuid4(),
            name="oms_tool",
            action="submit_outage_report",
            status=ToolResultStatus.SUCCESS,
            data={"reportId": "OMS-1"},
            simulation=True,
        )
        updated = action.model_copy(
            update={"status": PendingActionStatus.SUBMITTED, "submission_result": result}
        )
        self.all_actions[pending_action_id] = updated
        return ActionDecisionResponse(
            pending_action=updated,
            tool_result=result,
            trace_id=uuid4(),
        )

    async def reject_pending_action(
        self,
        pending_action_id: UUID,
        reason: str,
    ) -> ActionDecisionResponse:
        self.reject_calls.append((pending_action_id, reason))
        action = self.all_actions[pending_action_id]
        updated = action.model_copy(update={"status": PendingActionStatus.REJECTED})
        self.all_actions[pending_action_id] = updated
        return ActionDecisionResponse(
            pending_action=updated,
            tool_result=None,
            trace_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_llm_cannot_decide_voice_confirmation_structural_safety() -> None:
    """🔒 พิสูจน์ด้วยโครงสร้างโค้ด: การเรียก confirm_current จากโมเดลหรือ tool call
    โดยไม่มีคำยินยอมจากเสียงจริงของผู้ใช้ ต้อง fail closed เสมอ
    """
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901", "phone": "0812345678"},
        summary="แจ้งเหตุไฟดับ CA 12345678901",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(pending)
    bridge = VoiceBridge(gateway)

    # 1. แชตจนเกิด pending action -> bridge อ่านทวนข้อมูล
    resp = await bridge.handle_text("แจ้งเหตุไฟดับครับ")
    assert bridge.has_pending_action is True
    assert bridge.read_back_completed is True

    # 2. จำลองกรณี LLM หลอน/พยายามเรียก confirm โดยที่ผู้ใช้ไม่ได้พูดคำยินยอม
    # ต้อง fail closed ทันทีด้วย code="consent_required"
    with pytest.raises(VoiceBridgeError) as exc_info:
        await bridge.confirm_current(confirmation_note="LLM สั่งยืนยันเอง")
    assert exc_info.value.code == "consent_required"
    assert len(gateway.confirm_calls) == 0

    # 3. จำลองผู้ใช้พูดเสียงจริงผ่าน speech transcription: "ยืนยันครับ"
    await bridge.process_user_transcription("ยืนยันครับ")

    # 4. ตอนนี้โมเดลจึงเรียก confirm_current ได้สำเร็จ
    result = await bridge.confirm_current()
    assert result["pendingAction"]["status"] == "submitted"
    assert len(gateway.confirm_calls) == 1
    # และมี evidence แนบไปด้วย
    call_evidence = gateway.confirm_calls[0][2]
    assert call_evidence is not None
    assert call_evidence["transcription"] == "ยืนยันครับ"
    assert "ขออ่านทวนข้อมูล" in call_evidence["readBackText"]

    # 5. เมื่อสถานะเป็น terminal แล้ว การเรียกซ้ำต้อง fail closed
    with pytest.raises(NoPendingActionError):
        await bridge.confirm_current()


@pytest.mark.asyncio
async def test_confirm_before_read_back_fails_closed() -> None:
    """การยืนยันก่อนอ่านทวนเสร็จ ต้อง fail closed (ordering safety)"""
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901"},
        summary="แจ้งไฟดับ",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(pending)
    bridge = VoiceBridge(gateway)
    bridge._pending_action_id = pending.pending_action_id
    bridge._read_back_completed = False  # ยังไม่ได้อ่านทวน!

    # ผู้ใช้พูด "ยืนยันครับ" ก่อนที่ระบบจะอ่านทวน
    await bridge.process_user_transcription("ยืนยันครับ")
    assert bridge._consent_granted is False

    with pytest.raises(ActionConflictError) as exc_info:
        await bridge.confirm_current()
    assert "ยังไม่ได้อ่านทวน" in str(exc_info.value)


# ===========================================================================
# 4. Spoken Refusal -> Schema-Driven Correction -> NEW Pending Action (T6.2 🔒)
# ===========================================================================

@pytest.mark.asyncio
async def test_refusal_terminates_old_action_and_enters_schema_driven_correction() -> None:
    """🔒 คำปฏิเสธ:
    1. action เดิมถูก reject เป็น terminal ใน trace และ stores ทันที (ห้ามปลุกของเดิม)
    2. ถามว่าต้องการแก้ไขช่องไหน โดยรายการช่องมาจาก inputSchema
    """
    old_action_id = uuid4()
    old_pending = PendingAction(
        pending_action_id=old_action_id,
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901", "phone": "0812345678"},
        summary="แจ้งเหตุไฟดับ CA 12345678901",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-old",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(old_pending)
    bridge = VoiceBridge(gateway)
    await bridge.handle_text("แจ้งเหตุไฟดับครับ")
    assert bridge.has_pending_action is True

    # ผู้ใช้พูดปฏิเสธ: "ไม่ใช่ครับ ข้อมูลเบอร์โทรผิด"
    result = await bridge.handle_text("ไม่ใช่ครับ")
    # 1. Action เดิมต้องถูก reject
    assert len(gateway.reject_calls) == 1
    assert gateway.reject_calls[0][0] == old_action_id
    assert gateway.all_actions[old_action_id].status is PendingActionStatus.REJECTED
    assert bridge.has_pending_action is False

    # 2. ระบบเข้าสู่โหมดแก้ไข และถามช่องที่แก้ได้
    assert bridge.in_correction_mode is True
    assert result.get("inCorrectionMode") is True
    assert "ต้องการแก้ไขส่วนไหน" in result["message"]
    assert "เบอร์โทรศัพท์" in result["message"] or "phone" in result["message"]
    assert "ทั้งหมด" in result["message"]

    # 3. ตรวจสอบว่า action เดิมยังคง terminal และไม่สามารถยืนยันได้อีก
    with pytest.raises(RuntimeError) as exc_info:
        await gateway.confirm_pending_action(old_action_id)
    assert "ไม่สามารถยืนยัน" in str(exc_info.value)


@pytest.mark.asyncio
async def test_correction_creates_brand_new_pending_action() -> None:
    """🔒 การแก้ไข: ต้องสร้าง pending action ใหม่ ห้ามปลุกของเดิม"""
    old_action_id = uuid4()
    new_action_id = uuid4()

    old_pending = PendingAction(
        pending_action_id=old_action_id,
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901", "phone": "0812345678"},
        summary="แจ้งไฟดับ",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    new_pending = PendingAction(
        pending_action_id=new_action_id,
        conversation_id=old_pending.conversation_id,
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901", "phone": "0899999999"},
        summary="แจ้งไฟดับ (แก้ไขเบอร์)",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-2",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class MultiActionGateway(StubVoiceGateway):
        async def handle_chat(self, request: ChatRequest) -> ChatResponse:
            self.chat_calls.append(request.message)
            if "แก้" in request.message or "089" in request.message:
                self.all_actions[new_action_id] = new_pending
                return ChatResponse(
                    conversation_id=request.conversation_id or uuid4(),
                    trace_id=uuid4(),
                    message="เตรียมข้อมูลใหม่เรียบร้อย",
                    pending_action=new_pending,
                )
            return await super().handle_chat(request)

    gateway = MultiActionGateway(old_pending)
    bridge = VoiceBridge(gateway)

    await bridge.handle_text("แจ้งเหตุไฟดับครับ")
    assert bridge.pending_action_id == str(old_action_id)

    # ปฏิเสธรายการเดิม -> เข้าโหมดแก้ไข
    await bridge.handle_text("ไม่ใช่ครับ")
    assert gateway.all_actions[old_action_id].status is PendingActionStatus.REJECTED
    assert bridge.in_correction_mode is True

    # ส่งข้อมูลแก้ไข
    resp = await bridge.handle_text("แก้เบอร์โทรเป็น 0899999999")

    # ต้องได้ pending action ใหม่ที่มี UUID ใหม่
    assert bridge.pending_action_id == str(new_action_id)
    assert new_action_id != old_action_id
    # ของเดิมต้องยังคงเป็น REJECTED (ห้ามปลุกชีพ!)
    assert gateway.all_actions[old_action_id].status is PendingActionStatus.REJECTED

    # Action ใหม่มี read-back ใหม่
    assert bridge.read_back_completed is True
    assert "0899999999" in bridge.read_back_text

    # ผู้ใช้พูด "ยืนยันครับ" ต่อรายการใหม่
    await bridge.process_user_transcription("ยืนยันครับ")
    decision = await bridge.confirm_current()
    assert decision["pendingAction"]["pendingActionId"] == str(new_action_id)
    assert decision["pendingAction"]["status"] == "submitted"
    # Action เดิมยังคง REJECTED
    assert gateway.all_actions[old_action_id].status is PendingActionStatus.REJECTED


@pytest.mark.asyncio
async def test_correction_ceiling_enforced() -> None:
    """🔒 เพดานรอบการแก้ไขทำงาน: เกิน 3 ครั้งต้องตัดจบลำดับการแก้ไข"""
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901"},
        summary="แจ้งไฟดับ",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(pending)
    bridge = VoiceBridge(gateway)

    # จำลองการปฏิเสธและขอแก้ 3 รอบ
    for i in range(3):
        await bridge.handle_text("แจ้งไฟดับ")
        res = await bridge.handle_text("ไม่ใช่ครับ")
        assert bridge.correction_count == i + 1
        assert bridge.in_correction_mode is True

    # รอบที่ 4: เกินเพดาน 3 ครั้ง
    await bridge.handle_text("แจ้งไฟดับ")
    res4 = await bridge.handle_text("ไม่ใช่ครับ")
    assert bridge.in_correction_mode is False
    assert "เกินเพดาน 3 ครั้ง" in res4["message"]
    assert "1129" in res4["message"]


# ===========================================================================
# 5. Bounded Retries for Ambiguous Speech (T6.1)
# ===========================================================================

@pytest.mark.asyncio
async def test_ambiguous_speech_bounded_retries_and_terminal_rejection() -> None:
    """คำพูดกำกวมไม่ตรงทั้งยืนยันและปฏิเสธ -> ถามซ้ำได้สูงสุด 3 ครั้ง เกินแล้วยกเลิกรายการ"""
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901"},
        summary="แจ้งไฟดับ",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(pending)
    bridge = VoiceBridge(gateway)
    await bridge.handle_text("แจ้งไฟดับ")

    # 1st ambiguous
    await bridge.process_user_transcription("ขอคิดดูก่อนนะ")
    assert bridge.retry_count == 1
    assert bridge.has_pending_action is True

    # 2nd ambiguous
    await bridge.process_user_transcription("อะไรนะ")
    assert bridge.retry_count == 2
    assert bridge.has_pending_action is True

    # 3rd ambiguous
    await bridge.process_user_transcription("เดี๋ยวก่อน")
    assert bridge.retry_count == 3
    assert bridge.has_pending_action is True

    # 4th ambiguous: เกินเพดาน 3 ครั้ง -> terminal reject
    await bridge.process_user_transcription("ฮัลโหล")
    assert bridge.has_pending_action is False
    assert gateway.all_actions[pending.pending_action_id].status is PendingActionStatus.REJECTED
    assert "ถามซ้ำเกินกำหนด" in gateway.reject_calls[0][1]


# ===========================================================================
# 6. voiceConfirm Gating (T6.3)
# ===========================================================================

@pytest.mark.asyncio
async def test_voice_confirm_false_fails_closed_in_bridge_and_main_agent() -> None:
    """T6.3: หาก operation มี voice_confirm=False การยืนยันด้วยเสียงต้อง fail closed"""
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="payment_tool",
        prepare_action="prepare_payment",
        submit_action="submit_payment",
        prepared_input={"amount": 1500},
        summary="ชำระเงินค่าไฟฟ้า 1500 บาท",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-pay",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class RestrictedGateway(StubVoiceGateway):
        def get_operation_spec(self, tool_slug: str, action: str) -> OperationSpec:
            return OperationSpec(
                policy=OperationPolicy.WRITE_CONFIRM,
                voice_confirm=False,  # 🔒 ไม่อนุญาตให้ยืนยันด้วยเสียง
            )

    gateway = RestrictedGateway(pending)
    bridge = VoiceBridge(gateway)
    await bridge.handle_text("จ่ายค่าไฟ")

    # Bridge ตรวจพบว่าไม่อนุญาตยืนยันด้วยเสียง
    assert bridge._voice_confirm_allowed is False

    # ผู้ใช้พูด "ยืนยันครับ" -> consent ต้องไม่ถูกเปิด
    await bridge.process_user_transcription("ยืนยันครับ")
    assert bridge._consent_granted is False

    # พยายามยืนยัน -> fail closed ด้วย code="voice_confirm_disabled"
    with pytest.raises(VoiceBridgeError) as exc_info:
        await bridge.confirm_current()
    assert exc_info.value.code == "voice_confirm_disabled"


# ===========================================================================
# 7. Voice Citation Degradation (T6.3)
# ===========================================================================

def test_strip_voice_citations_removes_urls_and_markers() -> None:
    """เสียงต้องไม่พูดหมายเลข citation หรือ URL อ้างอิงตาม T6.3"""
    raw_text = "อัตราค่าไฟประเภท 1.1 คิดตามช่วงเวลา [1] ดูรายละเอียดที่ https://www.pea.co.th/tariff [2] ครับ"
    stripped = strip_voice_citations(raw_text)
    assert "[1]" not in stripped
    assert "[2]" not in stripped
    assert "https://www.pea.co.th/tariff" not in stripped
    assert "อัตราค่าไฟประเภท 1.1 คิดตามช่วงเวลา ดูรายละเอียดที่ ครับ" == stripped


# ===========================================================================
# 8. Redacted Confirmation Evidence (T6.4)
# ===========================================================================

def test_sanitize_confirmation_evidence_scrubs_pii_and_tokens() -> None:
    """T6.4: หลักฐานการยืนยันต้องปกปิด PII และ token (บัตรประชาชน 13 หลัก, บัตรเครดิต 16 หลัก, bearer token)"""
    text_with_pii = "ยืนยันข้อมูล บัตรประชาชน 1234567890123 และ Bearer secret-token-abc บัตรเครดิต 1111222233334444"
    sanitized = sanitize_confirmation_evidence(text_with_pii)
    assert "1234567890123" not in sanitized
    assert "[redacted-id]" in sanitized
    assert "secret-token-abc" not in sanitized
    assert "[redacted-token]" in sanitized
    assert "1111222233334444" not in sanitized
    assert "[redacted-card]" in sanitized


# ===========================================================================
# 9. GeminiLiveSession Real Audio / Transcription Routing
# ===========================================================================

class LiveSessionFakeWebSocket:
    def __init__(self) -> None:
        self.sent_json: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent_json.append(data)


@pytest.mark.asyncio
async def test_gemini_live_session_routes_transcripts_and_blocks_unconsented_tool_call() -> None:
    """ทดสอบการประสานระหว่าง GeminiLiveSession กับ VoiceBridge:
    - input_transcription ของผู้ใช้ถูกส่งเข้า process_user_transcription
    - หากผู้ใช้ยังไม่ยินยอม โมเดลเรียก pea_confirm_pending_action จะได้ error consent_required
    - หากผู้ใช้ถอดเสียงได้ "ยืนยันครับ" โมเดลเรียก confirm จะได้ submitted
    """
    pending = PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_outage_report",
        submit_action="submit_outage_report",
        prepared_input={"ca_number": "12345678901"},
        summary="แจ้งไฟดับ",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key="idem-key",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gateway = StubVoiceGateway(pending)
    bridge = VoiceBridge(gateway)
    await bridge.handle_text("แจ้งไฟดับ")

    session = object.__new__(GeminiLiveSession)
    session._bridge = bridge
    websocket = LiveSessionFakeWebSocket()

    # 1. โมเดลพยายามลักไก่เรียก confirm โดยที่ไม่มี transcription คำยินยอมของผู้ใช้
    res_unconsented = await session._call_bridge("pea_confirm_pending_action", {"confirmationNote": "ยืนยัน"})
    assert "error" in res_unconsented
    assert res_unconsented["error"]["code"] == "consent_required"

    # 2. เสียงผู้ใช้เข้ามาทาง WebSocket transcription: "ไม่ใช่ครับ"
    fake_content = SimpleNamespace(
        input_transcription=SimpleNamespace(text="ไม่ใช่ครับ", finished=True),
        output_transcription=None,
    )
    await session._forward_transcripts(websocket, fake_content)
    # Action เดิมต้องถูก reject
    assert bridge.has_pending_action is False
    assert gateway.all_actions[pending.pending_action_id].status is PendingActionStatus.REJECTED

    # 3. โมเดลเรียก confirm หลังถูก reject -> ต้องได้ no_pending_action
    res_rejected = await session._call_bridge("pea_confirm_pending_action", {})
    assert res_rejected["error"]["code"] == "no_pending_action"
