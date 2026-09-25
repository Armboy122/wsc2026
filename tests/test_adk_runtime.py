"""Real ADK runner with a fake model connection; no external API credentials."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import httpx
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

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import Citation, ToolName
from app.llm import LLMClient, ScriptedLLMAdapter
from app.llm.models import ToolDefinition
from app.plugins.oms.response import OmsResponsePolicy
from app.plugins.voc.flow import VocGuidedFlow
from app.plugins.voc.response import VocResponsePolicy
from app.plugins.tests.test_voc_intake import _catalog, _TEXT_ANSWERS
from app.runtime.adk_live import AdkLiveSession, forward_event, live_run_config
from app.agent.adk_agent import AdkKnowledgeTool
from app.tools.adk_tools import WscTools
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool
from app.tools.voc_tool import VocTool


class Evidence:
    def __init__(self):
        self.queries = []

    async def search(self, query, max_results):
        self.queries.append(query)
        return GroundedEvidence("หลักฐานจากเอกสาร", 1, (Citation(
            source_id="demo", title="คู่มือ", uri="knowledge://demo", snippet="หลักฐานจากเอกสาร",
        ),))


@pytest.fixture
def domain():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("catalog"):
            return httpx.Response(200, json=_catalog())
        if request.url.path.endswith("cases/lookup"):
            return httpx.Response(200, json={"case": {
                "vocNumber": "VOC-1", "status": "submitted", "journeyCode": "SERVICE_ISSUE",
                "createdAt": "2026-09-01T00:00:00Z", "updatedAt": "2026-09-01T00:00:00Z",
            }})
        if request.url.path.endswith("cases"):
            return httpx.Response(201, json={"caseId": "1", "vocNumber": "VOC-1", "keyCode": "KEY-1", "journeyCode": "SERVICE_ISSUE"})
        if request.method == "GET":
            return httpx.Response(200, json={
                "caNumber": "100000000003", "customerFound": True,
                "network": {"meterId": "M", "transformerId": "T", "feederId": "F"},
                "activeEvent": None, "recommendedAction": "CREATE_METER_EVENT",
            })
        return httpx.Response(201, json={"reportId": "OMS-1", "status": "RECEIVED", "message": "รับแจ้งแล้ว", "location": None})

    evidence = Evidence()
    oms = OmsTool(base_url="http://oms.test/", transport=httpx.MockTransport(handler))
    voc = VocTool(base_url="http://voc.test/", transport=httpx.MockTransport(handler))
    flow = VocGuidedFlow(voc, consent_notice_version="TEST")
    registry = ToolRegistry([KnowledgeTool(evidence), oms, voc], catalogue=(
        ToolDefinition(ToolName.OMS, "OMS", ("get_outage_by_ca", "prepare_outage_with_ca", "prepare_anonymous_outage")),
        ToolDefinition(ToolName.VOC, "VOC", ("list_categories", "prepare_case", "get_case")),
    ), response_policies=(OmsResponsePolicy(), VocResponsePolicy()))
    # An empty scripted planner fails if migration accidentally invokes it.
    agent = MainAgent(LLMClient(ScriptedLLMAdapter([])), registry, guided_flows=GuidedFlows((flow,)))
    adapter = WscTools(agent, uuid4(), has_display=True)
    yield SimpleNamespace(agent=agent, adapter=adapter, evidence=evidence, requests=requests, flow=flow)
    oms.close()
    voc.close()


async def call(adapter, name, args, state, *, turn=None):
    tool = next(t for t in adapter.definitions() if t.name == name)
    session = SimpleNamespace(events=[Event(id=turn or str(uuid4()), author="user",
        input_transcription=types.Transcription(text="คำพูดผู้ใช้", finished=True))])
    return await tool.run_async(args=args, tool_context=SimpleNamespace(state=state, session=session))


@pytest.mark.asyncio
async def test_knowledge_oms_voc_share_conversation_without_legacy_planner(domain):
    state = {}
    responses = [
        await call(domain.adapter, "knowledge_tool_search", {"query": "ขอใช้ไฟใหม่"}, state),
        await call(domain.adapter, "knowledge_tool_search", {"query": "ขอใช้ไฟใหม่ นิติบุคคลใช้เอกสารอะไร"}, state),
        await call(domain.adapter, "oms_tool_get_outage_by_ca", {"caNumber": "100000000003"}, state),
        await call(domain.adapter, "voc_tool_get_case", {"vocId": "VOC-1", "trackingKey": "KEY-1"}, state),
    ]
    assert {r["conversationId"] for r in responses} == {str(domain.adapter.conversation_id)}
    assert all(r["toolResults"][0]["status"] == "success" for r in responses)
    assert responses[0]["citations"][0]["sourceId"] == "demo"
    assert responses[-1]["toolResults"][0]["simulation"] is True
    assert len(domain.evidence.queries) == 2
    assert not domain.agent._conversations.messages_for(domain.adapter.conversation_id)


@pytest.mark.asyncio
async def test_prepare_confirm_once_and_cross_session_isolation(domain):
    state = {}
    payload = {"description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678"}
    # All supplied input goes straight into the existing preparation path.
    prepared = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", payload, state)
    assert prepared["pendingAction"]["status"] == "pending_confirmation"
    assert prepared["choicePrompt"] is None
    assert not domain.requests  # prepare never writes externally
    assert prepared["pendingAction"]["idempotencyKey"] == "[redacted]"
    other = WscTools(domain.agent, uuid4(), has_display=True)
    denied = await call(other, "pea_confirm_pending_action", {"confirmationNote": "ยืนยัน"}, {})
    assert denied["error"]["code"] == "no_pending_action"
    confirmed = await call(domain.adapter, "pea_confirm_pending_action", {"confirmationNote": "ยืนยัน"}, state)
    assert confirmed["pendingAction"]["status"] == "submitted"
    again = await call(domain.adapter, "pea_confirm_pending_action", {"confirmationNote": "ยืนยัน"}, state)
    assert again["error"]["code"] == "no_pending_action"
    assert len(domain.requests) == 1
    trace = domain.agent.get_trace(UUID(confirmed["traceId"]))
    assert [e.sequence for e in trace.events] == list(range(1, len(trace.events) + 1))


@pytest.mark.asyncio
async def test_missing_input_rejection_and_prepare_allowlist(domain):
    state = {}
    incomplete = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", {"description": "ไฟดับ"}, state)
    assert incomplete["error"]["code"] == "invalid_input"
    assert incomplete["missingFields"] == ["contactPhone", "location"]
    assert not domain.requests
    names = {t.name for t in domain.adapter.definitions()}
    assert not any("submit" in name or "prepare_case" in name for name in names)
    denied = await call(domain.adapter, "oms_tool_prepare_outage_with_ca", {
        "caNumber": "100000000003", "description": "ไฟดับ",
    }, state)
    assert denied["error"]["code"] == "action_conflict"
    prepared = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", {
        "description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678",
    }, state)
    denied_new = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", {
        "description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678",
    }, state)
    assert denied_new["error"]["code"] == "action_conflict"
    rejected = await call(domain.adapter, "pea_reject_pending_action", {"reason": "ยกเลิก"}, state)
    assert rejected["pendingAction"]["status"] == "rejected"
    with pytest.raises(RuntimeError):
        await domain.agent.confirm_pending_action(UUID(prepared["pendingAction"]["pendingActionId"]))
    assert not domain.requests


@pytest.mark.asyncio
async def test_model_cannot_prepare_and_confirm_in_same_user_turn(domain):
    state = {}
    await call(domain.adapter, "oms_tool_prepare_anonymous_outage", {
        "description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678",
    }, state, turn="original-request")
    response = await call(domain.adapter, "pea_confirm_pending_action", {
        "confirmationNote": "ยืนยัน",
    }, state, turn="original-request")
    assert response["error"]["code"] == "confirmation_required"
    assert not domain.requests


@pytest.mark.asyncio
async def test_existing_http_decision_does_not_leave_voice_pending_stuck(domain):
    state = {}
    args = {"description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678"}
    prepared = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", args, state)
    # Same domain method used by the existing HTTP confirmation endpoint.
    await domain.agent.confirm_pending_action(UUID(prepared["pendingAction"]["pendingActionId"]))
    next_request = await call(domain.adapter, "oms_tool_prepare_anonymous_outage", args, state)
    assert next_request["pendingAction"]["status"] == "pending_confirmation"
    assert next_request["pendingAction"]["pendingActionId"] != prepared["pendingAction"]["pendingActionId"]


@pytest.mark.asyncio
async def test_voc_intake_retains_catalog_and_explicit_consent(domain):
    state = {}
    response = await call(domain.adapter, "voc_intake", {"message": "ร้องเรียนบริการ"}, state)
    for _ in range(30):
        prompt = response.get("choicePrompt")
        if not prompt:
            break
        assert not any(r.url.path.endswith("cases") for r in domain.requests)
        options = prompt["options"]
        answer = options[0]["label"] if options else _TEXT_ANSWERS.get(prompt["promptId"], "ข้อมูลสำหรับทดสอบ")
        if prompt["promptId"] == "voc_ca_number":
            answer = "ไม่มี"
        response = await call(domain.adapter, "voc_intake", {"message": answer}, state)
    assert response.get("pendingAction"), response
    assert not domain.agent._conversations.messages_for(domain.adapter.conversation_id)
    assert not any(r.url.path.endswith("cases") for r in domain.requests)


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
                      ("search_knowledge", {"query": "ขอใช้ไฟ"}))
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
async def test_real_adk_runner_dispatches_knowledge_returns_audio_and_keeps_session(domain):
    connection = Connection()
    service = InMemorySessionService()
    await service.create_session(app_name="test", user_id="user", session_id="session")
    runner = Runner(
        app_name="test",
        agent=Agent(
            name="pea", model=LiveModel(connection),
            tools=[AdkKnowledgeTool(KnowledgeTool(domain.evidence))],
        ),
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
    assert len(domain.evidence.queries) == 2
    assert len(connection.responses) == 2
    assert all(c.parts[0].function_response.response["citations"] for c in connection.responses)
    saved = await service.get_session(app_name="test", user_id="user", session_id="session")
    assert saved is not None
    assert len(saved.events) >= 4
    assert any(e.content and any(p.inline_data for p in e.content.parts) for e in events)


@pytest.mark.asyncio
async def test_socket_cleanup_and_provider_error_are_isolated(domain):
    live = AdkLiveSession(
        api_key="test", model="fake", voice="Puck", knowledge_tool=KnowledgeTool(domain.evidence)
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
        api_key="test", model="fake", voice="Puck", knowledge_tool=KnowledgeTool(domain.evidence)
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


@pytest.mark.asyncio
async def test_adk_state_persists_pending_id_until_next_spoken_turn(domain):
    connection = Connection([
        ("oms_tool_prepare_anonymous_outage", {"description": "ไฟดับ", "location": "หาดใหญ่", "contactPhone": "0812345678"}),
        ("pea_confirm_pending_action", {"confirmationNote": "ยืนยัน"}),
    ])
    service = InMemorySessionService()
    await service.create_session(app_name="test", user_id="user", session_id="session")
    runner = Runner(app_name="test", agent=Agent(name="pea", model=LiveModel(connection), tools=domain.adapter.definitions()), session_service=service)
    queue = LiveRequestQueue()
    queue.send_realtime(types.Blob(data=b"\x00\x00", mime_type="audio/pcm;rate=16000"))
    async with asyncio.timeout(5):
        async for event in runner.run_live(user_id="user", session_id="session", live_request_queue=queue, run_config=live_run_config("Puck")):
            if event.turn_complete:
                if len(connection.audio) == 1:
                    saved = await service.get_session(app_name="test", user_id="user", session_id="session")
                    assert saved is not None
                    assert saved.state["wsc_pending_action_id"]
                    assert not domain.requests
                    queue.send_realtime(types.Blob(data=b"\x01\x00", mime_type="audio/pcm;rate=16000"))
                else:
                    queue.close()
    assert connection.responses[-1].parts[0].function_response.response["pendingAction"]["status"] == "submitted"
    assert len(domain.requests) == 1


@pytest.mark.asyncio
async def test_slow_operational_request_does_not_block_audio_loop(domain):
    import threading
    started, release = threading.Event(), threading.Event()
    tool = domain.agent._tools._tools[ToolName.OMS]
    original = tool._run

    def slow(action, value):
        started.set()
        assert release.wait(2)
        return original(action, value)

    tool._run = slow
    task = asyncio.create_task(call(domain.adapter, "oms_tool_get_outage_by_ca", {"caNumber": "100000000003"}, {}))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        # This coroutine can run while the synchronous HTTP operation is waiting.
        assert not task.done()
        release.set()
        result = await asyncio.wait_for(task, 1)
        assert result["toolResults"][0]["status"] == "success"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


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
    monkeypatch.setattr(live, "get_knowledge_tool", lambda: object())
    monkeypatch.setattr(live, "load_settings", lambda: Settings(gemini_api_key="test"))

    with TestClient(app).websocket_connect("/ws/live") as websocket:
        assert websocket.receive_json()["type"] == "session.ready"

    assert len(selected) == 1
    assert "knowledge_tool" in selected[0]
    assert not hasattr(Settings, "voice_runtime")
