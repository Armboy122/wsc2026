# PEA One Agent MVP

## การติดตั้ง การรัน และการตรวจสอบคุณภาพ

จากไดเรกทอรีรากของ repository ให้ติดตั้งส่วนเสริมสำหรับการพัฒนาและความรู้ คัดลอกไฟล์ตั้งค่า วาง DOCX ที่ผ่านอนุมัติไว้ใต้ `knowledge/source/` จากนั้นเริ่ม API และเปิด UI:

```bash
python3 -m pip install -e ".[dev,knowledge]"
cp .env.example .env
# แก้ค่า provider/model/key ใน .env โดยห้าม commit ค่าลับ
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

Main Agent, Knowledge และ Judge เลือก provider/model แยกกันได้จาก `.env` ไฟล์เดียว โดย Main Agent รองรับ `demo`, `gemini` และ `maxplus_openai` ผ่าน adapter factory กลาง ส่วน Judge ถูกสร้างผ่าน factory เดียวกันและพร้อมส่งให้ integration ของกรรมการภายหลัง:

```dotenv
MAIN_LLM_PROVIDER=gemini
MAIN_LLM_MODEL=gemini-3.5-flash-lite

KNOWLEDGE_LLM_PROVIDER=gemini
KNOWLEDGE_LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your-google-ai-key

JUDGE_LLM_PROVIDER=demo
```

ถ้าเลือก `maxplus_openai` และไม่กำหนด `MAIN_LLM_MODEL`, `MAIN_LLM_API_KEY` หรือ `MAIN_LLM_BASE_URL` ระบบจะใช้ `MAXPLUS_MODEL`, `MAXPLUS_API_KEY` และ `MAXPLUS_BASE_URL` ตามลำดับ ทำให้เปลี่ยนโมเดล MaxPlus ที่ใช้ร่วมกันได้จุดเดียว:

```dotenv
MAIN_LLM_PROVIDER=maxplus_openai
KNOWLEDGE_LLM_PROVIDER=maxplus_openai
MAXPLUS_API_KEY=your-ccsk-key
MAXPLUS_BASE_URL=https://api.maxplus-ai.cc/v1
MAXPLUS_MODEL=deepseek-v4-flash-0731
```

ห้ามใช้ `ccmk-…` management token กับ inference; runtime ต้องใช้ `ccsk-…` key ที่ผูกกับ pool ของ model เท่านั้น

ในอีก terminal หนึ่ง ให้รันชุดทดสอบตามสัญญาที่ตรึงไว้ และตัวประเมิน public envelope:

```bash
python3 -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

ชุด QA ตามสัญญาที่ตรึงไว้คือ `tests/test_mvp_evaluation.py` ครอบคลุม route envelopes และ validation, พฤติกรรมที่แน่นอนของ tool, หลักฐาน/การอ้างอิงจากเอกสารที่เลือก, ข้อเท็จจริงปฏิบัติการจำลอง, state transition ของ prepare/confirm/reject, idempotent writes, ลำดับและการปกปิดข้อมูลใน trace, reset, ความปลอดภัยในการใช้หลาย tools และ adversarial prompts

ชุดข้อมูลเป้าหมายที่กำหนดผลได้แน่นอนอยู่ภายใต้ `evaluation/datasets/` (Knowledge 40, OMS 10, Sabuy 10, VOC 10, Multi-tool 10, Adversarial 10) โดยใช้เฉพาะ fixture เดโมที่ตรึงไว้ (`PEA-1001`..`PEA-1003`, `BKK-01`, `CNX-02`, `HKT-03`) และ prompt สำหรับ prepare จะมีรายละเอียดผู้ใช้อย่างชัดเจน

OMS, Sabuy และ VOC เป็นระบบ **SIMULATED** ส่วนความรู้ใช้ Document Router เลือก DOCX ที่เกี่ยวข้อง รวมถึง Approved Q&A ใต้ `knowledge/source/qa/` และส่งข้อความฉบับเต็มของไฟล์ที่เลือกให้ provider ที่กำหนด (`gemini` หรือ `maxplus_openai`) เมื่อไม่มีเอกสารที่เลือกได้หรือ provider ใช้งานไม่ได้ ระบบจะแจ้งว่าจะขอส่งต่อคำถามให้เจ้าหน้าที่ตรวจสอบ โดยต้องไม่รายงานว่าเป็นความรู้ที่มีหลักฐานรองรับ ทั้งนี้ยังไม่มีการสร้าง ticket จริงจนกว่าจะทำ optional roadmap ใน `docs/plans/qa-learning-roadmap.md` ข้อความแชตไม่ใช่การยืนยัน

## โหมดเสียง Gemini Live (Voice Mode)

โหมดเสียงเป็นช่องทางขนส่งเรียลไทม์เพิ่มเติมบน Main Agent เดิม ขอบเขตความสามารถ
คือ **Knowledge และ VOC** (ตรงกับ runtime catalogue ที่เปิดใช้) เปิด/ปิดด้วย
ปุ่มไมโครโฟนในช่องเขียนข้อความ เบราว์เซอร์จับเสียงไมโครโฟน (AudioWorklet),
downsample เป็น PCM16 16kHz แล้วส่งเป็น binary ผ่าน WebSocket `/ws/live`
(same-origin) และเล่นเสียงตอบกลับ PCM16 24kHz แบบต่อเนื่อง

ความปลอดภัย: การยืนยัน/ปฏิเสธรายการที่เตรียมไว้ทำด้วยเสียงและ **ผูกกับเซสชัน**
— ระบบเลือก "รายการปัจจุบัน" ให้เอง โมเดลไม่ได้รับ `pendingActionId` จะถามย้ำ
เมื่อคำตอบกำกวม และห้ามยืนยัน/ปฏิเสธเอง รายละเอียดสัญญาอยู่ในส่วน
"ช่องเสียง `/ws/live`" ของ `CONTRACTS.md`

### ตัวแปร environment ที่จำเป็น

```dotenv
GEMINI_API_KEY=your-google-ai-key      # ใช้ฝั่งเซิร์ฟเวอร์เท่านั้น ห้ามส่งไปเบราว์เซอร์
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_LIVE_VOICE=Puck
```

โมเดล Live เป็น **Preview** — พฤติกรรมและเสียงอาจเปลี่ยนได้โดยไม่แจ้งเตือนล่วงหน้า

### การรัน

ใช้คำสั่งเดียวกับแชตข้อความ แล้วเปิดหน้าเว็บและกดปุ่มไมโครโฟน:

```bash
python3 -m uvicorn app.main:app --reload
open http://127.0.0.1:8000
```

เมื่อกดปุ่มไมโครโฟนครั้งแรก เบราว์เซอร์จะขอสิทธิ์ไมโครโฟน — ต้องอนุญาตจึงใช้งานได้

### คำแนะนำไมโครโฟน/หูฟัง

- **ใช้หูฟัง** เพื่อลดเสียงสะท้อนระหว่างลำโพงกับไมโครโฟน (echo)
- ใช้ไมโครโฟนในที่เงียบ ห่างปากประมาณ 15–30 ซม. และพูดทีละประโยค
- เบราว์เซอร์ต้องรองรับ AudioWorklet และ `getUserMedia` — แนะนำ Chrome/Edge ล่าสุด
  (เสียงผู้พูดแทรกจะตัดเสียงตอบที่เหลือทันทีผ่าน `audio.interrupted`)

### การแก้ปัญหา (troubleshooting)

| อาการ | วิธีแก้ |
|---|---|
| "โหมดเสียงยังไม่ได้ตั้งค่า" | ตั้ง `GEMINI_API_KEY` ใน `.env` แล้ว restart เซิร์ฟเวอร์ |
| เปิดโหมดเสียงไม่สำเร็จ | อนุญาตสิทธิ์ไมโครโฟน ใช้ `http://127.0.0.1:8000` หรือ https และตรวจว่าเบราว์เซอร์รองรับ AudioWorklet |
| ได้ยินเสียงสะท้อน/ไม่ชัด | ใช้หูฟัง ลดเสียงรอบข้าง และตรวจว่าไมโครโฟนเริ่มต้นของระบบเป็นตัวที่ต้องการ |
| ไม่ได้ยินเสียงตอบกลับ | ตรวจระดับเสียงเบราว์เซอร์/ระบบ — การพูดแทรกระหว่างที่ผู้ช่วยพูดจะตัดเสียงที่เหลือ (interruption) |
| โหมดเสียงหลุดกลางคัน | ตรวจ network และ API key; WebSocket ใหม่จะสร้าง Gemini session และการสนทนาใหม่เสมอ |

### ข้อจำกัดการตรวจสอบ (honest)

- **ยังไม่มีการทดสอบไมโครโฟน/ลำโพงจริงแบบอัตโนมัติใน CI** — ต้องซ้อมสดด้วยมือก่อนนำเสนอ
- การตรวจสอบสดด้วย key จริงยืนยันแล้วว่า `/ws/live` เชื่อม Gemini Live และได้รับ `session.ready`; การทดสอบ SDK โดยตรงรับ transcription และ PCM audio กลับมาได้ แต่ยังไม่แทนการซ้อมผ่านไมโครโฟน/ลำโพงของเบราว์เซอร์
- โมเดล Preview อาจเปลี่ยนพฤติกรรมโดยไม่แจ้งเตือนล่วงหน้า และช่องเสียงเปิดใช้เฉพาะ Knowledge/VOC

## หลักฐานการตรวจสอบล่าสุด

ชุด `pytest` ทั้งหมดผ่าน **238 tests** พร้อม deprecation warnings 5 รายการจาก dependency ภายนอก การทดสอบสดผ่าน `POST /api/v1/chat` ยืนยันว่า Document Router เลือกเฉพาะไฟล์ `PEA_01_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.docx`, ส่งข้อความฉบับเต็มของไฟล์ดังกล่าวให้ Gemini Long Context และคืนคำตอบรายการเอกสารที่ครบถ้วนพร้อม citation ของไฟล์จริง ส่วน MaxPlus ผ่าน automated adapter/configuration tests แล้ว แต่ยังต้องใช้ `ccsk-…` key ของผู้ดูแลเพื่อ benchmark สด

ระบบปฏิบัติการ (OMS, Sabuy และ VOC) ยังคงแสดงอย่างชัดเจนว่าเป็น **SIMULATED** ไม่มีการบันทึกข้อมูลลับใด ๆ ไว้ที่นี่

**สถานะการเผยแพร่: NOT READY.** ก่อนเผยแพร่ต้องให้เจ้าของข้อมูลยืนยันว่า DOCX ทั้ง 38 ไฟล์ใต้ `knowledge/source/` เป็นเอกสารที่อนุมัติแล้ว และรันชุดประเมิน knowledge แบบสดครบทุกกรณี ห้ามถือว่าการผ่านตัวอย่างสดหนึ่งคำถามเป็นการอนุมัติ deployment

ดูหลักฐานการผสานระบบและเกณฑ์อนุมัติการเผยแพร่ได้ที่ [`docs/integration_report.md`](docs/integration_report.md)
