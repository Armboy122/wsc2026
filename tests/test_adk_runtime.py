"""Real ADK runner with a fake model connection; no external API credentials."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import WebSocket

pytest.importorskip("google.adk")

from google.adk.agents import Agent
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import PrivateAttr

from app.runtime.adk_live import AdkLiveSession, forward_event, live_run_config
from app.agent.adk_agent import AdkKnowledgeTool, create_adk_agent
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.service import KnowledgeDocumentService




ALPHA_MARKDOWN = "# บริการอัลฟ่า\n\n## ขั้นตอน\n\nยื่นคำขอที่สำนักงาน PEA\n"


@pytest.fixture
def knowledge_service(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "alpha.md").write_text(ALPHA_MARKDOWN, encoding="utf-8")
    (source / "beta.md").write_text("# บริการบีต้า\n\nเนื้อหาบีต้า\n", encoding="utf-8")
    return KnowledgeDocumentService(KnowledgeCatalog(source, alias_root=tmp_path / "aliases"))


class Wire:
    def __init__(self):
        self.events, self.audio = [], []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def accept(self): pass
    async def receive(self): return await self.incoming.get()
    async def send_json(self, event): self.events.append(event)
    async def send_bytes(self, data): self.audio.append(data)
    async def close(self): self.closed = True


@pytest.mark.asyncio
async def test_event_mapping_audio_interruption_transcripts_and_no_thoughts():
    wire = Wire()
    await forward_event(cast(WebSocket, wire), Event(author="pea_one_agent", partial=True, content=types.Content(parts=[
        types.Part(text="hidden reasoning", thought=True),
        types.Part(inline_data=types.Blob(data=b"\x00\x01", mime_type="audio/pcm;rate=24000")),
    ]), output_transcription=types.Transcription(text="สวัสดี", finished=False)))
    await forward_event(cast(WebSocket, wire), Event(author="pea_one_agent", interrupted=True, content=types.Content(parts=[
        types.Part(inline_data=types.Blob(data=b"stale", mime_type="audio/pcm;rate=24000")),
    ])))
    await forward_event(cast(WebSocket, wire), Event(author="pea_one_agent", turn_complete=True,
        output_transcription=types.Transcription(text="สวัสดีครับ", finished=True)))
    assert wire.audio == [b"\x00\x01"]
    assert wire.events[1] == {"type": "audio.interrupted"}
    assert wire.events[2]["replace"] is True
    assert wire.events[-1] == {"type": "turn.complete"}
    assert "hidden" not in str(wire.events)
    with pytest.raises(RuntimeError):
        await forward_event(cast(WebSocket, wire), Event(author="pea_one_agent", error_code="500", error_message="SECRET"))
    assert "SECRET" not in str(wire.events)


class Connection(BaseLlmConnection):
    def __init__(self, plans=None):
        self.events = asyncio.Queue()
        self.audio, self.responses = [], []
        self.closed = False
        self.plans = plans

    async def send_history(self, history): pass

    async def send_realtime(self, blob):
        self.audio.append(blob)
        name, args = (self.plans[len(self.audio) - 1] if self.plans else
                      ("get_knowledge_documents", {"source_ids": ["alpha.md"]}))
        await self.events.put(LlmResponse(input_transcription=types.Transcription(text="ขอใช้ไฟ", finished=True)))
        await self.events.put(LlmResponse(content=types.Content(role="model", parts=[types.Part(
            function_call=types.FunctionCall(id=f"call-{len(self.audio)}", name=name, args=args),
        )])))

    async def send_content(self, content):
        self.responses.append(content)
        await self.events.put(LlmResponse(content=types.Content(role="model", parts=[types.Part(
            inline_data=types.Blob(data=b"\x00\x01", mime_type="audio/pcm;rate=24000"),
        )]), partial=True))
        await self.events.put(LlmResponse(turn_complete=True))

    async def receive(self):
        while not self.closed:
            event = await self.events.get()
            if event is None:
                return
            yield event

    async def close(self):
        self.closed = True
        await self.events.put(None)


class LiveModel(BaseLlm):
    _connection: Connection = PrivateAttr()

    def __init__(self, connection):
        super().__init__(model="fake-live")
        self._connection = connection

    @asynccontextmanager
    async def connect(self, llm_request):
        yield self._connection

    async def generate_content_async(self, *args, **kwargs):
        raise AssertionError("Must use Live")
        yield


@pytest.mark.asyncio
async def test_real_adk_runner_returns_selected_documents_into_same_live_session(
    knowledge_service, monkeypatch
):
    from google.genai import models as genai_models

    generative_calls = []

    def forbidden(*args, **kwargs):
        generative_calls.append(kwargs)
        raise AssertionError("Knowledge must not call a generative provider")

    monkeypatch.setattr(genai_models.Models, "generate_content", forbidden)
    monkeypatch.setattr(genai_models.AsyncModels, "generate_content", forbidden)
    connection = Connection()
    service = InMemorySessionService()
    await service.create_session(app_name="test", user_id="user", session_id="session")
    knowledge_tool = AdkKnowledgeTool(knowledge_service)
    runner = Runner(
        app_name="test",
        agent=Agent(name="pea", model=LiveModel(connection), tools=[knowledge_tool]),
        session_service=service,
    )
    queue = LiveRequestQueue()
    queue.send_realtime(types.Blob(data=b"\x00\x00", mime_type="audio/pcm;rate=16000"))
    events = []
    async with asyncio.timeout(10):
        async for event in runner.run_live(user_id="user", session_id="session", live_request_queue=queue, run_config=live_run_config("Puck")):
            events.append(event)
            if event.turn_complete:
                if len(connection.audio) == 1:
                    queue.send_realtime(types.Blob(data=b"\x01\x00", mime_type="audio/pcm;rate=16000"))
                else:
                    queue.close()
    assert len(connection.audio) == 2
    # Each tool result goes back over the same Live connection, not to another model.
    assert len(connection.responses) == 2
    for content in connection.responses:
        response = content.parts[0].function_response
        assert response.name == "get_knowledge_documents"
        assert response.response["status"] == "success"
        assert response.response["documents"] == [{
            "sourceId": "alpha.md",
            "title": "บริการอัลฟ่า",
            "uri": "knowledge://source/alpha.md",
            "content": ALPHA_MARKDOWN,
        }]
        assert response.response["sources"][0]["sourceId"] == "alpha.md"
    assert generative_calls == []
    saved = await service.get_session(app_name="test", user_id="user", session_id="session")
    assert saved is not None
    assert len(saved.events) >= 4
    assert any(e.content and any(p.inline_data for p in e.content.parts) for e in events)


@pytest.mark.asyncio
async def test_invalid_model_selection_returns_safe_failure_into_same_live_session(knowledge_service):
    connection = Connection([
        ("get_knowledge_documents", {"source_ids": ["../secrets.md"]}),
    ])
    service = InMemorySessionService()
    await service.create_session(app_name="test", user_id="user", session_id="session")
    runner = Runner(
        app_name="test",
        agent=Agent(name="pea", model=LiveModel(connection), tools=[AdkKnowledgeTool(knowledge_service)]),
        session_service=service,
    )
    queue = LiveRequestQueue()
    queue.send_realtime(types.Blob(data=b"\x00\x00", mime_type="audio/pcm;rate=16000"))
    async with asyncio.timeout(10):
        async for event in runner.run_live(user_id="user", session_id="session", live_request_queue=queue, run_config=live_run_config("Puck")):
            if event.turn_complete:
                queue.close()
    response = connection.responses[0].parts[0].function_response.response
    assert response["status"] == "error"
    assert response["error"]["code"] == "invalid_input"
    assert "documents" not in response


def test_live_agent_instruction_carries_compact_catalog_and_one_tool(knowledge_service):
    from google.genai import Client

    client = Client(api_key="test")
    try:
        tool = AdkKnowledgeTool(knowledge_service)
        agent = create_adk_agent(model="fake-live", client=client, knowledge_tool=tool)
    finally:
        client.close()
    assert agent.tools == [tool]
    assert '"sourceId":"alpha.md"' in agent.instruction
    assert '"title":"บริการอัลฟ่า"' in agent.instruction
    assert "get_knowledge_documents" in agent.instruction
    # The catalog is metadata only; document bodies are fetched through the tool.
    assert "ยื่นคำขอที่สำนักงาน PEA" not in agent.instruction


@pytest.mark.asyncio
async def test_socket_cleanup_and_provider_error_are_isolated(knowledge_service):
    live = AdkLiveSession(
        api_key="test", model="fake", voice="Puck", knowledge_service=knowledge_service
    )
    wire = Wire()

    async def fail(**kwargs):
        raise RuntimeError("SECRET_API_KEY")
        yield

    live._runner = cast(Runner, SimpleNamespace(run_live=fail))
    await live.serve(cast(WebSocket, wire))
    assert wire.closed
    assert wire.events[-1]["type"] == "error"
    assert "SECRET" not in str(wire.events)
    assert await live._service.get_session(app_name="wsc_voice", user_id=live._user_id, session_id=live._id) is None
    # A second socket can still connect and close cleanly.
    second = AdkLiveSession(
        api_key="test", model="fake", voice="Puck", knowledge_service=knowledge_service
    )
    other = Wire()
    await other.incoming.put({"type": "websocket.disconnect", "code": 1000})

    async def hold(**kwargs):
        await asyncio.Event().wait()
        yield

    second._runner = cast(Runner, SimpleNamespace(run_live=hold))
    await second.serve(cast(WebSocket, other))
    assert other.closed and other.events == [{"type": "session.ready"}]
    assert second._id != live._id


def test_live_run_config_preserves_audio_interruption_and_resumption_contract() -> None:
    config = live_run_config("Puck")

    assert config.streaming_mode.value == "bidi"
    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.speech_config is not None
    assert config.speech_config.voice_config is not None
    assert config.speech_config.voice_config.prebuilt_voice_config is not None
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"
    assert config.input_audio_transcription == types.AudioTranscriptionConfig()
    assert config.output_audio_transcription == types.AudioTranscriptionConfig()
    assert config.realtime_input_config is not None
    assert (
        config.realtime_input_config.activity_handling
        == types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    )
    assert (
        config.realtime_input_config.turn_coverage
        == types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
    )
    assert config.session_resumption == types.SessionResumptionConfig()


@pytest.mark.parametrize("audio", [b"", b"\x00", b"\x00" * 32002])
@pytest.mark.asyncio
async def test_browser_rejects_invalid_pcm16_frames(audio: bytes) -> None:
    wire, queue = Wire(), LiveRequestQueue()
    await wire.incoming.put({"type": "websocket.receive", "bytes": audio})

    with pytest.raises(ValueError, match="Invalid PCM16 frame"):
        await AdkLiveSession._receive_browser(
            cast(AdkLiveSession, object()), cast(WebSocket, wire), queue
        )


@pytest.mark.asyncio
async def test_browser_accepts_maximum_pcm16_frame() -> None:
    audio = b"\x00" * 32000
    wire, queue = Wire(), LiveRequestQueue()
    await wire.incoming.put({"type": "websocket.receive", "bytes": audio})
    task = asyncio.create_task(
        AdkLiveSession._receive_browser(
            cast(AdkLiveSession, object()), cast(WebSocket, wire), queue
        )
    )

    try:
        packet = await asyncio.wait_for(queue.get(), 1)
        assert packet.blob is not None
        assert packet.blob.data is not None
        assert len(packet.blob.data) == 32000
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_binary_audio_and_json_cannot_invoke_writes():
    wire, queue = Wire(), LiveRequestQueue()
    await wire.incoming.put({"type": "websocket.receive", "text": '{"function":"pea_confirm_pending_action"}'})
    await wire.incoming.put({"type": "websocket.receive", "bytes": b"\x00\x01"})
    task = asyncio.create_task(AdkLiveSession._receive_browser(
        cast(AdkLiveSession, object()), cast(WebSocket, wire), queue
    ))
    packet = await asyncio.wait_for(queue.get(), 1)
    assert packet.blob is not None
    assert packet.blob.data == b"\x00\x01" and packet.blob.mime_type == "audio/pcm;rate=16000"
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_fastapi_websocket_always_uses_adk_without_runtime_selector(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import Settings
    from app.api import live

    selected = []
    monkeypatch.setenv("VOICE_RUNTIME", "legacy")

    class Session:
        def __init__(self, **kwargs):
            selected.append(kwargs)

        async def serve(self, websocket):
            await websocket.accept()
            await websocket.send_json({"type": "session.ready"})
            await websocket.close()

    monkeypatch.setattr("app.runtime.adk_live.AdkLiveSession", Session)
    monkeypatch.setattr(live, "get_knowledge_service", lambda: object())
    monkeypatch.setattr(live, "load_settings", lambda: Settings(gemini_api_key="test"))

    with TestClient(app).websocket_connect("/ws/live") as websocket:
        assert websocket.receive_json()["type"] == "session.ready"

    assert len(selected) == 1
    assert "knowledge_service" in selected[0]
    assert not hasattr(Settings, "voice_runtime")
