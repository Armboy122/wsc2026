# -*- coding: utf-8 -*-
"""Section 5: Slides 34-36 (Live Case Studies) — เกณฑ์ A (16 คะแนน)"""

def get_slides():
    return [
        {
            "id": 34,
            "section": 5,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การอธิบายขั้นตอนการทำงาน",
            "title": "Case Study: แจ้งเหตุไฟฟ้าดับผ่าน Web Chat",
            "subtitle": "เดินตามลำดับเหตุการณ์จริง 7 ขั้นตอน ตั้งแต่รับข้อความจนบันทึกสำเร็จเข้าระบบ OMS",
            "content": """
<div class="casestudy-container">
    <div class="timeline-7steps">
        <div class="t-step">
            <div class="t-num">1</div>
            <div class="t-content">
                <strong>ลูกค้าพิมพ์ข้อความ:</strong>
                <span>"ไฟดับที่บ้าน เลขผู้ใช้ไฟ 020012345678"</span>
            </div>
        </div>
        <div class="t-step">
            <div class="t-num">2</div>
            <div class="t-content">
                <strong>Main Agent วิเคราะห์และวางแผน:</strong>
                <span>เรียก <code>oms_tool.get_outage_by_ca</code> เพื่อตรวจสอบข้อมูลสด</span>
            </div>
        </div>
        <div class="t-step">
            <div class="t-num">3</div>
            <div class="t-content">
                <strong>OMS ตรวจสอบจุดเชื่อมต่อ:</strong>
                <span>Meter ➔ หม้อแปลง ➔ Feeder พบว่ายังไม่มีการรายงานในพื้นที่</span>
            </div>
        </div>
        <div class="t-step">
            <div class="t-num">4</div>
            <div class="t-content">
                <strong>Main Agent เรียกร่างรายการ:</strong>
                <span>เรียก <code>prepare_outage_with_ca</code> ได้ <code>pendingActionId</code></span>
            </div>
        </div>
        <div class="t-step">
            <div class="t-num">5</div>
            <div class="t-content">
                <strong>ส่ง choicePrompt ให้ผู้ใช้:</strong>
                <span>แสดงข้อมูลให้ตรวจทาน พร้อมปุ่ม "ยืนยันแจ้งเหตุ" / "ยกเลิก"</span>
            </div>
        </div>
        <div class="t-step t-highlight">
            <div class="t-num">6</div>
            <div class="t-content">
                <strong>ลูกค้ากดปุ่มยืนยัน:</strong>
                <span>ยิง <code>/api/v1/actions/{id}/confirm</code> ➔ เรียก <code>submit_outage_with_ca</code></span>
            </div>
        </div>
        <div class="t-step">
            <div class="t-num">7</div>
            <div class="t-content">
                <strong>บันทึก Trace และแจ้งผล:</strong>
                <span>ออกเลขรับแจ้งเหตุให้ลูกค้า ตรวจสอบย้อนหลังได้ใน TraceStore</span>
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 35,
            "section": 5,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การทำงานข้ามช่องทาง",
            "title": "Case Study เดียวกัน แต่ผ่านช่องทางเสียง (Voice)",
            "subtitle": "ตรรกะทางธุรกิจเหมือนกัน 100% แต่ปรับเปลี่ยน Presentation ให้เข้ากับสายโทรศัพท์",
            "content": """
<div class="voice-case-container">
    <div class="voice-comparison-grid">
        <div class="vc-card same-card">
            <div class="vc-header">
                <span class="vc-icon">🧠</span>
                <h4>ตรรกะเบื้องหลังที่ไม่เปลี่ยน (100% Identical)</h4>
            </div>
            <ul class="vc-list">
                <li>การวิเคราะห์ความต้องการและการตัดสินใจของ Main Agent</li>
                <li>การเรียก <code>oms_tool.get_outage_by_ca</code> ตรวจสอบหม้อแปลง</li>
                <li>การเข้าสู่สถานะ <code>pending_confirmation</code> เพื่อความปลอดภัย</li>
                <li>การส่ง <code>submit_outage_with_ca</code> ด้วย Internal Exposure</li>
                <li>การบันทึก Audit Trace ตามลำดับเหตุการณ์</li>
            </ul>
        </div>

        <div class="vc-card diff-card">
            <div class="vc-header">
                <span class="vc-icon">🎙️</span>
                <h4>สิ่งที่ปรับแต่งเฉพาะช่องทางเสียง (Voice Guidance)</h4>
            </div>
            <ul class="vc-list">
                <li><strong>ไม่มีหน้าจอให้กด:</strong> ระบบ Voice Guidance สั่งให้ AI อ่านทวนเลขที่ผู้ใช้ไฟและสถานที่ให้ฟังทางหูโทรศัพท์อย่างชัดเจน</li>
                <li><strong>ยืนยันด้วยเสียง:</strong> ลูกค้าพูดว่า "ยืนยันครับ" ➔ โมเดลเรียกฟังก์ชันเสียง <code>pea_confirm_pending_action</code> โดยไม่ต้องจำรหัส ID</li>
                <li><strong>Barge-in Support:</strong> หากลูกค้าพูดว่า "ไม่ใช่บ้านนี้" ระบบตัดเสียงทันทีและเข้าสู่กระบวนการแก้ไข</li>
            </ul>
        </div>
    </div>

    <div class="vc-summary-box">
        💡 <strong>ข้อพิสูจน์:</strong> การแยกชั้น Presentation และ Business Logic อย่างเด็ดขาด ทำให้ กฟภ. พัฒนาระบบงานเพียงครั้งเดียว แต่ใช้งานได้ทุกช่องทาง
    </div>
</div>
"""
        },
        {
            "id": 36,
            "section": 5,
            "theme": "light",
            "rubric": "เกณฑ์ A + B: กลไก Fail-Closed",
            "title": "Fail-Closed Example: เมื่อไม่มีหลักฐาน ระบบบอกว่าไม่รู้",
            "subtitle": "ตัวอย่างจริงเมื่อผู้ใช้ถามคำถามที่ไม่มีในระเบียบ กฟภ. — ห้ามเดาคำตอบอย่างเด็ดขาด",
            "content": """
<div class="failclosed-demo-container">
    <div class="two-chat-comparison">
        <div class="chat-scenario bad-scenario">
            <div class="scenario-header">
                <span class="badge badge-red">❌ Traditional AI Chatbot (เสี่ยงสูง)</span>
            </div>
            <div class="scenario-body">
                <div class="c-bubble u-bubble">
                    <strong>ผู้ใช้:</strong> "กฟภ. มีโปรโมชั่นแจกเครื่องปรับอากาศอินเวอร์เตอร์ฟรีให้บ้านที่ใช้ไฟเกิน 500 หน่วยไหมครับ?"
                </div>
                <div class="c-bubble ai-hallucinate">
                    <strong>AI ทั่วไป (Hallucinate):</strong> "มีครับ! กฟภ. มีโครงการประหยัดพลังงาน สามารถลงทะเบียนรับสิทธิ์ได้ที่สำนักงานการไฟฟ้าใกล้บ้านท่าน..."
                </div>
                <div class="scenario-danger">
                    ⚠️ <strong>อันตราย:</strong> ก่อให้เกิดความเข้าใจผิด สร้างความเสียหายต่อชื่อเสียง กฟภ. และเกิดข้อพิพาทกับผู้ใช้ไฟฟ้า
                </div>
            </div>
        </div>

        <div class="chat-scenario good-scenario">
            <div class="scenario-header">
                <span class="badge badge-green">✅ PEA One Agent (Fail-Closed)</span>
            </div>
            <div class="scenario-body">
                <div class="c-bubble u-bubble">
                    <strong>ผู้ใช้:</strong> "กฟภ. มีโปรโมชั่นแจกเครื่องปรับอากาศอินเวอร์เตอร์ฟรีให้บ้านที่ใช้ไฟเกิน 500 หน่วยไหมครับ?"
                </div>
                <div class="c-bubble ai-grounded">
                    <strong>PEA One Agent:</strong> "จากการตรวจสอบระเบียบและประกาศทางการของ กฟภ. ไม่พบข้อมูลโครงการแจกเครื่องปรับอากาศฟรีดังกล่าวครับ หากต้องการสอบถามข้อมูลเพิ่มเติม แนะนำติดต่อศูนย์บริการ 1129 ครับ"
                </div>
                <div class="scenario-safe">
                    🛡️ <strong>ปลอดภัย:</strong> Document Router ไม่พบคู่มือที่ตรง ➔ ส่งสถานะ <code>no-evidence</code> ➔ ตอบปฏิเสธอย่างถูกต้องและสุภาพ
                </div>
            </div>
        </div>
    </div>
</div>
"""
        }
    ]
