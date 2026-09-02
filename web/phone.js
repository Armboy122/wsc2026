import { GeminiLiveClient } from './gemini-live-client.js';

(() => {
  // Elements
  const els = {
    time: document.getElementById('status-time'),
    numberDisplay: document.getElementById('number-display'),
    addNumberLabel: document.getElementById('add-number-label'),
    deleteBtn: document.getElementById('delete-btn'),
    callBtn: document.getElementById('call-btn'),
    keys: document.querySelectorAll('.key-btn'),
    tabItems: document.querySelectorAll('.tab-item'),
    dynamicIsland: document.getElementById('dynamic-island'),
    toast: document.getElementById('ios-toast'),
    
    // In-Call Elements
    viewDialer: document.getElementById('view-dialer'),
    viewIncall: document.getElementById('view-incall'),
    incallName: document.getElementById('incall-name'),
    incallTimer: document.getElementById('incall-timer'),
    incallStatusText: document.getElementById('incall-status-text'),
    incallStatusDot: document.getElementById('incall-status-dot'),
    endCallBtn: document.getElementById('end-call-btn'),
    muteBtn: document.getElementById('mute-btn'),
    speakerBtn: document.getElementById('speaker-btn'),
    transcriptBubble: document.getElementById('transcript-bubble'),
    transcriptLabel: document.getElementById('transcript-label'),
    transcriptText: document.getElementById('transcript-text'),
    pulseRings: document.querySelectorAll('.pulse-ring'),
  };

  let dialedNumber = '1129';
  let liveClient = null;
  let callTimerInterval = null;
  let callStartTime = null;
  let isMuted = false;
  let isSpeaker = true;
  let deleteHoldTimeout = null;

  // --- 1. Authentic DTMF Tone Synthesizer (Web Audio API) ---
  const DTMF_FREQS = {
    '1': [697, 1209], '2': [697, 1336], '3': [697, 1477],
    '4': [770, 1209], '5': [770, 1336], '6': [770, 1477],
    '7': [852, 1209], '8': [852, 1336], '9': [852, 1477],
    '*': [941, 1209], '0': [941, 1336], '#': [941, 1477]
  };

  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContext();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playDtmfTone(char, duration = 0.15) {
    const freqs = DTMF_FREQS[char];
    if (!freqs) return;
    try {
      const ctx = getAudioContext();
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gainNode = ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'sine';
      osc1.frequency.value = freqs[0];
      osc2.frequency.value = freqs[1];

      gainNode.gain.setValueAtTime(0.12, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

      osc1.connect(gainNode);
      osc2.connect(gainNode);
      gainNode.connect(ctx.destination);

      osc1.start();
      osc2.start();
      osc1.stop(ctx.currentTime + duration);
      osc2.stop(ctx.currentTime + duration);
    } catch (e) {
      console.warn('Audio play failed', e);
    }
  }

  function playCallTone(type) {
    try {
      const ctx = getAudioContext();
      const osc = ctx.createOscillator();
      const gainNode = ctx.createGain();
      
      if (type === 'connect') {
        osc.frequency.setValueAtTime(440, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.2);
        gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
        osc.connect(gainNode);
        gainNode.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.25);
      } else if (type === 'hangup') {
        osc.frequency.setValueAtTime(480, ctx.currentTime);
        gainNode.gain.setValueAtTime(0.15, ctx.currentTime);
        gainNode.gain.setValueAtTime(0, ctx.currentTime + 0.15);
        gainNode.gain.setValueAtTime(0.15, ctx.currentTime + 0.25);
        gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.connect(gainNode);
        gainNode.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.45);
      }
    } catch (_) {}
  }

  // --- 2. Live Status Bar Clock ---
  function updateClock() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    if (els.time) els.time.textContent = `${hours}:${minutes}`;
  }
  updateClock();
  setInterval(updateClock, 10000);

  // --- 3. Keypad & Number Input Handling ---
  function updateNumberDisplay() {
    if (els.numberDisplay) {
      els.numberDisplay.textContent = dialedNumber;
    }
    if (els.deleteBtn) {
      if (dialedNumber.length > 0) {
        els.deleteBtn.classList.remove('hidden');
      } else {
        els.deleteBtn.classList.add('hidden');
      }
    }
    if (els.addNumberLabel) {
      if (dialedNumber && dialedNumber !== '1129') {
        els.addNumberLabel.textContent = 'เพิ่มหมายเลข';
        els.addNumberLabel.style.color = 'var(--ios-blue-light)';
      } else {
        els.addNumberLabel.textContent = '';
      }
    }
  }

  els.keys.forEach((key) => {
    const num = key.getAttribute('data-key');
    const handlePress = (e) => {
      e.preventDefault();
      if (dialedNumber.length < 16) {
        dialedNumber += num;
        updateNumberDisplay();
        playDtmfTone(num);
      }
      key.classList.add('pressed');
      setTimeout(() => key.classList.remove('pressed'), 120);
    };
    key.addEventListener('pointerdown', handlePress);
  });

  // Backspace Button
  if (els.deleteBtn) {
    const deleteDigit = () => {
      if (dialedNumber.length > 0) {
        dialedNumber = dialedNumber.slice(0, -1);
        updateNumberDisplay();
        playDtmfTone('1', 0.05);
      }
    };

    els.deleteBtn.addEventListener('click', deleteDigit);
    els.deleteBtn.addEventListener('pointerdown', () => {
      deleteHoldTimeout = setTimeout(() => {
        dialedNumber = '';
        updateNumberDisplay();
      }, 600);
    });
    els.deleteBtn.addEventListener('pointerup', () => clearTimeout(deleteHoldTimeout));
    els.deleteBtn.addEventListener('pointerleave', () => clearTimeout(deleteHoldTimeout));
  }

  // Show Toast Message
  let toastTimeout = null;
  function showToast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      els.toast.classList.remove('show');
    }, 3200);
  }

  // --- 4. Call Handling & Live Session with Gemini Live ---

  function startCallTimer() {
    callStartTime = Date.now();
    clearInterval(callTimerInterval);
    callTimerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
      const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const secs = String(elapsed % 60).padStart(2, '0');
      if (els.incallTimer) els.incallTimer.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  function stopCallTimer() {
    clearInterval(callTimerInterval);
    callTimerInterval = null;
    if (els.incallTimer) els.incallTimer.textContent = '00:00';
  }

  function setVisualState(state) {
    if (!els.incallStatusDot || !els.incallStatusText) return;
    els.incallStatusDot.className = 'incall-status-dot';
    
    if (state === 'connecting') {
      els.incallStatusDot.classList.add('connecting');
      els.incallStatusText.textContent = 'กำลังเชื่อมต่อระบบสายตรง...';
      setRipplesActive(false);
    } else if (state === 'listening') {
      els.incallStatusText.textContent = 'ไมโครโฟนเปิดอยู่ (กำลังรับฟัง)';
      setRipplesActive(true, 'green');
    } else if (state === 'speaking') {
      els.incallStatusDot.classList.add('speaking');
      els.incallStatusText.textContent = 'PEA Agent กำลังสนทนาตอบกลับ...';
      setRipplesActive(true, 'blue');
    } else if (state === 'interrupted') {
      els.incallStatusText.textContent = 'ผู้ใช้แทรกเสียง...';
    } else if (state === 'off' || state === 'disconnected') {
      els.incallStatusText.textContent = 'สิ้นสุดการโทร';
      setRipplesActive(false);
    } else if (state === 'error') {
      els.incallStatusDot.classList.add('error');
      els.incallStatusText.textContent = 'สายหลุด หรือการเชื่อมต่อล้มเหลว';
      setRipplesActive(false);
    }
  }

  function setRipplesActive(active, color = 'green') {
    els.pulseRings.forEach(ring => {
      if (active) {
        ring.style.animationPlayState = 'running';
        ring.style.borderColor = color === 'blue' ? 'rgba(10, 132, 255, 0.4)' : 'rgba(52, 199, 89, 0.3)';
        ring.style.background = color === 'blue' ? 'rgba(10, 132, 255, 0.15)' : 'rgba(52, 199, 89, 0.12)';
      } else {
        ring.style.animationPlayState = 'paused';
      }
    });
  }

  function renderVoiceTranscript(role, text, isFinal) {
    if (!els.transcriptBubble || !els.transcriptText || !els.transcriptLabel) return;
    els.transcriptBubble.style.display = 'block';
    if (role === 'user') {
      els.transcriptLabel.textContent = 'คุณ:';
      els.transcriptLabel.className = 'transcript-label user';
    } else {
      els.transcriptLabel.textContent = 'PEA 1129:';
      els.transcriptLabel.className = 'transcript-label';
    }
    els.transcriptText.textContent = text;
  }

  async function startCall() {
    const numberToCall = dialedNumber || '1129';
    if (els.incallName) els.incallName.textContent = numberToCall;

    // Transition Screen to In-Call View
    els.viewIncall.classList.add('active');
    els.dynamicIsland.classList.add('active-call');
    setVisualState('connecting');
    playCallTone('connect');

    if (els.transcriptText) els.transcriptText.textContent = 'กำลังเริ่มการสนทนาด้วยเสียง...';

    try {
      liveClient = new GeminiLiveClient({
        onTranscript: renderVoiceTranscript,
        onAgentResponse: (op, resp) => console.log('Live Agent response:', op, resp),
        onTurnComplete: () => setVisualState('listening'),
        onInterrupted: () => setVisualState('interrupted'),
        onState: (state) => {
          setVisualState(state);
          if (state === 'listening' && !callTimerInterval) {
            startCallTimer();
          }
        },
        onError: (err) => {
          showToast(err || 'เกิดข้อผิดพลาดในการเชื่อมต่อโหมดเสียง');
          setVisualState('error');
        }
      });

      await liveClient.connect();
      startCallTimer();
      showToast('เชื่อมต่อสาย 1129 สำเร็จ พูดคุยได้ทันที');
    } catch (error) {
      console.error('Call connection failed:', error);
      const isPerm = error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError';
      const msg = isPerm 
        ? 'กรุณาอนุญาตการเข้าถึงไมโครโฟนเพื่อคุยสาย' 
        : (error.message || 'ไม่สามารถต่อสายได้');
      showToast(msg);
      setVisualState('error');
      setTimeout(() => endCall(), 2500);
    }
  }

  async function endCall() {
    playCallTone('hangup');
    stopCallTimer();
    setVisualState('off');

    if (liveClient) {
      try {
        await liveClient.disconnect();
      } catch (_) {}
      liveClient = null;
    }

    els.viewIncall.classList.remove('active');
    els.dynamicIsland.classList.remove('active-call');
    if (els.transcriptBubble) {
      els.transcriptText.textContent = '';
    }
    showToast('วางสายแล้ว');
  }

  // --- 5. In-Call Controls ---
  if (els.callBtn) {
    els.callBtn.addEventListener('click', startCall);
  }

  if (els.endCallBtn) {
    els.endCallBtn.addEventListener('click', endCall);
  }

  if (els.muteBtn) {
    els.muteBtn.addEventListener('click', () => {
      isMuted = !isMuted;
      els.muteBtn.classList.toggle('active', isMuted);
      showToast(isMuted ? 'ปิดเสียงไมค์แล้ว' : 'เปิดเสียงไมค์แล้ว');
    });
  }

  if (els.speakerBtn) {
    els.speakerBtn.addEventListener('click', () => {
      isSpeaker = !isSpeaker;
      els.speakerBtn.classList.toggle('active', isSpeaker);
      showToast(isSpeaker ? 'เปิดลำโพงแล้ว' : 'ปิดลำโพงแล้ว');
    });
  }

  // Tab Item Selection
  els.tabItems.forEach((tab) => {
    tab.addEventListener('click', () => {
      els.tabItems.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
    });
  });

  // Initial State
  updateNumberDisplay();
})();
