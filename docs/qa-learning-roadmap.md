# Optional roadmap: ระบบเรียนรู้จากคำถามที่ส่งต่อเจ้าหน้าที่

> สถานะ: Optional / ยังไม่อยู่ในขอบเขต implementation ปัจจุบัน

## เป้าหมายในอนาคต

เก็บคำถามที่ระบบตอบไม่ได้ ส่งให้เจ้าหน้าที่ตอบ นำคำตอบผ่านการตรวจสอบก่อนเผยแพร่เป็น Approved Q&A และนำกลับมาใช้กับคำถามที่มีความหมายใกล้เคียง

## ขอบเขตที่ทำแล้วในปัจจุบัน

- Knowledge Router สามารถเลือก Approved Q&A รูปแบบ DOCX ใต้ `knowledge/source/qa/` ร่วมกับเอกสารทางการได้
- คำตอบจาก Q&A ต้องมี citation ที่ตรวจสอบกับข้อความจริงในไฟล์ได้
- เมื่อไม่พบหลักฐานหรือ Knowledge backend ใช้งานไม่ได้ แชตจะแจ้งว่าจะขอส่งต่อคำถามให้เจ้าหน้าที่ตรวจสอบ
- ยังไม่มีการสร้าง ticket หรือส่งข้อมูลไปยังระบบเจ้าหน้าที่จริง

## งาน Optional

### 1. Persistent conversation log

- เก็บ conversation, user message, agent answer, trace และแหล่งอ้างอิงลงฐานข้อมูล
- ปกปิดข้อมูลส่วนบุคคลและกำหนด retention
- ห้ามนำ raw chat ไปใช้เป็น knowledge โดยอัตโนมัติ

### 2. Unanswered queue

- สร้างเคสเมื่อไม่มีหลักฐาน, backend ล้มเหลว หรือผู้ใช้ให้ negative feedback
- สถานะ `open → assigned → answered → reviewed → resolved`
- ป้องกันเคสซ้ำและเก็บ audit history

### 3. Staff review

- เจ้าหน้าที่ดูคำถามและบริบทที่จำเป็น
- เจ้าหน้าที่ตอบและสร้าง Q&A draft
- Reviewer อนุมัติก่อนเผยแพร่

### 4. Approved Q&A lifecycle

- สถานะ `draft → reviewed → approved → published`
- เก็บเวอร์ชัน แหล่งอ้างอิง ผู้อนุมัติ วันเผยแพร่ และวันหมดอายุ
- ยกเลิก Q&A ที่ล้าสมัยได้ทันที

### 5. Retrieval และ evaluation

- ค้น Q&A ที่มีความหมายใกล้เคียงร่วมกับเอกสารทางการ
- เอกสารทางการล่าสุดมีลำดับความน่าเชื่อถือสูงกว่า Q&A ที่ขัดแย้งกัน
- วัด answer rate, escalation rate, Q&A reuse และ citation correctness

## ลำดับแนะนำเมื่อต้องการเริ่ม

1. Persistent log และ redaction
2. Unanswered queue และ staff interface
3. Review/approval workflow
4. Published Q&A sync
5. Evaluation และ dashboard

## เกณฑ์สำคัญ

- Restart แล้วข้อมูลไม่หาย
- ไม่มีคำตอบเจ้าหน้าที่ใดถูกเผยแพร่ก่อนอนุมัติ
- Q&A ที่หมดอายุหรือถูกยกเลิกไม่ถูกใช้ตอบ
- ทุกคำตอบระบุแหล่งที่มาได้
- การแจ้งว่าส่งต่อสำเร็จทำได้ต่อเมื่อระบบ ticket ตอบรับจริงเท่านั้น
