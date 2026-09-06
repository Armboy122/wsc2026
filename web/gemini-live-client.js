/* Same-origin Gemini Live transport; binary PCM only, never encoded or logged. */
import { MediaHandler } from './media-handler.js';

export class GeminiLiveClient {
  constructor(handlers = {}) {
    const { channel, ...rest } = handlers;
    // ช่องทางกำหนดว่ามีหน้าจอหรือไม่ เสียงล้วนแบบ 1129 ต้องได้ยินชื่อเว็บไซต์
    this.channel = channel === 'phone' ? 'phone' : 'web';
    this.handlers = rest;
    this.socket = null;
    this.media = new MediaHandler((chunk) => this.sendAudio(chunk));
    this.closed = false;
    this.ready = false;
    this.resolveReady = null;
    this.rejectReady = null;
  }

  async connect() {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${scheme}//${location.host}/ws/live?channel=${this.channel}`);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;
    const ready = new Promise((resolve, reject) => {
      this.resolveReady = resolve;
      this.rejectReady = reject;
    });
    socket.onmessage = (event) => this.handleMessage(event);
    socket.onclose = () => this.handleClose();
    socket.onerror = () => this.failReady(new Error('ไม่สามารถเชื่อมต่อโหมดเสียงได้'));
    try {
      await ready;
      await this.media.startCapture();
      this.handlers.onState?.('listening');
    } catch (error) {
      await this.disconnect();
      throw error;
    } finally {
      this.resolveReady = null;
      this.rejectReady = null;
    }
  }

  sendAudio(chunk) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(chunk);
  }

  handleMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      this.media.playPcm16(event.data);
      this.handlers.onState?.('speaking');
      return;
    }
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (!message?.type) return;
    if (message.type === 'session.ready') {
      this.ready = true;
      this.resolveReady?.();
    } else if (message.type === 'transcript' || message.type === 'transcript.user' || message.type === 'transcript.assistant') {
      const role = message.role || (message.type.endsWith('.user') ? 'user' : 'assistant');
      this.handlers.onTranscript?.(role, String(message.text || ''), message.final !== false);
      if (role === 'user') this.handlers.onState?.('listening');
    } else if (message.type === 'audio.interrupted') {
      this.media.flushPlayback();
      this.handlers.onInterrupted?.();
      this.handlers.onState?.('interrupted');
    } else if (message.type === 'state') {
      this.handlers.onState?.(message.state || 'listening');
    } else if (message.type === 'turn.complete') {
      this.handlers.onTurnComplete?.();
      this.handlers.onState?.('listening');
    } else if (message.type === 'agent.response') {
      this.handlers.onAgentResponse?.(message.operation, message.response || {});
    } else if (message.type === 'error') {
      const error = new Error(message.message || 'โหมดเสียงเกิดข้อผิดพลาด');
      if (!this.ready) this.failReady(error);
      else this.handlers.onError?.(error.message);
    }
  }

  failReady(error) {
    if (!this.ready) this.rejectReady?.(error);
  }

  async handleClose() {
    this.failReady(new Error('การเชื่อมต่อโหมดเสียงถูกปิด'));
    await this.finish('disconnected');
  }

  async disconnect() {
    this.closed = true;
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
    await this.media.stop();
    this.handlers.onState?.('off');
  }

  async finish(state) {
    if (this.closed) return;
    this.closed = true;
    this.socket = null;
    await this.media.stop();
    this.handlers.onState?.(state);
  }
}
