"""Regression tests for the Live session transport boundary."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.live.gemini_live import (
    _AUDIO_QUEUE_SIZE,
    PROGRESS_ACKNOWLEDGEMENT_TEXT,
    GeminiLiveSession,
    live_connect_config,
)


def test_live_instruction_speaks_a_useful_summary_without_internal_jargon() -> None:
    instruction = live_connect_config("Puck").system_instruction

    assert isinstance(instruction, str)
    assert "ห้ามตอบเพียง" in instruction
    assert "ไม่เกิน 6 ข้อ" in instruction
    assert "3–5 ประเด็น" in instruction
    assert "ห้ามอ่าน URL" in instruction
    assert "หมายเลข citation" in instruction
    assert "30–45 วินาที" in instruction
    assert "ความหมาย ตัวเลข เงื่อนไข" in instruction
    assert "หากคำตอบกำกวมต้องถามย้ำ" in instruction
    assert "ทุกคำขอที่ต้องใช้ข้อมูล" in instruction
    assert "ยกเว้นเพียงคำทักทาย" in instruction
    assert "ห้ามกล่าวคำว่า MainAgent" in instruction


class FakeWebSocket:
    def __init__(self) -> None:
        self.json_events: list[dict[str, object]] = []
        self.binary_events: list[bytes] = []

    async def send_json(self, event: dict[str, object]) -> None:
        self.json_events.append(event)

    async def send_bytes(self, audio: bytes) -> None:
        self.binary_events.append(audio)


class BurstWebSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.received = 0
        self._hold = asyncio.Event()

    async def receive(self) -> dict[str, object]:
        if self._chunks:
            self.received += 1
            return {"type": "websocket.receive", "bytes": self._chunks.pop(0)}
        await self._hold.wait()
        return {"type": "websocket.disconnect", "code": 1000}


class SuccessiveTurnSession:
    """Mimics google-genai: each receive() iterator ends at turn_complete."""

    def __init__(self) -> None:
        self.calls = 0
        self._hold = asyncio.Event()

    async def receive(self):
        self.calls += 1
        if self.calls <= 2:
            yield SimpleNamespace(
                server_content=SimpleNamespace(
                    interrupted=False,
                    input_transcription=None,
                    output_transcription=None,
                    model_turn=None,
                    turn_complete=True,
                ),
                tool_call=None,
            )
            return
        await self._hold.wait()
        if False:  # pragma: no cover - keeps this as an async generator
            yield None


@pytest.mark.asyncio
async def test_browser_audio_queue_keeps_only_the_latest_300ms() -> None:
    chunks = [bytes([index]) for index in range(5)]
    websocket = BurstWebSocket(chunks)
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_AUDIO_QUEUE_SIZE)
    live = object.__new__(GeminiLiveSession)

    task = asyncio.create_task(live._receive_browser(websocket, queue))
    try:
        for _ in range(20):
            if websocket.received == len(chunks):
                break
            await asyncio.sleep(0)
        assert queue.maxsize == 3
        assert [queue.get_nowait() for _ in range(queue.qsize())] == chunks[-3:]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_receive_gemini_reenters_receive_for_successive_complete_turns() -> None:
    session = SuccessiveTurnSession()
    websocket = FakeWebSocket()
    live = object.__new__(GeminiLiveSession)

    task = asyncio.create_task(live._receive_gemini(websocket, session))
    try:
        for _ in range(20):
            if len(websocket.json_events) == 2:
                break
            await asyncio.sleep(0)
        assert session.calls >= 2
        assert websocket.json_events == [
            {"type": "turn.complete"},
            {"type": "turn.complete"},
        ]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class RecordingBridge:
    def __init__(self, websocket: FakeWebSocket, session: FakeLiveSession | None = None) -> None:
        self.websocket = websocket
        self.session = session
        self.events_at_call_time: list[dict[str, object]] = []
        self.tool_responses_at_call_time: list[object] = []

    async def handle_text(self, message: str) -> dict[str, object]:
        self.events_at_call_time = list(self.websocket.json_events)
        if self.session is not None:
            self.tool_responses_at_call_time = list(self.session.tool_responses)
        await asyncio.sleep(0.001)
        return {"message": "คำตอบจาก MainAgent", "conversationId": "conv-123"}

    async def confirm_current(self, note: str | None) -> dict[str, object]:
        self.events_at_call_time = list(self.websocket.json_events)
        if self.session is not None:
            self.tool_responses_at_call_time = list(self.session.tool_responses)
        await asyncio.sleep(0.001)
        return {"pendingAction": {"status": "submitted"}}


class FakeLiveSession:
    def __init__(self) -> None:
        self.tool_responses: list[object] = []

    async def send_tool_response(self, *, function_responses: list[object]) -> None:
        self.tool_responses.append(function_responses)


@pytest.mark.asyncio
async def test_respond_to_calls_emits_progress_before_bridge_completion_and_tool_response() -> None:
    websocket = FakeWebSocket()
    session = FakeLiveSession()
    live = object.__new__(GeminiLiveSession)
    bridge = RecordingBridge(websocket, session)
    live._bridge = bridge

    call = SimpleNamespace(id="call-chat-1", name="pea_agent_chat", args={"message": "ตรวจสอบค่าไฟ"})
    await live._respond_to_calls(websocket, session, [call])

    # 1. While bridge was running, assistant.progress had already been sent
    assert bridge.events_at_call_time == [
        {"type": "state", "state": "thinking"},
        {"type": "assistant.progress", "text": PROGRESS_ACKNOWLEDGEMENT_TEXT},
    ]
    # At call time, tool response was NOT yet sent
    assert len(bridge.tool_responses_at_call_time) == 0

    # 2. Final event ordering
    assert websocket.json_events == [
        {"type": "state", "state": "thinking"},
        {"type": "assistant.progress", "text": PROGRESS_ACKNOWLEDGEMENT_TEXT},
        {
            "type": "agent.response",
            "operation": "chat",
            "response": {"message": "คำตอบจาก MainAgent", "conversationId": "conv-123"},
        },
    ]
    # 3. Tool response was sent after completion
    assert len(session.tool_responses) == 1
    assert session.tool_responses[0][0].name == "pea_agent_chat"


@pytest.mark.asyncio
async def test_respond_to_calls_does_not_emit_progress_for_confirmation() -> None:
    websocket = FakeWebSocket()
    session = FakeLiveSession()
    live = object.__new__(GeminiLiveSession)
    bridge = RecordingBridge(websocket)
    live._bridge = bridge

    call = SimpleNamespace(id="call-confirm-1", name="pea_confirm_pending_action", args={"confirmationNote": "ยืนยัน"})
    await live._respond_to_calls(websocket, session, [call])

    # No assistant.progress event emitted at all
    assert not any(event.get("type") == "assistant.progress" for event in websocket.json_events)
    assert websocket.json_events == [
        {"type": "state", "state": "thinking"},
        {
            "type": "agent.response",
            "operation": "confirm",
            "response": {"pendingAction": {"status": "submitted"}},
        },
    ]
    assert len(session.tool_responses) == 1
    assert session.tool_responses[0][0].name == "pea_confirm_pending_action"


@pytest.mark.asyncio
async def test_respond_to_calls_does_not_emit_progress_for_unknown_function() -> None:
    websocket = FakeWebSocket()
    session = FakeLiveSession()
    live = object.__new__(GeminiLiveSession)
    bridge = RecordingBridge(websocket)
    live._bridge = bridge

    call = SimpleNamespace(id="call-unknown-1", name="unsupported_function", args={})
    await live._respond_to_calls(websocket, session, [call])

    # No assistant.progress event emitted
    assert not any(event.get("type") == "assistant.progress" for event in websocket.json_events)
    assert len(websocket.json_events) == 2
    assert websocket.json_events[0] == {"type": "state", "state": "thinking"}
    assert websocket.json_events[1]["type"] == "agent.response"
    assert websocket.json_events[1]["operation"] == "unknown"
    assert len(session.tool_responses) == 1


@pytest.mark.asyncio
async def test_receive_gemini_does_not_emit_progress_when_no_tool_call_in_turn() -> None:
    session = SuccessiveTurnSession()
    websocket = FakeWebSocket()
    live = object.__new__(GeminiLiveSession)

    task = asyncio.create_task(live._receive_gemini(websocket, session))
    try:
        for _ in range(20):
            if len(websocket.json_events) == 2:
                break
            await asyncio.sleep(0)
        assert not any(event.get("type") == "assistant.progress" for event in websocket.json_events)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

