# PEA One Agent MVP

## การติดตั้ง การรัน และการตรวจสอบคุณภาพ

จากไดเรกทอรีรากของ repository ให้ติดตั้งส่วนเสริมสำหรับการพัฒนาและความรู้แบบโฮสต์ กำหนดค่า Gemini โดยไม่แสดงค่าลับ จากนั้นเริ่ม API และเปิด UI:

```bash
python3 -m pip install -e ".[dev,knowledge]"
read -rsp "Gemini API key: " GEMINI_API_KEY; echo; export GEMINI_API_KEY
read -rp "Gemini File Search store: " GEMINI_FILE_SEARCH_STORE; export GEMINI_FILE_SEARCH_STORE
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

ในอีก terminal หนึ่ง ให้รันชุดทดสอบตามสัญญาที่ตรึงไว้ และตัวประเมิน public envelope:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

ชุด QA ตามสัญญาที่ตรึงไว้คือ `tests/test_mvp_evaluation.py` ครอบคลุม route envelopes และ validation, พฤติกรรมที่แน่นอนของ tool, หลักฐาน/การอ้างอิงจาก hosted knowledge, ข้อเท็จจริงปฏิบัติการจำลอง, state transition ของ prepare/confirm/reject, idempotent writes, ลำดับและการปกปิดข้อมูลใน trace, reset, ความปลอดภัยในการใช้หลาย tools และ adversarial prompts

ชุดข้อมูลเป้าหมายที่กำหนดผลได้แน่นอนอยู่ภายใต้ `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10) โดยใช้เฉพาะ fixture เดโมที่ตรึงไว้ (`PEA-1001`..`PEA-1003`, `BKK-01`, `CNX-02`, `HKT-03`) และ prompt สำหรับ prepare จะมีรายละเอียดผู้ใช้อย่างชัดเจน

OMS, Sabuy และ VOC เป็นระบบ **SIMULATED** Gemini File Search คือผู้ให้บริการความรู้แบบโฮสต์ และจะปิดการทำงานเมื่อเกิดข้อผิดพลาด: หากไม่มีหรือใช้ค่า Gemini ไม่ได้ ต้องรายงานว่า degraded และห้ามรายงานว่าเป็นความรู้ที่มีหลักฐานรองรับ ข้อความแชตไม่ใช่การยืนยัน

## หลักฐานสำหรับรุ่นสุดท้ายที่ผ่านการเสริมความแข็งแกร่ง

การรันครั้งสุดท้ายที่หัวหน้าทีมจัดเตรียมใช้โมเดล **OpenAI Terra** ที่ได้รับมอบหมายใหม่ ชุด `pytest` ทั้งหมดผ่าน **131 passed** พร้อม **4 deprecation warnings** ตัวประเมินแบบ live ที่ `127.0.0.1:8010` ประเมินกรณีทดสอบจากชุดข้อมูลครบทั้ง 90 กรณี รวมถึงสถานะระบบ ได้ผลดังนี้:

| รายการตรวจ | ผลลัพธ์ |
|---|---:|
| `routingAccuracy` | 1.0 |
| `writeSafety` | 1.0 |
| `scenarioCompletion` | 1.0 |
| `completion` | 1.0 |
| `unsupportedClaimRate` | 0.0 |
| เวลาตอบสนองเฉลี่ย | 0.86 ms |
| เวลาตอบสนอง P95 | 1.07 ms |
| เวลาตอบสนองสูงสุด | 5.38 ms |
| `knowledgeCorrectness` | 0.0 |
| `citationPresence` | 0.025 |
| สถานะระบบ | degraded: knowledge unavailable |

ค่า `citationPresence` ที่ `0.025` มาจากกรณีควบคุมเชิงลบหนึ่งกรณีที่มี `mustCite=false` จึง **ไม่ใช่** หลักฐานของการอ้างอิงที่มีแหล่งข้อมูลรองรับ ที่เก็บโค้ดนี้ตั้งใจไม่บรรจุเอกสารต้นฉบับ PEA ที่เชื่อถือได้ไว้ใต้ `knowledge/source`; ข้อเท็จจริงตัวอย่างที่ไม่มีแหล่งอ้างอิงถูกลบออกแล้ว

ระบบปฏิบัติการ (OMS, Sabuy และ VOC) ยังคงแสดงอย่างชัดเจนว่าเป็น **SIMULATED** ไม่มีการบันทึกข้อมูลลับใด ๆ ไว้ที่นี่

**สถานะการเผยแพร่: NOT READY.** การเผยแพร่ต้องมีครบทั้งสองข้อ: (ก) เอกสาร PEA ที่เชื่อถือได้ซึ่งหัวหน้าทีมอนุมัติ และซิงก์เข้าสู่ Gemini File Search store จริงพร้อมข้อมูลรับรอง รวมถึงมีผลการรันจริงที่ผ่านเกณฑ์ citations; และ (ข) หากการแข่งขันกำหนดให้ใช้ผู้ให้บริการสำหรับกรรมการแบบใช้งานจริงแทน `DemoLLMAdapter` ที่กำหนดผลได้แน่นอน ต้องจัดหาและเชื่อมต่อ `LLMAdapter` ของผู้ให้บริการนั้น โค้ดมีเพียงจุดเชื่อมต่อ `JudgeLLMClient` ที่ไม่ผูกกับผู้ให้บริการรายใด ห้ามถือว่าการผสานระบบภายนอกที่ไม่พร้อมใช้งานผ่านการตรวจแล้ว

ดูหลักฐานการผสานระบบและเกณฑ์อนุมัติการเผยแพร่ได้ที่ [`docs/integration_report.md`](docs/integration_report.md)
