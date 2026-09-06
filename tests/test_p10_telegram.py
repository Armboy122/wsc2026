"""การทดสอบ Telegram adapter และ shared channel layer ตาม V2 เฟส 4 (T4.1–T4.4)

เทสที่ครอบคลุม:
1. Telegram webhook auth — token ผิด/ขาด ถูกปฏิเสธ (403)
2. callback ทำงานถูกต้อง — answerCallbackQuery ถูกเรียกทุกครั้ง
3. editMessageReplyMarkup ลบปุ่มสำหรับ single-use
4. กดยืนยันซ้ำไม่สร้างรายการซ้ำ (state machine / idempotency ป้องกัน)
5. callback_data เกิน 64 bytes ไม่ถูกส่ง
6. migrate_to_chat_id ย้าย state ใน bridge
7. capability declarations: LINE ตัด 1900, Telegram ตัด 4096, Web ไม่ตัด, API degrade เป็นข้อความ + id
8. ไม่ตั้ง token = fail closed (404)
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.telegram import configure_telegram_webhook, router as telegram_router
from app.channel import (
    ACTION_CONFIRM,
    ACTION_NEW_CHAT,
    ACTION_REJECT,
    CHANNEL_CAPABILITIES,
    degrade_for_channel,
    format_actions,
    get_channel_capabilities,
    parse_action_callback,
    split_text,
)
from app.contracts import Action, ChatRequest, ChatResponse, ChoiceOption, ChoicePrompt, PendingAction, PendingActionStatus
from app.telegram.api_client import TelegramApiClient
from app.telegram.bridge import TelegramBridge, TelegramBridgeError
from app.telegram.service import (
    TelegramWebhookService,
    build_inline_keyboard,
    format_telegram_chat_messages,
)


class _MockTelegramClient(TelegramApiClient):
    """Client จำลองบันทึกทุกคำขอที่ยิงออกไป"""

    def __init__(self) -> None:
        super().__init__("mock_token")
        self.sent_messages: list[tuple[int | str, str, dict[str, Any] | None]] = []
        self.edited_markups: list[tuple[int | str, int, dict[str, Any] | None]] = []
        self.answered_callbacks: list[tuple[str, str | None, bool]] = []
        self.chat_actions: list[tuple[int | str, str]] = []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.sent_messages.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": len(self.sent_messages)}}

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.edited_markups.append((chat_id, message_id, reply_markup))
        return {"ok": True, "result": {"message_id": message_id}}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        self.answered_callbacks.append((callback_query_id, text, show_alert))
        return {"ok": True, "result": True}

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = "typing",
    ) -> None:
        self.chat_actions.append((chat_id, action))


class _StubAgent:
    """Agent จำลองสำหรับทดสอบการทำงานของ Telegram adapter"""

    def __init__(self) -> None:
        self.handled_requests: list[ChatRequest] = []
        self.confirmed_ids: list[UUID] = []
        self.rejected_ids: list[UUID] = []
        self.pending_action: PendingAction | None = None

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        self.handled_requests.append(request)
        actions = format_actions(pending_action=self.pending_action)
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            trace_id=uuid4(),
            message=f"คำตอบสำหรับ: {request.message}",
            pending_action=self.pending_action,
            simulation=True,
            actions=actions,
        )

    async def confirm_pending_action(
        self,
        pending_action_id: UUID,
        confirmation_note: str | None = None,
    ) -> Any:
        if self.pending_action is None or self.pending_action.pending_action_id != pending_action_id:
            from app.agent.main_agent import NotFoundError
            raise NotFoundError("ไม่พบรายการ")
        if self.pending_action.status in {PendingActionStatus.SUBMITTED, PendingActionStatus.REJECTED}:
            from app.agent.main_agent import InvalidActionStateError
            raise InvalidActionStateError("รายการอยู่ในสถานะสิ้นสุดแล้ว")

        self.confirmed_ids.append(pending_action_id)
        submitted = self.pending_action.model_copy(update={"status": PendingActionStatus.SUBMITTED})
        self.pending_action = submitted

        class _Decision:
            def __init__(self, action: PendingAction):
                self.pending_action = action
                self.tool_result = None
                self.trace_id = uuid4()

            def model_dump(self, mode: str = "json", by_alias: bool = True) -> dict[str, Any]:
                return {
                    "pendingAction": {
                        "pendingActionId": str(self.pending_action.pending_action_id),
                        "status": self.pending_action.status.value,
                        "summary": self.pending_action.summary,
                    },
                    "toolResult": None,
                    "traceId": str(self.trace_id),
                }

        return _Decision(submitted)

    async def reject_pending_action(
        self,
        pending_action_id: UUID,
        reason: str | None = None,
    ) -> Any:
        if self.pending_action is None or self.pending_action.pending_action_id != pending_action_id:
            from app.agent.main_agent import NotFoundError
            raise NotFoundError("ไม่พบรายการ")

        self.rejected_ids.append(pending_action_id)
        rejected = self.pending_action.model_copy(update={"status": PendingActionStatus.REJECTED})
        self.pending_action = rejected

        class _Decision:
            def __init__(self, action: PendingAction):
                self.pending_action = action

            def model_dump(self, mode: str = "json", by_alias: bool = True) -> dict[str, Any]:
                return {
                    "pendingAction": {
                        "pendingActionId": str(self.pending_action.pending_action_id),
                        "status": self.pending_action.status.value,
                        "summary": self.pending_action.summary,
                    }
                }

        return _Decision(rejected)


from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def _make_pending_action(conv_id: UUID | None = None) -> PendingAction:
    now = datetime.now(UTC)
    return PendingAction(
        pending_action_id=uuid4(),
        conversation_id=conv_id or uuid4(),
        tool_slug="oms_tool",
        prepare_action="prepare_anonymous_outage",
        submit_action="submit_anonymous_outage",
        prepared_input={"description": "ไฟดับ"},
        summary="แจ้งเหตุไฟฟ้าขัดข้อง ถนนสุขุมวิท",
        status=PendingActionStatus.PENDING_CONFIRMATION,
        idempotency_key=str(uuid4()),
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# 1. Webhook Auth tests
# ---------------------------------------------------------------------------

def test_telegram_webhook_auth_rejects_missing_or_invalid_secret_token() -> None:
    """webhook ต้องปฏิเสธ 403 เมื่อไม่มี token หรือ token ไม่ถูกต้อง (compare_digest fail-closed)"""
    test_app = FastAPI()
    test_app.include_router(telegram_router)

    service = TelegramWebhookService(
        secret="valid-secret-123456",
        client=_MockTelegramClient(),
        bridge=TelegramBridge(_StubAgent()),
    )
    configure_telegram_webhook(service)
    client = TestClient(test_app)

    # 1. ไม่มี header เลย
    r1 = client.post("/webhook/telegram", json={"update_id": 1})
    assert r1.status_code == 403
    assert r1.json()["detail"] == "secret_token ไม่ถูกต้อง"

    # 2. secret ผิด
    r2 = client.post(
        "/webhook/telegram",
        json={"update_id": 2},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert r2.status_code == 403

    # 3. secret ถูกต้อง
    r3 = client.post(
        "/webhook/telegram",
        json={"update_id": 3},
        headers={"X-Telegram-Bot-Api-Secret-Token": "valid-secret-123456"},
    )
    assert r3.status_code == 200
    assert r3.json() == {}


def test_telegram_webhook_unconfigured_returns_404() -> None:
    """เมื่อไม่ได้ตั้งค่า bot / service ให้ปิดช่องทางแบบ fail closed (404) ไม่ crash"""
    test_app = FastAPI()
    test_app.include_router(telegram_router)

    import app.api.telegram as telegram_module
    old_service = telegram_module._service
    try:
        telegram_module._service = None
        client = TestClient(test_app)
        res = client.post("/webhook/telegram", json={"update_id": 1})
        assert res.status_code == 404
        assert "ยังไม่ได้เปิดใช้งาน" in res.json()["detail"]
    finally:
        telegram_module._service = old_service


# ---------------------------------------------------------------------------
# 2. Callback Query & Single-use Button tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_callback_always_answers_and_edits_reply_markup() -> None:
    """กฎ 🔒: answerCallbackQuery ต้องถูกเรียกทุกครั้ง และ editMessageReplyMarkup ลบปุ่มออก (real service path)"""
    agent = _StubAgent()
    pending = _make_pending_action()
    agent.pending_action = pending

    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    chat_id = 12345
    # ส่งข้อความผ่าน real service path
    await service.handle_update({
        "message": {
            "message_id": 87,
            "chat": {"id": chat_id},
            "from": {"id": chat_id},
            "text": "แจ้งไฟดับ",
        }
    })

    assert len(mock_client.sent_messages) >= 1
    sent_markup = mock_client.sent_messages[-1][2]
    assert sent_markup is not None
    confirm_btn = sent_markup["inline_keyboard"][0][0]
    confirm_cb_data = confirm_btn["callback_data"]

    # ผู้ใช้กดปุ่ม confirm
    callback = {
        "id": "query_1001",
        "data": confirm_cb_data,
        "from": {"id": chat_id},
        "message": {"message_id": 88, "chat": {"id": chat_id}},
    }
    await service.handle_update({"callback_query": callback})

    # 1. ต้องเรียก answerCallbackQuery
    assert len(mock_client.answered_callbacks) == 1
    assert mock_client.answered_callbacks[0][0] == "query_1001"
    assert "ยืนยันสำเร็จ" in str(mock_client.answered_callbacks[0][1])

    # 2. ต้องเรียก editMessageReplyMarkup ลบปุ่มออก (reply_markup=None)
    assert len(mock_client.edited_markups) == 1
    assert mock_client.edited_markups[0] == (chat_id, 88, None)

    # 3. ต้องส่งข้อความผลลัพธ์
    assert len(mock_client.sent_messages) >= 2
    assert "ยืนยันสำเร็จ" in mock_client.sent_messages[-1][1]


@pytest.mark.asyncio
async def test_telegram_callback_answers_even_on_unknown_or_error() -> None:
    """answerCallbackQuery ต้องถูกเรียกแม้ callback data ไม่ถูกต้องหรือเกิด error"""
    agent = _StubAgent()
    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    # Callback ที่ไม่มี pending action อยู่ใน bridge
    callback = {
        "id": "query_9999",
        "data": "act:invalid_token_9999",
        "from": {"id": 99999},
        "message": {"message_id": 99, "chat": {"id": 99999}},
    }
    await service.handle_update({"callback_query": callback})

    # ยังคงต้องตอบ answerCallbackQuery เสมอ ผู้ใช้จะได้ไม่ติด loading spinner
    assert len(mock_client.answered_callbacks) == 1
    assert mock_client.answered_callbacks[0][0] == "query_9999"


# ---------------------------------------------------------------------------
# 3. Double-confirm / Idempotency tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_double_confirm_does_not_create_duplicate_write() -> None:
    """กฎ 🔒: กดยืนยันซ้ำไม่สร้างรายการซ้ำ (state machine และ registry ป้องกัน replay)"""
    agent = _StubAgent()
    pending = _make_pending_action()
    agent.pending_action = pending

    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    chat_id = 555
    await service.handle_update({
        "message": {
            "message_id": 9,
            "chat": {"id": chat_id},
            "from": {"id": chat_id},
            "text": "แจ้งไฟดับ",
        }
    })
    sent_markup = mock_client.sent_messages[-1][2]
    confirm_cb_data = sent_markup["inline_keyboard"][0][0]["callback_data"]

    callback = {
        "id": "q1",
        "data": confirm_cb_data,
        "from": {"id": chat_id},
        "message": {"message_id": 10, "chat": {"id": chat_id}},
    }
    # กดครั้งที่ 1
    await service.handle_update({"callback_query": callback})
    assert len(agent.confirmed_ids) == 1

    # กดครั้งที่ 2 (replay หรือ double click)
    callback2 = {
        "id": "q2",
        "data": confirm_cb_data,
        "from": {"id": chat_id},
        "message": {"message_id": 10, "chat": {"id": chat_id}},
    }
    await service.handle_update({"callback_query": callback2})

    # ต้องไม่เกิด submit ซ้ำ!
    assert len(agent.confirmed_ids) == 1
    # แต่ answerCallbackQuery ของครั้งที่ 2 ต้องยังถูกตอบ
    assert len(mock_client.answered_callbacks) == 2
    assert "ถูกใช้งานไปแล้ว" in str(mock_client.answered_callbacks[-1][1])


# ---------------------------------------------------------------------------
# 4. callback_data <= 64 bytes tests
# ---------------------------------------------------------------------------

def test_telegram_inline_keyboard_omits_callback_data_longer_than_64_bytes() -> None:
    """กฎ 🔒: callback_data ยาวเกิน 64 bytes ต้องไม่ถูกส่ง"""
    long_value = "a" * 65  # 65 bytes
    valid_value = "a" * 64  # 64 bytes

    actions = [
        {"label": "ปุ่มยาวเกิน", "value": long_value, "kind": "pick", "single_use": True},
        {"label": "ปุ่มพอดี", "value": valid_value, "kind": "pick", "single_use": True},
        {"label": "ปุ่มยืนยัน", "value": ACTION_CONFIRM, "kind": "confirm", "single_use": True},
    ]

    markup = build_inline_keyboard(actions=actions)
    assert markup is not None
    buttons = [btn for row in markup["inline_keyboard"] for btn in row]

    # ปุ่มยาวเกินต้องไม่อยู่ในผลลัพธ์
    labels = [b["text"] for b in buttons]
    assert "ปุ่มยาวเกิน" not in labels
    assert "ปุ่มพอดี" in labels
    assert "ปุ่มยืนยัน" in labels

    # ทุก callback_data ต้อง <= 64 bytes
    for b in buttons:
        if "callback_data" in b:
            assert len(b["callback_data"].encode("utf-8")) <= 64


# ---------------------------------------------------------------------------
# 5. migrate_to_chat_id tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_migrate_to_chat_id_preserves_conversation_and_pending() -> None:
    """เมื่อกลุ่มย้ายเป็น supergroup (migrate_to_chat_id) ต้องย้าย state ตาม"""
    agent = _StubAgent()
    pending = _make_pending_action()
    agent.pending_action = pending

    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    old_chat_id = -1001
    new_chat_id = -100200300

    # 1. แชตในกลุ่มเดิม
    resp = await bridge.handle_chat(old_chat_id, "ขอแจ้งไฟดับครับ")
    assert str(bridge._conversation_ids[str(old_chat_id)]) == resp["conversationId"]
    assert bridge._pending_action_ids[str(old_chat_id)] == pending.pending_action_id

    # 2. ข้อความ migrate_to_chat_id เข้ามา
    migrate_update = {
        "message": {
            "chat": {"id": old_chat_id},
            "migrate_to_chat_id": new_chat_id,
        }
    }
    await service.handle_update(migrate_update)

    # 3. state ต้องย้ายไปยัง new_chat_id
    assert str(old_chat_id) not in bridge._conversation_ids
    assert str(bridge._conversation_ids[str(new_chat_id)]) == resp["conversationId"]
    assert bridge._pending_action_ids[str(new_chat_id)] == pending.pending_action_id

    # 4. กดยืนยันใน chat ใหม่ได้สำเร็จ
    decision = await bridge.confirm_current(new_chat_id)
    assert decision["pendingAction"]["status"] == "submitted"


# ---------------------------------------------------------------------------
# 6. Channel Capabilities and Degradation tests (CONTRACTS-V2.md §5.4, §5.5)
# ---------------------------------------------------------------------------

def test_capabilities_declarations_and_text_splitting() -> None:
    """เทสบังคับ T4.3: LINE ตัด 1900, Telegram ตัด 4096, Web ไม่ตัด, API degrade เป็นข้อความ + id"""
    line_cap = get_channel_capabilities("line")
    assert line_cap.max_text_length == 1900
    assert line_cap.max_buttons == 13
    assert line_cap.buttons is True

    tg_cap = get_channel_capabilities("telegram")
    assert tg_cap.max_text_length == 4096
    assert tg_cap.buttons is True

    web_cap = get_channel_capabilities("web")
    assert web_cap.max_text_length is None
    assert web_cap.buttons is True

    api_cap = get_channel_capabilities("api")
    assert api_cap.max_text_length is None
    assert api_cap.buttons is False

    # ตรวจสอบการตัดข้อความ:
    # 1. ข้อความยาว 5,000 ตัวอักษร
    long_text = "คำตอบทดสอบ " * 450  # ~5,400 chars

    # LINE: ตัดที่ 1900
    line_parts = split_text(long_text, line_cap.max_text_length)
    assert len(line_parts) > 1
    assert all(len(p) <= 1900 for p in line_parts)

    # Telegram: ตัดที่ 4096
    tg_parts = split_text(long_text, tg_cap.max_text_length)
    assert len(tg_parts) > 1
    assert all(len(p) <= 4096 for p in tg_parts)

    # Web: ไม่ตัด
    web_parts = split_text(long_text, web_cap.max_text_length)
    assert len(web_parts) == 1
    assert web_parts[0] == long_text

    # API: ไม่มีปุ่มแล้ว degrade เป็นข้อความ + id
    actions = [
        Action(label="ยืนยัน", value="action=confirm", kind="confirm", single_use=True),
        Action(label="ยกเลิก", value="action=reject", kind="reject", single_use=True),
    ]
    api_parts, api_actions = degrade_for_channel(
        message="กรุณายืนยันรายการ",
        actions=actions,
        capabilities=api_cap,
        pending_action_id="act-12345",
    )
    assert api_actions == []  # ไม่มีปุ่ม
    assert len(api_parts) == 1
    degraded_text = api_parts[0]
    assert "act-12345" in degraded_text  # คืน id ในข้อความ
    assert "ยืนยัน" in degraded_text
    assert "action=confirm" in degraded_text


# ---------------------------------------------------------------------------
# 7. ChatResponse V2 additive contract & Action model
# ---------------------------------------------------------------------------

def test_chat_response_contains_simulation_and_actions() -> None:
    """T4.1: เติม simulation และ actions ใน ChatResponse โดยไม่พัง client เก่า"""
    conv_id = uuid4()
    trace_id = uuid4()

    # Default values
    resp_default = ChatResponse(
        conversation_id=conv_id,
        trace_id=trace_id,
        message="สวัสดี",
    )
    assert resp_default.simulation is False
    assert resp_default.actions == ()

    # Explicit values
    action = Action(label="ทดสอบ", value="test_val", kind="pick", single_use=True)
    resp_custom = ChatResponse(
        conversation_id=conv_id,
        trace_id=trace_id,
        message="มีตัวเลือก",
        simulation=True,
        actions=(action,),
    )
    assert resp_custom.simulation is True
    assert len(resp_custom.actions) == 1
    data = resp_custom.model_dump(mode="json", by_alias=True)
    assert data["simulation"] is True
    assert data["actions"][0]["label"] == "ทดสอบ"
    assert data["actions"][0]["singleUse"] is True


def test_parse_action_callback_helper() -> None:
    """ทดสอบ helper กลาง parse_action_callback"""
    assert parse_action_callback("action=confirm") == {"action": "confirm"}
    assert parse_action_callback("action=reject") == {"action": "reject"}
    assert parse_action_callback("action=new_chat") == {"action": "new_chat"}
    assert parse_action_callback("action=intent&text=%E0%B9%84%E0%B8%9F%E0%B8%94%E0%B8%B1%E0%B8%9A") == {
        "action": "intent",
        "text": "ไฟดับ",
    }
    assert parse_action_callback("action=pick&p=voc_cat&v=power") == {
        "action": "pick",
        "prompt_id": "voc_cat",
        "value": "power",
    }
    assert parse_action_callback("pick:prompt1:value1") == {
        "action": "pick",
        "prompt_id": "prompt1",
        "value": "value1",
    }


# ---------------------------------------------------------------------------
# 8. Ownership & Wrong-Action Confirmation tests (Review Blocker 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_real_service_path_two_users_cross_user_and_stale_rejection() -> None:
    """ทดสอบกรณี user1 เตรียม A แล้วตามด้วย B ในกลุ่ม -123:
    1. user2 กดปุ่มของข้อความ 1 (action A) -> ต้องถูกปฏิเสธ (cross-user rejection) และ B ต้องไม่ถูก submit
    2. user1 กดปุ่มของข้อความ 1 (action A ที่ stale) -> ต้องถูกปฏิเสธ (stale rejection) และ B ต้องไม่ถูก submit
    3. user1 กดปุ่มของข้อความ 2 (action B) -> ยืนยันสำเร็จ (B ถูก submit)
    4. user1 กดปุ่มของข้อความ 2 ซ้ำ -> ปฏิเสธ (replayed rejection) ไม่ submit ซ้ำ
    """
    agent = _StubAgent()
    pending_a = _make_pending_action()
    pending_b = _make_pending_action()

    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    group_chat_id = -123
    user1_id = 1111
    user2_id = 2222

    # 1. User 1 ส่งคำขอ A
    agent.pending_action = pending_a
    await service.handle_update({
        "message": {
            "message_id": 101,
            "chat": {"id": group_chat_id, "type": "group"},
            "from": {"id": user1_id, "first_name": "User 1"},
            "text": "แจ้งไฟดับ รายการ A",
        }
    })
    msg1_markup = mock_client.sent_messages[-1][2]
    assert msg1_markup is not None
    cb_a = msg1_markup["inline_keyboard"][0][0]["callback_data"]

    # 2. User 1 ส่งคำขอ B (แทนที่ A ในฐานะ pending action ล่าสุดของ User 1)
    agent.pending_action = pending_b
    await service.handle_update({
        "message": {
            "message_id": 102,
            "chat": {"id": group_chat_id, "type": "group"},
            "from": {"id": user1_id, "first_name": "User 1"},
            "text": "แจ้งไฟดับ รายการ B",
        }
    })
    msg2_markup = mock_client.sent_messages[-1][2]
    assert msg2_markup is not None
    cb_b = msg2_markup["inline_keyboard"][0][0]["callback_data"]

    # 3. User 2 กดปุ่มยืนยันของข้อความ 1 (รายการ A) -> ต้องถูก REJECT ทันที (cross-user)
    await service.handle_update({
        "callback_query": {
            "id": "q_u2_msg1",
            "data": cb_a,
            "from": {"id": user2_id, "first_name": "User 2"},
            "message": {"message_id": 101, "chat": {"id": group_chat_id}},
        }
    })
    assert len(agent.confirmed_ids) == 0  # B ต้องไม่ถูก submit!
    assert "ไม่มีสิทธิ์" in str(mock_client.answered_callbacks[-1][1])

    # 4. User 1 กดปุ่มยืนยันของข้อความ 1 (รายการ A ที่ถูกแทนที่ด้วย B แล้ว) -> ต้องถูก REJECT (stale)
    await service.handle_update({
        "callback_query": {
            "id": "q_u1_msg1",
            "data": cb_a,
            "from": {"id": user1_id, "first_name": "User 1"},
            "message": {"message_id": 101, "chat": {"id": group_chat_id}},
        }
    })
    assert len(agent.confirmed_ids) == 0  # B ต้องไม่ถูก submit!
    assert "แทนที่หรือหมดอายุ" in str(mock_client.answered_callbacks[-1][1])

    # 5. User 1 กดปุ่มยืนยันของข้อความ 2 (รายการ B ที่เป็นรายการปัจจุบัน) -> สำเร็จ!
    await service.handle_update({
        "callback_query": {
            "id": "q_u1_msg2",
            "data": cb_b,
            "from": {"id": user1_id, "first_name": "User 1"},
            "message": {"message_id": 102, "chat": {"id": group_chat_id}},
        }
    })
    assert len(agent.confirmed_ids) == 1
    assert agent.confirmed_ids[0] == pending_b.pending_action_id  # รายการ B ถูก submit!
    assert "ยืนยันสำเร็จ" in str(mock_client.answered_callbacks[-1][1])

    # 6. User 1 กดปุ่มเดิมซ้ำ (replay) -> ต้องถูก REJECT
    await service.handle_update({
        "callback_query": {
            "id": "q_u1_msg2_replay",
            "data": cb_b,
            "from": {"id": user1_id, "first_name": "User 1"},
            "message": {"message_id": 102, "chat": {"id": group_chat_id}},
        }
    })
    assert len(agent.confirmed_ids) == 1  # ไม่ submit ซ้ำ
    assert "ถูกใช้งานไปแล้ว" in str(mock_client.answered_callbacks[-1][1])


@pytest.mark.asyncio
async def test_telegram_rejects_forged_unregistered_callback_data() -> None:
    """คำสั่ง callback แปลกปลอมหรือ raw action=confirm ที่ไม่ได้ลงทะเบียนต้องถูกปฏิเสธ (fail closed)"""
    agent = _StubAgent()
    agent.pending_action = _make_pending_action()
    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    await service.handle_update({
        "callback_query": {
            "id": "forged_query",
            "data": "action=confirm",
            "from": {"id": 999},
            "message": {"message_id": 50, "chat": {"id": 999}},
        }
    })
    assert len(agent.confirmed_ids) == 0
    assert "ไม่รองรับหรือหมดอายุ" in str(mock_client.answered_callbacks[-1][1])


# ---------------------------------------------------------------------------
# 9. Token Leak Prevention & Redaction tests (Review Blocker 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_api_client_redacts_synthetic_token_in_all_logs_and_exceptions() -> None:
    """ทดสอบการป้องกัน token หลุดใน httpx INFO logger, transport errors, response errors และ logger.exception"""
    import logging
    import httpx
    SYNTHETIC_TOKEN_FOR_REVIEW = "token_synthetic_secret_xyz_12345"

    captured_logs: list[str] = []
    class LogCatcher(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_logs.append(self.format(record))

    catcher = LogCatcher()
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.INFO)
    httpx_logger.addHandler(catcher)

    tg_logger = logging.getLogger("app.telegram")
    tg_logger.setLevel(logging.INFO)
    tg_logger.addHandler(catcher)

    root_logger = logging.getLogger()
    root_logger.addHandler(catcher)

    try:
        # 1. ทดสอบ Success path ด้วย MockTransport
        mock_transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        )
        client = TelegramApiClient(SYNTHETIC_TOKEN_FOR_REVIEW)
        # ทำการ inject client ที่ใช้ mock_transport
        async with httpx.AsyncClient(transport=mock_transport) as async_client:
            client._client = async_client
            await client.send_message(chat_id=123, text="ทดสอบความปลอดภัยของ log")

        # ตรวจสอบว่ามี log การยิง HTTP แต่ต้องไม่มี synthetic token เด็ดขาด
        assert len(captured_logs) > 0
        assert any("HTTP Request" in log_msg for log_msg in captured_logs)
        assert all(SYNTHETIC_TOKEN_FOR_REVIEW not in log_msg for log_msg in captured_logs)
        assert any("[REDACTED]" in log_msg for log_msg in captured_logs)

        # 2. ทดสอบ Transport error (ConnectError ที่มี URL)
        captured_logs.clear()
        def fail_connect(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"Connection failed for {req.url}", request=req)

        fail_transport = httpx.MockTransport(fail_connect)
        async with httpx.AsyncClient(transport=fail_transport) as fail_client:
            client._client = fail_client
            with pytest.raises(Exception) as exc_info:
                await client.send_message(chat_id=123, text="ส่งไม่สำเร็จ")

            # ตรวจสอบว่าข้อความ exception และ traceback ถูกปิดบัง token
            assert SYNTHETIC_TOKEN_FOR_REVIEW not in str(exc_info.value)
            assert "[REDACTED]" in str(exc_info.value)

        assert all(SYNTHETIC_TOKEN_FOR_REVIEW not in log_msg for log_msg in captured_logs)

        # 3. ทดสอบ Response error (500 Internal Server Error)
        captured_logs.clear()
        err_transport = httpx.MockTransport(
            lambda req: httpx.Response(
                500,
                text=f"Server error for bot{SYNTHETIC_TOKEN_FOR_REVIEW}/sendMessage",
                request=req,
            )
        )
        async with httpx.AsyncClient(transport=err_transport) as err_client:
            client._client = err_client
            with pytest.raises(Exception) as exc_info:
                await client.send_message(chat_id=123, text="ยิงเจอบั๊ก 500")

            assert SYNTHETIC_TOKEN_FOR_REVIEW not in str(exc_info.value)
            assert "[REDACTED]" in str(exc_info.value)

        assert all(SYNTHETIC_TOKEN_FOR_REVIEW not in log_msg for log_msg in captured_logs)

        # 4. ทดสอบ logger.exception ไม่หลุด token ลงใน traceback
        captured_logs.clear()
        try:
            raise RuntimeError(f"จำลอง error ที่มี URL: https://api.telegram.org/bot{SYNTHETIC_TOKEN_FOR_REVIEW}/sendMessage")
        except Exception:
            tg_logger.exception("จำลอง logger.exception สำหรับตรวจสอบความปลอดภัย")

        assert len(captured_logs) > 0
        assert all(SYNTHETIC_TOKEN_FOR_REVIEW not in log_msg for log_msg in captured_logs)
        assert any("[REDACTED]" in log_msg for log_msg in captured_logs)

    finally:
        httpx_logger.removeHandler(catcher)
        tg_logger.removeHandler(catcher)
        root_logger.removeHandler(catcher)


# ---------------------------------------------------------------------------
# 10. Choice Prompt Encoding, Ownership, and Byte Ceiling (Review Blocker 3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_choice_prompt_exact_prompt_id_and_value_preserved() -> None:
    """ทดสอบ ChoicePrompt ที่มี promptId ยาว 64 ตัวอักษร และข้อความภาษาไทยที่มี &, +, =:
    1. prompt_id ต้องไม่ถูกตัดทิ้งเป็น None
    2. value ต้องคงอักขระพิเศษไว้ครบถ้วน
    3. callback_data ต้องไม่เกิน 64 bytes
    4. ChatRequest ต้องรับค่าได้ถูกต้องโดยไม่ถูก reject
    """
    long_prompt_id = "prompt_id_exactly_64_characters_long_abcdefghijklmnopqrstuvwx123"
    assert len(long_prompt_id) == 64

    special_thai_value = "แจ้งไฟดับ & ซอย 55 + อาคาร B = ด่วนพิเศษ 🔥"

    choice_prompt = ChoicePrompt(
        prompt_id=long_prompt_id,
        question="กรุณาเลือกประเภทการแจ้งเหตุ",
        options=(
            ChoiceOption(label="เลือกแจ้งไฟดับ", value=special_thai_value),
            ChoiceOption(label="ยกเลิก", value="no"),
        ),
    )

    actions = format_actions(choice_prompt=choice_prompt)
    assert len(actions) == 2

    # 1. callback data ต้องยาว <= 64 bytes เสมอ
    pick_action = actions[0]
    assert len(pick_action.value.encode("utf-8")) <= 64

    # 2. เมื่อแยกวิเคราะห์กลับมา ต้องได้ prompt_id เดิมครบถ้วน และ value เดิมครบถ้วน
    parsed = parse_action_callback(pick_action.value)
    assert parsed["action"] == "pick"
    assert parsed["prompt_id"] == long_prompt_id
    assert parsed["value"] == special_thai_value

    # 3. ChatRequest ต้องสามารถสร้างได้อย่างถูกต้องโดยไม่ติด ValidationError
    chat_req = ChatRequest(
        conversation_id=uuid4(),
        message=parsed["value"],
        selected_prompt_id=parsed["prompt_id"],
        selected_value=parsed["value"],
    )
    assert chat_req.selected_prompt_id == long_prompt_id
    assert chat_req.selected_value == special_thai_value


@pytest.mark.asyncio
async def test_telegram_choice_real_service_path_and_cross_user_rejection() -> None:
    """ทดสอบ Choice callback ผ่าน real service path พร้อมการป้องกันการกดข้ามผู้ใช้ (cross-user)"""
    agent = _StubAgent()
    mock_client = _MockTelegramClient()
    bridge = TelegramBridge(agent)
    service = TelegramWebhookService(secret="sec", client=mock_client, bridge=bridge)

    chat_id = -123
    user1_id = 1111
    user2_id = 2222

    prompt_id = "select_category_step"
    val = "ไฟฟ้าขัดข้อง & สายไฟขาด"
    mock_response = {
        "conversationId": str(uuid4()),
        "message": "กรุณาเลือกรายการ",
        "choicePrompt": {
            "promptId": prompt_id,
            "options": [{"label": "แจ้งเหตุ", "value": val}],
        },
    }

    # Format ข้อความพร้อมผูก sender (user1)
    parts, reply_markup = format_telegram_chat_messages(
        mock_response,
        chat_id=chat_id,
        user_id=user1_id,
        registry=service.registry,
    )
    assert reply_markup is not None
    choice_btn_cb = reply_markup["inline_keyboard"][0][0]["callback_data"]
    assert len(choice_btn_cb.encode("utf-8")) <= 64

    # 1. User 2 กด choice ของ User 1 -> REJECT (cross-user)
    await service.handle_update({
        "callback_query": {
            "id": "q_choice_u2",
            "data": choice_btn_cb,
            "from": {"id": user2_id},
            "message": {"message_id": 201, "chat": {"id": chat_id}},
        }
    })
    assert "ไม่มีสิทธิ์" in str(mock_client.answered_callbacks[-1][1])
    assert len(agent.handled_requests) == 0

    # 2. User 1 กด choice ของตัวเอง -> สำเร็จ!
    await service.handle_update({
        "callback_query": {
            "id": "q_choice_u1",
            "data": choice_btn_cb,
            "from": {"id": user1_id},
            "message": {"message_id": 201, "chat": {"id": chat_id}},
        }
    })
    assert len(agent.handled_requests) == 1
    last_req = agent.handled_requests[-1]
    assert last_req.selected_prompt_id == prompt_id
    assert last_req.selected_value == val
