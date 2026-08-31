/* Microphone capture plus gap-free 24 kHz PCM16 playback for Gemini Live. */
export class MediaHandler {
  constructor(onAudio) { this.onAudio = onAudio; this.context = null; this.stream = null; this.source = null; this.worklet = null; this.silentGain = null; this.nextStartTime = 0; this.scheduledSources = new Set(); }
  async startCapture() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('เบราว์เซอร์นี้ไม่รองรับการใช้ไมโครโฟน');
    try { this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch (_) { this.stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    this.context = new AudioContext(); await this.context.audioWorklet.addModule('/pcm-processor.js?v=voice-audio-1');
    this.source = this.context.createMediaStreamSource(this.stream); this.worklet = new AudioWorkletNode(this.context, 'pea-pcm-processor', { processorOptions: { targetSampleRate: 16000 } });
    this.worklet.port.onmessage = ({ data }) => this.onAudio(data); this.silentGain = this.context.createGain(); this.silentGain.gain.value = 0;
    this.source.connect(this.worklet); this.worklet.connect(this.silentGain).connect(this.context.destination); await this.context.resume();
  }
  playPcm16(buffer) { if (!this.context || !buffer?.byteLength) return; const pcm = new Int16Array(buffer.slice(0)); const audio = this.context.createBuffer(1, pcm.length, 24000); const channel = audio.getChannelData(0); for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 0x8000; const source = this.context.createBufferSource(); source.buffer = audio; source.connect(this.context.destination); const start = Math.max(this.context.currentTime, this.nextStartTime); source.start(start); this.nextStartTime = start + audio.duration; this.scheduledSources.add(source); source.onended = () => this.scheduledSources.delete(source); }
  flushPlayback() { this.scheduledSources.forEach((source) => { try { source.stop(); } catch (_) {} }); this.scheduledSources.clear(); this.nextStartTime = this.context?.currentTime || 0; }
  async stop() { this.flushPlayback(); this.worklet?.port && (this.worklet.port.onmessage = null); this.source?.disconnect(); this.worklet?.disconnect(); this.silentGain?.disconnect(); this.stream?.getTracks().forEach((track) => track.stop()); const context = this.context; this.context = this.stream = this.source = this.worklet = this.silentGain = null; if (context && context.state !== 'closed') await context.close(); }
}
