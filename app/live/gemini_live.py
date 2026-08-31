"""Gemini Live transport for one browser WebSocket and one VoiceBridge."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from app.core.logging import get_logger
from app.live.bridge import VoiceBridge, VoiceBridgeError
from app.live.models import MainAgentGateway

logger = get_logger(__name__)
_AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
_AUDIO_QUEUE_SIZE = 8
_SYSTEM_INSTRUCTION = """คุณเป็นเพียงส่วนติดต่อด้วยเสียงของ PEA One Agent ไม่ใช่แหล่งความจริงของ PEA
สำหรับทุกคำขอ PEA ต้องเรียก pea_agent_chat เพื่อส่งต่อให้ MainAgent เท่านั้น ห้ามสร้างข้อเท็จจริง,
แหล่งอ้างอิง, สถานะเรื่อง หรือผลการดำเนินการของ PEA ขึ้นเอง ให้รักษาข้อความและข้อเท็จจริงที่ MainAgent
คืนมาอย่างครบถ้วน หากมี pending action ให้พูดสรุปที่ MainAgent คืนมา แล้วถามผู้ใช้อย่างชัดเจนว่า
ต้องการยืนยันหรือปฏิเสธหรือไม่ เรียก pea_confirm_pending_action หรือ pea_reject_pending_action
เฉพาะเมื่อผู้ใช้ตอบชัดเจนเท่านั้น หากคำตอบกำกวม ต้องถามย้ำและห้ามเรียกฟังก์ชันตัดสินใจ
ห้ามขอ รับ หรือส่ง pending action id; action ถูกผูกกับเซสชันโดยระบบ และ VOC เป็นข้อมูลจำลอง."""


def live_connect_config(voice: str) -> types.LiveConnectConfig:
    """Return the fixed, Thai Gemini Live configuration for this MVP."""
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=_SYSTEM_INSTRUCTION,
        speech_config=types.SpeechConfig(
            language_code="th-TH",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            ),
        ),
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=False),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
        tools=[types.Tool(function_declarations=_function_declarations())],
    )


def _function_declarations() -> list[types.FunctionDeclaration]:
    """Expose only the three safe session-bound bridge operations."""
    return [
        types.FunctionDeclaration(
            name="pea_agent_chat",
            description="ส่งข้อความที่ผู้ใช้พูดไปยัง MainAgent ของ PEA",
            parameters_json_schema={
                "type": "object",
                "properties": {"message": {"type": "string", "description": "ข้อความของผู้ใช้"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        ),
        types.FunctionDeclaration(
            name="pea_confirm_pending_action",
            description="ยืนยันรายการที่กำลังรอในเซสชันนี้เท่านั้น",
            parameters_json_schema={
                "type": "object",
                "properties": {"confirmationNote": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        types.FunctionDeclaration(
            name="pea_reject_pending_action",
            description="ปฏิเสธรายการที่กำลังรอในเซสชันนี้เท่านั้น",
            parameters_json_schema={
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        ),
    ]


class GeminiLiveSession:
    """Run exactly one Gemini session, VoiceBridge, and audio queue per socket."""

    def __init__(self, *, api_key: str, model: str, voice: str, agent: MainAgentGateway) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._config = live_connect_config(voice)
        self._bridge = VoiceBridge(agent)

    async def serve(self, websocket: WebSocket) -> None:
        """Forward PCM and safe control events until a peer or sender stops."""
        await websocket.accept()
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_AUDIO_QUEUE_SIZE)
        tasks: set[asyncio.Task[None]] = set()
        try:
            async with self._client.aio.live.connect(model=self._model, config=self._config) as session:
                logger.info("gemini_live_session_connected")
                await websocket.send_json({"type": "session.ready"})
                tasks = {
                    asyncio.create_task(self._receive_browser(websocket, audio_queue)),
                    asyncio.create_task(self._send_microphone_audio(session, audio_queue)),
                    asyncio.create_task(self._receive_gemini(websocket, session)),
                }
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except WebSocketDisconnect:
            logger.info("gemini_live_browser_disconnected")
        except Exception:
            logger.error("gemini_live_session_failed")
            with suppress(Exception):
                await websocket.send_json({"type": "error", "message": "โหมดเสียงไม่พร้อมใช้งาน กรุณาลองใหม่อีกครั้ง"})
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(Exception):
                await websocket.close()
            logger.info("gemini_live_session_closed")

    async def _receive_browser(self, websocket: WebSocket, audio_queue: asyncio.Queue[bytes]) -> None:
        while True:
            packet = await websocket.receive()
            if packet["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(packet.get("code", 1000))
            audio = packet.get("bytes")
            if audio is None:
                continue  # Browser JSON can never trigger PEA actions.
            if audio_queue.full():
                with suppress(asyncio.QueueEmpty):
                    audio_queue.get_nowait()
                    logger.warning("gemini_live_stale_audio_dropped")
            with suppress(asyncio.QueueFull):
                audio_queue.put_nowait(audio)

    async def _send_microphone_audio(self, session: Any, audio_queue: asyncio.Queue[bytes]) -> None:
        while True:
            audio = await audio_queue.get()
            await session.send_realtime_input(audio=types.Blob(data=audio, mime_type=_AUDIO_MIME_TYPE))

    async def _receive_gemini(self, websocket: WebSocket, session: Any) -> None:
        # google-genai's receive() ends after each complete model turn.  Re-enter it
        # to preserve this WebSocket's VoiceBridge conversation across turns.
        while True:
            async for event in session.receive():
                content = event.server_content
                if content is not None:
                    if content.interrupted:
                        await websocket.send_json({"type": "audio.interrupted"})
                    await self._forward_transcripts(websocket, content)
                    for part in ((content.model_turn.parts or ()) if content.model_turn else ()):
                        inline_data = part.inline_data
                        if inline_data is not None and inline_data.data:
                            await websocket.send_bytes(inline_data.data)
                    if content.turn_complete:
                        await websocket.send_json({"type": "turn.complete"})
                if event.tool_call is not None:
                    await self._respond_to_calls(websocket, session, event.tool_call.function_calls or [])

    async def _forward_transcripts(self, websocket: WebSocket, content: Any) -> None:
        for name, event_type, role in (
            ("input_transcription", "transcript.user", "user"),
            ("output_transcription", "transcript.assistant", "assistant"),
        ):
            transcription = getattr(content, name, None)
            text = getattr(transcription, "text", None)
            if text:
                await websocket.send_json({
                    "type": event_type,
                    "role": role,
                    "text": text,
                    "final": bool(getattr(transcription, "finished", False)),
                })

    async def _respond_to_calls(self, websocket: WebSocket, session: Any, calls: list[Any]) -> None:
        responses: list[types.FunctionResponse] = []
        for call in calls:
            await websocket.send_json({"type": "state", "state": "thinking"})
            result = await self._call_bridge(call.name, call.args or {})
            operation = {
                "pea_agent_chat": "chat",
                "pea_confirm_pending_action": "confirm",
                "pea_reject_pending_action": "reject",
            }.get(call.name, "unknown")
            logger.info("gemini_live_bridge_called", extra={"function_name": call.name})
            await websocket.send_json({"type": "agent.response", "operation": operation, "response": result})
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
        if responses:
            await session.send_tool_response(function_responses=responses)

    async def _call_bridge(self, name: str | None, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "pea_agent_chat":
                return await self._bridge.handle_text(args.get("message", ""))
            if name == "pea_confirm_pending_action":
                return await self._bridge.confirm_current(args.get("confirmationNote"))
            if name == "pea_reject_pending_action":
                return await self._bridge.reject_current(args.get("reason", ""))
            return {"error": {"code": "unknown_function", "message": "คำสั่งเสียงนี้ไม่รองรับครับ"}}
        except VoiceBridgeError as error:
            return error.to_dict()
        except Exception:
            logger.error("gemini_live_bridge_failed")
            return {"error": {"code": "unavailable", "message": "ไม่สามารถดำเนินการได้ในขณะนี้ครับ"}}
