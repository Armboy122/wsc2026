from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "web" / "gemini-live-client.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for GeminiLiveClient tests")
def test_gemini_live_client_event_handling_without_progress_injection() -> None:
    """Client event handling must stay display-only for JSON events.

    Regression: assistant.progress used to be spoken aloud through browser
    speechSynthesis — a non-Gemini voice that leaked into the microphone and
    looped the conversation.  The progress acknowledgement was removed
    entirely; the client must never synthesize speech and must ignore the
    event if a server ever sends it again.
    """
    script = r"""
import { GeminiLiveClient } from "./web/gemini-live-client.js";

let speakCalls = 0;
let cancelCalls = 0;

// Browser TTS must never be touched by the client for progress text.
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) {
    this.text = text;
    this.lang = null;
    this.rate = 1.0;
  }
};
globalThis.speechSynthesis = {
  speaking: false,
  pending: false,
  speak(utterance) {
    speakCalls += 1;
    this.speaking = true;
  },
  cancel() {
    cancelCalls += 1;
    this.speaking = false;
  }
};

let stateHistory = [];
let interruptedCount = 0;
let turnCompleteCount = 0;
let agentResponses = [];
let transcripts = [];
let errors = [];

const client = new GeminiLiveClient({
  onState: (state) => { stateHistory.push(state); },
  onInterrupted: () => { interruptedCount += 1; },
  onTurnComplete: () => { turnCompleteCount += 1; },
  onAgentResponse: (op, resp) => { agentResponses.push({ op, resp }); },
  onTranscript: (role, text, final) => { transcripts.push({ role, text, final }); },
  onError: (msg) => { errors.push(msg); },
});

// Spy on media methods
let pcmBuffers = [];
let playbackFlushes = 0;
client.media.playPcm16 = (buf) => { pcmBuffers.push(buf); };
client.media.flushPlayback = () => { playbackFlushes += 1; };

// 1. assistant.progress is ignored — never spoken, never forwarded
client.handleMessage({
  data: JSON.stringify({
    type: "assistant.progress",
    text: "ขอตรวจสอบรายละเอียดให้สักครู่นะครับ"
  })
});

if (speakCalls !== 0) {
  throw new Error(`expected speechSynthesis.speak to never be called, got ${speakCalls} calls`);
}
if (cancelCalls !== 0) {
  throw new Error(`expected speechSynthesis.cancel to never be called, got ${cancelCalls} calls`);
}
if (stateHistory.length !== 0) {
  throw new Error(`expected no state change for progress, got ${stateHistory.join(",")}`);
}

// 2. Real Gemini audio still plays and reports 'speaking'
const audioChunk = new ArrayBuffer(640);
client.handleMessage({ data: audioChunk });
if (pcmBuffers.length !== 1 || pcmBuffers[0] !== audioChunk) {
  throw new Error("expected PCM buffer to be scheduled for playback");
}
if (stateHistory[stateHistory.length - 1] !== "speaking") {
  throw new Error(`expected state 'speaking', got ${stateHistory[stateHistory.length - 1]}`);
}

// 3. User interrupts -> playback flushes and onInterrupted fires
client.handleMessage({ data: JSON.stringify({ type: "audio.interrupted" }) });
if (playbackFlushes !== 1) {
  throw new Error("expected media playback to flush on interruption");
}
if (interruptedCount !== 1) {
  throw new Error("expected onInterrupted handler to be called");
}

// 4. User transcript is forwarded
client.handleMessage({
  data: JSON.stringify({ type: "transcript.user", role: "user", text: "ขอยกเลิกครับ", final: false })
});
if (transcripts.length !== 1 || transcripts[0].text !== "ขอยกเลิกครับ") {
  throw new Error("expected onTranscript to receive user utterance");
}

// 5. Turn completes -> onTurnComplete fires
client.handleMessage({ data: JSON.stringify({ type: "turn.complete" }) });
if (turnCompleteCount !== 1) {
  throw new Error("expected onTurnComplete handler to be called");
}

// 6. Error event is surfaced
client.ready = true;
client.handleMessage({ data: JSON.stringify({ type: "error", message: "ระบบขัดข้อง" }) });
if (errors.length !== 1 || errors[0] !== "ระบบขัดข้อง") {
  throw new Error("expected onError handler to be called with error message");
}

// 7. agent.response is forwarded unchanged
client.handleMessage({
  data: JSON.stringify({
    type: "agent.response",
    operation: "chat",
    response: { message: "ผลลัพธ์", conversationId: "c-1" }
  })
});
if (agentResponses.length !== 1 || agentResponses[0].op !== "chat" || agentResponses[0].resp.conversationId !== "c-1") {
  throw new Error("expected agent.response to be forwarded unchanged");
}
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
