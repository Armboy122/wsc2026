/* ============================================================
 * PEA One Agent — UI สาธิตสำหรับการแข่งขัน (AI-05)
 * ไคลเอนต์แบบสแตติกที่ไม่พึ่งพาไลบรารี สำหรับสัญญา v1 ที่ตรึงไว้:
 *   POST /api/v1/chat
 *   POST /api/v1/actions/{pendingActionId}/confirm
 *   POST /api/v1/actions/{pendingActionId}/reject
 *   GET  /api/v1/traces/{traceId}
 *   POST /api/v1/reset
 *
 * กฎความปลอดภัยที่ฝังอยู่ในไฟล์นี้:
 *   - ไม่แสดง chain-of-thought โดยเด็ดขาด และปิดบังคีย์ใด ๆ ที่คล้ายข้อมูลความคิด
 *     ในข้อมูลเหตุการณ์ trace เพื่อป้องกันไว้ก่อนแสดงผล
 *   - ผลลัพธ์จากการดำเนินงานจะมีป้าย SIMULATED กำกับเสมอ
 *   - ข้อมูลที่เขียนจะออกจากเบราว์เซอร์ผ่านเส้นทาง confirm / reject
 *     ที่ระบุไว้อย่างชัดเจนเท่านั้น และจะไม่ส่งผ่านข้อความแชต
 * ============================================================ */

(() => {
  'use strict';

  /* ---------- เส้นทางที่ตรึงไว้ ---------- */
  const API = {
    chat: '/api/v1/chat',
    confirm: (id) => `/api/v1/actions/${encodeURIComponent(id)}/confirm`,
    reject: (id) => `/api/v1/actions/${encodeURIComponent(id)}/reject`,
    trace: (id) => `/api/v1/traces/${encodeURIComponent(id)}`,
    reset: '/api/v1/reset',
  };

  /* คีย์ที่ห้ามแสดงโดยเด็ดขาด แม้บั๊กของระบบหลังบ้านจะทำให้ข้อมูลรั่วไหลออกมา */
  const COT_KEY_RE = /thought|thinking|reasoning|chain[_-]?of[_-]?thought|cot|scratchpad/i;

  const TRACE_KINDS = {
    chat_received: { label: 'รับข้อความจากผู้ใช้', cat: 'recv' },
    llm_requested: { label: 'ส่งคำขอไปยังโมเดล', cat: 'llm' },
    llm_responded: { label: 'โมเดลตอบกลับ', cat: 'llm' },
    tool_called: { label: 'เรียกใช้เครื่องมือ', cat: 'tool' },
    tool_result: { label: 'ได้ผลลัพธ์เครื่องมือ', cat: 'tool' },
    action_prepared: { label: 'เตรียมการกระทำ (ยังไม่มีผล)', cat: 'action' },
    action_confirmed: { label: 'ผู้ใช้ยืนยันการกระทำ', cat: 'action' },
    action_rejected: { label: 'ผู้ใช้ยกเลิกการกระทำ', cat: 'action' },
    action_submitted: { label: 'ส่งการกระทำไปยังระบบจำลอง', cat: 'action' },
    error: { label: 'เกิดข้อผิดพลาด', cat: 'error' },
  };

  const STATUS_FALLBACK = {
    404: 'ไม่พบข้อมูลที่ระบุ (404) — อาจถูกรีเซ็ตไปแล้ว',
    409: 'สถานะขัดแย้งกับกฎการยืนยัน (409) — การกระทำนี้อยู่ในสถานะสุดท้ายแล้ว',
    422: 'คำขอไม่ถูกต้องตามสัญญา (422)',
    500: 'เซิร์ฟเวอร์ขัดข้อง (500)',
    502: 'บริการต้นทางไม่พร้อมใช้งาน (502)',
  };

  /* ---------- สถานะ ---------- */
  const state = {
    conversationId: null,
    lastTraceId: null,
    busy: false,        // กำลังรับส่งข้อมูลแชตแบบไปกลับ
    actionBusy: false,  // กำลังรับส่งข้อมูล confirm/reject แบบไปกลับ
    traceOpen: false,
  };

  /* ---------- องค์ประกอบ ---------- */
  const els = {
    thread: document.getElementById('thread'),
    welcome: document.getElementById('welcome'),
    form: document.getElementById('composer-form'),
    input: document.getElementById('message-input'),
    send: document.getElementById('send-btn'),
    promptChips: Array.from(document.querySelectorAll('.prompt-chip')),
    resetBtn: document.getElementById('reset-btn'),
    traceToggle: document.getElementById('trace-toggle'),
    tracePanel: document.getElementById('trace-panel'),
    traceBackdrop: document.getElementById('trace-backdrop'),
    traceEvents: document.getElementById('trace-events'),
    traceEmpty: document.getElementById('trace-empty'),
    traceIdLabel: document.getElementById('trace-id-label'),
    traceRefresh: document.getElementById('trace-refresh'),
    traceClose: document.getElementById('trace-close'),
    srStatus: document.getElementById('sr-status'),
  };

  /* ---------- ฟังก์ชันอรรถประโยชน์ ---------- */

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
  }

  function fmtTimeMs(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function announce(text) {
    if (els.srStatus) els.srStatus.textContent = text;
  }

  function scrollThread() {
    requestAnimationFrame(() => {
      els.thread.scrollTop = els.thread.scrollHeight;
    });
  }

  function humanizeKey(key) {
    return String(key)
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .replace(/_/g, ' ')
      .trim();
  }

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status;
    }
  }

  function extractApiMessage(payload, status) {
    const detail = payload && payload.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((item) => {
          const field = Array.isArray(item && item.loc) ? item.loc[item.loc.length - 1] : '';
          const msg = (item && item.msg) || 'ข้อมูลไม่ถูกต้อง';
          return field ? `${field}: ${msg}` : msg;
        })
        .join(' · ');
    }
    if (payload && typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim();
    }
    return STATUS_FALLBACK[status] || `เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ (${status})`;
  }

  async function api(url, options = {}) {
    let res;
    try {
      res = await fetch(url, {
        method: options.method || 'GET',
        headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
    } catch (err) {
      throw new ApiError(0, 'ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ — โปรดตรวจสอบว่าระบบหลังบ้าน (backend) กำลังทำงานอยู่');
    }
    let payload = null;
    try {
      payload = await res.json();
    } catch (err) {
      /* เนื้อหาว่างเปล่าหรือไม่ได้อยู่ในรูปแบบ JSON */
    }
    if (!res.ok) throw new ApiError(res.status, extractApiMessage(payload, res.status));
    return payload;
  }

  /* การปิดบังเชิงป้องกัน: ลบข้อมูลใด ๆ ที่คล้ายความคิดออกจากข้อมูล trace ที่ส่งมา */
  function redactThoughts(value) {
    if (Array.isArray(value)) return value.map(redactThoughts);
    if (value && typeof value === 'object') {
      const out = {};
      for (const [k, v] of Object.entries(value)) {
        out[k] = COT_KEY_RE.test(k) ? '«redacted-by-ui»' : redactThoughts(v);
      }
      return out;
    }
    return value;
  }

  /* ---------- การแสดงผลเธรด ---------- */

  function timestampHtml(iso, alignClass) {
    const t = fmtTime(iso);
    return t ? `<time class="msg-time ${alignClass || ''}" datetime="${escapeHtml(iso || '')}">${escapeHtml(t)}</time>` : '';
  }

  function addUserMessage(text) {
    const el = document.createElement('article');
    el.className = 'msg msg-user';
    el.innerHTML = `
      <div>
        <div class="bubble">${escapeHtml(text)}</div>
        ${timestampHtml(new Date().toISOString(), '')}
      </div>`;
    els.thread.appendChild(el);
    scrollThread();
  }

  function addSystemNotice(html, kind) {
    const el = document.createElement('div');
    el.className = `notice ${kind || 'notice-system'}`;
    el.innerHTML = html;
    els.thread.appendChild(el);
    scrollThread();
    return el;
  }

  let typingEl = null;

  function showTyping() {
    if (typingEl) return;
    typingEl = document.createElement('div');
    typingEl.className = 'typing';
    typingEl.setAttribute('aria-label', 'ผู้ช่วยกำลังพิมพ์คำตอบ');
    typingEl.innerHTML = `
      <span class="agent-avatar" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M13.6 1.6 4.9 13.9h4.9L8.6 22.4l9.1-12.7h-5l.9-8.1z"/></svg>
      </span>
      <div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
    els.thread.appendChild(typingEl);
    scrollThread();
  }

  function hideTyping() {
    if (typingEl) {
      typingEl.remove();
      typingEl = null;
    }
  }

  function setBusy(busy) {
    state.busy = busy;
    els.send.disabled = busy;
    els.input.disabled = busy;
    els.promptChips.forEach((b) => { b.disabled = busy; });
    if (!busy) els.input.focus();
  }

  /* ชิปเครื่องมือ: บันทึกอย่างตรงไปตรงมาและกระชับว่าเรียกใช้เครื่องมือใดบ้าง */
  function renderToolChips(toolResults) {
    if (!Array.isArray(toolResults) || !toolResults.length) return '';
    const chips = toolResults
      .map((r) => {
        if (!r) return '';
        const ok = r.status === 'success';
        const sim = r.simulation === true
          ? '<span class="tc-sim">SIMULATED</span>'
          : '';
        return `
          <span class="tool-chip ${ok ? 'ok' : 'err'}" title="${escapeHtml(`${r.name || 'tool'} · ${r.action || ''} — ${ok ? 'สำเร็จ' : 'ผิดพลาด'}${r.simulation ? ' (ข้อมูลจำลอง)' : ''}`)}">
            <span class="tc-name">${escapeHtml(r.name || 'tool')}.${escapeHtml(r.action || '')}</span>
            <span class="tc-status">${ok ? '✓' : '✕'}</span>
            ${sim}
          </span>`;
      })
      .join('');
    return `<div class="tool-chips" aria-label="เครื่องมือที่ถูกเรียกใช้">${chips}</div>`;
  }

  function renderCitations(citations) {
    if (!Array.isArray(citations) || !citations.length) return '';
    const items = citations
      .map((c, i) => {
        if (!c) return '';
        const page = (typeof c.page === 'number' && c.page > 0)
          ? `<span class="citation-page">หน้า ${escapeHtml(c.page)}</span>`
          : '';
        const snippet = c.snippet ? `<p class="citation-snippet">${escapeHtml(c.snippet)}</p>` : '';
        const link = c.uri
          ? `<a class="citation-link" href="${escapeHtml(c.uri)}" target="_blank" rel="noopener noreferrer">แหล่งที่มา <span aria-hidden="true">↗</span><span class="visually-hidden">(เปิดแท็บใหม่)</span></a>`
          : '';
        return `
          <li class="citation">
            <div class="citation-head">
              <span class="citation-index" aria-label="อ้างอิงที่ ${i + 1}">[${i + 1}]</span>
              <span class="citation-title">${escapeHtml(c.title || 'เอกสาร')}</span>
              ${page}
            </div>
            ${snippet}
            ${link}
          </li>`;
      })
      .join('');
    return `
      <section class="citations" aria-label="แหล่งอ้างอิงจากคลังความรู้">
        <p class="citations-title">แหล่งอ้างอิง (Gemini File Search)</p>
        <ol class="citation-list">${items}</ol>
      </section>`;
  }

  function renderDataList(obj) {
    if (!obj || typeof obj !== 'object' || !Object.keys(obj).length) return '';
    const rows = Object.entries(obj)
      .map(([k, v]) => {
        let val;
        if (v === null || v === undefined) val = '—';
        else if (typeof v === 'object') val = JSON.stringify(v);
        else val = String(v);
        return `<dt>${escapeHtml(humanizeKey(k))}</dt><dd>${escapeHtml(val)}</dd>`;
      })
      .join('');
    return rows;
  }

  /* ---------- การ์ดการกระทำที่รอดำเนินการ ---------- */

  const SIM_LABEL = '<span class="pa-sim">SIMULATED · ข้อมูลจำลอง</span>';

  function renderPendingCard(pa) {
    if (!pa || !pa.pendingActionId) return '';

    const card = document.createElement('section');
    card.className = 'pending-card';
    card.dataset.paId = pa.pendingActionId;
    card.setAttribute('aria-label', 'การกระทำที่รอการยืนยัน');

    const status = pa.status || 'pending_confirmation';
    const pending = status === 'pending_confirmation';

    const badgeClass = {
      pending_confirmation: 'pa-badge-waiting',
      confirmed: 'pa-badge-confirmed',
      submitted: 'pa-badge-submitted',
      rejected: 'pa-badge-rejected',
      failed: 'pa-badge-failed',
    }[status] || 'pa-badge-waiting';

    const badgeText = {
      pending_confirmation: 'รอการยืนยัน — ยังไม่มีผลใด ๆ',
      confirmed: 'ยืนยันแล้ว',
      submitted: 'สำเร็จ — ส่งแล้ว (ระบบจำลอง)',
      rejected: 'ยกเลิกแล้ว',
      failed: 'ล้มเหลว',
    }[status] || status;

    const inputRows = renderDataList(pa.preparedInput);

    card.innerHTML = `
      <header class="pa-head">
        <span class="pa-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
        <span class="pa-tool">${escapeHtml(pa.toolName || '')} · ${escapeHtml(pa.prepareAction || '')}</span>
        ${SIM_LABEL}
      </header>
      <h3 class="pa-summary" tabindex="-1">${escapeHtml(pa.summary || '')}</h3>
      ${inputRows ? `<dl class="pa-input"><dt class="visually-hidden">รายละเอียดข้อมูล</dt>${inputRows}</dl>` : ''}
      <div class="pa-body"></div>`;

    const body = card.querySelector('.pa-body');

    if (pending) {
      body.innerHTML = `
        <div class="pa-note">
          <label for="pa-note-${escapeHtml(pa.pendingActionId)}">หมายเหตุประกอบการยืนยัน หรือเหตุผลการยกเลิก</label>
          <input id="pa-note-${escapeHtml(pa.pendingActionId)}" type="text" maxlength="500"
                 autocomplete="off" placeholder="ไม่บังคับสำหรับการยืนยัน · จำเป็นเมื่อยกเลิก">
          <p class="pa-hint">การยกเลิกต้องระบุเหตุผล (1–500 ตัวอักษร) · ยืนยันซ้ำจะไม่ทำให้ส่งข้อมูลสองครั้ง (idempotent)</p>
        </div>
        <p class="pa-error" role="alert" hidden></p>
        <div class="pa-actions">
          <button type="button" class="btn btn-confirm">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12.5 9.5 18 20 6.5"/></svg>
            ยืนยันและดำเนินการ
          </button>
          <button type="button" class="btn btn-cancel">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
            ยกเลิก
          </button>
        </div>`;
      bindDecisionButtons(card, body, pa);
    } else {
      renderTerminalState(body, pa);
    }

    return card;
  }

  function showCardError(body, message) {
    const errEl = body.querySelector('.pa-error');
    if (errEl) {
      errEl.textContent = message;
      errEl.hidden = false;
    }
  }

  function bindDecisionButtons(card, body, pa) {
    const noteInput = body.querySelector('input');
    const confirmBtn = body.querySelector('.btn-confirm');
    const cancelBtn = body.querySelector('.btn-cancel');
    const errEl = body.querySelector('.pa-error');

    confirmBtn.addEventListener('click', () => decide(card, body, pa, 'confirm', noteInput, confirmBtn));
    cancelBtn.addEventListener('click', () => {
      errEl.hidden = true;
      const reason = (noteInput.value || '').trim();
      if (!reason) {
        showCardError(body, 'การยกเลิกต้องระบุเหตุผล — กรุณาพิมพ์เหตุผลสั้น ๆ ในช่องหมายเหตุก่อนกดยกเลิก');
        noteInput.focus();
        return;
      }
      decide(card, body, pa, 'reject', noteInput, cancelBtn);
    });
  }

  async function decide(card, body, pa, kind, noteInput, clickedBtn) {
    if (state.actionBusy) return;
    state.actionBusy = true;

    const errEl = body.querySelector('.pa-error');
    if (errEl) errEl.hidden = true;

    body.querySelectorAll('.btn').forEach((b) => { b.disabled = true; });
    const original = clickedBtn.innerHTML;
    clickedBtn.innerHTML = kind === 'confirm' ? 'กำลังยืนยัน…' : 'กำลังยกเลิก…';

    try {
      let resp;
      if (kind === 'confirm') {
        const note = (noteInput.value || '').trim();
        resp = await api(API.confirm(pa.pendingActionId), {
          method: 'POST',
          body: { confirmationNote: note || null },
        });
      } else {
        resp = await api(API.reject(pa.pendingActionId), {
          method: 'POST',
          body: { reason: (noteInput.value || '').trim() },
        });
      }
      const updated = resp && resp.pendingAction ? resp.pendingAction : pa;
      if (resp && resp.traceId) state.lastTraceId = resp.traceId;
      updateTraceIdLabel();
      renderTerminalState(body, updated, resp && resp.toolResult);
      if (kind === 'confirm') {
        announce('ยืนยันการกระทำเรียบร้อย');
      } else {
        announce('ยกเลิกการกระทำเรียบร้อย');
      }
      if (state.traceOpen) refreshTrace(true);
    } catch (err) {
      body.querySelectorAll('.btn').forEach((b) => { b.disabled = false; });
      clickedBtn.innerHTML = original;
      showCardError(body, err instanceof ApiError ? err.message : 'เกิดข้อผิดพลาด ไม่สามารถติดต่อเซิร์ฟเวอร์ได้');
      announce('การดำเนินการล้มเหลว');
    } finally {
      state.actionBusy = false;
    }
  }

  function renderTerminalState(body, pa, toolResult) {
    const status = pa.status || '';
    let resultHtml = '';

    if (status === 'submitted') {
      const data = (toolResult && toolResult.data) || pa.submissionResult && pa.submissionResult.data;
      const rows = data ? renderDataList(data) : '';
      resultHtml = `
        ${rows ? `<dl class="pa-result-data">${rows}</dl>` : ''}
        <p class="pa-meta">ผลลัพธ์นี้เกิดขึ้นบนระบบจำลองเท่านั้น — ไม่มีการเคลื่อนไหวข้อมูลจริงใด ๆ</p>`;
    } else if (status === 'failed') {
      const errMsg = (toolResult && toolResult.error && toolResult.error.message)
        || (pa.submissionResult && pa.submissionResult.error && pa.submissionResult.error.message)
        || 'การส่งข้อมูลไม่สำเร็จ';
      resultHtml = `
        <p class="pa-error">${escapeHtml(errMsg)}</p>
        <p class="pa-meta">การกระทำนี้ไม่เกิดผลใด ๆ กับข้อมูลจำลอง</p>`;
    } else if (status === 'rejected') {
      resultHtml = `<p class="pa-meta">การกระทำนี้ถูกปฏิเสธและไม่มีผลกับข้อมูลใด ๆ (สถานะนี้เป็นแบบถาวร)</p>`;
    } else if (status === 'confirmed') {
      resultHtml = `<p class="pa-meta">ได้รับการยืนยันแล้ว — กำลังรอผลการส่ง</p>`;
    }

    body.innerHTML = resultHtml;
  }

  /* ---------- ข้อความจากผู้ช่วย ---------- */

  function addAgentMessage(resp) {
    const el = document.createElement('article');
    el.className = 'msg msg-agent';
    el.innerHTML = `
      <span class="agent-avatar" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M13.6 1.6 4.9 13.9h4.9L8.6 22.4l9.1-12.7h-5l.9-8.1z"/></svg>
      </span>
      <div class="msg-stack">
        <div class="bubble">${escapeHtml(resp.message || '(ไม่มีข้อความตอบกลับ)')}</div>
        ${renderToolChips(resp.toolResults)}
        ${renderCitations(resp.citations)}
      </div>
      ${timestampHtml(new Date().toISOString(), '')}`;

    const stack = el.querySelector('.msg-stack');
    if (resp.pendingAction) {
      const card = renderPendingCard(resp.pendingAction);
      if (card) {
        stack.appendChild(card);
        const heading = card.querySelector('.pa-summary');
        if (heading) heading.focus({ preventScroll: true });
      }
    }

    els.thread.appendChild(el);
    scrollThread();
  }

  /* ---------- การส่งแชต ---------- */

  async function sendMessage(text) {
    const message = (text || '').trim();
    if (!message || state.busy) return;

    if (els.welcome) {
      els.welcome.remove();
      els.welcome = null;
    }

    addUserMessage(message);
    setBusy(true);
    showTyping();
    announce('กำลังส่งข้อความถึงผู้ช่วย');

    const body = {
      message,
      requestId: uuid(),
    };
    if (state.conversationId) body.conversationId = state.conversationId;

    try {
      const resp = await api(API.chat, { method: 'POST', body });
      hideTyping();
      if (resp) {
        if (resp.conversationId) state.conversationId = resp.conversationId;
        if (resp.traceId) state.lastTraceId = resp.traceId;
        updateTraceIdLabel();
        addAgentMessage(resp);
        if (resp.pendingAction) {
          announce('ได้รับคำตอบแล้ว — มีการกระทำที่รอคุณยืนยัน');
        } else {
          announce('ได้รับคำตอบจากผู้ช่วยแล้ว');
        }
        if (state.traceOpen) refreshTrace(true);
      }
    } catch (err) {
      hideTyping();
      const msg = err instanceof ApiError ? err.message : 'เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ';
      addSystemNotice(
        `<strong>ส่งข้อความไม่สำเร็จ</strong><br>${escapeHtml(msg)}<br>คุณสามารถลองส่งใหม่อีกครั้งได้`,
        'notice-error'
      );
      announce('ส่งข้อความล้มเหลว');
    } finally {
      setBusy(false);
      hideTyping();
    }
  }

  /* ---------- แผง trace ---------- */

  function updateTraceIdLabel() {
    els.traceIdLabel.textContent = state.lastTraceId
      ? `รอบล่าสุด: ${state.lastTraceId}`
      : '— ยังไม่มีรอบการทำงาน —';
  }

  function openTrace() {
    state.traceOpen = true;
    els.tracePanel.hidden = false;
    els.traceBackdrop.hidden = false;
    els.traceToggle.setAttribute('aria-expanded', 'true');
    refreshTrace(false);
    els.traceClose.focus();
  }

  function closeTrace() {
    state.traceOpen = false;
    els.tracePanel.hidden = true;
    els.traceBackdrop.hidden = true;
    els.traceToggle.setAttribute('aria-expanded', 'false');
    els.traceToggle.focus();
  }

  async function refreshTrace(silent) {
    if (!state.lastTraceId) {
      els.traceEmpty.hidden = false;
      els.traceEmpty.textContent = 'ยังไม่มีเหตุการณ์ — ส่งข้อความเพื่อเริ่มต้น';
      els.traceEvents.innerHTML = '';
      return;
    }
    els.traceEmpty.hidden = true;
    els.traceEvents.innerHTML = '<li class="trace-event"><div class="te-body"><span class="te-kind">กำลังโหลด…</span></div></li>';
    try {
      const trace = await api(API.trace(state.lastTraceId));
      renderTraceEvents((trace && trace.events) || []);
    } catch (err) {
      els.traceEvents.innerHTML = '';
      els.traceEmpty.hidden = false;
      els.traceEmpty.textContent = err instanceof ApiError
        ? `โหลดข้อมูลการตรวจสอบไม่สำเร็จ: ${err.message}`
        : 'โหลดข้อมูลการตรวจสอบไม่สำเร็จ';
      if (!silent) announce('โหลดข้อมูลการตรวจสอบไม่สำเร็จ');
    }
  }

  function renderTraceEvents(events) {
    els.traceEvents.innerHTML = '';
    if (!events.length) {
      els.traceEmpty.hidden = false;
      els.traceEmpty.textContent = 'รอบนี้ยังไม่มีเหตุการณ์ใด ๆ';
      return;
    }
    els.traceEmpty.hidden = true;

    const frag = document.createDocumentFragment();

    events.forEach((ev) => {
      const meta = TRACE_KINDS[ev.kind] || { label: ev.kind || 'เหตุการณ์', cat: 'recv' };
      const li = document.createElement('li');
      li.className = `trace-event cat-${meta.cat}`;

      const seq = String(ev.sequence ?? '?').padStart(2, '0');
      const at = fmtTimeMs(ev.at);
      const data = redactThoughts(ev.data);
      const dataHtml = (data && Object.keys(data).length)
        ? `<details class="te-data"><summary>ข้อมูล (ปิดบังข้อมูลอ่อนไหวแล้ว)</summary><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>`
        : '';

      li.innerHTML = `
        <span class="te-seq" aria-hidden="true">${escapeHtml(seq)}</span>
        <div class="te-body">
          <div class="te-row">
            <span class="te-kind">${escapeHtml(meta.label)}</span>
            <span class="te-kind-id mono">${escapeHtml(ev.kind || '')}</span>
            <time class="te-time mono">${escapeHtml(at)}</time>
          </div>
          ${dataHtml}
        </div>`;
      frag.appendChild(li);
    });

    els.traceEvents.appendChild(frag);
  }

  /* ---------- การรีเซ็ต ---------- */

  async function resetDemo() {
    els.resetBtn.disabled = true;
    try {
      await api(API.reset, { method: 'POST' });
      state.conversationId = null;
      state.lastTraceId = null;
      updateTraceIdLabel();
      els.traceEvents.innerHTML = '';
      els.traceEmpty.hidden = false;
      els.traceEmpty.textContent = 'ยังไม่มีเหตุการณ์ — ส่งข้อความเพื่อเริ่มต้น';

      els.thread.innerHTML = '';
      addSystemNotice(
        '<strong>รีเซ็ตข้อมูลการสาธิตเรียบร้อย</strong> — ล้างบทสนทนา การกระทำที่รอยืนยัน ข้อมูลระบบจำลอง และบันทึกการตรวจสอบทั้งหมดแล้ว (ข้อมูลจำลองเท่านั้น)',
        'notice-system'
      );
      announce('รีเซ็ตระบบสาธิตเรียบร้อยแล้ว');
      els.input.focus();
    } catch (err) {
      addSystemNotice(
        `<strong>รีเซ็ตไม่สำเร็จ</strong><br>${escapeHtml(err instanceof ApiError ? err.message : 'ไม่สามารถติดต่อเซิร์ฟเวอร์ได้')}`,
        'notice-error'
      );
      announce('รีเซ็ตล้มเหลว');
    } finally {
      els.resetBtn.disabled = false;
    }
  }

  /* ---------- การเชื่อมการทำงานของช่องเขียนข้อความ ---------- */

  function autosize() {
    els.input.style.height = 'auto';
    els.input.style.height = `${Math.min(els.input.scrollHeight, 132)}px`;
  }

  els.form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = els.input.value;
    if (!text.trim()) {
      els.input.focus();
      return;
    }
    els.input.value = '';
    autosize();
    sendMessage(text);
  });

  els.input.addEventListener('input', autosize);

  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });

  els.promptChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt || chip.textContent.trim();
      if (chip.hasAttribute('data-prefill')) {
        /* แทรกโครงแบบให้ผู้นำเสนอกรอกจนสมบูรณ์ โดยยังไม่ส่งข้อมูลใด ๆ และ UI
         * จะไม่สร้างข้อเท็จจริงของเรื่องร้องเรียนขึ้นเอง */
        els.input.value = prompt;
        autosize();
        els.input.focus();
        const end = els.input.value.length;
        els.input.setSelectionRange(end, end);
        announce('แทรกแบบฟอร์มเรื่องร้องเรียนแล้ว กรุณากรอกหัวเรื่องและรายละเอียดของคุณ แล้วจึงกดส่ง');
        return;
      }
      sendMessage(prompt);
    });
  });

  els.resetBtn.addEventListener('click', resetDemo);

  /* ---------- การเชื่อมการทำงานของ trace ---------- */

  els.traceToggle.addEventListener('click', () => {
    if (state.traceOpen) closeTrace();
    else openTrace();
  });

  els.traceClose.addEventListener('click', closeTrace);
  els.traceBackdrop.addEventListener('click', closeTrace);
  els.traceRefresh.addEventListener('click', () => refreshTrace(false));

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.traceOpen) closeTrace();
  });

  /* ---------- การเริ่มต้น ---------- */

  updateTraceIdLabel();
  autosize();
  els.input.focus();
})();
