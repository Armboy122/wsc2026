# -*- coding: utf-8 -*-
"""Section 2: Slides 8-11 (Agentic AI Concept & Principles) — เกณฑ์ A + B (16 + 10 คะแนน)"""

def get_slides():
    return [
        {
            "id": 8,
            "section": 2,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: ออกแบบแนวคิด Agentic AI",
            "title": "Chatbot vs Agentic AI: ตารางเปรียบเทียบ 7 มิติ",
            "subtitle": "เติมเต็มช่องว่างจากโจทย์การแข่งขัน: จากระบบตอบคำถาม สู่ปัญญาประดิษฐ์ที่ทำงานแทนลูกค้า",
            "content": """
<div class="comparison-table-wrapper">
    <table class="consulting-table">
        <thead>
            <tr>
                <th style="width: 18%;">มิติการเปรียบเทียบ</th>
                <th style="width: 38%;">Traditional AI Chatbot (ระบบเดิม)</th>
                <th style="width: 44%;" class="col-highlight">PEA One Agent (Agentic AI)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td class="dim-title">1. ขอบเขตการทำงาน</td>
                <td>ตอบคำถามตาม Script หรือข้อความที่ฝึกมาเท่านั้น</td>
                <td class="col-highlight"><strong>วิเคราะห์ความต้องการ → วางแผนงาน → เรียกเครื่องมือจริง</strong></td>
            </tr>
            <tr>
                <td class="dim-title">2. แหล่งข้อมูลที่ใช้</td>
                <td>ฐานข้อมูลเดี่ยว หรือ FAQ แบบ Static ข้อมูลไม่อัปเดต</td>
                <td class="col-highlight"><strong>ดึงข้อมูลสดจากระบบงาน กฟภ. (OMS / VOC / Knowledge)</strong></td>
            </tr>
            <tr>
                <td class="dim-title">3. งานข้ามระบบ</td>
                <td>ทำไม่ได้ ต้องส่งต่อให้เจ้าหน้าที่มนุษย์ดำเนินการต่อ</td>
                <td class="col-highlight"><strong>ประสานงานหลายระบบจบในลูปเดียว (Bounded Agent Loop)</strong></td>
            </tr>
            <tr>
                <td class="dim-title">4. ความเสี่ยง Hallucination</td>
                <td>มักเดาคำตอบ (แต่งเรื่อง) เมื่อไม่พบข้อมูล ก่อผลเสีย</td>
                <td class="col-highlight"><strong>Grounded ด้วยเอกสาร กฟภ. เต็มไฟล์ + Fail-Closed ถ้าไม่มีหลักฐาน</strong></td>
            </tr>
            <tr class="row-spotlight">
                <td class="dim-title"><strong>5. การเขียนข้อมูล (Write Ops)</strong></td>
                <td>ปกติทำไม่ได้ หรือทำแบบเสี่ยงโดยไม่มีการกลั่นกรอง</td>
                <td class="col-highlight"><strong>🔒 มนุษย์ต้องยืนยันเสมอ (prepare → confirm → submit)</strong></td>
            </tr>
            <tr>
                <td class="dim-title">6. ช่องทางการติดต่อ</td>
                <td>แยกแชตบอทคนละตัวตามแต่ละแอป ข้อมูลไม่เชื่อมกัน</td>
                <td class="col-highlight"><strong>สมองเดียว (Single Brain) บริการทั้ง Web, Voice และ LINE</strong></td>
            </tr>
            <tr class="row-spotlight">
                <td class="dim-title"><strong>7. การขยายระบบ (Extensibility)</strong></td>
                <td>ต้องแก้โค้ดและพัฒนาใหม่ทั้งระบบเมื่อมีระบบใหม่</td>
                <td class="col-highlight"><strong>⚡ เพิ่มระบบผ่าน Plugin Manifest โดยไม่แตะ Main Agent</strong></td>
            </tr>
        </tbody>
    </table>
</div>
"""
        },
        {
            "id": 9,
            "section": 2,
            "theme": "light",
            "rubric": "เกณฑ์ B (10 คะแนน): วุฒิภาวะและความคิดสร้างสรรค์",
            "title": "หลักการออกแบบ (Design Principles)",
            "subtitle": "ลำดับความสำคัญที่ทีมยึดถือเป็นลายลักษณ์อักษรใน AGENTS.md ตั้งแต่วันแรกของโครงการ",
            "content": """
<div class="principles-container">
    <div class="staircase-wrapper">
        <div class="stair-step step-1">
            <div class="step-num">#1</div>
            <div class="step-content">
                <strong>Correctness and safety</strong>
                <span>ความถูกต้องและปลอดภัยสูงสุด — ไม่ยอมแลกกับความเร็ว</span>
            </div>
            <div class="step-badge">หัวใจหลัก</div>
        </div>

        <div class="stair-step step-2">
            <div class="step-num">#2</div>
            <div class="step-content">
                <strong>Working MVP</strong>
                <span>ระบบทำงานได้จริงบนเส้นทางหลัก (Critical Path) ที่ผู้ใช้ต้องใช้งาน</span>
            </div>
        </div>

        <div class="stair-step step-3">
            <div class="step-num">#3</div>
            <div class="step-content">
                <strong>Simplicity</strong>
                <span>เรียบง่าย ชัดเจน ไม่สร้างความซับซ้อนที่ยังไม่จำเป็น</span>
            </div>
        </div>

        <div class="stair-step step-4">
            <div class="step-num">#4</div>
            <div class="step-content">
                <strong>Maintainability</strong>
                <span>โค้ดอ่านเข้าใจง่าย มีแบบแผน บำรุงรักษาง่ายในระยะยาว</span>
            </div>
        </div>

        <div class="stair-step step-5">
            <div class="step-num">#5</div>
            <div class="step-content">
                <strong>Test coverage</strong>
                <span>ทดสอบจุดเสี่ยงสูง (Contracts, Write Safety, State Machine)</span>
            </div>
        </div>

        <div class="stair-step step-6">
            <div class="step-num">#6</div>
            <div class="step-content">
                <strong>Architectural purity</strong>
                <span>ไม่ยึดติดกับความสมบูรณ์แบบเชิงทฤษฎีจนลืมคุณค่าทางธุรกิจ</span>
            </div>
        </div>

        <div class="stair-step step-7">
            <div class="step-num">#7</div>
            <div class="step-content">
                <strong>Hypothetical scalability</strong>
                <span>ไม่ออกแบบเผื่อสเกลที่ยังไม่เกิดขึ้นจริงจนเกินความจำเป็น</span>
            </div>
        </div>
    </div>

    <div class="principles-quote-box">
        <div class="p-quote-header">🛡️ ENGINEERING COMMITMENT</div>
        <div class="p-quote-text">
            "เราไม่สร้างระบบที่ Over-engineered เกินความจำเป็น แต่จะ<strong>ไม่มีวันแลกความถูกต้อง ความปลอดภัยของข้อมูลลูกค้า และสัญญาระบบ (API Contracts)</strong> กับความเร็วหรือการโอ้อวดเทคโนโลยี"
        </div>
        <div class="p-quote-meta">บันทึกเป็นกฎเหล็กใน AGENTS.md ของ Repository</div>
    </div>
</div>
"""
        },
        {
            "id": 10,
            "section": 2,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: ภาพรวมโซลูชัน",
            "title": "Solution Overview: สมองเดียว ทุกช่องทาง ทุกระบบ",
            "subtitle": "สถาปัตยกรรมศูนย์รวมที่ประสานช่องทางบริการเข้ากับเครื่องมือ กฟภ. อย่างไร้รอยต่อ",
            "content": """
<div class="solution-overview-container">
    <div class="arch-overview-diagram">
        <div class="arch-col channels-col">
            <div class="arch-col-title">3 ช่องทางบริการ (Channels)</div>
            <div class="arch-box channel-box">
                <span class="icon">💬</span>
                <span class="name">Web Chat</span>
                <span class="detail">choicePrompt แบบโครงสร้าง</span>
            </div>
            <div class="arch-box channel-box">
                <span class="icon">🎙️</span>
                <span class="name">Voice (Gemini Live)</span>
                <span class="detail">PCM16 16/24kHz Realtime</span>
            </div>
            <div class="arch-box channel-box">
                <span class="icon">📱</span>
                <span class="name">LINE Messaging</span>
                <span class="detail">HMAC-SHA256 & Postback</span>
            </div>
        </div>

        <div class="arch-arrow">➔</div>

        <div class="arch-col core-col">
            <div class="arch-col-title">ศูนย์กลางประสานงาน (Orchestrator)</div>
            <div class="arch-box main-agent-box">
                <div class="box-head">
                    <span class="icon">🧠</span>
                    <strong>Main Agent (Gateway)</strong>
                </div>
                <div class="box-sub">Bounded Loop (&le; 12 Steps)</div>
                <div class="feature-bullets">
                    <div>• วิเคราะห์เจตนา & ตรวจสอบบริบท</div>
                    <div>• วางแผนการเรียก Tool แบบเป็นลำดับ</div>
                    <div>• คุม Human-in-the-Loop State Machine</div>
                </div>
            </div>
            <div class="arch-box adapter-box">
                <span class="icon">🔌</span>
                <span><strong>LLMAdapter</strong> (Gemini Production / Demo Stub)</span>
            </div>
        </div>

        <div class="arch-arrow">➔</div>

        <div class="arch-col tools-col">
            <div class="arch-col-title">คลังเครื่องมือ (ToolRegistry)</div>
            <div class="arch-box tool-box">
                <span class="icon">📚</span>
                <span class="name">Knowledge Tool</span>
                <span class="detail">ค้นหาระเบียบ กฟภ. เต็มไฟล์</span>
            </div>
            <div class="arch-box tool-box">
                <span class="icon">⚡</span>
                <span class="name">OMS Plugin</span>
                <span class="detail">ตรวจสอบ & แจ้งไฟฟ้าขัดข้อง</span>
            </div>
            <div class="arch-box tool-box">
                <span class="icon">📋</span>
                <span class="name">VOC Plugin</span>
                <span class="detail">รับเรื่องร้องเรียน & งานบริการ</span>
            </div>
        </div>
    </div>

    <div class="overview-summary-pill">
        🔒 <strong>หัวใจสำคัญ:</strong> Orchestrator ตัวเดียวควบคุมทุกกระบวนงาน — ปราศจาก Sub-Agents ซ้อนกัน ป้องกัน Audit Trail สูญหาย
    </div>
</div>
"""
        },
        {
            "id": 11,
            "section": 2,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): เป้าหมายเชิงผลลัพธ์",
            "title": "เป้าหมายเชิงผลลัพธ์: เร็วขึ้น แม่นยำขึ้น รองรับได้มากขึ้น",
            "subtitle": "กำหนดเป้าหมายตรงตามโจทย์การแข่งขันอย่างเป็นรูปธรรมและสามารถวัดผลได้",
            "content": """
<div class="targets-container">
    <div class="targets-grid">
        <div class="target-card">
            <div class="target-icon">⚡</div>
            <h4>ลดระยะเวลา & ขั้นตอน</h4>
            <p>รวมขั้นตอนการค้นหาข้อมูลและการส่งต่อเรื่องให้จบในที่เดียว จากเดิมที่ลูกค้าต้องรอประสานงานหลายวัน เหลือเพียง 2-3 นาที</p>
            <div class="target-metric">Speed of Answer &lt; 10 วินาที</div>
        </div>

        <div class="target-card">
            <div class="target-icon">🎯</div>
            <h4>ลดภาระงาน & ข้อผิดพลาด</h4>
            <p>ขจัดข้อผิดพลาดจากการจดบันทึกของคนด้วย Typed Schema Validation และให้ระบบกรอกข้อมูลเข้าระบบงานจริงโดยอัตโนมัติ</p>
            <div class="target-metric">Zero Data Entry Errors</div>
        </div>

        <div class="target-card">
            <div class="target-icon">👥</div>
            <h4>รองรับลูกค้าได้มหาศาล</h4>
            <p>แก้ไขปัญหาคอขวด 25,173 Abandon Calls ด้วยระบบ Concurrent Voice AI ที่รับสายพร้อมกันได้หลายร้อยสายช่วงเกิดพายุ</p>
            <div class="target-metric">Zero Queue Capacity</div>
        </div>

        <div class="target-card">
            <div class="target-icon">💰</div>
            <h4>ลดต้นทุนการดำเนินงาน</h4>
            <p>ลดต้นทุนค่าจ้าง Agent สำหรับตอบเรื่องพื้นฐานซ้ำๆ จาก 9.2 บาท เหลือ 3.0 บาทต่อสาย ประหยัดงบประมาณกว่า 16.4 ล้านบาท/ปี</p>
            <div class="target-metric">ประหยัดต้นทุน 67.4%</div>
        </div>

        <div class="target-card" style="grid-column: span 2;">
            <div class="target-icon">📊</div>
            <h4>เพิ่มประสิทธิภาพการใช้ทรัพยากรบุคลากร (Human-AI Synergy)</h4>
            <p>ปลดปล่อยเจ้าหน้าที่มนุษย์จากงานตอบคำถามและรับแจ้งเหตุแบบวนซ้ำ ให้สามารถทุ่มเทเวลากับการจัดการข้อร้องเรียนที่มีความละเอียดอ่อน งานแก้ไขปัญหาหน้างานจริง และการดูแลลูกค้ากลุ่มพิเศษ</p>
            <div class="target-metric">ยกระดับคุณค่างานของพนักงาน กฟภ.</div>
        </div>
    </div>
</div>
"""
        }
    ]
