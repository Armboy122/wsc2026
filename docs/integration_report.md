# รายงานการผสานรวม QA ของ PEA One Agent

## ขอบเขตปัจจุบัน

ระบบมี Main Agent หนึ่งตัวและ tool ระดับบนสุดสี่รายการ ได้แก่ `knowledge_tool`, `sabuy_tool`, `voc_tool` และ `oms_tool` โดย OMS, Sabuy และ VOC เป็น **SIMULATED** ส่วน knowledge ใช้ Gemini กับเอกสารจริงที่เลือกจาก `knowledge/source/`

Knowledge เปลี่ยนเป็น **Document Routing + Full-file Long Context** แล้ว และไม่ใช้ Gemini File Search, RAG, embedding, vector index หรือ chunk retrieval

## การตั้งค่าและรัน

```bash
python3 -m pip install -e ".[dev,knowledge]"
read -rsp "Gemini API key: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
export KNOWLEDGE_BACKEND_NAME=full_document
export KNOWLEDGE_SOURCE_ROOT="$PWD/knowledge/source"
export GEMINI_LONG_CONTEXT_MODEL=gemini-3.6-flash
python3 -m uvicorn app.main:app --reload
```

ตรวจสอบด้วย:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

## เส้นทาง Knowledge ที่ตรวจสอบแล้ว

```text
คำถามผู้ใช้
→ Main Agent เรียก knowledge_tool.search
→ Document Router เห็นเฉพาะ sourceId, filename และ title
→ เลือก allowlisted DOCX ไม่เกิน maxResults
→ backend อ่านข้อความฉบับเต็มของไฟล์ที่เลือก
→ Gemini Long Context สร้างคำตอบที่ครบและตรงคำถาม
→ backend ตรวจว่า citation อ้างไฟล์ที่เลือกและ snippet อยู่ในไฟล์จริง
→ Main Agent แสดง answerContext พร้อม citation
```

หาก router เลือกไฟล์ไม่ได้, JSON จากโมเดลไม่ถูกต้อง, sourceId อยู่นอก allowlist, ข้อความเกิน context budget หรือ citation ตรวจสอบไม่ได้ ระบบจะ fail closed โดยไม่ตอบจากความจำของโมเดล ห้ามตัดข้อความท้ายไฟล์โดยเงียบ และห้ามโหลดทั้ง corpus เมื่อใช้เพียงบางไฟล์ได้

## หลักฐานการตรวจสอบล่าสุด

- DOCX ใต้ `knowledge/source/`: **27 ไฟล์**
- ข้อความฉบับเต็มที่แปลงได้: **90,468 ตัวอักษร**
- ชื่อเอกสารที่อ่านได้สำหรับ catalog: **27/27 ไฟล์**
- Full test suite: **176 passed**, deprecation warnings 5 รายการจาก dependency ภายนอก
- Targeted full-document/runtime tests: **29 passed**
- `python -m compileall`: ผ่าน
- `git diff --check`: ผ่าน
- ตรวจเส้นทางสดผ่าน `POST /api/v1/chat`: HTTP 200 และเลือกเฉพาะ `PEA_01_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.docx` สำหรับคำถามเอกสารขอใช้ไฟฟ้าใหม่ พร้อมตอบรายการเอกสารโดยตรงและคืน citation ของไฟล์จริง

การทดสอบสดข้างต้นเป็นหลักฐานหนึ่งกรณี ไม่ใช่ผลประเมิน knowledge ครบทั้งชุด

## ชุดข้อมูลประเมิน

| ชุดข้อมูล | จำนวนกรณี | ความครอบคลุม |
|---|---:|---|
| Knowledge | 40 | การตอบตรงคำถามจากเอกสาร การอ้างอิง และ no-evidence |
| OMS | 10 | สถานะและการรายงานไฟฟ้าดับ (**SIMULATED**) |
| Sabuy | 10 | บัญชีตัวอย่างและการเตรียมชำระเงิน (**SIMULATED**) |
| VOC | 10 | การจัดหมวดหมู่และเตรียมเคส (**SIMULATED**) |
| Multi-tool | 10 | การประสานหลาย tool |
| Adversarial | 10 | prompt injection, invalid fields และ write safety |

## เกณฑ์การเผยแพร่

**สถานะการเผยแพร่: NOT READY** จนกว่าจะครบทุกข้อ:

1. เจ้าของข้อมูลยืนยันว่า DOCX ทั้ง 27 ไฟล์เป็นเอกสารที่อนุมัติและเป็นปัจจุบัน
2. รัน evaluator แบบสดครบทุกกรณีและผ่านเกณฑ์ `knowledgeCorrectness`, `citationPresence`, routing และ no-evidence
3. ตรวจ context budget กับคำถามที่เลือกหลายไฟล์
4. หากการแข่งขันบังคับให้ Main Agent ใช้ provider จริงแทน `DemoLLMAdapter` ต้องเชื่อมต่อ `LLMAdapter` ของ provider นั้น
5. การ deploy จริงต้องได้รับการยืนยันจากผู้ใช้ก่อน
