# -*- coding: utf-8 -*-
"""Section 1: Slides 3-7 (Problem Statement & Root Causes) — เกณฑ์ A (16 คะแนน)"""

def get_slides():
    return [
        {
            "id": 3,
            "section": 1,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การระบุและวิเคราะห์ปัญหา",
            "title": "งานบริการลูกค้าที่ซับซ้อนขึ้น แต่ทรัพยากรคงที่",
            "subtitle": "ความท้าทายจริงของศูนย์บริการข้อมูลผู้ใช้ไฟฟ้า การไฟฟ้าส่วนภูมิภาค",
            "content": """
<div class="problem-container">
    <div class="three-cards-grid">
        <div class="stat-card border-left-purple">
            <div class="card-badge">ความต้องการที่หลากหลาย</div>
            <h3 class="card-heading">กระบวนการข้ามหลายระบบ</h3>
            <p class="card-desc">ผู้ใช้ไฟฟ้ามีคำขอที่แตกต่างกันอย่างสิ้นเชิง ทั้งสอบถามระเบียบ/อัตราค่าไฟ, แจ้งเหตุไฟฟ้าขัดข้อง (OMS), ขอใช้ไฟฟ้าใหม่, หรือร้องเรียนการบริการ (VOC)</p>
            <div class="mini-tag-list">
                <span class="tag">ข้อมูลหลากหลาย</span>
                <span class="tag">ประสานงานข้ามแผนก</span>
                <span class="tag">ระบบสารสนเทศแยกส่วน</span>
            </div>
        </div>

        <div class="stat-card border-left-amber">
            <div class="card-badge badge-amber">ผลกระทบต่อกระบวนงาน</div>
            <h3 class="card-heading">รอนาน & เสี่ยงส่งต่อคลาดเคลื่อน</h3>
            <p class="card-desc">การประสานงานข้ามหน่วยงานแบบ Manual ทำให้ระยะเวลาการให้บริการยืดเยื้อ ลูกค้าต้องติดต่อหลายช่องทางหรือเล่าปัญหาซ้ำเดิม และเสี่ยงต่อความผิดพลาดของข้อมูล</p>
            <div class="mini-tag-list">
                <span class="tag">ลูกค้ารอนาน</span>
                <span class="tag">เล่าปัญหาซ้ำหลายรอบ</span>
                <span class="tag">ข้อมูลสูญหายระหว่างส่งต่อ</span>
            </div>
        </div>

        <div class="stat-card border-left-red">
            <div class="card-badge badge-red">ขีดจำกัดด้านทรัพยากร</div>
            <h3 class="card-heading">บุคลากรโตไม่ทันปริมาณงาน</h3>
            <p class="card-desc">ปริมาณและความซับซ้อนของคำขอเพิ่มขึ้นต่อเนื่อง แต่บุคลากรมีขีดจำกัด การพึ่งพาแรงงานมนุษย์ตอบคำถามและดำเนินการด้วยมือจึงไม่สามารถรองรับได้อย่างทันท่วงที</p>
            <div class="mini-tag-list">
                <span class="tag">ภาระงานเจ้าหน้าที่สูง</span>
                <span class="tag">สายล้นช่วงวิกฤต</span>
                <span class="tag">ต้นทุนคงที่สูง</span>
            </div>
        </div>
    </div>

    <div class="callout-box amber-callout">
        <div class="callout-icon">⚠️</div>
        <div class="callout-text">
            <strong>สาระสำคัญจากโจทย์การแข่งขัน:</strong> "การให้บริการแบบเดิมที่เน้นการตอบคำถามหรือดำเนินการแบบ Manual ไม่สามารถตอบสนองความต้องการของลูกค้าได้อย่างรวดเร็วและมีประสิทธิภาพ ส่งผลต่อระยะเวลา ต้นทุนดำเนินงาน และภาระงานของเจ้าหน้าที่"
        </div>
    </div>
</div>
"""
        },
        {
            "id": 4,
            "section": 1,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การวิเคราะห์ต้นเหตุเชิงลึก",
            "title": "Root Cause 1: SLA ที่พลาดเป้าจริง (พ.ค. 2568)",
            "subtitle": "ข้อมูลจริงจากรายงานผลการดำเนินงานศูนย์ 1129 PEA Contact Center (Call Offer 244,737 สาย)",
            "content": """
<div class="sla-container">
    <div class="metric-cards-row">
        <div class="metric-box alert-red">
            <div class="metric-header">
                <span class="metric-title">% Abandon Call</span>
                <span class="status-pill status-fail">❌ ไม่ผ่าน SLA</span>
            </div>
            <div class="metric-big-num">10.29%</div>
            <div class="metric-sub">เป้าหมาย &lt; 5.00% (เกินเกณฑ์ 2 เท่า)</div>
            <div class="metric-footer">สายทิ้งค้างสูงถึง <strong>25,173 สาย/เดือน</strong></div>
        </div>

        <div class="metric-box alert-red">
            <div class="metric-header">
                <span class="metric-title">Speed of Answer</span>
                <span class="status-pill status-fail">❌ ไม่ผ่าน SLA</span>
            </div>
            <div class="metric-big-num">46 วินาที</div>
            <div class="metric-sub">เป้าหมาย &lt; 10 วินาที</div>
            <div class="metric-footer">ลูกค้ารอนานกว่ามาตรฐานที่กำหนด <strong>4.6 เท่า</strong></div>
        </div>

        <div class="metric-box alert-red">
            <div class="metric-header">
                <span class="metric-title">สายที่รอใน 10 วินาที</span>
                <span class="status-pill status-fail">❌ ไม่ผ่าน SLA</span>
            </div>
            <div class="metric-big-num">57.40%</div>
            <div class="metric-sub">เป้าหมาย &gt; 85.00%</div>
            <div class="metric-footer">พลาดเป้าหมายการให้บริการไปกว่า <strong>27.60%</strong></div>
        </div>
    </div>

    <div class="sla-insight-row">
        <div class="talktime-card">
            <div class="talktime-header">
                <h4>🎯 แต่ระยะเวลาพูดสาย (Talk Time) ผ่านเกณฑ์ทุกหมวดบริการ!</h4>
                <span class="badge badge-green">คุณภาพการตอบของ Agent ผ่าน 100%</span>
            </div>
            <div class="talktime-grid">
                <div class="tt-item"><span class="tt-label">แจ้งไฟฟ้าดับ:</span> <span class="tt-val">3:34 น.</span> <span class="tt-target">(เป้า &lt;5:00) ✅</span></div>
                <div class="tt-item"><span class="tt-label">สอบถามข้อมูล:</span> <span class="tt-val">2:24 น.</span> <span class="tt-target">(เป้า &lt;3:00) ✅</span></div>
                <div class="tt-item"><span class="tt-label">ขอใช้ไฟฟ้า:</span> <span class="tt-val">4:29 น.</span> <span class="tt-target">(เป้า &lt;10:00) ✅</span></div>
                <div class="tt-item"><span class="tt-label">ร้องเรียนบริการ:</span> <span class="tt-val">3:31 น.</span> <span class="tt-target">(เป้า &lt;5:00) ✅</span></div>
            </div>
        </div>

        <div class="core-insight-card">
            <div class="insight-badge">KEY ARCHITECTURAL INSIGHT</div>
            <div class="insight-text">
                "เจ้าหน้าที่ กฟภ. ตอบคำถามได้รวดเร็วและมีคุณภาพสูง แต่คอขวดของระบบคือ <strong>ความจุในการเข้าถึง (Capacity)</strong> ลูกค้าเข้าไม่ถึงเพราะไม่มีคนรับสาย ไม่ใช่เพราะเจ้าหน้าที่ขาดทักษะ"
            </div>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 5,
            "section": 1,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การวิเคราะห์ต้นเหตุเชิงลึก",
            "title": "Root Cause 2: ปริมาณงานกับจำนวนคน",
            "subtitle": "เพิ่ม Headcount จาก 80 เป็น 135 คน (+68.7%) แต่ Abandon Rate ยังคงเพิ่มขึ้น",
            "content": """
<div class="two-col-charts-container">
    <div class="chart-panel">
        <div class="chart-header">
            <h4>จำนวน Agent ประจำการ (ม.ค. - พ.ค. 2568)</h4>
            <span class="badge badge-purple">เพิ่มขึ้น 68.7%</span>
        </div>
        <div class="custom-bar-chart">
            <div class="bar-col">
                <div class="bar-val">80</div>
                <div class="bar-fill" style="height: 59%;"></div>
                <div class="bar-lbl">ม.ค.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">80</div>
                <div class="bar-fill" style="height: 59%;"></div>
                <div class="bar-lbl">ก.พ.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">80</div>
                <div class="bar-fill" style="height: 59%;"></div>
                <div class="bar-lbl">มี.ค.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">125</div>
                <div class="bar-fill" style="height: 92%;"></div>
                <div class="bar-lbl">เม.ย.</div>
            </div>
            <div class="bar-col active-col">
                <div class="bar-val">135</div>
                <div class="bar-fill" style="height: 100%;"></div>
                <div class="bar-lbl">พ.ค.</div>
            </div>
        </div>
        <div class="chart-note">กฟภ. เพิ่มกำลังคนจาก 80 สู่ 135 คน เพื่อเตรียมรับมือฤดูร้อน</div>
    </div>

    <div class="chart-panel">
        <div class="chart-header">
            <h4>อัตราลูกค้ารอไม่ไหวและทิ้งสาย (% Abandon Call)</h4>
            <span class="badge badge-red">เป้าหมาย &lt; 5.0%</span>
        </div>
        <div class="custom-bar-chart red-bars">
            <div class="bar-col">
                <div class="bar-val">2.98%</div>
                <div class="bar-fill" style="height: 26%;"></div>
                <div class="bar-lbl">ม.ค.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">7.38%</div>
                <div class="bar-fill" style="height: 65%;"></div>
                <div class="bar-lbl">ก.พ.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">11.21%</div>
                <div class="bar-fill" style="height: 100%;"></div>
                <div class="bar-lbl">มี.ค.</div>
            </div>
            <div class="bar-col">
                <div class="bar-val">8.79%</div>
                <div class="bar-fill" style="height: 78%;"></div>
                <div class="bar-lbl">เม.ย.</div>
            </div>
            <div class="bar-col active-col-red">
                <div class="bar-val">10.29%</div>
                <div class="bar-fill" style="height: 91%;"></div>
                <div class="bar-lbl">พ.ค.</div>
            </div>
        </div>
        <div class="chart-note">แม้เพิ่มคนแล้วใน เม.ย.-พ.ค. อัตรา Abandon ก็ยังคงเกินเกณฑ์กว่า 2 เท่า</div>
    </div>
</div>

<div class="supporting-stats-row">
    <div class="sub-stat-box">
        <div class="sub-stat-num">244,737</div>
        <div class="sub-stat-label">สายเข้า พ.ค. 68 (ลดลง 22.07% จากปีก่อน) แต่ Abandon แย่ลงจาก 6.32% เป็น 10.29%</div>
    </div>
    <div class="sub-stat-box">
        <div class="sub-stat-num">+30,290</div>
        <div class="sub-stat-label">คำขอ Non-Voice (Chat 14,848 / Social 12,879 / Email 2,542) ทับถมภาระงาน</div>
    </div>
    <div class="sub-stat-box">
        <div class="sub-stat-num">พายุฤดูร้อน</div>
        <div class="sub-stat-label">สาเหตุแท้จริงคือสายกระจุกตัวเฉียบพลันช่วงพายุฝน การเพิ่มคนแบบ Linear จึงแก้ไม่ตรงจุด</div>
    </div>
</div>
"""
        },
        {
            "id": 6,
            "section": 1,
            "theme": "light",
            "rubric": "เกณฑ์ A (16 คะแนน): การวิเคราะห์ผลกระทบ",
            "title": "Root Cause 3: ทำไม Manual ถึงตันที่ตรงนี้",
            "subtitle": "ลักษณะสายเข้ากระจุกตัว 17 ชม./วัน (06:00 - 23:00 น.) และกับดักต้นทุนเชิงเส้น",
            "content": """
<div class="rootcause3-container">
    <div class="hourly-chart-wrapper">
        <div class="chart-title-row">
            <h4>ความหนาแน่นของสายรายชั่วโมง (00:00 - 23:00 น.)</h4>
            <span class="badge badge-amber">⚡ ช่วงเวลาวิกฤต: 06:00 - 23:00 น. (17 ชั่วโมง/วัน)</span>
        </div>
        
        <div class="hourly-visual-strip">
            <div class="hour-block offpeak"><span class="h-txt">00-05</span><span class="h-status">Off-Peak</span><span class="h-vol">~3%</span></div>
            <div class="hour-block peak-highlight">
                <div class="peak-badge-overlay">ช่วงพีคต่อเนื่อง 17 ชั่วโมง (สายเข้า &gt; 94% ของทั้งวัน)</div>
                <div class="peak-sub-hours">
                    <span>06</span><span>07</span><span>08</span><span>09</span><span>10</span><span>11</span><span>12</span><span>13</span><span>14</span><span>15</span><span>16</span><span>17</span><span>18</span><span>19</span><span>20</span><span>21</span><span>22</span>
                </div>
            </div>
            <div class="hour-block offpeak"><span class="h-txt">23</span><span class="h-status">Off-Peak</span><span class="h-vol">~3%</span></div>
        </div>
        <div class="hourly-legend">
            <span>■ ช่วงปกติ (Off-Peak): สายเบาบาง คนเหลือ</span>
            <span class="txt-amber">■ ช่วงพีค (Peak Hours): พายุเข้าพร้อมกัน คนรับไม่ทัน สายค้างทิ้ง</span>
        </div>
    </div>

    <div class="strategy-comparison-grid">
        <div class="strategy-card manual-trap">
            <div class="strategy-header">
                <span class="strategy-icon">❌</span>
                <h4>Manual Headcount (กับดักต้นทุนเชิงเส้น)</h4>
            </div>
            <ul class="strategy-list">
                <li><strong>ต้นทุนคงที่ตลอด 24 ชม.:</strong> จ้างคนเพิ่ม 1 คน จ่ายเงินเดือนเต็มเดือน ไม่ว่าจะคุยหรือไม่</li>
                <li><strong>จำกัด 1 คน = 1 สาย:</strong> เมื่อเกิดฝนตกหนักสายโทรเข้าพร้อมกัน 1,000 คน ไม่สามารถรับพร้อมกันได้</li>
                <li><strong>ความเมื่อยล้าและลาออก:</strong> ทำงานภายใต้แรงกดดันช่วงพายุ ทำให้ Turn-over สูง</li>
            </ul>
        </div>

        <div class="strategy-card agentic-solution">
            <div class="strategy-header">
                <span class="strategy-icon">✅</span>
                <h4>Agentic Voice AI (แก้ปัญหาเชิงโครงสร้าง)</h4>
            </div>
            <ul class="strategy-list">
                <li><strong>Zero Queue Concurrent Lines:</strong> รับสายพร้อมกันได้หลายร้อยสายทันที ไม่มีคำว่าสายไม่ว่าง</li>
                <li><strong>Pay-per-minute:</strong> คิดค่าบริการตามนาทีที่คุยจริง ช่วงดึกสายเงียบต้นทุนลดเหลือศูนย์</li>
                <li><strong>มาตรฐานสม่ำเสมอ:</strong> อ้างอิงระเบียบทางการ กฟภ. ตอบถูกต้อง 100% ไม่มีความเมื่อยล้า</li>
            </ul>
        </div>
    </div>
</div>
"""
        },
        {
            "id": 7,
            "section": 1,
            "theme": "dark",
            "rubric": "เกณฑ์ A: สรุปปัญหาและทิศทางแก้ปัญหา",
            "title": "สรุปปัญหา: Capacity คือโจทย์จริง",
            "subtitle": "คำตอบไม่ใช่แค่ 'จ้างคนเพิ่ม' หรือ 'Chatbot ตอบคำถามพื้นฐาน' แต่คือ Agentic AI",
            "content": """
<div class="transition-container">
    <div class="transition-card">
        <div class="transition-icon-large">
            <svg viewBox="0 0 24 24" width="72" height="72" fill="#E2D9F3"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
        </div>
        <h2 class="transition-title">ปัญหาของ กฟภ. คือ "Capacity" ไม่ใช่ "คุณภาพของคน"</h2>
        <p class="transition-quote">
            "การตอบคำถามอย่างเดียวแบบ Chatbot เก่าๆ ไม่ได้ช่วยลดสายโทรเข้าเมื่อไฟดับ<br>
            ผู้ใช้ไฟฟ้าต้องการระบบที่ <strong>ตรวจสอบข้อมูลได้จริง, ดำเนินการแจ้งเหตุแทนได้,</strong> และ <strong>ประสานงานข้ามระบบให้เสร็จสิ้นในสายเดียว</strong>"
        </p>

        <div class="transition-arrow-box">
            <div class="arrow-item past">
                <div class="arrow-tag">เดิม (Traditional)</div>
                <div class="arrow-title">Rule-based Chatbot / Manual IVR</div>
                <div class="arrow-sub">ได้แค่ส่งลิงก์ หรือตอบข้อความแข็งๆ ไม่ช่วยปิดงาน</div>
            </div>
            <div class="arrow-divider">➔</div>
            <div class="arrow-item future">
                <div class="arrow-tag badge-purple-glow">ใหม่ (PEA One Agent)</div>
                <div class="arrow-title">Autonomous Agentic AI</div>
                <div class="arrow-sub">วิเคราะห์ วางแผน ดึงระบบ OMS/VOC และทำงานแทนลูกค้าจริง</div>
            </div>
        </div>
    </div>
</div>
"""
        }
    ]
