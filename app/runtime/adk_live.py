"""Transport bridge between WSC's wire protocol and ADK bidirectional Live."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from app.agent.adk_agent import create_adk_agent
from app.agent.main_agent import MainAgent
from app.core.logging import get_logger
from app.tools.adk_tools import WscTools

logger = get_logger(__name__)
APP_NAME = "wsc_voice"
_ERROR = {"type": "error", "message": "โหมดเสียงไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"}


def live_run_config(voice: str) -> RunConfig:
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice),
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=False),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
        session_resumption=types.SessionResumptionConfig(),
    )


class AdkLiveSession:
    """One browser connection; SessionService can be replaced by persistent storage.

    As in legacy, a new browser connection starts a new conversation. ADK handles
    upstream Live reconnection within that connection; there is no custom retry
    or tool-response loop here. No raw ADK events or provider errors reach clients.
    """

    def __init__(self, *, api_key: str, model: str, voice: str, agent: MainAgent,
                 has_display: bool = True, session_service: BaseSessionService | None = None) -> None:
        self._id = str(uuid4())
        self._user_id = str(uuid4())
        self._agent = agent
        self._client = genai.Client(api_key=api_key, vertexai=False,
                                    http_options=types.HttpOptions(api_version="v1alpha"))
        self._service = session_service or InMemorySessionService()
        self._tools = WscTools(agent, UUID(self._id), has_display=has_display)
        self._runner = Runner(
            app_name=APP_NAME,
            agent=create_adk_agent(model=model, client=self._client, tools=self._tools),
            session_service=self._service,
        )
        self._config = live_run_config(voice)

    async def serve(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue = LiveRequestQueue()
        tasks: set[asyncio.Task] = set()
        try:
            await self._service.create_session(
                app_name=APP_NAME, user_id=self._user_id, session_id=self._id,
            )
            # ADK exposes no setup-complete event. This signals input readiness;
            # upstream connection failures are sent as the existing error event.
            await websocket.send_json({"type": "session.ready"})
            tasks = {
                asyncio.create_task(self._receive_browser(websocket, queue)),
                asyncio.create_task(self._send_events(websocket, queue)),
            }
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except WebSocketDisconnect:
            logger.info("adk_live_browser_disconnected")
        except Exception:
            logger.error("adk_live_session_failed")
            with suppress(Exception):
                await websocket.send_json(_ERROR)
        finally:
            queue.close()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._agent.cancel_domain_intake(self._tools.conversation_id)
            with suppress(Exception):
                await self._service.delete_session(
                    app_name=APP_NAME, user_id=self._user_id, session_id=self._id,
                )
            with suppress(Exception):
                await self._client.aio.aclose()
            self._client.close()
            with suppress(Exception):
                await websocket.close()
            logger.info("adk_live_session_closed")

    async def _receive_browser(self, websocket: WebSocket, queue: LiveRequestQueue) -> None:
        while True:
            packet = await websocket.receive()
            if packet["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(packet.get("code", 1000))
            audio = packet.get("bytes")
            if audio is None:
                continue  # Browser JSON must never invoke tools or confirm writes.
            if not audio or len(audio) % 2 or len(audio) > 32000:
                raise ValueError("Invalid PCM16 frame")
            queue.send_realtime(types.Blob(data=audio, mime_type="audio/pcm;rate=16000"))

    async def _send_events(self, websocket: WebSocket, queue: LiveRequestQueue) -> None:
        async for event in self._runner.run_live(
            user_id=self._user_id, session_id=self._id,
            live_request_queue=queue, run_config=self._config,
        ):
            await forward_event(websocket, event)


async def forward_event(websocket: WebSocket, event: Event) -> None:
    if event.error_code:
        raise RuntimeError("ADK live provider failure")
    if event.interrupted:
        await websocket.send_json({"type": "audio.interrupted"})
    for transcription, role in (
        (event.input_transcription, "user"), (event.output_transcription, "assistant"),
    ):
        if transcription and transcription.text:
            await websocket.send_json({
                "type": f"transcript.{role}", "role": role,
                "text": transcription.text, "final": bool(transcription.finished),
                # ADK's final transcription is the accumulated text, not a delta.
                "replace": bool(transcription.finished),
            })
    for part in event.content.parts or () if event.content else ():
        if part.thought:
            continue
        if part.inline_data and part.inline_data.data and not event.interrupted:
            mime = part.inline_data.mime_type or ""
            if not mime.startswith("audio/pcm"):
                raise ValueError("Unsupported audio encoding")
            await websocket.send_bytes(part.inline_data.data)
        if part.function_call:
            await websocket.send_json({"type": "state", "state": "thinking"})
        if part.function_response:
            operation = {
                "pea_confirm_pending_action": "confirm", "pea_reject_pending_action": "reject",
            }.get(part.function_response.name, "chat")
            await websocket.send_json({"type": "agent.response", "operation": operation,
                                       "response": part.function_response.response})
    if event.turn_complete:
        await websocket.send_json({"type": "turn.complete"})
