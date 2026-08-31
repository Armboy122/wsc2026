"""Regression tests for the Live session transport boundary."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.live.gemini_live import _AUDIO_QUEUE_SIZE, GeminiLiveSession, live_connect_config


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
