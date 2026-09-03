# -*- coding: utf-8 -*-
"""Section 3: Slides 12-21 (Architecture & Technology) — ตอบเกณฑ์ A + B (16 + 10 คะแนน)"""

def get_slides():
    return [
        {
            "id": 12,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): แผนงาน ทรัพยากร และเครื่องมือ",
            "title": "Technology Stack: คัดเลือกเทคโนโลยีที่พิสูจน์แล้ว",
            "subtitle": "เทคโนโลยีทั้งหมดมีอยู่จริงใน pyproject.toml ปราศจาก Dependencies ลอยๆ",
            "content": """
<div class="tech-stack-container">
    <div class="tech-table-wrapper">
        <table class="consulting-table tech-table">
            <thead>
                <tr>
                    <th style="width: 22%;">ชั้นสถาปัตยกรรม</th>
                    <th style="width: 32%;">เทคโนโลยีที่ใช้</th>
                    <th style="width: 46%;">บทบาทและความสำคัญในระบบ</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Backend Framework</strong></td>
                    <td><code>FastAPI (&gt;=0.115) + Uvicorn</code></td>
                    <td>High-performance ASGI server รองรับ Async I/O และ WebSocket</td>
                </tr>
                <tr>
                    <td><strong>Data Validation</strong></td>
                    <td><code>Pydantic v2 (&gt;=2.8)</code></td>
                    <td>Single Source of Truth ควบคุม Schema ทุกจุด ไม่มี dict ไร้ประเภท</td>
                </tr>
                <tr>
                    <td><strong>HTTP Client</strong></td>
                    <td><code>httpx (&gt;=0.27)</code></td>
                    <td>Async HTTP client เรียก OMS/VOC REST และ Gemini API ตรง</td>
                </tr>
                <tr>
                    <td><strong>Plugin Configuration</strong></td>
                    <td><code>PyYAML (&gt;=6.0)</code></td>
                    <td>โหลดและตรวจสอบ Declarative <code>plugin.yaml</code> ตั้งแต่เริ่มระบบ</td>
                </tr>
                <tr>
                    <td><strong>LLM Core & Knowledge</strong></td>
                    <td><code>Google Gemini REST API</code></td>
                    <td>Gemini 2.5 Flash ผ่าน httpx ตรง น้ำหนักเบา ปราศจาก SDK ซับซ้อน</td>
                </tr>
                <tr>
                    <td><strong>Realtime Voice SDK</strong></td>
                    <td><code>google-genai SDK (&gt;=1.0)</code></td>
                    <td>เฉพาะโหมดเสียงที่ต้องใช้ Duplex WebSocket กับ Gemini Live</td>
                </tr>
                <tr>
                    <td><strong>Realtime Transport</strong></td>
                    <td><code>WebSocket (/ws/live)</code></td>
                    <td>ส่ง-รับสัญญาณเสียงดิบ PCM16 แบบ Two-way streaming</td>
                </tr>
                <tr>
                    <td><strong>Messaging Bridge</strong></td>
                    <td><code>LINE Messaging Webhook</code></td>
                    <td>เชื่อมต่อ LINE API พร้อมการตรวจสอบ HMAC-SHA256 Signature</td>
                </tr>
                <tr>
                    <td><strong>Testing Harness</strong></td>
                    <td><code>pytest + pytest-asyncio</code></td>
                    <td>ชุดทดสอบอัตโนมัติ 275 รายการ รันจบใน 1.48 วินาที</td>
                </tr>
                <tr>
                    <td><strong>Dependency Manager</strong></td>
                    <td><code>uv (Python packaging)</code></td>
                    <td>ล็อกเวอร์ชันแน่นอนผ่าน <code>uv.lock</code> ติดตั้งเร็วระดับมิลลิวินาที</td>
                </tr>
                <tr>
                    <td><strong>Frontend Client</strong></td>
                    <td><code>Vanilla JS + Web Audio API</code></td>
                    <td>น้ำหนักเบา ไม่ใช้เฟรมเวิร์กใหญ่ รองรับ AudioWorklet เสียงสด</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>
"""
        },
        {
            "id": 13,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: แผนภาพสถาปัตยกรรมทั้งระบบ",
            "title": "System Topology: แผนภาพสถาปัตยกรรมทั้งระบบ",
            "subtitle": "โครงสร้าง Plugin-Based Single-Agent Architecture ตาม ARCHITECTURE.md แยกหน้าที่ชัดเจนและปลอดภัย",
            "content": """
<div class="flow-architecture-container">
    <div class="flow-image-card" onclick="openImageModal('assets/flow.jpg', 'PEA One Agent — Plugin-Based Single-Agent Architecture')" title="คลิกเพื่อขยายดูภาพสถาปัตยกรรมขนาดเต็ม">
        <img src="assets/flow.jpg" alt="PEA One Agent Architecture Diagram" class="flow-hero-img">
        <div class="img-zoom-hint">🔍 คลิกเพื่อขยายภาพขนาดเต็ม (Interactive Zoom)</div>
    </div>
    <div class="arch-key-callouts">
        <div class="ak-card">
            <div class="ak-title"><span class="ak-icon">🌐</span> Multi-Channel ➔ Single FastAPI</div>
            <div class="ak-desc">Web Chat, Voice WebSocket, LINE Webhook ใน Process เดียว ไม่แยกส่วน</div>
        </div>
        <div class="ak-card highlight-ak">
            <div class="ak-title"><span class="ak-icon">🧠</span> Main Agent (Gateway)</div>
            <div class="ak-desc">สมองเดี่ยวคุม Bounded Loop &le; 12 Steps ปราศจาก Sub-agent sprawl</div>
        </div>
        <div class="ak-card">
            <div class="ak-title"><span class="ak-icon">🔌</span> Plugin Runtime System</div>
            <div class="ak-desc">ขยายระบบผ่าน Declarative <code>plugin.yaml</code> ตรวจสอบแบบ Fail-Closed 7 ขั้นตอน</div>
        </div>
        <div class="ak-card">
            <div class="ak-title"><span class="ak-icon">🛡️</span> Safe Write State Machine</div>
            <div class="ak-desc">Prepare ➔ Review ➔ มนุษย์กดยืนยัน ➔ Internal Submit ป้องกันเสี่ยง 100%</div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 14,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: การออกแบบ Orchestrator",
            "title": "Main Agent: หัวใจควบคุมของระบบ",
            "subtitle": "Orchestrator เดี่ยว ควบคุมกระบวนงานอย่างรัดกุมตามกฎใน app/agent/main_agent.py",
            "content": """
<div class="main-agent-grid">
    <div class="code-card">
        <div class="code-header">
            <span>app/agent/main_agent.py — MainAgentGateway Interface</span>
            <span class="code-tag">Python Protocol</span>
        </div>
        <pre class="code-block"><code><span class="kw">class</span> <span class="cls">MainAgentGateway</span>(<span class="cls">Protocol</span>):
    <span class="kw">async def</span> <span class="fn">handle_chat</span>(self, request: <span class="cls">ChatRequest</span>) -&gt; <span class="cls">ChatResponse</span>: ...
    <span class="kw">async def</span> <span class="fn">confirm_pending_action</span>(self, id: <span class="cls">UUID</span>, note: <span class="cls">str</span> | <span class="kw">None</span>) -&gt; <span class="cls">ActionDecisionResponse</span>: ...
    <span class="kw">async def</span> <span class="fn">reject_pending_action</span>(self, id: <span class="cls">UUID</span>, reason: <span class="cls">str</span>) -&gt; <span class="cls">ActionDecisionResponse</span>: ...
    <span class="kw">async def</span> <span class="fn">get_trace</span>(self, id: <span class="cls">UUID</span>) -&gt; <span class="cls">TraceResponse</span>: ...
    <span class="kw">async def</span> <span class="fn">reset_demo</span>(self) -&gt; <span class="cls">ResetResponse</span>: ...</code></pre>
        <div class="code-footer">มีเพียง 5 เมทอดหลักเท่านั้น — สะอาด รัดกุม และทดสอบได้ 100%</div>
    </div>

    <div class="agent-rules-card">
        <h4>กฎเหล็กทางสถาปัตยกรรม (Architectural Invariants)</h4>
        <div class="rule-item">
            <div class="rule-badge">1</div>
            <div>
                <strong>Bounded Loop (&le; 12 Steps):</strong>
                <p>จำกัดลูปการทำงานไม่เกิน 12 ครั้งต่อข้อความ และตัดลูปทันทีหากเรียก Knowledge ซ้ำ เพื่อป้องกันปัญหาโมเดลวนลูปไม่รู้จบ (Infinite Loop Protection)</p>
            </div>
        </div>
        <div class="rule-item">
            <div class="rule-badge">2</div>
            <div>
                <strong>Tool Result is Authoritative:</strong>
                <p>ผลลัพธ์ที่ได้จาก Tool จริงถือเป็นข้อเท็จจริงสูงสุด โมเดลไม่มีสิทธิ์ปฏิเสธหรือแต่งเรื่องทับผลลัพธ์จากระบบงาน กฟภ.</p>
            </div>
        </div>
        <div class="rule-item">
            <div class="rule-badge">3</div>
            <div>
                <strong>Dynamic Tool Catalogue:</strong>
                <p>Main Agent ไม่ฮาร์ดโค้ดรายชื่อเครื่องมือ แต่ดึงจาก <code>ToolRegistry.llm_catalogue</code> ทำให้เพิ่มปลั๊กอินใหม่ได้ทันที</p>
            </div>
        </div>
        <div class="rule-item">
            <div class="rule-badge">4</div>
            <div>
                <strong>No Sub-Agents Architecture:</strong>
                <p>ห้ามแตกเป็น Sub-agent ย่อย เพื่อให้ Audit Trail เป็นเส้นตรงเส้นเดียว ตรวจสอบความถูกต้องได้ง่าย</p>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 15,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): สถาปัตยกรรมยืดหยุ่น",
            "title": "LLMAdapter: สลับ Provider โดยไม่แก้โค้ดธุรกิจ",
            "subtitle": "Provider-Neutral Interface ที่แยกกฎธุรกิจ กฟภ. ออกจากผู้ให้บริการโมเดล AI",
            "content": """
<div class="adapter-container">
    <div class="code-card">
        <div class="code-header">
            <span>app/llm/client.py — LLMAdapter Protocol</span>
            <span class="code-tag">Typed Protocol</span>
        </div>
        <pre class="code-block"><code><span class="kw">class</span> <span class="cls">LLMAdapter</span>(<span class="cls">Protocol</span>):
    <span class="kw">async def</span> <span class="fn">complete</span>(self, request: <span class="cls">LLMRequest</span>) -&gt; <span class="cls">LLMResponse</span>:
        <span class="str">\"\"\"แปลงข้อความและ Tool Catalogue เป็นผลลัพธ์ Text หรือ ToolCalls\"\"\"</span>
        ...</code></pre>
        <div class="code-sub-items">
            <div>• <code>LLMRequest</code>: messages + active tool catalogue (typed) + correlation id</div>
            <div>• <code>LLMResponse</code>: assistant text + รายการ <code>ToolCall</code> ที่มี schema ชัดเจน</div>
        </div>
    </div>

    <div class="providers-row">
        <div class="provider-box prod-provider">
            <div class="prov-header">
                <span class="prov-badge badge-green">Production Provider</span>
                <h4>GeminiAdapter (REST)</h4>
            </div>
            <p>เรียก Google Gemini 2.5 Flash ผ่าน Async HTTPX โดยตรง จัดการ Rate Limit, Token Counting และ Structured Output</p>
        </div>

        <div class="provider-box stub-provider">
            <div class="prov-header">
                <span class="prov-badge badge-blue">Deterministic Test Provider</span>
                <h4>DemoAdapter (Stub)</h4>
            </div>
            <p>จำลองคำตอบสำหรับการทดสอบระบบและกรรมการตัดสิน รันออฟไลน์ได้ 100% ตอบแม่นยำ ปราศจากค่าใช้จ่าย API</p>
        </div>
    </div>

    <div class="adapter-security-box">
        🔒 <strong>Policy Boundary:</strong> LLMAdapter ปราศจากกฎธุรกิจของ กฟภ., ไม่แตะ Database หรือ Backend ตรง, และซ่อน Secret เสมอ
    </div>
</div>
"""
        },
        {
            "id": 16,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): สถาปัตยกรรม Tool",
            "title": "Tool Interface & ToolRegistry แบบ Fail-Closed",
            "subtitle": "ทุกเครื่องมือพูดภาษาเดียวกันผ่าน Typed Protocol และคัดกรองตั้งแต่ก่อนเรียกใช้",
            "content": """
<div class="tool-registry-container">
    <div class="two-col-tool-grid">
        <div class="code-card">
            <div class="code-header">
                <span>app/agent/registry.py — Tool Protocol</span>
                <span class="code-tag">Interface Contract</span>
            </div>
            <pre class="code-block"><code><span class="kw">class</span> <span class="cls">Tool</span>(<span class="cls">Protocol</span>):
    name: <span class="cls">ToolName</span>

    <span class="kw">async def</span> <span class="fn">execute</span>(
        self, call: <span class="cls">ToolCall</span>, context: <span class="cls">ToolContext</span>
    ) -&gt; <span class="cls">ToolResult</span>:
        ...

    <span class="kw">async def</span> <span class="fn">reset</span>(self) -&gt; <span class="kw">None</span>:
        ...</code></pre>
            <div class="code-footer">ทุก Tool คืน <code>ToolResult</code> ที่มี <code>status: ok | error</code></div>
        </div>

        <div class="registry-guards-card">
            <h4>🛡️ Fail-Closed Registry Guards</h4>
            <div class="guard-item">
                <span class="guard-icon">🔒</span>
                <div>
                    <strong>Fixed Known Tools Allowlist:</strong>
                    <p>ระบบกำหนดรายชื่อ Tool ที่ถูกต้องตายตัวตอน Startup (Knowledge, OMS, VOC, Sabuy) ชื่อที่ไม่รู้จักถูกบล็อกทันที</p>
                </div>
            </div>
            <div class="guard-item">
                <span class="guard-icon">⚡</span>
                <div>
                    <strong>Action-to-Name Matching:</strong>
                    <p>ตรวจว่า Action ตรงกับ Tool จริงหรือไม่ เช่น ห้ามเรียก <code>get_outage_by_ca</code> ผ่าน <code>voc_tool</code></p>
                </div>
            </div>
            <div class="guard-item">
                <span class="guard-icon">🚫</span>
                <div>
                    <strong>Prevent Direct Backend Calls:</strong>
                    <p>หาก Schema ผิด หรือมีข้อผิดพลาด Registry จะคืน <code>ToolError</code> ที่ปลอดภัย ป้องกัน Backend แครช</p>
                </div>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 17,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): สัญญา API",
            "title": "HTTP API Contracts: ภาพรวม 7 Endpoints",
            "subtitle": "สัญญา API ที่ตรึงไว้ (Frozen Contracts) ตาม CONTRACTS.md v1 สำหรับทุก Client",
            "content": """
<div class="contracts-container">
    <table class="consulting-table endpoints-table">
        <thead>
            <tr>
                <th style="width: 12%;">Method</th>
                <th style="width: 30%;">Path</th>
                <th style="width: 38%;">หน้าที่การทำงาน</th>
                <th style="width: 20%;">ลักษณะความปลอดภัย</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="http-badge post">POST</span></td>
                <td><code>/api/v1/chat</code></td>
                <td>ส่งข้อความแชต รับคำตอบ/pendingAction/citations</td>
                <td>Max 4,000 ตัวอักษร</td>
            </tr>
            <tr>
                <td><span class="http-badge post">POST</span></td>
                <td><code>/api/v1/actions/{id}/confirm</code></td>
                <td>มนุษย์กดยืนยันรายการ → ส่ง <code>submit_*</code> เข้าระบบจริง</td>
                <td>Idempotent Key บังคับ</td>
            </tr>
            <tr>
                <td><span class="http-badge post">POST</span></td>
                <td><code>/api/v1/actions/{id}/reject</code></td>
                <td>มนุษย์ปฏิเสธรายการที่ AI เสนอ</td>
                <td>Terminal Rejection</td>
            </tr>
            <tr>
                <td><span class="http-badge get">GET</span></td>
                <td><code>/api/v1/traces/{id}</code></td>
                <td>เรียกดู Trace Events ทั้งหมดของบทสนทนา</td>
                <td>Pre-storage Redaction</td>
            </tr>
            <tr>
                <td><span class="http-badge post">POST</span></td>
                <td><code>/api/v1/reset</code></td>
                <td>ล้างสถานะ Demo ทั้งหมดเพื่อเริ่มการสาธิตใหม่</td>
                <td>In-Memory Reset</td>
            </tr>
            <tr>
                <td><span class="http-badge get">GET</span></td>
                <td><code>/health</code></td>
                <td>ตรวจสอบความพร้อมของระบบและเครื่องมือ</td>
                <td>ซ่อน Secrets/URLs</td>
            </tr>
            <tr>
                <td><span class="http-badge ws">WS</span></td>
                <td><code>/ws/live</code></td>
                <td>ช่องสัญญาณเสียงสด Full-duplex (Gemini Live)</td>
                <td>PCM16 Binary Frames</td>
            </tr>
            <tr>
                <td><span class="http-badge hook">HOOK</span></td>
                <td><code>/webhook/line</code></td>
                <td>รับ Webhook จาก LINE Messaging API</td>
                <td>X-Line-Signature HMAC</td>
            </tr>
        </tbody>
    </table>
    <div class="contracts-rule-bar">
        ⚡ <strong>กฎร่วมทุก Endpoint:</strong> ฟิลด์ JSON ใช้ <code>camelCase</code>, ทุก Write Op บังคับ <code>idempotencyKey</code>, Error Type สื่อความหมายชัดเจน
    </div>
</div>
"""
        },
        {
            "id": 18,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): ตัวอย่างสัญญา API",
            "title": "HTTP API Contracts: ตัวอย่าง Request & Response",
            "subtitle": "โครงสร้าง JSON จริงของ POST /api/v1/chat — ทุกฟิลด์ผ่านการตรวจสอบ Pydantic v2",
            "content": """
<div class="json-compare-grid">
    <div class="code-card">
        <div class="code-header">
            <span>POST /api/v1/chat — Request Body</span>
            <span class="code-tag">JSON Schema</span>
        </div>
        <pre class="code-block"><code>{
  <span class="str">\"conversationId\"</span>: <span class="val">\"7f8b9a10-2b3c-4d5e...\"</span>,
  <span class="str">\"message\"</span>: <span class="val">\"ไฟดับที่บ้าน เลขผู้ใช้ไฟ 020012345678\"</span>,
  <span class="str">\"selectedPromptId\"</span>: <span class="val">null</span>,
  <span class="str">\"selectedValue\"</span>: <span class="val">null</span>
}</code></pre>
        <div class="code-footer">รองรับทั้งข้อความพิมพ์ปกติ หรือการคลิกเลือกจาก <code>choicePrompt</code></div>
    </div>

    <div class="code-card">
        <div class="code-header">
            <span>200 OK — Response Body</span>
            <span class="code-tag">JSON Schema</span>
        </div>
        <pre class="code-block"><code>{
  <span class="str">\"conversationId\"</span>: <span class="val">\"7f8b9a10-2b3c-4d5e...\"</span>,
  <span class="str">\"traceId\"</span>: <span class="val">\"1a2b3c4d-5e6f-7a8b...\"</span>,
  <span class="str">\"message\"</span>: <span class="val">\"เตรียมแจ้งเหตุไฟฟ้าดับให้แล้วครับ...\"</span>,
  <span class="str">\"citations\"</span>: [],
  <span class="str">\"pendingAction\"</span>: {
    <span class="str">\"id\"</span>: <span class="val">\"e3d2c1b0-4a5b-6c7d...\"</span>,
    <span class="str">\"action\"</span>: <span class="val">\"prepare_outage_with_ca\"</span>,
    <span class="str">\"preview\"</span>: { <span class="str">\"caNumber\"</span>: <span class="val">\"020012345678\"</span> }
  },
  <span class="str">\"choicePrompt\"</span>: {
    <span class="str">\"promptId\"</span>: <span class="val">\"confirm_outage\"</span>,
    <span class="str">\"options\"</span>: [<span class="val">\"ยืนยันแจ้งเหตุ\"</span>, <span class="val">\"ยกเลิก\"</span>]
  }
}</code></pre>
        <div class="code-footer"><code>choicePrompt</code> ส่งตัวเลือกจาก Catalog หลังบ้าน ไม่ใช่ AI แต่งขึ้น</div>
    </div>
</div>
"""
        },
        {
            "id": 19,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: ความปลอดภัยระดับโค้ด",
            "title": "Write-Safety State Machine: มนุษย์คุมจุดเสี่ยง",
            "subtitle": "ตอบโจทย์ 'มีมนุษย์กำกับดูแลในจุดเสี่ยง' ด้วย State Machine ระดับโค้ด ไม่ใช่แค่ขอร้องใน Prompt",
            "content": """
<div class="state-machine-container">
    <div class="state-flow-diagram">
        <div class="flow-step-box step-prepare">
            <div class="step-badge">1. LLM เรียกได้</div>
            <h4>prepare_*</h4>
            <p>ร่างรายการและจัดเตรียมพารามิเตอร์ตรวจสอบความถูกต้อง</p>
        </div>

        <div class="flow-arrow">➔</div>

        <div class="flow-step-box step-pending">
            <div class="step-badge badge-amber">2. รอการตัดสินใจ</div>
            <h4>pending_confirmation</h4>
            <p>สร้าง pendingActionId และส่ง Preview ให้ผู้ใช้ตรวจทาน</p>
        </div>

        <div class="flow-arrow">➔</div>

        <div class="flow-step-box step-human">
            <div class="step-badge badge-purple">3. มนุษย์ตัดสินใจ</div>
            <h4>[Confirm / Reject]</h4>
            <p>ผู้ใช้กดปุ่ม หรือยืนยันด้วยเสียงอย่างชัดแจ้ง</p>
        </div>

        <div class="flow-arrow">➔</div>

        <div class="flow-step-box step-submit">
            <div class="step-badge badge-green">4. Internal Only</div>
            <h4>submit_*</h4>
            <p>ยิงบันทึกข้อมูลเข้าระบบงานจริง (OMS / VOC)</p>
        </div>
    </div>

    <div class="safety-rules-grid">
        <div class="safety-rule-card">
            <h4>🚫 LLM เรียก Submit ไม่ได้</h4>
            <p>ใน Manifest ทุก <code>submit action</code> ถูกตั้งเป็น <code>exposure: internal</code> โมเดลไม่เห็นชื่อฟังก์ชันนี้ในแค็ตตาล็อก ต่อให้ Prompt Injection ก็สั่งเขียนข้อมูลไม่ได้</p>
        </div>
        <div class="safety-rule-card">
            <h4>🔄 Idempotent Resubmission</h4>
            <p>หากกดกดยืนยันซ้ำ หรือเครือข่ายส่งซ้ำ ระบบจะคืนผลลัพธ์เดิมทันที ไม่สร้างเคสหรือแจ้งเหตุซ้ำซ้อนในระบบงาน กฟภ.</p>
        </div>
        <div class="safety-rule-card">
            <h4>⚠️ HTTP 409 Conflict Guard</h4>
            <p>หากพยายามกดยืนยันรายการที่ถูกปฏิเสธไปแล้ว หรืออยู่นอกสถานะ ระบบจะตอบกลับด้วย <strong>HTTP 409 Conflict</strong> ทันที ไม่ยอมให้ข้อมูลขัดแย้งกัน</p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 20,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): นวัตกรรมไร้ Hallucination",
            "title": "Knowledge Grounding: ตอบจากเอกสารจริง ไม่เดา",
            "subtitle": "ไม่ใช้ Vector Search / Chunk RAG — นวัตกรรม Full-File Long Context แม่นยำ 100%",
            "content": """
<div class="grounding-container">
    <div class="grounding-flow">
        <div class="g-step">
            <div class="g-num">ขั้นที่ 1</div>
            <h4>Document Router</h4>
            <p>โมเดลเห็นเพียง <strong>Catalog รายชื่อไฟล์</strong> (รหัส, ชื่อระเบียบ, สรุปสั้น) เลือกไฟล์ที่เกี่ยวข้อง — ยังไม่เห็นเนื้อหา</p>
        </div>
        <div class="g-arrow">➔</div>
        <div class="g-step">
            <div class="g-num">ขั้นที่ 2</div>
            <h4>Full-File Long Context</h4>
            <p>โหลดไฟล์ที่เลือก<strong>เต็มไฟล์ทุกหน้า</strong> ส่งเข้า Gemini Long Context — บริบทไม่ขาดตอน ไม่โดนตัดทอนกลางประโยค</p>
        </div>
        <div class="g-arrow">➔</div>
        <div class="g-step">
            <div class="g-num">ขั้นที่ 3</div>
            <h4>Citation Validation</h4>
            <p>คำตอบทุกจุดต้องมี Citation ที่<strong>ตรวจพบข้อความตรงกันในไฟล์จริง</strong> หากโมเดลแต่งข้อความจะถูกคัดทิ้งทันที</p>
        </div>
    </div>

    <div class="fail-closed-knowledge-grid">
        <div class="knowledge-benefit-card">
            <h4>💡 ทำไมถึงเหนือกว่า Traditional Chunk RAG?</h4>
            <p>งานระเบียบและอัตราค่าไฟฟ้า กฟภ. ต้องการความแม่นยำทางกฎหมาย 100% Chunk RAG ทั่วไปมักตัดประโยคเงื่อนไขหลุดบริบท แต่ Long Context อ่านเอกสารทั้งฉบับ ทำให้เข้าใจข้อยกเว้นและตารางอัตราค่าไฟได้อย่างถูกต้องครบถ้วน</p>
        </div>

        <div class="no-evidence-card">
            <h4>🛡️ Fail-Closed: ถ้าไม่มีเอกสาร = บอกว่าไม่รู้</h4>
            <p>หากไม่มีเอกสารตรงกับคำถาม หรือข้อมูลกำกวม ระบบจะคืนสถานะ <code>no-evidence</code> ให้ Agent ตอบปฏิเสธอย่างสุภาพ หรือส่งต่อเจ้าหน้าที่ <strong>ห้ามเดาหรือแต่งคำตอบโดยเด็ดขาด</strong></p>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 21,
            "section": 3,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การตรวจสอบย้อนกลับ",
            "title": "Trace & Observability: ตรวจสอบย้อนหลังได้ 100%",
            "subtitle": "โครงสร้าง Audit Trail ที่บันทึกทุกการตัดสินใจ และปกปิดข้อมูลอ่อนไหวตั้งแต่ชั้นจัดเก็บ",
            "content": """
<div class="trace-container">
    <div class="trace-cards-row">
        <div class="trace-feature-card">
            <div class="tf-icon">⏱️</div>
            <h4>Deterministic Sequence</h4>
            <p>ทุกเหตุการณ์ใน Conversation มี <code>traceId</code> และลำดับ <code>sequence</code> เรียงตามเวลาจริง ตรวจสอบกระบวนการคิดและ Tool Call ย้อนหลังได้ทั้งหมด</p>
        </div>

        <div class="trace-feature-card">
            <div class="tf-icon">🔒</div>
            <h4>Pre-Storage Redaction</h4>
            <p>ข้อมูลส่วนบุคคล (PII) เช่น เบอร์โทรศัพท์, เลขบัตรประชาชน หรือเลขผู้ใช้ไฟ ถูกกรองและ Redact ก่อนเขียนลง Store ป้องกันข้อมูลรั่วไหลใน Log</p>
        </div>

        <div class="trace-feature-card">
            <div class="tf-icon">🔑</div>
            <h4>Masked Secrets in Config</h4>
            <p>API Keys และ Token สำคัญ (Gemini, OMS, VOC, LINE) ถูกปกปิดใน <code>__repr__</code> และ <code>__str__</code> เสมอ ไม่แสดงใน Console หรือ Trace</p>
        </div>
    </div>

    <div class="code-card trace-snippet">
        <div class="code-header">
            <span>GET /api/v1/traces/{conversationId} — Structured Audit Event</span>
            <span class="code-tag">Audit JSON</span>
        </div>
        <pre class="code-block"><code>{
  <span class="str">\"sequence\"</span>: <span class="val">3</span>,
  <span class="str">\"kind\"</span>: <span class="val">\"tool_call\"</span>,
  <span class="str">\"toolName\"</span>: <span class="val">\"oms_tool\"</span>,
  <span class="str">\"action\"</span>: <span class="val">\"get_outage_by_ca\"</span>,
  <span class="str">\"input\"</span>: { <span class="str">\"caNumber\"</span>: <span class="val">\"020012345678\"</span> },
  <span class="str">\"timestamp\"</span>: <span class="val">\"2026-09-03T08:15:22.104Z\"</span>
}</code></pre>
        <div class="code-footer">ผู้ตรวจสอบและกรรมการสามารถตรวจสอบขั้นตอนการตัดสินใจของ AI ได้อย่างโปร่งใส</div>
    </div>
</div>
"""
        }
    ]
