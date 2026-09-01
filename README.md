# PEA One Agent — ระบบสาธิต (MVP)

ผู้ช่วยบริการลูกค้าไฟฟ้าแบบ **ระบบสาธิต** ที่ตอบคำถามจากเอกสารความรู้ (Knowledge) ตรวจ/เตรียม
แจ้งเหตุไฟฟ้าขัดข้องผ่าน OMS จำลอง และคุยด้วยเสียงได้ (Voice Mode ผ่าน Gemini Live)

> ⚠️ โปรเจกต์นี้เป็น **ข้อมูลจำลอง (Simulated Backend)** เท่านั้น — ไม่มีการเข้าถึงข้อมูลลูกค้าจริง
> ระบบชำระเงินจริง หรือระบบการผลิตของ กฟภ. หน้าจอจะแสดงป้าย `SIMULATED BACKEND` ตลอดเวลา

---

## Quick Start — รันให้ได้ใน 5 นาที

เปิด Terminal แล้วพิมพ์ตามนี้ทีละบรรทัด (คัดลอกได้เลย):

```bash
# 1) โคลนโปรเจกต์ (ชื่อโฟลเดอร์อาจต่างจากนี้ตามชื่อ repo)
git clone https://github.com/Armboy122/wsc2026.git
cd wsc2026

# 2) ติดตั้ง dependencies (ใช้ uv — ดูวิธีติดตั้งด้านล่าง)
uv sync --extra dev --extra knowledge

# 3) สร้างไฟล์ตั้งค่าจากตัวอย่าง
cp .env.example .env

# 4) เปิดไฟล์ .env แล้วใส่ GEMINI_API_KEY (หาได้จาก https://aistudio.google.com/apikey)
#    ลงในบรรทัด GEMINI_API_KEY=...

# 5) รันเซิร์ฟเวอร์
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 6) เปิดเว็บในเบราว์เซอร์
open http://127.0.0.1:8000
```

เสร็จแล้ว พิมพ์ถามได้เลย เช่น *"ต้องการขอใช้ไฟฟ้าต้องมีเอกสารอะไรบ้าง"*

> **ข้อสำคัญสำหรับโหมดเสียง:** ถ้าจะใช้ Voice ต้องกดปุ่มไมโครโฟน 🎙 แล้วกดปุ่ม **"อนุญาต" (Allow)**
> เมื่อเบราว์เซอร์ขอสิทธิ์ใช้ไมโครโฟน — ดูรายละเอียดในส่วน [โหมดเสียง](#voice-mode)

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

| ของที่ต้องมี | รายละเอียด |
|---|---|
| **Python 3.11 ขึ้นไป** | ตรวจด้วย `python3 --version` |
| **[uv](https://docs.astral.sh/uv/)** | ตัวจัดการ dependency + virtualenv ติดตั้งด้วย `curl -LsSf https://astral.sh/uv/install.sh \| sh` แล้วเปิด Terminal ใหม่ |
| **GEMINI_API_KEY** | คีย์ฟรีจาก [Google AI Studio](https://aistudio.google.com/apikey) — จำเป็นสำหรับแชต (provider `gemini`), การค้นหาความรู้ และโหมดเสียง |
| **เบราว์เซอร์** | Chrome / Edge เวอร์ชันล่าสุด (จำเป็นสำหรับโหมดเสียง — ต้องรองรับ AudioWorklet) |
| **เนื้อหาความรู้ (Knowledge)** | อยู่ใน repo อยู่แล้ว — ดูหัวข้อถัดไป ไม่ต้องโหลดอะไรเพิ่ม |

---

## ความรู้ (Knowledge) — ต้องมีเนื้อหาอยู่ก่อนถึงจะตอบได้

ระบบหาคำตอบจากไฟล์ DOCX ที่ผ่านการอนุมัติ ซึ่งอยู่ในโฟลเดอร์นี้:

```text
knowledge/source/          เอกสารบริการต่าง ๆ (เช่น ขอใช้ไฟฟ้าใหม่, ขอคืนเงินประกัน, eBill …)
knowledge/source/qa/       คำถาม-คำตอบที่อนุมัติแล้ว (หนึ่งหัวข้อต่อหนึ่งไฟล์)
```

**ใน repo นี้มีไฟล์ DOCX ให้ครบแล้ว 38 ไฟล์** (เอกสารบริการ 27 + Q&A 11) — โคลนมาแล้วใช้ได้ทันที
**ไม่ต้องดาวน์โหลด/อัปโหลด/ซิงก์อะไรเพิ่ม** ระบบอ่านไฟล์โดยตรงตอนเริ่มเซิร์ฟเวอร์
(backend `full_document` อ่านจาก `KNOWLEDGE_SOURCE_ROOT` ซึ่งค่าเริ่มต้นคือ `knowledge/source`)

### ถ้าอยากใช้เนื้อหาของตัวเอง (ไฟล์ DOCX ของคุณเอง)

1. นำไฟล์ DOCX ที่ผ่านการอนุมัติไปวางใน `knowledge/source/`
   (ไฟล์ Q&A วางใน `knowledge/source/qa/` โดยหนึ่งหัวข้อต่อหนึ่งไฟล์)
2. Restart เซิร์ฟเวอร์ — ระบบค้นพบไฟล์ใหม่ให้อัตโนมัติ ไม่มีขั้นตอนอัปโหลด

### เงื่อนไขที่ Knowledge ต้องมีเพื่อจะตอบได้

- ตั้งค่าใน `.env`:
  ```dotenv
  KNOWLEDGE_LLM_PROVIDER=gemini        # หรือ maxplus_openai
  GEMINI_API_KEY=your-google-ai-key    # เมื่อใช้ gemini
  ```
- ตรวจสอบความพร้อมได้ที่ `http://127.0.0.1:8000/health` — ต้องเห็น
  `"knowledge_backend": "ready"` (ถ้าเป็น `unavailable` แปลว่า key/ไฟล์ไม่พร้อม)

> หมายเหตุ: `scripts/sync_knowledge.py` เป็นสคริปต์ซิงก์ไปยัง Gemini File Search ของระบบเก่า
> **ไม่จำเป็นต้องรัน** เพื่อใช้ Knowledge ในเวอร์ชันปัจจุบัน

### ถ้าถามแล้วตอบว่า "ไม่มีหลักฐาน"

ตรวจลำดับนี้: 1) ไฟล์ DOCX อยู่ใน `knowledge/source/` จริงไหม 2) `GEMINI_API_KEY` ถูกต้องไหม
3) ระบบ restart หลังเพิ่มไฟล์หรือยัง — ระบบจะตอบแบบ fail-closed (ไม่เดาข้อเท็จจริง) เมื่อหาเอกสารไม่เจอ

---

<a id="voice-mode"></a>
## โหมดเสียง (Voice Mode) — ต้องกด "อนุญาต" (Allow) ก่อน

โหมดเสียงใช้ Gemini Live พูดคุยกับผู้ช่วยแบบเรียลไทม์ (ครอบคลุม Knowledge + OMS)

### ข้อกำหนดก่อนใช้

- [x] ตั้ง `GEMINI_API_KEY` ใน `.env` แล้ว restart เซิร์ฟเวอร์ (ไม่งั้นเจอข้อความ "โหมดเสียงยังไม่ได้ตั้งค่า")
- [x] ติดตั้ง dependency ครบแล้ว — `uv sync --extra dev --extra knowledge` (มี `--extra knowledge`
  ซึ่งติดตั้ง `google-genai` ที่โหมดเสียงต้องใช้)
- [x] เปิดเว็บผ่าน **`http://127.0.0.1:8000` หรือ https** (สิทธิ์ไมโครโฟนไม่ทำงานบน `http://` ที่ไม่ใช่ localhost)
- [x] เบราว์เซอร์ Chrome/Edge ล่าสุด

### วิธีเปิดใช้ (ขั้นตอนนี้สำคัญ)

1. กดปุ่มไมโครโฟน **🎙** ในช่องพิมพ์ข้อความ
2. เบราว์เซอร์จะแสดงป๊อปอัปถามสิทธิ์ใช้ไมโครโฟน → **ต้องกดปุ่ม "อนุญาต" (Allow)**
3. ถึงจะเริ่มฟังได้ — พูดคำถามได้เลย และจะได้ยินเสียงตอบกลับจากผู้ช่วย

> หากไม่กดอนุญาต หรือกด "บล็อก" โหมดเสียงจะเปิดไม่ได้ (หน้าจอแจ้ง "เปิดโหมดเสียงไม่สำเร็จ
> กรุณาอนุญาตไมโครโฟนและลองใหม่อีกครั้ง")
>
> เคยบล็อกไปแล้ว? แก้ได้ที่ไอคอนรูปกุญแจ 🔒 ข้าง URL → ตั้งค่าไซต์ → ไมโครโฟน → **อนุญาต** → รีเฟรชหน้า

### ตัวแปร environment สำหรับเสียง (มีค่าเริ่มต้นแล้ว ไม่ต้องแก้ก็ได้)

```dotenv
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview   # โมเดลเสียง (เป็น Preview)
GEMINI_LIVE_VOICE=Puck                             # เสียงพูด
```

### เคล็ดลับไมโครโฟน/หูฟัง

- **ใช้หูฟัง** เพื่อลดเสียงสะท้อนระหว่างลำโพงกับไมโครโฟน
- พูดในที่เงียบ ห่างปากประมาณ 15–30 ซม. พูดทีละประโยค
- การพูดแทรกขณะผู้ช่วยกำลังพูดจะตัดเสียงที่เหลือทันที (interruption) — รอจบก่อนพูด

---

## รันและตรวจสอบคุณภาพ

ในอีก Terminal หนึ่ง (ขณะที่เซิร์ฟเวอร์รันอยู่) รันชุดทดสอบและตัวประเมิน:

```bash
uv run pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

---

## ตั้งค่าเพิ่มเติม (ตัวแปร environment หลัก)

ไฟล์ตั้งค่าอยู่ที่ `.env` (สร้างจาก `cp .env.example .env` — **ห้าม commit .env**)

### Provider ของ LLM (เลือกแยกกันได้)

| บทบาท | ตัวแปร | ค่าที่รองรับ |
|---|---|---|
| Main Agent | `MAIN_LLM_PROVIDER` / `MAIN_LLM_MODEL` | `demo`, `gemini`, `maxplus_openai` |
| Knowledge | `KNOWLEDGE_LLM_PROVIDER` / `KNOWLEDGE_LLM_MODEL` | `gemini`, `maxplus_openai` |
| Judge | `JUDGE_LLM_PROVIDER` | `demo` (สำหรับการพัฒนาทั่วไป) |

ตัวอย่างการตั้งค่า Gemini:

```dotenv
MAIN_LLM_PROVIDER=gemini
MAIN_LLM_MODEL=gemini-3.5-flash-lite
KNOWLEDGE_LLM_PROVIDER=gemini
KNOWLEDGE_LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your-google-ai-key
JUDGE_LLM_PROVIDER=demo
```

ตัวอย่างการตั้งค่า MaxPlus (OpenAI-compatible):

```dotenv
MAIN_LLM_PROVIDER=maxplus_openai
KNOWLEDGE_LLM_PROVIDER=maxplus_openai
MAXPLUS_API_KEY=your-ccsk-key
MAXPLUS_BASE_URL=https://api.maxplus-ai.cc/v1
MAXPLUS_MODEL=deepseek-v4-flash-0731
```

> ⚠️ ใช้ `ccsk-…` key สำหรับ inference เท่านั้น — ห้ามใช้ `ccmk-…` management token

### ตัวแปรอื่น ๆ ที่น่าสนใจ

| ตัวแปร | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `KNOWLEDGE_SOURCE_ROOT` | โฟลเดอร์เอกสารความรู้ | `knowledge/source` |
| `KNOWLEDGE_BACKEND_NAME` | backend ของความรู้ (ปัจจุบันรองรับค่าเดียว) | `full_document` |
| `OMS_BASE_URL` / `OMS_API_KEY` | OMS จำลอง (REST) | `http://127.0.0.1:8080/api/v1/oms` / `88888888` |
| `APP_ENV` / `LOG_LEVEL` | environment และระดับ log | `development` / `info` |

---

## ความสามารถของระบบสาธิต

- **แชตข้อความ** — ถาม-ตอบ พร้อม citation ของเอกสารความรู้ (DOCX ที่ Document Router เลือก)
- **ความรู้ (Knowledge)** — ตอบจากข้อความฉบับเต็มของ DOCX ที่เลือก + ตรวจ citation แบบ fail-closed
- **OMS จำลอง** — ตรวจ/เตรียมแจ้งเหตุไฟฟ้าขัดข้อง (แสดงผลเป็น SIMULATED) โดยต้องกด **ยืนยัน** ก่อนเขียนเสมอ
- **Trace (การตรวจสอบ)** — ดูเหตุการณ์ที่เรียงตามลำดับและปกปิดข้อมูลแล้ว
- **โหมดเสียง (Voice)** — พูดคุยด้วย Gemini Live (ต้องอนุญาตไมโครโฟนก่อน)
- **รีเซ็ต** — ล้างบทสนทนาและสถานะจำลอง

### API หลัก

| เส้นทาง | ใช้สำหรับ |
|---|---|
| `POST /api/v1/chat` | ส่งข้อความ |
| `POST /api/v1/actions/{id}/confirm` / `reject` | ยืนยัน / ปฏิเสธรายการที่เตรียมไว้ |
| `GET /api/v1/traces/{traceId}` | ดู trace |
| `POST /api/v1/reset` | รีเซ็ตการสาธิต |
| `GET /health` | ตรวจสอบความพร้อม |
| `WS /ws/live` | โหมดเสียง Gemini Live |

---

## การแก้ปัญหา (Troubleshooting)

| อาการ | วิธีแก้ |
|---|---|
| `command not found: uv` | ติดตั้ง uv ก่อน: `curl -LsSf https://astral.sh/uv/install.sh \| sh` แล้วเปิด Terminal ใหม่ |
| รัน `uv sync` ไม่ผ่าน | ตรวจว่า Python ≥ 3.11 และอินเทอร์เน็ตปกติ |
| "โหมดเสียงยังไม่ได้ตั้งค่า" | ตั้ง `GEMINI_API_KEY` ใน `.env` แล้ว restart เซิร์ฟเวอร์ |
| เปิดโหมดเสียงไม่สำเร็จ | กด **อนุญาต (Allow)** เมื่อเบราว์เซอร์ขอสิทธิ์ไมโครโฟน; ใช้ `http://127.0.0.1:8000` หรือ https; ตรวจว่าใช้ Chrome/Edge ล่าสุด |
| เคยบล็อกไมโครโฟนไปแล้ว | ไอคอนกุญแจ 🔒 ข้าง URL → ตั้งค่าไซต์ → ไมโครโฟน → อนุญาต → รีเฟรช |
| ได้ยินเสียงสะท้อน/ไม่ชัด | ใช้หูฟัง ลดเสียงรอบข้าง ตรวจไมโครโฟนเริ่มต้นของระบบ |
| ไม่ได้ยินเสียงตอบกลับ | ตรวจระดับเสียงเบราว์เซอร์/ระบบ; การพูดแทรกจะตัดเสียงที่เหลือ (interruption) |
| โหมดเสียงหลุดกลางคัน | ตรวจ network และ API key — WebSocket ใหม่จะสร้าง Gemini session และการสนทนาใหม่เสมอ |
| Knowledge ตอบว่าไม่มีหลักฐาน | ตรวจไฟล์ใน `knowledge/source/`, `GEMINI_API_KEY`, และ restart หลังเพิ่มไฟล์ |
| `/health` แสดง `knowledge_backend: unavailable` | ตั้งค่า Knowledge provider/key ให้ถูกต้อง (ดูส่วนความรู้) |

---

## ข้อจำกัด (พูดตรง ๆ)

- โปรเจกต์เป็น **ระบบสาธิต** — OMS/VOC ทำงานแบบจำลอง ไม่มีการเชื่อมต่อระบบจริง
- **สถานะการเผยแพร่: NOT READY** — ก่อนเผยแพร่ต้องให้เจ้าของข้อมูลยืนยันว่า DOCX ทั้ง 38 ไฟล์
  ใต้ `knowledge/source/` เป็นเอกสารที่อนุมัติแล้ว และรันชุดประเมิน knowledge แบบสดครบทุกกรณี
- โมเดล Gemini Live เป็น **Preview** — พฤติกรรมและเสียงอาจเปลี่ยนได้โดยไม่แจ้งล่วงหน้า
- ยังไม่มีการทดสอบไมโครโฟน/ลำโพงจริงแบบอัตโนมัติใน CI — ต้องซ้อมสดด้วยมือก่อนนำเสนอ
- การยืนยัน/ปฏิเสธรายการด้วยเสียงผูกกับเซสชัน — ระบบเลือก "รายการปัจจุบัน" ให้เอง
  (โมเดลไม่ได้รับ `pendingActionId` และห้ามยืนยัน/ปฏิเสธเอง)

---

ดูรายละเอียดเชิงเทคนิคเพิ่มเติมได้ที่:

- [`knowledge/README.md`](knowledge/README.md) — สเปกและนโยบายคลังความรู้
- [`web/README.md`](web/README.md) — ส่วนติดต่อผู้ใช้และโหมดเสียง
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — สถาปัตยกรรม
- [`CONTRACTS.md`](CONTRACTS.md) — สัญญา API และช่องเสียง `/ws/live`
- [`docs/integration_report.md`](docs/integration_report.md) — หลักฐานการผสานระบบและเกณฑ์อนุมัติการเผยแพร่
