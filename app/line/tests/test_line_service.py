"""พฤติกรรมปุ่มเริ่มแชทใหม่และปุ่มลิงก์ citation ของช่องทาง LINE"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.contracts import ChatResponse
from app.line.bridge import LineBridge
from app.line.service import LineWebhookService, format_chat_messages


class _StubGateway:
    """Gateway จำลองที่บันทึกว่าแต่ละข้อความมาจาก conversation ใหม่หรือเดิม"""

    def __init__(self) -> None:
        self.seen_conversation_ids: list[UUID | None] = []

    async def handle_chat(self, request: Any) -> ChatResponse:
        self.seen_conversation_ids.append(request.conversation_id)
        return ChatResponse(
            conversation_id=request.conversation_id or uuid4(),
            trace_id=uuid4(),
            message="ตอบกลับจากระบบจำลอง",
        )

    async def confirm_pending_action(self, pending_action_id: UUID, confirmation_note: str | None = None) -> Any:
        raise AssertionError("ไม่ควรถูกเรียกในเทสชุดนี้")

    async def reject_pending_action(self, pending_action_id: UUID, reason: str | None = None) -> Any:
        raise AssertionError("ไม่ควรถูกเรียกในเทสชุดนี้")


def _citations(*uris: str) -> list[dict[str, Any]]:
    return [
        {"sourceId": f"s{i}", "title": f"เอกสารอ้างอิงฉบับที่ {i} ชื่อยาวมากจนเกินยี่สิบตัวอักษร", "uri": uri, "snippet": "ข้อความ", "page": 1}
        for i, uri in enumerate(uris, start=1)
    ]


def test_new_chat_clears_conversation_and_pending_action() -> None:
    bridge = LineBridge(_StubGateway())
    user = "U123"

    first = asyncio.run(bridge.handle_chat(user, "สวัสดี"))
    assert first["pendingAction"] is None

    asyncio.run(bridge.start_new_chat(user))
    gateway = bridge._agent
    assert isinstance(gateway, _StubGateway)
    asyncio.run(bridge.handle_chat(user, "ถามใหม่"))
    # ข้อความหลังเริ่มใหม่ต้องไม่ส่ง conversation เดิมไป
    assert gateway.seen_conversation_ids[-1] is None


def test_citations_render_uri_buttons_and_new_chat_button() -> None:
    response = {
        "message": "คำตอบ",
        "citations": _citations("https://pea.example/doc1", "https://pea.example/doc2"),
        "pendingAction": None,
        "toolResults": [],
    }
    messages = format_chat_messages(response)
    templates = [m for m in messages if m.get("type") == "template"]
    assert templates, "ควรมี template ปุ่ม citation"
    actions = templates[-1]["template"]["actions"]
    uri_actions = [a for a in actions if a["type"] == "uri"]
    postbacks = [a for a in actions if a["type"] == "postback"]
    assert [a["uri"] for a in uri_actions] == ["https://pea.example/doc1", "https://pea.example/doc2"]
    assert all(a["data"] == "action=new_chat" for a in postbacks)
    assert all(len(a["label"]) <= 20 for a in actions)


def test_more_than_three_citations_keep_three_uri_buttons() -> None:
    response = {
        "message": "คำตอบ",
        "citations": _citations(*[f"https://pea.example/doc{i}" for i in range(1, 6)]),
        "pendingAction": None,
        "toolResults": [],
    }
    messages = format_chat_messages(response)
    templates = [m for m in messages if m.get("type") == "template"]
    actions = templates[-1]["template"]["actions"]
    uri_actions = [a for a in actions if a["type"] == "uri"]
    assert len(uri_actions) == 3
    assert len(actions) == 4  # 3 uri + เริ่มแชทใหม่


def test_non_http_citation_is_not_a_button() -> None:
    response = {
        "message": "คำตอบ",
        "citations": _citations("internal://doc1"),
        "pendingAction": None,
        "toolResults": [],
    }
    messages = format_chat_messages(response)
    templates = [m for m in messages if m.get("type") == "template"]
    # ไม่มีปุ่ม uri ที่ใช้ได้จึงไม่ควรส่ง template ปุ่มออกไป
    assert not templates


def test_service_handles_new_chat_postback() -> None:
    """postback action=new_chat ต้องล้าง state และตอบข้อความต้อนรับ"""

    sent: list[tuple[str, list[dict[str, Any]]]] = []

    class _Client:
        async def reply_message(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
            sent.append((reply_token, messages))

        async def push_message(self, user_id: str, messages: list[dict[str, Any]]) -> None:
            sent.append((user_id, messages))

        async def show_loading_indicator(self, user_id: str, seconds: int) -> None:
            return None

    async def scenario() -> None:
        gateway = _StubGateway()
        bridge = LineBridge(gateway)
        service = LineWebhookService(secret="s", client=_Client(), bridge=bridge)  # type: ignore[arg-type]
        await bridge.handle_chat("U1", "สวัสดี")
        await service.handle_events([
            {
                "type": "postback",
                "replyToken": "rt",
                "source": {"userId": "U1"},
                "postback": {"data": "action=new_chat"},
            }
        ])
        await bridge.handle_chat("U1", "ถามใหม่")
        assert gateway.seen_conversation_ids[-1] is None
        # ข้อความตอบ postback ต้องเป็นข้อความต้อนรับ
        reply = [m for _, batch in sent for m in batch]
        assert any("สวัสดีครับ" in m.get("text", "") for m in reply)

    asyncio.run(scenario())


def test_unknown_postback_fails_closed() -> None:
    assert format_chat_messages({"message": "x", "citations": [], "pendingAction": None, "toolResults": []})[0]["text"] == "x"


@pytest.mark.parametrize("label,limit", [("สั้น", 20), ("x" * 30, 20)])
def test_label_truncation(label: str, limit: int) -> None:
    from app.line.service import _truncate_button_label

    assert len(_truncate_button_label(label)) <= limit


def test_chat_reply_always_carries_new_chat_quick_reply() -> None:
    """ทุกคำตอบแชตต้องมี quickReply เริ่มแชทใหม่ แม้ไม่มี citation"""
    response = {"message": "คำตอบ", "citations": [], "pendingAction": None, "toolResults": []}
    messages = format_chat_messages(response)
    assert messages[-1]["quickReply"]["items"][0]["action"]["data"] == "action=new_chat"
