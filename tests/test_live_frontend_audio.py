from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROCESSOR = ROOT / "web" / "pcm-processor.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the AudioWorklet regression")
def test_pcm_processor_defaults_to_16khz_and_batches_frames() -> None:
    """The browser must emit useful PCM chunks even when no processor options are passed."""
    script = r"""
globalThis.sampleRate = 48000;
const messages = [];
globalThis.AudioWorkletProcessor = class {
  constructor() {
    this.port = {
      postMessage(buffer) { messages.push(buffer.byteLength); },
    };
  }
};
globalThis.registerProcessor = (_name, processor) => { globalThis.Processor = processor; };
require(process.argv[1]);
const processor = new globalThis.Processor({});
const frame = new Float32Array(128).fill(0.25);
for (let index = 0; index < 375; index += 1) processor.process([[frame]]);
if (messages.length !== 10) {
  throw new Error(`expected exactly 10 chunks/second, got ${messages.length}`);
}
if (messages.some((size) => size !== 3200)) {
  throw new Error(`expected 3200-byte PCM16 chunks, got ${messages.join(',')}`);
}
if (processor.pendingPcm.length !== 0) {
  throw new Error(`expected exactly 16000 samples/second, got ${processor.pendingPcm.length} extra`);
}
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "-e", script, str(PROCESSOR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
