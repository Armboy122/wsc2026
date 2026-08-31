"""Regression tests for the Live session transport boundary."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.live.gemini_live import GeminiLiveSession


class FakeWebSocket:
    def __init__(self) -> None:
        self.json_events: list[dict[str, object]] = []
        self.binary_events: list[bytes] = []

    async def send_json(self, event: dict[str, object]) -> None:
        self.json_events.append(event)

    async def send_bytes(self, audio: bytes) -> None:
        self.binary_events.append(audio)


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
