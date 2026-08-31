"""พฤติกรรมและความปลอดภัยของ VoiceBridge แบบผูกกับเซสชัน

ครอบคลุมข้อกำหนดของ t1: ความต่อเนื่องของ conversation, การเก็บ pending
เฉพาะรายการปัจจุบัน, การส่งต่อ confirm/reject, การ fail closed เมื่อไม่มี
pending action และรูปผลลัพธ์ JSON camelCase ที่ปลอดภัย
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.contracts import (
    ActionDecisionResponse,
    ChatRequest,
    ChatResponse,
    PendingAction,
    PendingActionStatus,
    ToolAction,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolResult,
    ToolResultStatus,
)
from app.live.bridge import (
    ActionConflictError,
    InvalidTextError,
    NoPendingActionError,
    VoiceBridge,
)
from app.live.models import MainAgentGateway


def _pending(
    *,
    status: PendingActionStatus = PendingActionStatus.PENDING_CONFIRMATION,
    submission_result: ToolResult | None = None,
) -> PendingAction:
    now = datetime.now(UTC)
    return PendingAction(
        pending_action_id=uuid4(),
        conversation_id=uuid4(),
        tool_name=ToolName.VOC,
        prepare_action=ToolAction.VOC_PREPARE_CASE,
        submit_action=ToolAction.VOC_SUBMIT_CASE,
        prepared_input={"category": "service", "contactName": "สมชาย ใจดี"},
        summary="เตรียมเรื่องร้องเรียนประเภท แจ้งปัญหาด้านบริการ",
        status=status,
        idempotency_key="voice-key-1",
        created_at=now,
        updated_at=now,
        submission_result=submission_result,
    )


def _voc_submit_result() -> ToolResult:
    return ToolResult(
        call_id=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_SUBMIT_CASE,
        status=ToolResultStatus.SUCCESS,
        data={
            "vocId": "SIM-VOC-000001",
            "trackingKey": "TRK-000001",
            "status": "submitted",
            "category": "service",
        },
        simulation=True,
    )


class FakeGateway:
    """Gateway จำลองที่บันทึกทุกการเรียกตามโปรโตคอล MainAgentGateway"""

    def __init__(self) -> None:
        self.chat_calls: list[ChatRequest] = []
        self.confirm_calls: list[tuple[UUID, str | None]] = []
        self.reject_calls: list[tuple[UUID, str]] = []
        self.chat_responses: list[ChatResponse] = []
        self.confirm_response: ActionDecisionResponse | None = None
        self.reject_response: ActionDecisionResponse | None = None
        self.confirm_error: Exception | None = None
        self.reject_error: Exception | None = None
        self._generated_conversation_id = uuid4()

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        self.chat_calls.append(request)
        if self.chat_responses:
            return self.chat_responses.pop(0)
        conversation_id = request.conversation_id or self._generated_conversation_id
        return ChatResponse(
            conversation_id=conversation_id,
            trace_id=uuid4(),
            message="ดำเนินการเรียบร้อยครับ",
        )

    async def confirm_pending_action(
        self,
        pending_action_id: UUID,
        confirmation_note: str | None = None,
    ) -> ActionDecisionResponse:
        self.confirm_calls.append((pending_action_id, confirmation_note))
        if self.confirm_error is not None:
            raise self.confirm_error
        if self.confirm_response is not None:
            return self.confirm_response
        terminal = _pending(
            status=PendingActionStatus.SUBMITTED,
            submission_result=_voc_submit_result(),
        )
        return ActionDecisionResponse(
            pending_action=terminal,
            tool_result=terminal.submission_result,
            trace_id=uuid4(),
        )

    async def reject_pending_action(
        self,
        pending_action_id: UUID,
        reason: str,
    ) -> ActionDecisionResponse:
        self.reject_calls.append((pending_action_id, reason))
        if self.reject_error is not None:
            raise self.reject_error
        if self.reject_response is not None:
            return self.reject_response
        terminal = _pending(status=PendingActionStatus.REJECTED)
        return ActionDecisionResponse(
            pending_action=terminal,
            tool_result=None,
            trace_id=uuid4(),
        )


async def _bridge_with_pending(
    gateway: FakeGateway | None = None,
    *,
    pending: PendingAction | None = None,
) -> tuple[VoiceBridge, FakeGateway]:
    """สร้าง bridge ที่มี conversation และ pending action ปัจจุบันแล้ว"""
    gateway = gateway or FakeGateway()
    bridge = VoiceBridge(gateway)
    if pending is None:
        pending = _pending()
    gateway.chat_responses.append(
        ChatResponse(
            conversation_id=uuid4(),
            trace_id=uuid4(),
            message="เตรียมเรื่องเรียบร้อย กรุณายืนยัน",
            pending_action=pending,
        )
    )
    result = await bridge.handle_text("เตรียมเรื่องร้องเรียน")
    assert result["pendingAction"] is not None
    return bridge, gateway


# ---------------------------------------------------------------------------
# ความต่อเนื่องของ conversation ต่อ WebSocket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_id_is_preserved_across_turns() -> None:
    gateway = FakeGateway()
    bridge = VoiceBridge(gateway)

    first = await bridge.handle_text("ต้องการร้องเรียนการบริการ")
    first_conversation_id = first["conversationId"]

    second = await bridge.handle_text("subject: บริการล่าช้า")
    third = await bridge.handle_text("detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ")

    assert bridge.conversation_id == first_conversation_id
    assert isinstance(first_conversation_id, str)
    assert second["conversationId"] == first_conversation_id
    assert third["conversationId"] == first_conversation_id
    # รอบแรกให้ Main Agent สร้าง id แล้วรอบต่อ ๆ ไปใช้ id เดียวกันทั้งหมด
    assert [call.conversation_id for call in gateway.chat_calls] == [
        None,
        UUID(first_conversation_id),
        UUID(first_conversation_id),
    ]


@pytest.mark.asyncio
async def test_first_turn_without_conversation_creates_and_adopts_one() -> None:
    gateway = FakeGateway()
    bridge = VoiceBridge(gateway)

    result = await bridge.handle_text("สวัสดี")

    assert result["conversationId"] == str(gateway._generated_conversation_id)
    assert bridge.conversation_id == result["conversationId"]


# ---------------------------------------------------------------------------
# การเก็บ pending action เฉพาะรายการปัจจุบัน
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_action_id_is_stored_after_prepare_turn() -> None:
    pending = _pending()
    gateway = FakeGateway()
    gateway.chat_responses.append(
        ChatResponse(
            conversation_id=uuid4(),
            trace_id=uuid4(),
            message="กรุณายืนยัน",
            pending_action=pending,
        )
    )
    bridge = VoiceBridge(gateway)

    result = await bridge.handle_text("เตรียมเรื่องร้องเรียน")

    assert bridge.has_pending_action is True
    assert bridge.pending_action_id == str(pending.pending_action_id)
    assert result["pendingAction"]["pendingActionId"] == str(pending.pending_action_id)
    assert result["pendingAction"]["status"] == "pending_confirmation"


@pytest.mark.asyncio
async def test_new_pending_action_replaces_the_stored_one() -> None:
    first_pending = _pending()
    second_pending = _pending()
    gateway = FakeGateway()
    conversation_id = uuid4()
    gateway.chat_responses.extend(
        [
            ChatResponse(
                conversation_id=conversation_id,
                trace_id=uuid4(),
                message="รายการแรก",
                pending_action=first_pending,
            ),
            ChatResponse(
                conversation_id=conversation_id,
                trace_id=uuid4(),
                message="รายการที่สอง",
                pending_action=second_pending,
            ),
        ]
    )
    bridge = VoiceBridge(gateway)

    await bridge.handle_text("เตรียมรายการแรก")
    assert bridge.pending_action_id == str(first_pending.pending_action_id)

    await bridge.handle_text("เตรียมรายการที่สอง")

    # เก็บเฉพาะ id ของรายการปัจจุบันเท่านั้น
    assert bridge.pending_action_id == str(second_pending.pending_action_id)
    assert bridge.has_pending_action is True


@pytest.mark.asyncio
async def test_chat_turn_without_pending_keeps_the_stored_current_pending() -> None:
    pending = _pending()
    gateway = FakeGateway()
    conversation_id = uuid4()
    gateway.chat_responses.extend(
        [
            ChatResponse(
                conversation_id=conversation_id,
                trace_id=uuid4(),
                message="กรุณายืนยัน",
                pending_action=pending,
            ),
            ChatResponse(
                conversation_id=conversation_id,
                trace_id=uuid4(),
                message="คำตอบความรู้ล้วน ๆ ไม่มีรายการใหม่",
                pending_action=None,
            ),
        ]
    )
    bridge = VoiceBridge(gateway)

    await bridge.handle_text("เตรียมเรื่องร้องเรียน")
    await bridge.handle_text("ค่าไฟคิดยังไง")

    # รายการก่อนหน้าที่ยังรอการยืนยันยังคงเป็นรายการปัจจุบันของเซสชัน
    assert bridge.has_pending_action is True
    assert bridge.pending_action_id == str(pending.pending_action_id)


# ---------------------------------------------------------------------------
# การส่งต่อ confirm / reject ไปยัง Main Agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_current_delegates_with_stored_id_and_clears_terminal_state() -> None:
    pending = _pending()
    gateway = FakeGateway()
    bridge, gateway = await _bridge_with_pending(gateway, pending=pending)

    result = await bridge.confirm_current(confirmation_note="ยืนยันด้วยเสียง")

    # ส่งต่อด้วย id ที่ bridge เก็บไว้เท่านั้น ไม่ใช่ id จากโมเดล
    assert gateway.confirm_calls == [
        (pending.pending_action_id, "ยืนยันด้วยเสียง")
    ]
    assert result["pendingAction"]["status"] == "submitted"
    assert result["toolResult"]["status"] == "success"
    assert result["traceId"]
    # สถานะสิ้นสุด → ล้างทันที และการยืนยันซ้ำต้อง fail closed
    assert bridge.has_pending_action is False
    assert bridge.pending_action_id is None


@pytest.mark.asyncio
async def test_confirm_without_note_passes_none() -> None:
    pending = _pending()
    gateway = FakeGateway()
    bridge, gateway = await _bridge_with_pending(gateway, pending=pending)

    await bridge.confirm_current()

    assert gateway.confirm_calls == [(pending.pending_action_id, None)]


@pytest.mark.asyncio
async def test_reject_current_delegates_with_stored_id_and_reason_and_clears() -> None:
    pending = _pending()
    gateway = FakeGateway()
    bridge, gateway = await _bridge_with_pending(gateway, pending=pending)

    result = await bridge.reject_current(reason="ผู้ใช้เปลี่ยนใจ")

    assert gateway.reject_calls == [(pending.pending_action_id, "ผู้ใช้เปลี่ยนใจ")]
    assert result["pendingAction"]["status"] == "rejected"
    assert result["toolResult"] is None
    assert bridge.has_pending_action is False
    assert bridge.pending_action_id is None


@pytest.mark.asyncio
async def test_failed_submission_is_terminal_and_clears_pending() -> None:
    pending = _pending()
    gateway = FakeGateway()
    failed_result = ToolResult(
        call_id=uuid4(),
        name=ToolName.VOC,
        action=ToolAction.VOC_SUBMIT_CASE,
        status=ToolResultStatus.ERROR,
        error=ToolError(code=ToolErrorCode.UNAVAILABLE, message="บริการไม่พร้อมใช้งานชั่วคราว"),
        simulation=True,
    )
    gateway.confirm_response = ActionDecisionResponse(
        pending_action=_pending(status=PendingActionStatus.FAILED, submission_result=failed_result),
        tool_result=failed_result,
        trace_id=uuid4(),
    )
    bridge, _ = await _bridge_with_pending(gateway, pending=pending)

    result = await bridge.confirm_current()

    assert result["pendingAction"]["status"] == "failed"
    assert bridge.has_pending_action is False


# ---------------------------------------------------------------------------
# การ fail closed เมื่อไม่มี pending action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_without_pending_fails_closed() -> None:
    gateway = FakeGateway()
    bridge = VoiceBridge(gateway)

    with pytest.raises(NoPendingActionError) as exc_info:
        await bridge.confirm_current()

    error = exc_info.value
    assert error.code == "no_pending_action"
    assert error.to_dict() == {
        "error": {"code": "no_pending_action", "message": error.message}
    }
    # ไม่มีการส่งต่อไปยัง Main Agent
    assert gateway.confirm_calls == []


@pytest.mark.asyncio
async def test_reject_without_pending_fails_closed() -> None:
    gateway = FakeGateway()
    bridge = VoiceBridge(gateway)

    with pytest.raises(NoPendingActionError):
        await bridge.reject_current(reason="ไม่เอาแล้ว")

    assert gateway.reject_calls == []


@pytest.mark.asyncio
async def test_second_confirm_after_terminal_clears_fails_closed() -> None:
    bridge, gateway = await _bridge_with_pending()
    await bridge.confirm_current()

    with pytest.raises(NoPendingActionError):
        await bridge.confirm_current()

    # ส่งต่อเพียงครั้งเดียว ไม่มีการยืนยันซ้ำ
    assert len(gateway.confirm_calls) == 1


@pytest.mark.asyncio
async def test_stale_pending_reported_by_agent_fails_closed_and_clears() -> None:
    from app.agent.main_agent import NotFoundError

    gateway = FakeGateway()
    gateway.confirm_error = NotFoundError("ไม่พบรายการที่รอดำเนินการ")
    bridge, _ = await _bridge_with_pending(gateway)

    with pytest.raises(NoPendingActionError):
        await bridge.confirm_current()

    assert bridge.has_pending_action is False


@pytest.mark.asyncio
async def test_invalid_state_from_agent_maps_to_action_conflict() -> None:
    from app.agent.main_agent import InvalidActionStateError

    gateway = FakeGateway()
    gateway.confirm_error = InvalidActionStateError("ไม่สามารถยืนยันรายการที่ถูกปฏิเสธแล้วได้")
    bridge, _ = await _bridge_with_pending(gateway)

    with pytest.raises(ActionConflictError) as exc_info:
        await bridge.confirm_current()

    assert exc_info.value.code == "action_conflict"


# ---------------------------------------------------------------------------
# การตรวจสอบข้อความขาเข้า (fail closed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_or_whitespace_text_fails_closed() -> None:
    bridge = VoiceBridge(FakeGateway())

    for bad_message in ("", "   ", "\t\n"):
        with pytest.raises(InvalidTextError):
            await bridge.handle_text(bad_message)


@pytest.mark.asyncio
async def test_overlong_text_fails_closed() -> None:
    bridge = VoiceBridge(FakeGateway())

    with pytest.raises(InvalidTextError):
        await bridge.handle_text("ก" * 4001)


@pytest.mark.asyncio
async def test_reject_without_reason_fails_closed() -> None:
    bridge, _ = await _bridge_with_pending()

    with pytest.raises(InvalidTextError):
        await bridge.reject_current(reason="   ")

    assert bridge.has_pending_action is True


# ---------------------------------------------------------------------------
# รูปผลลัพธ์ JSON camelCase ที่ปลอดภัย
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_result_is_json_serializable_camel_case() -> None:
    pending = _pending()
    gateway = FakeGateway()
    gateway.chat_responses.append(
        ChatResponse(
            conversation_id=uuid4(),
            trace_id=uuid4(),
            message="ข้อความตอบกลับ",
            pending_action=pending,
        )
    )
    bridge = VoiceBridge(gateway)

    result = await bridge.handle_text("เตรียมเรื่องร้องเรียน")

    assert set(result) == {"conversationId", "traceId", "message", "citations", "pendingAction", "toolResults"}
    assert isinstance(result["pendingAction"], dict)
    assert json.dumps(result, ensure_ascii=False)  # JSON-safe


# ---------------------------------------------------------------------------
# ทำงานกับ Main Agent จริงแบบ end-to-end
# ---------------------------------------------------------------------------


def _real_agent() -> object:
    from app.agent.main_agent import MainAgent
    from app.agent.registry import ToolRegistry
    from app.backends.full_document_knowledge import FullDocumentKnowledgeBackend
    from app.llm import DemoLLMAdapter, LLMClient
    from app.tools.knowledge_tool import KnowledgeTool
    from app.tools.oms_tool import OmsTool
    from app.tools.sabuy_tool import SabuyTool
    from app.tools.voc_tool import VocTool

    registry = ToolRegistry(
        [
            KnowledgeTool(FullDocumentKnowledgeBackend()),
            SabuyTool(),
            VocTool(),
            OmsTool(),
        ]
    )
    return MainAgent(LLMClient(DemoLLMAdapter()), registry)


@pytest.mark.asyncio
async def test_bridge_accepts_real_main_agent_instance() -> None:
    agent = _real_agent()

    # MainAgent จริงเป็นไปตามโปรโตคอลขั้นต่ำของ voice bridge
    assert isinstance(agent, MainAgentGateway)


@pytest.mark.asyncio
async def test_voice_flow_against_real_main_agent() -> None:
    agent = _real_agent()
    bridge = VoiceBridge(agent)  # type: ignore[arg-type]

    # รอบแรก: เริ่มการร้องเรียน → ถามรายละเอียด ยังไม่มี pending
    first = await bridge.handle_text("ต้องการร้องเรียนการบริการ")
    assert first["pendingAction"] is None
    assert "หัวข้อ" in first["message"]

    # รอบสอง: ให้ข้อมูลครบ → เตรียมเคส → bridge เก็บ pending ปัจจุบัน
    second = await bridge.handle_text(
        "subject: เจ้าหน้าที่ให้บริการล่าช้า; detail: รอเจ็ดวันแล้วยังไม่มีการติดต่อกลับ; "
        "contactName: สมชาย ใจดี; contactPhone: 0812345678; location: ถนนสุขุมวิท กรุงเทพฯ"
    )
    assert second["pendingAction"] is not None
    assert second["pendingAction"]["status"] == "pending_confirmation"
    assert second["pendingAction"]["toolName"] == "voc_tool"
    assert bridge.has_pending_action is True

    # ยืนยันด้วยเสียง → submit_case หนึ่งครั้ง → สถานะสิ้นสุดและล้าง pending
    decision = await bridge.confirm_current(confirmation_note="ยืนยันจากเสียง")
    assert decision["pendingAction"]["status"] == "submitted"
    assert decision["toolResult"]["status"] == "success"
    assert decision["toolResult"]["data"]["vocId"]
    assert bridge.has_pending_action is False

    # การยืนยันซ้ำ fail closed
    with pytest.raises(NoPendingActionError):
        await bridge.confirm_current()
