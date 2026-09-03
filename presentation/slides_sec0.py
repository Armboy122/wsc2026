# -*- coding: utf-8 -*-
"""Section 0: Slides 1-2 (Opening & Agenda)"""

def get_slides():
    return [
        {
            "id": 1,
            "section": 0,
            "theme": "dark",
            "rubric": "ภาพรวมโครงการ",
            "title": "PEA One Agent",
            "subtitle": "จาก \"ตอบคำถาม\" สู่ \"ทำงานแทนลูกค้า\" — Agentic AI สำหรับศูนย์บริการข้อมูลผู้ใช้ไฟฟ้า",
            "content": """
<div class="cover-container">
    <div class="cover-badge-row">
        <span class="badge badge-purple-glow">⚡ PEA Innovation Awards 2026</span>
        <span class="badge badge-outline-light">หัวข้อที่ 3: Agentic AI for Customer Service</span>
        <span class="badge badge-green-glow">⏱️ 10 นาที (43 สไลด์กระชับ)</span>
    </div>

    <div class="cover-hero">
        <div class="cover-logo-bolt">
            <svg viewBox="0 0 24 24" width="64" height="64" fill="#F4EFFB"><path d="M13.6 1.6 4.9 13.9h4.9L8.6 22.4l9.1-12.7h-5l.9-8.1z"/></svg>
        </div>
        <h1 class="cover-title">PEA ONE AGENT</h1>
        <p class="cover-tagline">ยกระดับงานบริการลูกค้า กฟภ. ด้วยปัญญาประดิษฐ์เชิงรุกที่คิด วิเคราะห์ วางแผน และประสานระบบแทนผู้ใช้ไฟฟ้า</p>
    </div>

    <div class="cover-highlights-grid">
        <div class="highlight-card dark-card">
            <div class="card-icon">🧠</div>
            <div class="card-body">
                <h4>สมองเดียว 3 ช่องทาง</h4>
                <p>Web Chat, Voice (Gemini Live) และ LINE เชื่อมโยงผ่าน Main Agent เดียวกัน ไม่แยกส่วน</p>
            </div>
        </div>
        <div class="highlight-card dark-card">
            <div class="card-icon">🛡️</div>
            <div class="card-body">
                <h4>ความปลอดภัยระดับโค้ด</h4>
                <p>State Machine บังคับ Human-in-the-Loop ยืนยันก่อนเขียนข้อมูล ปราศจาก Hallucination</p>
            </div>
        </div>
        <div class="highlight-card dark-card">
            <div class="card-icon">🔌</div>
            <div class="card-body">
                <h4>Plugin Architecture</h4>
                <p>ขยายระบบใหม่ผ่าน Declarative Manifest โดยไม่ต้องแก้โค้ดระบบหลักแม้แต่บรรทัดเดียว</p>
            </div>
        </div>
        <div class="highlight-card dark-card">
            <div class="card-icon">💰</div>
            <div class="card-body">
                <h4>ประหยัด 16.4 ล้านบาท/ปี</h4>
                <p>ลดต้นทุนจาก 9.2 เหลือ 3.0 บาท/สาย (~67.4%) รองรับสายพร้อมกันไม่จำกัดช่วงวิกฤต</p>
            </div>
        </div>
    </div>

    <div class="cover-footer-meta">
        <div>ทีมผู้พัฒนาโครงการ PEA One Agent | การไฟฟ้าส่วนภูมิภาค (PEA)</div>
        <div class="mono-text">Production MVP • 275 Automated Tests Passed • 3 ก.ย. 2568</div>
    </div>
</div>
"""
        },
        {
            "id": 2,
            "section": 0,
            "theme": "light",
            "rubric": "ภาพรวมโครงการ",
            "title": "สิ่งที่จะพูดวันนี้ (Agenda)",
            "subtitle": "6 หัวข้อสำคัญในการเปลี่ยนผ่านจาก Manual Call Center สู่ Agentic AI เต็มรูปแบบ",
            "content": """
<div class="agenda-grid">
    <div class="agenda-card">
        <div class="agenda-num">01</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">ปัญหาและต้นเหตุ</span>
                <span class="badge badge-amber">เกณฑ์ A: 16 คะแนน</span>
            </div>
            <p class="agenda-desc">วิเคราะห์ SLA พ.ค. 68: Abandon Call 10.29%, รอคิว 46s และกับดักต้นทุนเชิงเส้น</p>
            <div class="agenda-tags">
                <span class="tag">1129.pdf</span>
                <span class="tag">Capacity Bottleneck</span>
                <span class="tag">Hourly Peak</span>
            </div>
        </div>
    </div>

    <div class="agenda-card">
        <div class="agenda-num">02</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">แนวคิด Agentic AI</span>
                <span class="badge badge-purple">เกณฑ์ A + B</span>
            </div>
            <p class="agenda-desc">เปรียบเทียบ 7 มิติ Chatbot vs Agentic AI และลำดับความสำคัญใน AGENTS.md</p>
            <div class="agenda-tags">
                <span class="tag">Design Principles</span>
                <span class="tag">Safety > Scalability</span>
            </div>
        </div>
    </div>

    <div class="agenda-card">
        <div class="agenda-num">03</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">สถาปัตยกรรม & เทคโนโลยี</span>
                <span class="badge badge-purple">เกณฑ์ A + B</span>
            </div>
            <p class="agenda-desc">ผัง 5 ชั้น, Frozen API Contracts, Human-in-the-Loop Gate (409 Conflict) และ No-Chunk Grounding</p>
            <div class="agenda-tags">
                <span class="tag">FastAPI</span>
                <span class="tag">Pydantic v2</span>
                <span class="tag">Gemini REST</span>
            </div>
        </div>
    </div>

    <div class="agenda-card">
        <div class="agenda-num">04</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">ช่องทางและระบบปลั๊กอิน</span>
                <span class="badge badge-purple">เกณฑ์ A + B</span>
            </div>
            <p class="agenda-desc">Voice 16/24kHz, LINE Postback, 7-Step Fail-Closed Loader และ CLI Scaffolding</p>
            <div class="agenda-tags">
                <span class="tag">Gemini Live</span>
                <span class="tag">./scripts/add-plugin</span>
            </div>
        </div>
    </div>

    <div class="agenda-card">
        <div class="agenda-num">05</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">ตัวอย่างการทำงานจริง</span>
                <span class="badge badge-blue">เกณฑ์ A</span>
            </div>
            <p class="agenda-desc">เจาะลึก 7 ขั้นตอนแจ้งไฟดับ (Web vs Voice) และกลไกตอบ 'ไม่รู้' เมื่อไม่มีเอกสารอ้างอิง</p>
            <div class="agenda-tags">
                <span class="tag">OMS Outage</span>
                <span class="tag">VOC Intake</span>
                <span class="tag">Zero Guessing</span>
            </div>
        </div>
    </div>

    <div class="agenda-card">
        <div class="agenda-num">06</div>
        <div class="agenda-content">
            <div class="agenda-header-row">
                <span class="agenda-title">ผลลัพธ์ & แผนต่อไป</span>
                <span class="badge badge-green">เกณฑ์ A + C: 24 คะแนน</span>
            </div>
            <p class="agenda-desc">ผลทดสอบ 275 รายการ, แผน Pilot 2 หน่วยงาน และการคำนวณ ROI ประหยัด 16.4 ล้าน/ปี</p>
            <div class="agenda-tags">
                <span class="tag">275 Tests 1.48s</span>
                <span class="tag">Pilot Roadmap</span>
                <span class="tag">ROI 67.4%</span>
            </div>
        </div>
    </div>
</div>
"""
        }
    ]
