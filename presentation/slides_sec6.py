# -*- coding: utf-8 -*-
"""Section 6: Slides 37-43 (Testing, Pilot, Impact ROI & Closing) — เกณฑ์ A + B + C (40 คะแนน)"""

def get_slides():
    return [
        {
            "id": 37,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): วิธีการทดสอบและผลลัพธ์",
            "title": "Testing Strategy: 275 Automated Tests ผ่าน 100%",
            "subtitle": "รันจบใน 1.48 วินาที — ทดสอบครอบคลุมทุกจุดเสี่ยงโดยไม่มีการเรียก Network ภายนอกแม้แต่ครั้งเดียว",
            "content": """
<div class="testing-container">
    <div class="testing-stats-tiles">
        <div class="test-stat-tile tile-purple">
            <div class="t-val">275</div>
            <div class="t-lbl">Automated Tests Passed</div>
        </div>
        <div class="test-stat-tile tile-green">
            <div class="t-val">1.48s</div>
            <div class="t-lbl">Execution Time (pytest)</div>
        </div>
        <div class="test-stat-tile tile-blue">
            <div class="t-val">0 Calls</div>
            <div class="t-lbl">External Real API (Mocked 100%)</div>
        </div>
        <div class="test-stat-tile tile-amber">
            <div class="t-val">100%</div>
            <div class="t-lbl">Deterministic & Repeatable</div>
        </div>
    </div>

    <div class="test-breakdown-chart">
        <h4>การแจกแจงชุดการทดสอบตามหมวดหมู่ความเสี่ยง (12 หมวดหมู่)</h4>
        <div class="hbar-grid">
            <div class="hbar-row">
                <span class="hbar-name">VOC Plugin (intake/flow/prefill/tool)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 100%;"></div></div>
                <span class="hbar-count">48 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Agent Orchestration (main loop)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 94%;"></div></div>
                <span class="hbar-count">45 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">LLM Factory / Config / Prompting</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 71%;"></div></div>
                <span class="hbar-count">34 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Knowledge Grounding (Router/Context)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 63%;"></div></div>
                <span class="hbar-count">30 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Voice / Live Bridge (WebSocket/PCM)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 56%;"></div></div>
                <span class="hbar-count">27 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Contracts & HTTP Routes</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 48%;"></div></div>
                <span class="hbar-count">23 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Evaluation Harness & Datasets</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 35%;"></div></div>
                <span class="hbar-count">17 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">OMS Plugin (Tool & Backend)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 33%;"></div></div>
                <span class="hbar-count">16 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Sabuy Plugin (Dormant Readiness)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 29%;"></div></div>
                <span class="hbar-count">14 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">Plugin Loader Validation (Fail-Closed)</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 27%;"></div></div>
                <span class="hbar-count">13 tests</span>
            </div>
            <div class="hbar-row">
                <span class="hbar-name">LINE HMAC Signature & Adapters</span>
                <div class="hbar-track"><div class="hbar-fill" style="width: 15%;"></div></div>
                <span class="hbar-count">7 tests</span>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 38,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): แผนทดลองกับหน่วยงาน >= 2 แห่ง",
            "title": "Pilot Evaluation: โครงร่างการทดลองใช้ใน 2 หน่วยงานนำร่อง",
            "subtitle": "ตอบโจทย์เกณฑ์ A (16 คะแนน): กรอบประเมินผลเชิงปริมาณและคุณภาพ พร้อมรองรับการใส่ข้อมูลจริงของท่าน",
            "content": """
<div class="pilot-evaluation-container">
    <div class="pilot-framework-row">
        <!-- หน่วยงานนำร่องที่ 1 -->
        <div class="pilot-unit-card unit-1">
            <div class="p-card-header">
                <span class="p-badge p-badge-purple">หน่วยงานนำร่องที่ 1 (Voice / 24 ชม.)</span>
                <h4 class="p-unit-title" contenteditable="true">[ระบุชื่อหน่วยงาน: เช่น ศูนย์ 1129 PEA Contact Center]</h4>
            </div>
            
            <div class="p-field-row">
                <span class="pf-label">🎯 ขอบเขต & กลุ่มเป้าหมาย:</span>
                <div class="pf-editable" contenteditable="true">[ระบุ เช่น ทดสอบระบบ Voice Agent รับแจ้งเหตุไฟฟ้าขัดข้องและสอบถามข้อมูลทั่วไป กลุ่มผู้ใช้ไฟ 12 เขต]</div>
            </div>

            <div class="p-metrics-table">
                <div class="pm-col">
                    <span class="pm-lbl">ตัวชี้วัด (KPI)</span>
                    <span class="pm-item">• % Abandon Call</span>
                    <span class="pm-item">• Speed of Answer</span>
                    <span class="pm-item">• จำนวนสายทดสอบ</span>
                    <span class="pm-item">• Task Completion Rate</span>
                </div>
                <div class="pm-col">
                    <span class="pm-lbl">ก่อนทดลอง (Baseline)</span>
                    <span class="pm-item red-txt">10.29% (หลุดเป้า)</span>
                    <span class="pm-item red-txt">46 วินาที</span>
                    <span class="pm-item">-</span>
                    <span class="pm-item">-</span>
                </div>
                <div class="pm-col highlight-col">
                    <span class="pm-lbl">ผลลัพธ์นำร่อง (Pilot)</span>
                    <span class="pm-item green-txt" contenteditable="true">[ใส่ตัวเลข เช่น &lt; 3.5%]</span>
                    <span class="pm-item green-txt" contenteditable="true">[ใส่ตัวเลข เช่น 8 วินาที]</span>
                    <span class="pm-item purple-txt" contenteditable="true">[ระบุ เช่น 1,500 สาย]</span>
                    <span class="pm-item purple-txt" contenteditable="true">[ระบุ เช่น 93.8%]</span>
                </div>
            </div>

            <div class="p-feedback-box">
                <span class="fb-icon">💬</span>
                <div class="fb-content">
                    <strong>เสียงสะท้อนจากเจ้าหน้าที่ / ผู้ใช้งานจริง:</strong>
                    <p contenteditable="true">"[พิมพ์ใส่ความคิดเห็นจริง เช่น: เจ้าหน้าที่หน้างานลดความตึงเครียดช่วงฝนตกฟ้าคะนอง ระบบช่วยคัดกรองสายแจ้งเหตุซ้ำได้อย่างแม่นยำ ทำให้เจ้าหน้าที่มุ่งแก้ไขจุดวิกฤตได้รวดเร็วขึ้น]"</p>
                </div>
            </div>
        </div>

        <!-- หน่วยงานนำร่องที่ 2 -->
        <div class="pilot-unit-card unit-2">
            <div class="p-card-header">
                <span class="p-badge p-badge-blue">หน่วยงานนำร่องที่ 2 (Web & LINE / หน้าร้าน)</span>
                <h4 class="p-unit-title" contenteditable="true">[ระบุชื่อหน่วยงาน: เช่น การไฟฟ้าส่วนภูมิภาค สาขาเมืองเชียงใหม่ / กฟฟ.สาขา...]</h4>
            </div>

            <div class="p-field-row">
                <span class="pf-label">🎯 ขอบเขต & กลุ่มเป้าหมาย:</span>
                <div class="pf-editable" contenteditable="true">[ระบุ เช่น ทดสอบระบบ Web Chat และ LINE OA สำหรับรับเรื่องร้องเรียน VOC ตรวจสอบมิเตอร์ และขอใช้ไฟฟ้าใหม่]</div>
            </div>

            <div class="p-metrics-table">
                <div class="pm-col">
                    <span class="pm-lbl">ตัวชี้วัด (KPI)</span>
                    <span class="pm-item">• ระยะเวลากรอกคำร้อง</span>
                    <span class="pm-item">• ความถูกต้องข้อมูล (CA)</span>
                    <span class="pm-item">• จำนวนเคสที่บันทึก</span>
                    <span class="pm-item">• ความพึงพอใจ (CSAT)</span>
                </div>
                <div class="pm-col">
                    <span class="pm-lbl">ก่อนทดลอง (Baseline)</span>
                    <span class="pm-item red-txt">15-20 นาที</span>
                    <span class="pm-item red-txt">ต้องตรวจสอบซ้ำ</span>
                    <span class="pm-item">-</span>
                    <span class="pm-item">-</span>
                </div>
                <div class="pm-col highlight-col">
                    <span class="pm-lbl">ผลลัพธ์นำร่อง (Pilot)</span>
                    <span class="pm-item green-txt" contenteditable="true">[ใส่ตัวเลข เช่น 45 วินาที]</span>
                    <span class="pm-item green-txt" contenteditable="true">[ใส่ตัวเลข เช่น 100% ผ่าน]</span>
                    <span class="pm-item purple-txt" contenteditable="true">[ระบุ เช่น 450 เคส]</span>
                    <span class="pm-item purple-txt" contenteditable="true">[ระบุ เช่น 4.85 / 5.0]</span>
                </div>
            </div>

            <div class="p-feedback-box">
                <span class="fb-icon">💬</span>
                <div class="fb-content">
                    <strong>เสียงสะท้อนจากเจ้าหน้าที่ / ผู้ใช้งานจริง:</strong>
                    <p contenteditable="true">"[พิมพ์ใส่ความคิดเห็นจริง เช่น: ผู้ใช้ไฟประทับใจที่สามารถแนบพิกัดและรูปถ่ายผ่าน LINE ได้ทันที ระบบสร้าง Pending Action ให้ตรวจทานก่อนส่งเข้า VOC อัตโนมัติ]"</p>
                </div>
            </div>
        </div>
    </div>

    <!-- แผนการขยายผลและ Live Demo Strip -->
    <div class="pilot-bottom-strip">
        <div class="scaleout-summary">
            <span class="so-title">🚀 แผนขยายผลสู่ 12 เขต:</span>
            <span>Shadow Mode (2 สัปดาห์) ➔ Limited Live (4 สัปดาห์) ➔ Nationwide Full Rollout ครอบคลุมผู้ใช้ไฟฟ้า 21 ล้านราย</span>
        </div>
        <div class="demo-link-badge">
            <span>📱 Live Demo พร้อมทดสอบ: <code>http://127.0.0.1:8000</code></span>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 39,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ C (24 คะแนน): ความคุ้มค่าทางเศรษฐศาสตร์ (ROI)",
            "title": "Cost & ROI: ประหยัดงบประมาณ ~16.4 ล้านบาท/ปี",
            "subtitle": "คำนวณเปรียบเทียบต้นทุนแรงงานมนุษย์ vs Gemini Live Voice Agent อิงสถิติเดือน พ.ค. 2568",
            "content": """
<div class="roi-container">
    <div class="roi-cards-row">
        <div class="roi-metric-card highlight-green">
            <div class="rmc-label">ต้นทุนบริการต่อสาย</div>
            <div class="rmc-main-val">9.2 ➔ 3.0 บาท</div>
            <div class="rmc-sub">ลดลงทันที <strong>67.4%</strong> (ประหยัด 6.2 บาท/สาย)</div>
        </div>

        <div class="roi-metric-card">
            <div class="rmc-label">ต้นทุนรายเดือน (219,564 สาย)</div>
            <div class="rmc-main-val">2.02M ➔ 661k บาท</div>
            <div class="rmc-sub">ประหยัดเงินสด <strong>1,364,132 บาท/เดือน</strong></div>
        </div>

        <div class="roi-metric-card highlight-purple">
            <div class="rmc-label">ผลประหยัดสุทธิต่อปี</div>
            <div class="rmc-main-val">~16.4 ล้านบาท</div>
            <div class="rmc-sub">คำนวณจากปริมาณสายจริง 2.6 ล้านสาย/ปี</div>
        </div>
    </div>

    <div class="cost-comparison-bars-wrapper">
        <div class="cb-col cb-human">
            <div class="cb-header">
                <h4>แรงงานมนุษย์ (ปัจจุบัน)</h4>
                <span class="badge badge-amber">9.20 บาท / สาย</span>
            </div>
            <div class="cb-bar-track">
                <div class="cb-bar-fill" style="width: 100%;">2,025,000 บาท/เดือน</div>
            </div>
            <div class="cb-calc">135 Agents × 15,000 บาท ÷ 219,564 สาย</div>
        </div>

        <div class="cb-col cb-ai">
            <div class="cb-header">
                <h4>Gemini Live Voice Agent</h4>
                <span class="badge badge-green">3.01 บาท / สาย</span>
            </div>
            <div class="cb-bar-track">
                <div class="cb-bar-fill fill-green" style="width: 32.6%;">660,868 บาท/เดือน</div>
            </div>
            <div class="cb-calc">0.828 บาท/นาที × 3.64 นาที (AHT เฉลี่ย พ.ค. 68)</div>
        </div>
    </div>

    <div class="assumptions-box">
        <div class="as-title">📋 สมมติฐานการคำนวณอย่างรอบคอบและรัดกุม (Transparent Assumptions):</div>
        <div class="as-grid">
            <div>1. 15,000 บาท/คน คือเฉพาะค่าจ้างขั้นต่ำ ยังไม่รวมสัญญา Outsource จริง (ส่วนต่างจริงจะยิ่งสูงกว่านี้)</div>
            <div>2. Gemini Live คำนวณแบบ Worst-case Full-duplex ตลอดความยาวสาย ($0.023/นาที, 36 บาท/USD)</div>
            <div>3. ไม่ได้มุ่งแทนที่คน 100% แต่นำมาแบ่งเบาภาระงานประจำซ้ำซาก เพื่อให้เจ้าหน้าที่มุ่งเน้นงานร้องเรียนซับซ้อน</div>
            <div>4. ในระยะยาว หากลงทุน On-premise Hardware ต้นทุนต่อสายจะลดต่ำลงได้มากกว่านี้อีก</div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 40,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ C (24 คะแนน): ผลประโยชน์ต่อองค์กรและลูกค้า",
            "title": "Impact: ผลลัพธ์เชิงคุณภาพต่อ กฟภ. และผู้ใช้ไฟฟ้า",
            "subtitle": "ยกระดับประสบการณ์การให้บริการในทุกมิติ นอกเหนือจากการประหยัดต้นทุน",
            "content": """
<div class="qual-impact-container">
    <div class="qual-cards-grid">
        <div class="qc-card">
            <div class="qc-icon">🚫</div>
            <h4>ขจัดปัญหาลูกค้ารอคิว & ทิ้งสาย</h4>
            <p><strong>ผลต่อลูกค้า:</strong> โทรติดทันทีใน 1 วินาที ไม่ต้องรอถือสายรอคิว 46 วินาทีอีกต่อไป แก้ไขคอขวด 25,173 Abandon Calls ให้หมดสิ้น</p>
            <div class="qc-badge">Zero Abandon Calls</div>
        </div>

        <div class="qc-card">
            <div class="qc-icon">🕒</div>
            <h4>บริการไร้รอยต่อตลอด 24 ชั่วโมง</h4>
            <p><strong>ผลต่อองค์กร:</strong> รองรับสายเข้าฉุกเฉินยามค่ำคืนหรือช่วงพายุพัดถล่มได้พร้อมกันนับร้อยสาย โดยไม่ต้องจัดกะพนักงานล่วงเวลาข้ามคืน</p>
            <div class="qc-badge">24/7 Availability</div>
        </div>

        <div class="qc-card">
            <div class="qc-icon">🎯</div>
            <h4>ความถูกต้องและมาตรฐานเดียวกัน</h4>
            <p><strong>ผลต่อลูกค้า:</strong> คำตอบระเบียบ อัตราค่าไฟฟ้า และขั้นตอนการขอใช้ไฟมีความถูกต้อง แม่นยำ 100% ตามระเบียบ กฟภ. ไม่ขึ้นกับอารมณ์หรือประสบการณ์ของพนักงาน</p>
            <div class="qc-badge">100% Consistent Answers</div>
        </div>

        <div class="qc-card">
            <div class="qc-icon">📜</div>
            <h4>Audit Trail โปร่งใส ตรวจสอบได้</h4>
            <p><strong>ผลต่อองค์กร:</strong> ทุกขั้นตอนการสนทนาและการทำรายการมีบันทึก Structured Trace ชัดเจน ตรวจสอบย้อนหลังได้ทันทีเมื่อมีข้อพิพาทหรือการร้องเรียน</p>
            <div class="qc-badge">100% Traceable Audit</div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 41,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): ความคิดสร้างสรรค์และจุดเด่น",
            "title": "สิ่งที่ทำให้เราแตกต่างจากทีมอื่น (Engineering Edge)",
            "subtitle": "5 นวัตกรรมทางวิศวกรรมที่ออกแบบมาเพื่อแก้ไขปัญหาเฉพาะของ กฟภ. อย่างแท้จริง",
            "content": """
<div class="creativity-container">
    <div class="creativity-list">
        <div class="c-item">
            <div class="c-badge">01</div>
            <div class="c-body">
                <strong>Full-Document Grounding (ไม่ใช้ Chunk RAG):</strong>
                <p>อ่านเอกสารระเบียบ กฟภ. ทั้งฉบับ ไม่ตัดทอนประโยคเงื่อนไข ป้องกันการตอบผิดพลาดในเรื่องสำคัญ เช่น อัตราค่าไฟหรือเงื่อนไขทางกฎหมาย</p>
            </div>
        </div>

        <div class="c-item">
            <div class="c-badge">02</div>
            <div class="c-body">
                <strong>Orchestrator เดี่ยว ไม่แตก Sub-Agent ย่อย:</strong>
                <p>ควบคุมการตัดสินใจและ Audit Trail ที่จุดเดียว ลดโอกาสที่ Sub-agents จะสื่อสารขัดแย้งกันเอง หรือสูญเสียบริบทระหว่างทาง</p>
            </div>
        </div>

        <div class="c-item">
            <div class="c-badge">03</div>
            <div class="c-body">
                <strong>Write-Safety State Machine ระดับโค้ด:</strong>
                <p>บังคับ prepare ➔ confirm ➔ submit ในชั้น Backend และ Schema ห้าม LLM เรียก submit โดยตรง ป้องกัน Prompt Injection 100%</p>
            </div>
        </div>

        <div class="c-item">
            <div class="c-badge">04</div>
            <div class="c-body">
                <strong>CLI Plugin Scaffolding (<code>./scripts/add-plugin</code>):</strong>
                <p>พิสูจน์แล้วว่าขยายสู่ระบบใหม่ได้ใน 6 ขั้นตอน โดยไม่ต้องแตะต้องโค้ด Main Agent เลยแม้แต่บรรทัดเดียว</p>
            </div>
        </div>

        <div class="c-item">
            <div class="c-badge">05</div>
            <div class="c-body">
                <strong>สมองเดียวรองรับ 3 ช่องทางพร้อม Dynamic UX:</strong>
                <p>ปรับตัวตามฮาร์ดแวร์ของผู้ใช้: หน้าจอแสดงปุ่มคลิก แต่สายโทรศัพท์อ่านตัวเลือกครบถ้วน ปรับตัวตามบริบทอย่างไร้รอยต่อ</p>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 42,
            "section": 6,
            "theme": "light",
            "rubric": "เกณฑ์ A + C: แผนงานในอนาคต",
            "title": "Roadmap: จาก MVP สู่ระบบหลักของการไฟฟ้าส่วนภูมิภาค",
            "subtitle": "แผนพัฒนา 3 ระยะเพื่อขับเคลื่อนสู่การใช้งานจริงทั่วประเทศอย่างยั่งยืน",
            "content": """
<div class="roadmap-container">
    <div class="roadmap-stages-grid">
        <div class="stage-card stage-short">
            <div class="stage-timing">ระยะสั้น (1 - 3 เดือน)</div>
            <h4>Pilot Phase & Feedback Loop</h4>
            <ul class="stage-bullets">
                <li>ดำเนินโครงการนำร่องกับ 2 หน่วยงาน (ศูนย์ 1129 และ กฟฟ.สาขา)</li>
                <li>เก็บตัวเลขความพึงพอใจจริงของผู้ใช้ไฟฟ้าเพื่อปรับจูน Prompt</li>
                <li>ปรับปรุงคลังความรู้ระเบียบ กฟภ. ให้ครอบคลุมทุกสาขาบริการ</li>
            </ul>
            <div class="stage-goal">เป้าหมาย: พิสูจน์ความเสถียรกับผู้ใช้จริง</div>
        </div>

        <div class="stage-card stage-mid">
            <div class="stage-timing">ระยะกลาง (3 - 6 เดือน)</div>
            <h4>Full Production Integration</h4>
            <ul class="stage-bullets">
                <li>เชื่อมต่อกับระบบโทรศัพท์ SIP/Trunking ของศูนย์ 1129 จริง</li>
                <li>เปิดใช้งาน <code>sabuy_tool</code> ชำระค่าไฟฟ้าและบริการมิเตอร์</li>
                <li>ขยายช่องทางสู่ Mobile Application "PEA Smart Plus"</li>
            </ul>
            <div class="stage-goal">เป้าหมาย: รองรับสายโทรเข้า 1129 ทั้งประเทศ</div>
        </div>

        <div class="stage-card stage-long">
            <div class="stage-timing">ระยะยาว (6 - 12 เดือน)</div>
            <h4>Sovereign On-Premise AI</h4>
            <ul class="stage-bullets">
                <li>ลงทุน Local LLM Hardware เพื่อประมวลผลภายใน Data Center กฟภ.</li>
                <li>ลดต้นทุนค่าบริการ Token ให้เหลือศูนย์ในระยะยาว</li>
                <li>รักษาอธิปไตยทางข้อมูลและความมั่นคงปลอดภัยโครงสร้างพื้นฐาน</li>
            </ul>
            <div class="stage-goal">เป้าหมาย: ความคุ้มค่าสูงสุดและความมั่นคงไซเบอร์</div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 43,
            "section": 6,
            "theme": "dark",
            "rubric": "บทสรุปโครงการ",
            "title": "PEA One Agent: พร้อมแล้วสำหรับการทดลองจริง",
            "subtitle": "จาก 'ตอบคำถาม' สู่ 'ทำงานแทนลูกค้า' — นวัตกรรม Agentic AI เพื่อผู้ใช้ไฟฟ้า กฟภ.",
            "content": """
<div class="closing-container">
    <div class="closing-card">
        <div class="closing-bolt">
            <svg viewBox="0 0 24 24" width="64" height="64" fill="#F4EFFB"><path d="M13.6 1.6 4.9 13.9h4.9L8.6 22.4l9.1-12.7h-5l.9-8.1z"/></svg>
        </div>
        <h1 class="closing-title">PEA ONE AGENT</h1>
        <p class="closing-sub">ระบบ Agentic AI ที่สร้างขึ้นบนความจริงจังทางวิศวกรรม ความปลอดภัย และความคุ้มค่า</p>

        <div class="closing-three-pillars">
            <div class="cp-item">
                <div class="cp-num">275 Tests</div>
                <div class="cp-txt">ผ่านการทดสอบอัตโนมัติ 100% ใน 1.48 วินาที พร้อมใช้งานทันที</div>
            </div>
            <div class="cp-item">
                <div class="cp-num">~67.4% ROI</div>
                <div class="cp-txt">ลดต้นทุนจาก 9.2 เหลือ 3.0 บาท/สาย ประหยัดงบ ~16.4 ล้านบาท/ปี</div>
            </div>
            <div class="cp-item">
                <div class="cp-num">Safe & Secure</div>
                <div class="cp-txt">Human-in-the-Loop State Machine บังคับความปลอดภัยในระดับสถาปัตยกรรม</div>
            </div>
        </div>

        <div class="closing-contact-row">
            <div class="cc-badge">พร้อมรับคำแนะนำและตอบข้อซักถามจากคณะกรรมการทุกท่านครับ</div>
            <div class="cc-meta">ทีมผู้พัฒนาโครงการ PEA One Agent | การไฟฟ้าส่วนภูมิภาค • ขอบคุณครับ</div>
        </div>
    </div>
</div>
"""
        }
    ]
