/* AudioWorklet: microphone Float32 frames -> 16 kHz little-endian PCM16. */
class PeaPcmProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions.targetSampleRate || 16000;
    this.ratio = sampleRate / this.targetRate;
    this.samples = [];
    this.next = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || !input.length) return true;
    for (let index = 0; index < input.length; index += 1) this.samples.push(input[index]);

    const pcm = [];
    while (this.next + 1 < this.samples.length) {
      const lower = Math.floor(this.next);
      const fraction = this.next - lower;
      const sample = this.samples[lower] + (this.samples[lower + 1] - this.samples[lower]) * fraction;
      const clamped = Math.max(-1, Math.min(1, sample));
      pcm.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
      this.next += this.ratio;
    }

    const consumed = Math.floor(this.next);
    if (consumed) {
      this.samples.splice(0, consumed);
      this.next -= consumed;
    }
    if (pcm.length) {
      const output = new Int16Array(pcm);
      this.port.postMessage(output.buffer, [output.buffer]);
    }
    return true;
  }
}

registerProcessor('pea-pcm-processor', PeaPcmProcessor);
