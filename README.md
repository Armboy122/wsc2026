# PEA One Agent MVP

## การติดตั้ง การรัน และการตรวจสอบคุณภาพ

จากไดเรกทอรีรากของ repository ให้ติดตั้งส่วนเสริมสำหรับการพัฒนาและความรู้ กำหนดค่า Gemini โดยไม่แสดงค่าลับ และวาง DOCX ที่ผ่านอนุมัติไว้ใต้ `knowledge/source/` จากนั้นเริ่ม API และเปิด UI:

```bash
python3 -m pip install -e ".[dev,knowledge]"
read -rsp "Gemini API key: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
export KNOWLEDGE_SOURCE_ROOT="$PWD/knowledge/source"
export GEMINI_LONG_CONTEXT_MODEL="gemini-3.6-flash"
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

ในอีก terminal หนึ่ง ให้รันชุดทดสอบตามสัญญาที่ตรึงไว้ และตัวประเมิน public envelope:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

ชุด QA ตามสัญญาที่ตรึงไว้คือ `tests/test_mvp_evaluation.py` ครอบคลุม route envelopes และ validation, พฤติกรรมที่แน่นอนของ tool, หลักฐาน/การอ้างอิงจากเอกสารที่เลือก, ข้อเท็จจริงปฏิบัติการจำลอง, state transition ของ prepare/confirm/reject, idempotent writes, ลำดับและการปกปิดข้อมูลใน trace, reset, ความปลอดภัยในการใช้หลาย tools และ adversarial prompts

ชุดข้อมูลเป้าหมายที่กำหนดผลได้แน่นอนอยู่ภายใต้ `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10) โดยใช้เฉพาะ fixture เดโมที่ตรึงไว้ (`PEA-1001`..`PEA-1003`, `BKK-01`, `CNX-02`, `HKT-03`) และ prompt สำหรับ prepare จะมีรายละเอียดผู้ใช้อย่างชัดเจน

OMS, Sabuy และ VOC เป็นระบบ **SIMULATED** ส่วนความรู้ใช้ Document Router เลือก DOCX ที่เกี่ยวข้อง รวมถึง Approved Q&A ใต้ `knowledge/source/qa/` และส่งข้อความฉบับเต็มของไฟล์ที่เลือกให้ Gemini Long Context เมื่อไม่มีเอกสารที่เลือกได้หรือใช้ค่า Gemini ไม่ได้ ระบบจะแจ้งว่าจะขอส่งต่อคำถามให้เจ้าหน้าที่ตรวจสอบ โดยต้องไม่รายงานว่าเป็นความรู้ที่มีหลักฐานรองรับ ทั้งนี้ยังไม่มีการสร้าง ticket จริงจนกว่าจะทำ optional roadmap ใน `docs/plans/qa-learning-roadmap.md` ข้อความแชตไม่ใช่การยืนยัน

## หลักฐานการตรวจสอบล่าสุด

ชุด `pytest` ทั้งหมดผ่าน **176 tests** พร้อม deprecation warnings 5 รายการจาก dependency ภายนอก การทดสอบสดผ่าน `POST /api/v1/chat` ยืนยันว่า Document Router เลือกเฉพาะไฟล์ `PEA_01_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.docx`, ส่งข้อความฉบับเต็มของไฟล์ดังกล่าวให้ Gemini Long Context และคืนคำตอบรายการเอกสารที่ครบถ้วนพร้อม citation ของไฟล์จริง

ระบบปฏิบัติการ (OMS, Sabuy และ VOC) ยังคงแสดงอย่างชัดเจนว่าเป็น **SIMULATED** ไม่มีการบันทึกข้อมูลลับใด ๆ ไว้ที่นี่

**สถานะการเผยแพร่: NOT READY.** ก่อนเผยแพร่ต้องให้เจ้าของข้อมูลยืนยันว่า DOCX ทั้ง 27 ไฟล์ใต้ `knowledge/source/` เป็นเอกสารที่อนุมัติแล้ว รันชุดประเมิน knowledge แบบสดครบทุกกรณี และหากการแข่งขันกำหนดให้ Main Agent ใช้ provider จริงแทน `DemoLLMAdapter` ต้องเชื่อมต่อ `LLMAdapter` ของ provider นั้นก่อน ห้ามถือว่าการผ่านตัวอย่างสดหนึ่งคำถามเป็นการอนุมัติ deployment

ดูหลักฐานการผสานระบบและเกณฑ์อนุมัติการเผยแพร่ได้ที่ [`docs/integration_report.md`](docs/integration_report.md)
