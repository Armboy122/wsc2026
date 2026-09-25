/* ============================================================
 * PEA Knowledge Voice Agent — static voice UI
 * Talks only to the same-origin `WS /ws/live` (ADK + Gemini Live). The page shows live
 * transcripts; it never renders model reasoning, and it has no chat or write actions.
 * ============================================================ */

import { GeminiLiveClient } from './gemini-live-client.js';

(() => {
  'use strict';

  const els = {
    thread: document.getElementById('thread'),
    srStatus: document.getElementById('sr-status'),
    voiceToggle: document.getElementById('voice-toggle'),
    voiceStatus: document.getElementById('voice-status'),
  };

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function announce(text) {
    if (els.srStatus) els.srStatus.textContent = text;
  }

  function scrollThread() {
    requestAnimationFrame(() => {
      els.thread.scrollTop = els.thread.scrollHeight;
    });
  }

  function addSystemNotice(html, kind) {
    const el = document.createElement('div');
    el.className = `notice ${kind || 'notice-system'}`;
    el.innerHTML = html;
    els.thread.appendChild(el);
    scrollThread();
    return el;
  }

  /* ---------- โหมดเสียง Gemini Live ---------- */
  let liveClient = null;
  const voiceDrafts = {};

  function renderVoiceTranscript(role, text, isFinal, replace = false) {
    if (!text) return;
    const key = role === 'user' ? 'user' : 'assistant';
    let el = voiceDrafts[key];
    if (!el) {
      el = document.createElement('article');
      el.className = `msg msg-${key === 'user' ? 'user' : 'agent'} voice-transcript`;
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      el.appendChild(bubble);
      els.thread.appendChild(el);
      voiceDrafts[key] = el;
    }
    el.dataset.final = String(isFinal);
    const bubble = el.querySelector('.bubble');
    bubble.textContent = replace ? text : bubble.textContent + text;
    scrollThread();
    if (isFinal) delete voiceDrafts[key];
  }

  function finishVoiceTranscripts() {
    for (const key of Object.keys(voiceDrafts)) {
      voiceDrafts[key].dataset.final = 'true';
      delete voiceDrafts[key];
    }
  }

  function setVoiceState(voiceState) {
    if (!els.voiceToggle) return;
    const labels = {
      connecting: 'กำลังเชื่อมต่อ',
      listening: 'กำลังฟัง',
      thinking: 'กำลังคิด',
      speaking: 'ผู้ช่วยกำลังพูด',
      interrupted: 'หยุดเสียงเพราะผู้ใช้พูดแทรก',
      disconnected: 'ตัดการเชื่อมต่อแล้ว',
      error: 'โหมดเสียงเกิดข้อผิดพลาด',
      off: 'โหมดเสียง',
    };
    const on = !['off', 'disconnected', 'error'].includes(voiceState);
    els.voiceToggle.setAttribute('aria-pressed', String(on));
    els.voiceToggle.classList.toggle('voice-speaking', voiceState === 'speaking');
    const label = labels[voiceState] || 'โหมดเสียง';
    els.voiceToggle.setAttribute('aria-label', on ? `ปิดโหมดเสียง — ${label}` : 'เริ่มโหมดเสียง');
    els.voiceToggle.title = label;
    if (els.voiceStatus) {
      els.voiceStatus.textContent = label;
      els.voiceStatus.hidden = voiceState === 'off';
    }
    if (voiceState === 'disconnected') liveClient = null;
  }

  async function toggleVoice() {
    if (liveClient) {
      await liveClient.disconnect();
      liveClient = null;
      announce('ปิดโหมดเสียงแล้ว');
      return;
    }
    els.voiceToggle.disabled = true;
    setVoiceState('connecting');

    // ขอ permission ไมโครโฟนทันทีใน user-gesture เพื่อให้ Chrome แสดง dialog
    // (Chrome บล็อก getUserMedia ที่เรียกหลัง await ข้าม async boundary)
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('เบราว์เซอร์นี้ไม่รองรับการใช้ไมโครโฟน หรือหน้าเว็บนี้ต้องใช้งานผ่าน HTTPS หรือ localhost');
      }
      const permStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // หยุด track ทันที — จะเปิดใหม่ใน MediaHandler.startCapture()
      permStream.getTracks().forEach((t) => t.stop());
    } catch (permErr) {
      liveClient = null;
      setVoiceState('error');
      const msg = permErr.name === 'NotAllowedError' || permErr.name === 'PermissionDeniedError'
        ? 'ไม่ได้รับอนุญาตให้ใช้ไมโครโฟน — กรุณาคลิก 🔒 ที่ address bar แล้วเลือก Allow ไมโครโฟน'
        : permErr.message || 'ไม่สามารถเข้าถึงไมโครโฟนได้';
      addSystemNotice(`<strong>เปิดโหมดเสียงไม่สำเร็จ</strong><br>${escapeHtml(msg)}`, 'notice-error');
      announce('เปิดโหมดเสียงไม่สำเร็จ');
      els.voiceToggle.disabled = false;
      return;
    }

    try {
      liveClient = new GeminiLiveClient({
        onTranscript: renderVoiceTranscript,
        onTurnComplete: finishVoiceTranscripts,
        onInterrupted: finishVoiceTranscripts,
        onState: setVoiceState,
        onError: (message) => addSystemNotice(`<strong>โหมดเสียงเกิดข้อผิดพลาด</strong><br>${escapeHtml(message)}`, 'notice-error'),
      });
      await liveClient.connect();
      announce('เปิดโหมดเสียงแล้ว กำลังรับฟัง');
    } catch (error) {
      liveClient = null;
      setVoiceState('error');
      addSystemNotice('<strong>เปิดโหมดเสียงไม่สำเร็จ</strong><br>กรุณาอนุญาตไมโครโฟนและลองใหม่อีกครั้ง', 'notice-error');
      announce('เปิดโหมดเสียงไม่สำเร็จ');
    } finally {
      els.voiceToggle.disabled = false;
    }
  }
  els.voiceToggle?.addEventListener('click', toggleVoice);
})();
