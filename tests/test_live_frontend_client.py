from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "web" / "gemini-live-client.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for GeminiLiveClient tests")
def test_gemini_live_client_acknowledgement_lifecycle_and_cancellation() -> None:
    """GeminiLiveClient must speak assistant.progress and cancel on interruption, real audio, turn completion, or disconnect."""
    script = r"""
import { GeminiLiveClient } from "./web/gemini-live-client.js";

let spokenUtterance = null;
let cancelCalls = 0;

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
    spokenUtterance = utterance;
    this.speaking = true;
  },
  cancel() {
    cancelCalls += 1;
    this.speaking = false;
  }
};

let progressReported = null;
let stateHistory = [];
let interruptedCount = 0;
let turnCompleteCount = 0;
let agentResponses = [];
let transcripts = [];
let errors = [];

const client = new GeminiLiveClient({
  onProgress: (text) => { progressReported = text; },
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

// 1. assistant.progress triggers Thai speech synthesis promptly
client.handleMessage({
  data: JSON.stringify({
    type: "assistant.progress",
    text: "ขอตรวจสอบรายละเอียดให้สักครู่นะครับ"
  })
});

if (!spokenUtterance || spokenUtterance.text !== "ขอตรวจสอบรายละเอียดให้สักครู่นะครับ") {
  throw new Error(`expected utterance text "ขอตรวจสอบรายละเอียดให้สักครู่นะครับ", got ${spokenUtterance?.text}`);
}
if (spokenUtterance.lang !== "th-TH") {
  throw new Error(`expected utterance lang "th-TH", got ${spokenUtterance?.lang}`);
}
if (progressReported !== "ขอตรวจสอบรายละเอียดให้สักครู่นะครับ") {
  throw new Error(`expected onProgress to receive text, got ${progressReported}`);
}

// 2. Real Gemini audio starts arriving -> cancels acknowledgement immediately and plays PCM
const audioChunk = new ArrayBuffer(640);
const preAudioCancels = cancelCalls;
client.handleMessage({ data: audioChunk });
if (cancelCalls <= preAudioCancels) {
  throw new Error("expected audio arrival to immediately cancel acknowledgement");
}
if (pcmBuffers.length !== 1 || pcmBuffers[0] !== audioChunk) {
  throw new Error("expected PCM buffer to be scheduled for playback");
}
if (stateHistory[stateHistory.length - 1] !== "speaking") {
  throw new Error(`expected state 'speaking', got ${stateHistory[stateHistory.length - 1]}`);
}

// 3. New progress message, then user interrupts -> cancels acknowledgement immediately
client.handleMessage({
  data: JSON.stringify({ type: "assistant.progress", text: "กำลังตรวจสอบ..." })
});
const preInterruptCancels = cancelCalls;
client.handleMessage({ data: JSON.stringify({ type: "audio.interrupted" }) });
if (cancelCalls <= preInterruptCancels) {
  throw new Error("expected audio.interrupted to immediately cancel acknowledgement");
}
if (playbackFlushes !== 1) {
  throw new Error("expected media playback to flush on interruption");
}
if (interruptedCount !== 1) {
  throw new Error("expected onInterrupted handler to be called");
}

// 4. User starts new utterance (transcript.user) -> cancels acknowledgement
client.handleMessage({
  data: JSON.stringify({ type: "assistant.progress", text: "กำลังตรวจสอบ..." })
});
const preUserCancels = cancelCalls;
client.handleMessage({
  data: JSON.stringify({ type: "transcript.user", role: "user", text: "ขอยกเลิกครับ", final: false })
});
if (cancelCalls <= preUserCancels) {
  throw new Error("expected transcript.user to immediately cancel acknowledgement");
}
if (transcripts.length !== 1 || transcripts[0].text !== "ขอยกเลิกครับ") {
  throw new Error("expected onTranscript to receive user utterance");
}

// 5. Turn completes -> cancels acknowledgement
client.handleMessage({
  data: JSON.stringify({ type: "assistant.progress", text: "กำลังตรวจสอบ..." })
});
const preTurnCancels = cancelCalls;
client.handleMessage({ data: JSON.stringify({ type: "turn.complete" }) });
if (cancelCalls <= preTurnCancels) {
  throw new Error("expected turn.complete to immediately cancel acknowledgement");
}
if (turnCompleteCount !== 1) {
  throw new Error("expected onTurnComplete handler to be called");
}

// 6. Error event -> cancels acknowledgement
client.ready = true;
client.handleMessage({
  data: JSON.stringify({ type: "assistant.progress", text: "กำลังตรวจสอบ..." })
});
const preErrorCancels = cancelCalls;
client.handleMessage({ data: JSON.stringify({ type: "error", message: "ระบบขัดข้อง" }) });
if (cancelCalls <= preErrorCancels) {
  throw new Error("expected error to immediately cancel acknowledgement");
}
if (errors.length !== 1 || errors[0] !== "ระบบขัดข้อง") {
  throw new Error("expected onError handler to be called with error message");
}

// 7. Disconnect -> cancels acknowledgement
client.handleMessage({
  data: JSON.stringify({ type: "assistant.progress", text: "กำลังตรวจสอบ..." })
});
const preDisconnectCancels = cancelCalls;
client.disconnect();
if (cancelCalls <= preDisconnectCancels) {
  throw new Error("expected disconnect to immediately cancel acknowledgement");
}

// 8. Existing safe events preserved
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
