# -*- coding: utf-8 -*-
"""Section 4: Slides 22-33 (Multi-Channel & Plugin System) — เกณฑ์ A + B (16 + 10 คะแนน)"""

def get_slides():
    return [
        {
            "id": 22,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: สถาปัตยกรรมหลายช่องทาง",
            "title": "3 ช่องทาง สมองเดียว (Unified Gateway)",
            "subtitle": "Web Chat, Voice และ LINE สื่อสารกับ Main Agent ผ่าน Protocol เดียวกัน",
            "content": """
<div class="channels-funnel-container">
    <div class="channel-cards-trio">
        <div class="channel-card ch-web">
            <div class="ch-badge">ช่องทางที่ 1</div>
            <div class="ch-icon">💻</div>
            <h4>Web Chat</h4>
            <p>เบราว์เซอร์สำหรับศูนย์บริการหรือผู้ใช้ไฟฟ้า มี <code>choicePrompt</code> และปุ่มกดโต้ตอบชัดเจน</p>
        </div>

        <div class="channel-card ch-voice">
            <div class="ch-badge">ช่องทางที่ 2</div>
            <div class="ch-icon">📞</div>
            <h4>Voice (Gemini Live)</h4>
            <p>สายโทรศัพท์ 1129 หรือระบบเสียงสด มี <code>voiceGuidance</code> อ่านตัวเลือกครบสำหรับกรณีไร้จอ</p>
        </div>

        <div class="channel-card ch-line">
            <div class="ch-badge">ช่องทางที่ 3</div>
            <div class="ch-icon">📱</div>
            <h4>LINE Messaging</h4>
            <p>แอปพลิเคชันยอดนิยมของผู้ใช้ไฟฟ้า บังคับยืนยันผ่าน <strong>Postback Buttons</strong> ป้องกันการตีความผิด</p>
        </div>
    </div>

    <div class="funnel-middle">
        <div class="funnel-line"></div>
        <div class="funnel-gateway-badge">
            ⚡ <strong>MainAgentGateway Protocol</strong>: <code>handle_chat()</code> | <code>confirm_pending_action()</code> | <code>reject_pending_action()</code>
        </div>
        <div class="funnel-line"></div>
    </div>

    <div class="brain-card">
        <div class="brain-icon">🧠</div>
        <div class="brain-body">
            <h4>Main Agent (Single Source of Business Truth)</h4>
            <p>ทุก Bridge (VoiceBridge, LineBridge) <strong>ไม่มีสิทธิ์เข้าถึง Database หรือ ToolRegistry โดยตรง</strong> — เพิ่มช่องทางใหม่ในอนาคต (เช่น Mobile App กฟภ. หรือ Smart Speaker) เพียงเขียน Bridge สื่อสารกับ Gateway เท่านั้น ไม่ต้องแตะ Business Logic</p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 23,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): ประสบการณ์ผู้ใช้ Web Chat",
            "title": "Web Chat Interface: การโต้ตอบแบบมีโครงสร้าง",
            "subtitle": "choicePrompt ที่ปลอดภัยจาก Prompt Injection และปุ่มยืนยันที่เรียก API จริง",
            "content": """
<div class="webchat-demo-container">
    <div class="chat-mockup-window">
        <div class="mockup-header">
            <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
            <span class="mockup-title">⚡ PEA One Agent — Web Service Portal</span>
        </div>
        <div class="mockup-body">
            <div class="msg-bubble user-bubble">
                <div class="bubble-sender">ผู้ใช้ไฟฟ้า</div>
                <div class="bubble-text">ไฟดับแถวบ้านครับ เลขที่ผู้ใช้ไฟ 020012345678</div>
            </div>
            <div class="msg-bubble ai-bubble">
                <div class="bubble-sender">PEA One Agent</div>
                <div class="bubble-text">ตรวจสอบระบบ OMS พบว่ายังไม่มีการแจ้งเหตุในบริเวณหม้อแปลงของท่านครับ ได้จัดเตรียมรายการแจ้งเหตุไฟฟ้าดับให้เรียบร้อยแล้ว กรุณาตรวจทานและกดยืนยันครับ</div>
                <div class="mockup-action-card">
                    <div class="action-card-title">📋 รายการที่รอการยืนยัน (Pending Action)</div>
                    <div class="action-card-detail">เลขผู้ใช้ไฟ: 020012345678 | สถานที่: อ.เมือง จ.เชียงใหม่</div>
                    <div class="action-buttons-row">
                        <button class="mock-btn btn-confirm">✅ ยืนยันแจ้งไฟฟ้าดับ</button>
                        <button class="mock-btn btn-reject">❌ ยกเลิกรายการ</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="webchat-features-card">
        <h4>🔒 คุณลักษณะด้านความปลอดภัยของ Web UI</h4>
        <div class="wf-item">
            <strong>Catalog-Driven choicePrompt:</strong>
            <p>ตัวเลือกทั้งหมดมาจาก Backend Catalog กฟภ. ไม่ใช่ข้อความที่ LLM แต่งขึ้น ป้องกันการฉีดข้อความหลอก (Prompt Injection)</p>
        </div>
        <div class="wf-item">
            <strong>Explicit Endpoint Invocation:</strong>
            <p>ปุ่มยืนยันยิงตรงไปยัง <code>/api/v1/actions/{id}/confirm</code> เป็น HTTP Request แยกต่างหาก ไม่ใช่การพิมพ์ "ใช่/ตกลง" ในแชต</p>
        </div>
        <div class="wf-item">
            <strong>Resettable Demo Context:</strong>
            <p>มีปุ่ม Reset Demo ที่เรียก <code>/api/v1/reset</code> ล้าง In-Memory Store สำหรับให้กรรมการทดสอบซ้ำได้ทันที</p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 24,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: สถาปัตยกรรมเสียงเรียลไทม์",
            "title": "Voice Interface: Gemini Live & WebSocket",
            "subtitle": "ระบบเสียง Full-Duplex Low-Latency สำหรับสายโทรศัพท์ 1129 หรือการคุยผ่านเว็บ",
            "content": """
<div class="voice-arch-container">
    <div class="audio-pipeline-grid">
        <div class="audio-box input-audio">
            <div class="ab-badge">ไมโครโฟน / สายเข้า</div>
            <div class="ab-title">PCM16 16kHz Mono</div>
            <p>รับเสียงดิบของผู้ใช้ แปลงเป็น Binary Frame ส่งผ่าน WebSocket สด</p>
        </div>

        <div class="pipeline-arrow">➔</div>

        <div class="audio-box session-audio">
            <div class="ab-badge badge-purple">VoiceBridge Session</div>
            <div class="ab-title">Gemini Live Session</div>
            <div class="waveform-svg-box">
                <svg viewBox="0 0 100 24" width="120" height="24">
                    <rect x="5" y="6" width="4" height="12" fill="#6B3FA0" rx="2"/>
                    <rect x="15" y="2" width="4" height="20" fill="#8E54E9" rx="2"/>
                    <rect x="25" y="8" width="4" height="8" fill="#6B3FA0" rx="2"/>
                    <rect x="35" y="4" width="4" height="16" fill="#8E54E9" rx="2"/>
                    <rect x="45" y="1" width="4" height="22" fill="#6B3FA0" rx="2"/>
                    <rect x="55" y="5" width="4" height="14" fill="#8E54E9" rx="2"/>
                    <rect x="65" y="8" width="4" height="8" fill="#6B3FA0" rx="2"/>
                    <rect x="75" y="3" width="4" height="18" fill="#8E54E9" rx="2"/>
                    <rect x="85" y="6" width="4" height="12" fill="#6B3FA0" rx="2"/>
                </svg>
            </div>
            <p>ถอดเสียงเป็นข้อความ + สตรีมเสียงตอบกลับแบบ Gap-free</p>
        </div>

        <div class="pipeline-arrow">➔</div>

        <div class="audio-box output-audio">
            <div class="ab-badge badge-green">ลำโพง / หูฟัง</div>
            <div class="ab-title">PCM16 24kHz Mono</div>
            <p>เล่นเสียงตอบกลับอย่างเป็นธรรมชาติ ล้างคิวทันทีหากผู้ใช้พูดแทรก</p>
        </div>
    </div>

    <div class="voice-invariants-grid">
        <div class="vi-card">
            <h4>🎙️ 3 ฟังก์ชันเสียงที่ปลอดภัย</h4>
            <p>โมเดลเห็นเพียง <code>pea_agent_chat</code>, <code>pea_confirm_pending_action</code>, และ <code>pea_reject_pending_action</code> <strong>โดยไม่มีฟังก์ชันไหนรับ pendingActionId เลย</strong> — Bridge จะผูก ID ของเซสชันให้เอง ป้องกันโมเดลปลอม ID</p>
        </div>
        <div class="vi-card">
            <h4>⚡ Barge-in & Interruption</h4>
            <p>เมื่อผู้ใช้พูดแทรก (Barge-in) ระบบจะส่งเหตุการณ์ <code>audio.interrupted</code> ล้างคิวเสียงที่ค้างอยู่ทันที เพื่อให้การสนทนาลื่นไหลเหมือนคุยกับคนจริง</p>
        </div>
        <div class="vi-card">
            <h4>📢 Dynamic Voice Guidance</h4>
            <p>คำแนะนำการพูดตามอุปกรณ์: กรณี<strong>มีหน้าจอ</strong> AI จะบอกให้กดปุ่มยืนยันบนจอ แต่กรณี<strong>ไร้หน้าจอ (สายโทรศัพท์)</strong> AI จะอ่านตัวเลือกให้ผู้ใช้ฟังจนครบถ้วน</p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 25,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): โปรโตคอลระบบเสียง",
            "title": "Voice Interface: โปรโตคอลเหตุการณ์ (Event Protocol)",
            "subtitle": "โครงสร้างเหตุการณ์แบบ Event-Driven ผ่าน WebSocket /ws/live",
            "content": """
<div class="events-table-container">
    <table class="consulting-table events-table">
        <thead>
            <tr>
                <th style="width: 25%;">Event Type</th>
                <th style="width: 15%;">ทิศทาง</th>
                <th style="width: 35%;">ความหมายและหน้าที่</th>
                <th style="width: 25%;">Payload ตัวอย่าง</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="event-pill ep-ready">🟢 session.ready</span></td>
                <td>Server ➔ Client</td>
                <td>เชื่อมต่อ WebSocket และเตรียม Audio Pipeline พร้อมแล้ว</td>
                <td><code>{ "conversationId": "uuid" }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-trans">🎙️ transcript.user</span></td>
                <td>Server ➔ Client</td>
                <td>ข้อความที่ถอดเสียงจากคำพูดของผู้ใช้ไฟฟ้าสดๆ</td>
                <td><code>{ "text": "ไฟดับครับ" }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-trans">🤖 transcript.assistant</span></td>
                <td>Server ➔ Client</td>
                <td>ข้อความที่ AI กำลังจะเปล่งเสียงตอบกลับ</td>
                <td><code>{ "text": "รับทราบครับ..." }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-resp">⚡ agent.response</span></td>
                <td>Server ➔ Client</td>
                <td>ผลลัพธ์ทางธุรกิจจาก Main Agent (Chat/Confirm/Reject)</td>
                <td><code>{ "pendingAction": {...} }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-stop">✋ audio.interrupted</span></td>
                <td>Server ➔ Client</td>
                <td>ผู้ใช้พูดแทรก — ให้ Client หยุดเล่นเสียงและล้าง Buffer</td>
                <td><code>{ "reason": "barge_in" }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-complete">✅ turn.complete</span></td>
                <td>Server ➔ Client</td>
                <td>AI พูดจบประโยคของรอบการสนทนานั้น</td>
                <td><code>{ "turnId": "..." }</code></td>
            </tr>
            <tr>
                <td><span class="event-pill ep-err">⚠️ error</span></td>
                <td>Server ➔ Client</td>
                <td>รหัสข้อผิดพลาดมาตรฐาน: <code>no_pending_action</code>, <code>invalid_input</code></td>
                <td><code>{ "code": "no_pending" }</code></td>
            </tr>
        </tbody>
    </table>
</div>
"""
        },
        {
            "id": 26,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): ประสบการณ์ผู้ใช้ LINE",
            "title": "LINE Interface: ความปลอดภัยผ่าน Postback Buttons",
            "subtitle": "ยืนยันรายการผ่านปุ่ม Postback เท่านั้น — ประกาศไม่ตีความแชตอย่างชัดเจน",
            "content": """
<div class="line-interface-container">
    <div class="line-mockup-wrapper">
        <div class="line-mockup-card">
            <div class="line-header">
                <span class="line-logo">LINE</span>
                <span class="line-title">PEA Official Service</span>
            </div>
            <div class="line-chat-flow">
                <div class="line-bubble line-user">
                    แจ้งเรื่องร้องเรียนมิเตอร์ไฟฟ้าอ่านผิดครับ
                </div>
                <div class="line-bubble line-agent">
                    PEA One Agent ได้ร่างเคสร้องเรียน VOC ให้ท่านแล้วครับ กรุณาตรวจสอบและกดปุ่มยืนยันด้านล่างครับ<br><br>
                    <small style="color:#777;">[ข้อมูลจำลองเพื่อการทดสอบ • Simulation]</small>
                </div>
                <div class="line-postback-box">
                    <div class="postback-info"><strong>เคส VOC:</strong> ตรวจสอบมิเตอร์ผิดปกติ (CA: 020012345678)</div>
                    <div class="postback-btn-row">
                        <button class="line-btn btn-line-confirm">🔘 ยืนยันเปิดเคส</button>
                        <button class="line-btn btn-line-cancel">ยกเลิก</button>
                    </div>
                </div>
            </div>
            <div class="line-richmenu-preview" onclick="openImageModal('assets/line_richmenu.jpg', 'PEA Official LINE Rich Menu (6 หมวดบริการด่วน)')" title="คลิกดูภาพ Rich Menu ขนาดเต็ม">
                <img src="assets/line_richmenu.jpg" alt="PEA LINE Official Rich Menu" class="line-richmenu-img">
                <div class="richmenu-caption">⚡ PEA Official Rich Menu (6 เมนูด่วน)</div>
            </div>
        </div>
    </div>

    <div class="line-specs-card">
        <h4>🛡️ กฎความปลอดภัยของช่องทาง LINE</h4>
        <div class="ls-item">
            <strong>X-Line-Signature Verification:</strong>
            <p>ตรวจสอบลายเซ็น HMAC-SHA256 ของ Raw Body ทุก Request หากไม่ถูกต้องจะตัดทิ้งด้วย <strong>HTTP 403 Forbidden</strong> ทันทีแบบ Fail-Closed</p>
        </div>
        <div class="ls-item">
            <strong>No Free-Text Confirmation:</strong>
            <p>การตีความคำว่า "ใช่/ตกลง/เอาเลย" จากแชตเป็น <strong>Non-Goal</strong> เพื่อความปลอดภัยสูงสุด ต้องกดปุ่ม Postback ที่มี ID กำกับเท่านั้น</p>
        </div>
        <div class="ls-item">
            <strong>Background Processing & 200 Fast Return:</strong>
            <p>ตอบกลับ HTTP 200 ให้ LINE ภายใน 1 วินาทีเพื่อป้องกัน Timeout แล้วประมวลผล Agent Loop ใน Background พร้อมแสดง Loading Indicator</p>
        </div>
        <div class="ls-item">
            <strong>Simulation Tagging:</strong>
            <p>แสดงป้าย <code>[Simulation]</code> ทุกครั้งเมื่อผลลัพธ์เชื่อมต่อกับ Backend จำลอง เพื่อความโปร่งใสต่อผู้ใช้และกรรมการ</p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 27,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A: ตารางเปรียบเทียบช่องทาง",
            "title": "เปรียบเทียบความสามารถ 3 ช่องทางบริการ",
            "subtitle": "สรุปการปรับแต่ง UX ให้เหมาะสมกับข้อจำกัดของแต่ละช่องทาง โดยใช้สมองเดียวกัน",
            "content": """
<div class="channels-matrix-container">
    <table class="consulting-table matrix-table">
        <thead>
            <tr>
                <th style="width: 28%;">มิติคุณลักษณะ</th>
                <th style="width: 24%;">💻 Web Chat</th>
                <th style="width: 24%;">🎙️ Voice (Gemini Live)</th>
                <th style="width: 24%;">📱 LINE Messaging</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>1. choicePrompt รูปแบบปุ่ม</strong></td>
                <td><span class="status-pill status-pass">✅ มี (คลิกเลือกได้)</span></td>
                <td><span class="status-pill status-fail">❌ ไม่มี (ใช้เสียงอ่านแทน)</span></td>
                <td><span class="status-pill status-pass">✅ มี (Quick Reply)</span></td>
            </tr>
            <tr>
                <td><strong>2. วิธียืนยันรายการ (Confirm)</strong></td>
                <td><span class="status-pill status-pass">🔘 ปุ่มกด / API Endpoint</span></td>
                <td><span class="status-pill status-pass">🗣️ ยืนยันด้วยเสียง (Session-bound)</span></td>
                <td><span class="status-pill status-pass">🔘 ปุ่ม Postback เท่านั้น</span></td>
            </tr>
            <tr>
                <td><strong>3. บังคับอ่านตัวเลือกให้ครบ</strong></td>
                <td><span class="status-pill status-neutral">⚪ ไม่จำเป็น (เห็นบนจอ)</span></td>
                <td><span class="status-pill status-amber">⚠️ บังคับอ่าน (กรณีไร้จอ)</span></td>
                <td><span class="status-pill status-neutral">⚪ ไม่จำเป็น (อ่านเองบนจอ)</span></td>
            </tr>
            <tr>
                <td><strong>4. การส่งข้อมูลสด (Realtime)</strong></td>
                <td>HTTP Request / Response</td>
                <td>WebSocket Duplex (PCM16)</td>
                <td>Webhook + Push Message</td>
            </tr>
            <tr>
                <td><strong>5. กลไกจัดการข้อความแทรก</strong></td>
                <td>ส่งคำขอใหม่</td>
                <td>Barge-in (Flush Queue ทันที)</td>
                <td>ต่อคิวข้อความใหม่</td>
            </tr>
        </tbody>
    </table>
    <div class="matrix-summary-bar">
        💡 <strong>บทสรุป:</strong> ช่องทางต่างกันที่การนำเสนอ (Presentation Layer) แต่กระบวนการตัดสินใจและเครื่องมือหลังบ้านเป็นตัวเดียวกัน 100%
    </div>
</div>
"""
        },
        {
            "id": 28,
            "section": 4,
            "theme": "dark",
            "rubric": "เกณฑ์ B (10 คะแนน): นวัตกรรมระบบปลั๊กอิน",
            "title": "ทำไมต้องมีระบบปลั๊กอิน (Plugin Architecture)?",
            "subtitle": "ระบบไฟฟ้า กฟภ. ไม่ได้มีแค่ OMS หรือ VOC — ต้องขยายสู่ระบบอนาคตได้โดยไม่แก้โค้ดแกนกลาง",
            "content": """
<div class="transition-container">
    <div class="transition-card">
        <div class="transition-icon-large">
            <svg viewBox="0 0 24 24" width="72" height="72" fill="#E2D9F3"><path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5C13 2.12 11.88 1 10.5 1S8 2.12 8 3.5V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5c1.49 0 2.7 1.21 2.7 2.7s-1.21 2.7-2.7 2.7H2V20c0 1.1.9 2 2 2h3.8v-1.5c0-1.49 1.21-2.7 2.7-2.7 1.49 0 2.7 1.21 2.7 2.7V22H17c1.1 0 2-.9 2-2v-4h1.5c1.38 0 2.5-1.12 2.5-2.5s-1.12-2.5-2.5-2.5z"/></svg>
        </div>
        <h2 class="transition-title">จุดตายของ Agent ทั่วไปคือ "เพิ่มระบบใหม่ = รื้อโค้ดเดิม"</h2>
        <p class="transition-quote">
            "ในอนาคต กฟภ. จะมีระบบชำระเงิน Sabuy, ระบบ Smart Meter AMI, หรือระบบสถานีชาร์จ PEA VOLTA...<br>
            ถ้าทุกครั้งที่ต่อระบบใหม่ต้องแก้โค้ด Main Agent ระบบจะพังง่ายและเสี่ยงอย่างยิ่ง<br>
            <strong>PEA One Agent จึงสร้างระบบ Declarative Plugin Manifest ขึ้นมา</strong>"
        </p>

        <div class="plugin-promise-grid">
            <div class="promise-item">
                <span class="promise-icon">📜</span>
                <strong>Declarative Manifest</strong>
                <p>ประกาศความสามารถผ่าน <code>plugin.yaml</code> สื่อสารให้ LLM เข้าใจ</p>
            </div>
            <div class="promise-item">
                <span class="promise-icon">🛡️</span>
                <strong>Fail-Closed Validation</strong>
                <p>ถ้า Manifest ไม่ตรงกับโค้ดจริง ระบบจะหยุดทำงานทันทีตั้งแต่เริ่ม</p>
            </div>
            <div class="promise-item">
                <span class="promise-icon">⚡</span>
                <strong>Zero Core Modification</strong>
                <p>เพิ่มปลั๊กอินใหม่โดยไม่ต้องแตะ <code>main_agent.py</code> เลยแม้แต่บรรทัดเดียว</p>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 29,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): Declarative Manifest",
            "title": "Plugin Manifest: ตัวอย่างจริง (app/plugins/oms/plugin.yaml)",
            "subtitle": "ประกาศเครื่องมือใหม่แบบ Declarative โดยไม่เก็บ Secret และบังคับ Internal Submit",
            "content": """
<div class="yaml-manifest-container">
    <div class="code-card yaml-code-card">
        <div class="code-header">
            <span>app/plugins/oms/plugin.yaml — Production Manifest</span>
            <span class="code-tag">YAML Specification</span>
        </div>
        <pre class="code-block"><code><span class="yaml-key">apiVersion</span>: <span class="val">pea.one/v1</span>
<span class="yaml-key">kind</span>: <span class="val">Plugin</span>
<span class="yaml-key">metadata</span>:
  <span class="yaml-key">id</span>: <span class="val">oms_tool</span>
  <span class="yaml-key">name</span>: <span class="val">OMS Outage</span>
  <span class="yaml-key">enabled</span>: <span class="val">true</span>
  <span class="yaml-key">description</span>: <span class="val">ตรวจเหตุไฟฟ้าขัดข้องด้วยเลขผู้ใช้ไฟ 12 หลัก...</span>
<span class="yaml-key">runtime</span>:
  <span class="yaml-key">factory</span>: <span class="val">app.plugins.oms.factory:create_plugin</span>
<span class="yaml-key">configuration</span>:
  <span class="yaml-key">baseUrlEnv</span>: <span class="val">OMS_BASE_URL</span>    <span class="comment"># เก็บเฉพาะชื่อ ENV ไม่เก็บ Secret ในไฟล์</span>
  <span class="yaml-key">apiKeyEnv</span>: <span class="val">OMS_API_KEY</span>
<span class="yaml-key">operations</span>:
  - <span class="yaml-key">action</span>: <span class="val">get_outage_by_ca</span>
    <span class="yaml-key">exposure</span>: <span class="val">llm</span>              <span class="comment"># LLM เรียกอ่านข้อมูลได้</span>
    <span class="yaml-key">mode</span>: <span class="val">read</span>
  - <span class="yaml-key">action</span>: <span class="val">prepare_outage_with_ca</span>
    <span class="yaml-key">exposure</span>: <span class="val">llm</span>              <span class="comment"># LLM เรียกร่างรายการได้</span>
    <span class="yaml-key">mode</span>: <span class="val">prepare</span>
    <span class="yaml-key">submitAction</span>: <span class="val">submit_outage_with_ca</span>
  - <span class="yaml-key">action</span>: <span class="val">submit_outage_with_ca</span>
    <span class="yaml-key">exposure</span>: <span class="val">internal</span>         <span class="comment"># 🔒 บังคับ Internal! LLM ไม่มีสิทธิ์เรียกตรง</span>
    <span class="yaml-key">mode</span>: <span class="val">submit</span></code></pre>
    </div>
</div>
"""
        },
        {
            "id": 30,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): วุฒิภาวะวิศวกรรมความปลอดภัย",
            "title": "Plugin Loader: 7-Step Fail-Closed Pipeline",
            "subtitle": "Manifest ผิด = ระบบไม่ Start — ดักจับข้อผิดพลาดตั้งแต่ก่อนรันจริงใน app/plugins/loader.py",
            "content": """
<div class="loader-pipeline-container">
    <div class="pipeline-7steps-flow">
        <div class="pipe-step">
            <div class="p-step-num">1</div>
            <div class="p-step-title">Glob plugin.yaml</div>
            <div class="p-step-desc">อ่านไฟล์ทุกโฟลเดอร์ ปลั๊กอินที่ <code>enabled: false</code> ข้ามไปอย่างปลอดภัย</div>
        </div>
        <div class="pipe-fail">❌ ไม่พบ / อ่านไม่ได้</div>

        <div class="pipe-step">
            <div class="p-step-num">2</div>
            <div class="p-step-title">Model Validate</div>
            <div class="p-step-desc">ตรวจสอบ Schema เบื้องต้นด้วย <code>PluginManifest.model_validate</code></div>
        </div>
        <div class="pipe-fail">❌ Schema ผิด</div>

        <div class="pipe-step">
            <div class="p-step-num">3</div>
            <div class="p-step-title">Contract Matching</div>
            <div class="p-step-desc">ตรวจ Action เทียบกับ <code>app/contracts.py</code> ต้องมี Pydantic Model รองรับจริง</div>
        </div>
        <div class="pipe-fail">❌ Action ไร้สัญญา</div>

        <div class="pipe-step">
            <div class="p-step-num">4</div>
            <div class="p-step-title">Action Completeness</div>
            <div class="p-step-desc">ตรวจสอบว่าประกาศครบตามที่โค้ดรองรับ ไม่ขาดและไม่เกิน (Missing / Unknown = Error)</div>
        </div>
        <div class="pipe-fail">❌ สัญญาไม่ตรง</div>

        <div class="pipe-step">
            <div class="p-step-num">5</div>
            <div class="p-step-title">Submit Exposure Check</div>
            <div class="p-step-desc">บังคับกฎเหล็ก: ทุก <code>submit action</code> ต้องเป็น <code>exposure: internal</code> เท่านั้น</div>
        </div>
        <div class="pipe-fail">❌ Submit เปิดให้ LLM</div>

        <div class="pipe-step">
            <div class="p-step-num">6</div>
            <div class="p-step-title">Trusted Factory Root</div>
            <div class="p-step-desc">ตรวจว่า Factory Module ต้องอยู่ใต้ <code>app.plugins.*</code> ป้องกันโค้ดแปลกปลอม</div>
        </div>
        <div class="pipe-fail">❌ Factory นอกพื้นที่</div>

        <div class="pipe-step">
            <div class="p-step-num">7</div>
            <div class="p-step-title">Runtime Protocol Check</div>
            <div class="p-step-desc">รัน Factory ตรวจว่ามี <code>execute</code>, <code>reset</code> และชื่อตรงกับ <code>metadata.id</code></div>
        </div>
        <div class="pipe-fail">❌ ไม่ครบ Protocol</div>
    </div>

    <div class="pipeline-result-bar">
        🛡️ <strong>Fail-Closed Principle:</strong> หากขั้นตอนใดล้มเหลว ระบบจะปฏิเสธการเริ่มระบบ (Startup Crash) ทันที ป้องกันข้อผิดพลาดหลุดไปถึงผู้ใช้
    </div>
</div>
"""
        },
        {
            "id": 31,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): ความสามารถในการขยายระบบ",
            "title": "CLI Scaffolding: ./scripts/add-plugin",
            "subtitle": "คำสั่ง CLI อัตโนมัติที่พิสูจน์แล้วว่าสร้างปลั๊กอินใหม่ได้ใน 6 ขั้นตอนโดยไม่แตะ Main Agent",
            "content": """
<div class="cli-demo-container">
    <div class="terminal-window">
        <div class="term-header">
            <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
            <span class="term-title">bash — ./scripts/add-plugin sabuy_v2 --preview</span>
        </div>
        <div class="term-body">
            <div class="term-line prompt-line">$ ./scripts/add-plugin sabuy_v2 --preview</div>
            <div class="term-line success-line">--- app/plugins/sabuy_v2/__init__.py ---</div>
            <div class="term-line info-line">&quot;&quot;&quot;ปลั๊กอิน sabuy_v2_tool ที่โหลดผ่าน manifest&quot;&quot;&quot;</div>
            <div class="term-line success-line">--- app/plugins/sabuy_v2/plugin.yaml ---</div>
            <div class="term-line info-line">apiVersion: pea.one/v1</div>
            <div class="term-line info-line">kind: Plugin</div>
            <div class="term-line info-line">metadata: { id: sabuy_v2_tool, enabled: false, category: operational }</div>
            <div class="term-line info-line">runtime: { factory: app.plugins.sabuy_v2.factory:create_plugin }</div>
            <div class="term-line success-line">--- app/plugins/sabuy_v2/factory.py ---</div>
            <div class="term-line info-line">def create_plugin(settings: Any) -> PluginRuntime:</div>
            <div class="term-line info-line">    tool = Sabuy_v2Tool()</div>
            <div class="term-line info-line">    return PluginRuntime(tool=tool)</div>
            <div class="term-line done-line">✔ Preview complete. Run without --preview to generate files.</div>
        </div>
    </div>

    <div class="cli-steps-card">
        <h4>⚡ 6 ขั้นตอนเพิ่มระบบใหม่สู่ PEA One Agent</h4>
        <div class="cs-step"><strong>1. ประกาศ Contract:</strong> เพิ่ม Pydantic Model ใน <code>app/contracts.py</code></div>
        <div class="cs-step"><strong>2. รัน CLI Tool:</strong> <code>./scripts/add-plugin &lt;ชื่อ&gt;</code> เจนโครงสร้างไฟล์อัตโนมัติ</div>
        <div class="cs-step"><strong>3. เขียน Tool Class:</strong> จัดการเชื่อมต่อ HTTP API และ Error Mapping</div>
        <div class="cs-step"><strong>4. ระบุ Description:</strong> อธิบายความสามารถให้ LLM เลือกใช้งานได้ถูกต้อง</div>
        <div class="cs-step"><strong>5. ตั้งค่า Config:</strong> เพิ่ม Base URL / API Key ใน Settings</div>
        <div class="cs-step"><strong>6. ตั้ง <code>enabled: true</code>:</strong> รีสตาร์ต Server — Main Agent จะมองเห็นและใช้งานได้ทันที!</div>
    </div>
</div>
"""
        },
        {
            "id": 32,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A: ปลั๊กอินที่พร้อมใช้งาน",
            "title": "ปลั๊กอินที่มีอยู่วันนี้: พิสูจน์การทำงานจริง",
            "subtitle": "ระบบรองรับหลายปลั๊กอินพร้อมกัน และพิสูจน์การแยกส่วนที่สมบูรณ์ด้วย Dormant Plugin",
            "content": """
<div class="existing-plugins-container">
    <div class="three-plugins-cards">
        <div class="plugin-status-card card-active">
            <div class="psc-top">
                <span class="status-pill status-pass">✅ ENABLED</span>
                <span class="psc-id">oms_tool</span>
            </div>
            <h3>OMS Outage Service</h3>
            <p class="psc-desc">เชื่อมต่อระบบไฟฟ้าขัดข้องของ กฟภ. ผ่าน REST API ด้วย HTTPX</p>
            <div class="psc-metrics">
                <div class="pm-box">
                    <span class="pm-num">5</span>
                    <span class="pm-lbl">Operations</span>
                </div>
                <div class="pm-box">
                    <span class="pm-num">2 Pairs</span>
                    <span class="pm-lbl">Prepare/Submit</span>
                </div>
            </div>
            <div class="psc-ops">
                <div>• <code>get_outage_by_ca</code> (Read)</div>
                <div>• <code>prepare_outage_with_ca</code> (Prepare)</div>
                <div>• <code>submit_outage_with_ca</code> (Submit/Internal)</div>
            </div>
        </div>

        <div class="plugin-status-card card-active">
            <div class="psc-top">
                <span class="status-pill status-pass">✅ ENABLED</span>
                <span class="psc-id">voc_tool</span>
            </div>
            <h3>VOC Feedback Service</h3>
            <p class="psc-desc">ระบบรับเรื่องร้องเรียนและข้อเสนอแนะบริการ เชื่อมต่อ SimulatedVocBackend</p>
            <div class="psc-metrics">
                <div class="pm-box">
                    <span class="pm-num">4</span>
                    <span class="pm-lbl">Operations</span>
                </div>
                <div class="pm-box">
                    <span class="pm-num">1 Pair</span>
                    <span class="pm-lbl">Prepare/Submit</span>
                </div>
            </div>
            <div class="psc-ops">
                <div>• <code>list_categories</code> (Read)</div>
                <div>• <code>prepare_case</code> (Prepare)</div>
                <div>• <code>submit_case</code> (Submit/Internal)</div>
                <div>• <code>get_case</code> (Read/Tracking)</div>
            </div>
        </div>

        <div class="plugin-status-card card-dormant">
            <div class="psc-top">
                <span class="status-pill status-neutral">⏸ DORMANT</span>
                <span class="psc-id">sabuy_tool</span>
            </div>
            <h3>Sabuy Payment Service</h3>
            <p class="psc-desc">ระบบตรวจสอบบิลและชำระค่าไฟฟ้า เขียนโค้ดและ Unit Test ครบ 14 เทสแล้ว</p>
            <div class="psc-metrics">
                <div class="pm-box">
                    <span class="pm-num">Ready</span>
                    <span class="pm-lbl">Code & Tests</span>
                </div>
                <div class="pm-box">
                    <span class="pm-num">False</span>
                    <span class="pm-lbl">enabled: false</span>
                </div>
            </div>
            <div class="psc-ops">
                <div>• พิสูจน์ว่าปลั๊กอินที่ยังไม่เปิดใช้งาน</div>
                <div>• อยู่ร่วมใน Repository ได้อย่างปลอดภัย</div>
                <div>• เปิดใช้งานได้ทันทีเมื่อ กฟภ. พร้อม</div>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 33,
            "section": 4,
            "theme": "light",
            "rubric": "เกณฑ์ A: ตัวอย่างกระบวนการ VOC",
            "title": "ตัวอย่างกระบวนงาน VOC: อ่าน ร่าง ยืนยัน ส่ง",
            "subtitle": "การประยุกต์ใช้ Safe Pattern เดียวกันกับระบบงานร้องเรียนและบริการ กฟภ.",
            "content": """
<div class="voc-flow-container">
    <div class="voc-sequence-grid">
        <div class="seq-card sc-1">
            <div class="sc-badge">ขั้นที่ 1: ดึงแค็ตตาล็อก</div>
            <h4>list_categories (Read)</h4>
            <p>ดึงหมวดหมู่เรื่องร้องเรียนทางการจาก VOC Backend เพื่อให้ LLM นำเสนอตัวเลือกที่ถูกต้อง</p>
            <div class="sc-exposure">Exposure: LLM</div>
        </div>

        <div class="seq-card sc-2">
            <div class="sc-badge badge-amber">ขั้นที่ 2: จัดเตรียมเคส</div>
            <h4>prepare_case (Prepare)</h4>
            <p>รวบรวมข้อมูล ชื่อ เบอร์ติดต่อ รายละเอียดเคส สร้าง Preview ให้ลูกค้าตรวจทาน</p>
            <div class="sc-exposure">Exposure: LLM</div>
        </div>

        <div class="seq-card sc-3">
            <div class="sc-badge badge-purple">ขั้นที่ 3: มนุษย์ยืนยัน</div>
            <h4>confirm endpoint</h4>
            <p>ผู้ใช้กดปุ่มยืนยันผ่าน Web หรือ LINE Postback ตรวจสอบความถูกต้องของข้อมูล</p>
            <div class="sc-exposure">Action: Human Decision</div>
        </div>

        <div class="seq-card sc-4">
            <div class="sc-badge badge-green">ขั้นที่ 4: ส่งข้อมูลจริง</div>
            <h4>submit_case (Submit)</h4>
            <p>ส่งข้อมูลเข้าระบบ VOC จริง ได้เลขที่คำร้อง (Case ID) สำหรับติดตามผล</p>
            <div class="sc-exposure">Exposure: Internal Only</div>
        </div>
    </div>

    <div class="voc-takeaway-bar">
        ⚡ <strong>Reusable Engineering Pattern:</strong> ไม่ว่าจะเป็นระบบแจ้งไฟดับ (OMS), รับเรื่องร้องเรียน (VOC) หรือชำระเงิน (Sabuy) ล้วนใช้สถาปัตยกรรมความปลอดภัยเดียวกันทั้งองค์กร
    </div>
</div>
"""
        }
    ]
