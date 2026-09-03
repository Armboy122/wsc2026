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
uv sync --extra dev --extra voice

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

ระบบหาคำตอบจากไฟล์ Markdown (`.md`) ที่ผ่านการอนุมัติ ซึ่งอยู่ในโฟลเดอร์นี้:

```text
knowledge/source/          เอกสารบริการต่าง ๆ (เช่น ขอใช้ไฟฟ้าใหม่, ขอคืนเงินประกัน, eBill …)
knowledge/source/qa/       คำถาม-คำตอบที่อนุมัติแล้ว (หนึ่งหัวข้อต่อหนึ่งไฟล์)
```

**ใน repo นี้มีไฟล์ Markdown ที่ผ่านการอนุมัติครบ 44 ไฟล์** (เอกสารบริการ 33 + Q&A 11) — โคลนมาแล้วใช้ได้ทันที
**ไม่ต้องดาวน์โหลด/อัปโหลด/ซิงก์อะไรเพิ่ม** ระบบอ่านไฟล์โดยตรงจากดิสก์
(backend `full_document` อ่านจาก `KNOWLEDGE_SOURCE_ROOT` ซึ่งค่าเริ่มต้นคือ `knowledge/source`)

### ถ้าอยากใช้เนื้อหาของตัวเอง (ไฟล์ Markdown ของคุณเอง)

1. นำไฟล์ `.md` แบบ UTF-8 ที่ผ่านการอนุมัติไปวางใน `knowledge/source/`
   (ไฟล์ Q&A วางใน `knowledge/source/qa/` โดยหนึ่งหัวข้อต่อหนึ่งไฟล์)
2. Restart เซิร์ฟเวอร์เมื่อเปลี่ยน corpus เพื่อให้สถานะ readiness ตรวจข้อมูลชุดใหม่

### เงื่อนไขที่ Knowledge ต้องมีเพื่อจะตอบได้

- ตั้งค่าใน `.env`:
  ```dotenv
  KNOWLEDGE_LLM_PROVIDER=gemini
  GEMINI_API_KEY=your-google-ai-key
  ```
- ตรวจสอบความพร้อมได้ที่ `http://127.0.0.1:8000/health` — ต้องเห็น
  `"knowledge_backend": "ready"` (ถ้าเป็น `unavailable` แปลว่า key/ไฟล์ไม่พร้อม)

> หมายเหตุ: ไม่มีขั้นตอนอัปโหลด ซิงก์ หรือสร้างดัชนีใด ๆ เอกสารทั้งหมดอยู่บนเครื่องนี้
> และถูกอ่านสด ๆ จากดิสก์ทุกครั้งที่ตอบ

### ถ้าถามแล้วตอบว่า "ไม่มีหลักฐาน"

ตรวจลำดับนี้: 1) ไฟล์ `.md` อยู่ใน `knowledge/source/` จริงไหม 2) `GEMINI_API_KEY` ถูกต้องไหม
3) ระบบ restart หลังเพิ่มไฟล์หรือยัง — ระบบจะตอบแบบ fail-closed (ไม่เดาข้อเท็จจริง) เมื่อหาเอกสารไม่เจอ

---

<a id="voice-mode"></a>
## โหมดเสียง (Voice Mode) — ต้องกด "อนุญาต" (Allow) ก่อน

โหมดเสียงใช้ Gemini Live พูดคุยกับผู้ช่วยแบบเรียลไทม์ (ครอบคลุม Knowledge + OMS)

### ข้อกำหนดก่อนใช้

- [x] ตั้ง `GEMINI_API_KEY` ใน `.env` แล้ว restart เซิร์ฟเวอร์ (ไม่งั้นเจอข้อความ "โหมดเสียงยังไม่ได้ตั้งค่า")
- [x] ติดตั้ง dependency ครบแล้ว — `uv sync --extra dev --extra voice` (มี `--extra voice`
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
| Main Agent | `MAIN_LLM_PROVIDER` / `MAIN_LLM_MODEL` | `demo`, `gemini` |
| Knowledge | `KNOWLEDGE_LLM_PROVIDER` / `KNOWLEDGE_LLM_MODEL` | `gemini` |
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

### ตัวแปรอื่น ๆ ที่น่าสนใจ

| ตัวแปร | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `KNOWLEDGE_SOURCE_ROOT` | โฟลเดอร์เอกสารความรู้ | `knowledge/source` |
| `KNOWLEDGE_BACKEND_NAME` | backend ของความรู้ (ปัจจุบันรองรับค่าเดียว) | `full_document` |
| `OMS_BASE_URL` / `OMS_API_KEY` | OMS จำลอง (REST) | `http://127.0.0.1:8080/api/v1/oms` / `88888888` |
| `VOC_BASE_URL` / `VOC_API_KEY` / `VOC_TIMEOUT_SECONDS` | VOC REST gateway (simulation) | `http://127.0.0.1:8080/api/v1/voc` / `88888888` / `5` |
| `APP_ENV` / `LOG_LEVEL` | environment และระดับ log | `development` / `info` |

---

## ความสามารถของระบบสาธิต

- **แชตข้อความ** — ถาม-ตอบ พร้อม citation ของเอกสารความรู้ Markdown ที่ Document Router เลือก
- **ความรู้ (Knowledge)** — ตอบจากข้อความฉบับเต็มของ Markdown ที่เลือก + ตรวจ citation แบบ fail-closed
- **OMS จำลอง** — ตรวจ/เตรียมแจ้งเหตุไฟฟ้าขัดข้อง (แสดงผลเป็น SIMULATED) โดยต้องกด **ยืนยัน** ก่อนเขียนเสมอ
- **VOC plugin** — เชื่อม VOC REST gateway แบบ simulation (catalog/สร้างเคส/ติดตามเคส) โดยต้องกด **ยืนยัน** ก่อนส่งเคสเสมอ; logic เฉพาะของ VOC อยู่ใน `app/plugins/voc/` และ `app/tools/voc_tool.py` เท่านั้น — MainAgent ไม่มี code เฉพาะ VOC
- **ระบบปลั๊กอิน** — เพิ่มเครื่องมือใหม่ด้วยการเพิ่มโฟลเดอร์ + `plugin.yaml` โดยไม่ต้องแก้ Main Agent; MainAgent ถือ policy กลางเท่านั้น (prepare→confirm→submit, redaction, trace) และไม่ฝัง logic/ข้อความเฉพาะ plugin ใหม่ ๆ
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

## เพิ่มเครื่องมือใหม่ด้วยระบบปลั๊กอิน

ระบบแบ่งเครื่องมือเป็นสองชั้น:

| ชั้น | ตัวอย่าง | ประกอบที่ไหน |
|---|---|---|
| **Built-in** | `knowledge_tool` | `app/main.py` โดยตรง |
| **Plugin** | `oms_tool` | `app/plugins/<id>/plugin.yaml` (ค้นพบตอน startup) |

เพิ่มเครื่องมือใหม่จึง **ไม่ต้องแก้ Main Agent, registry, `main.py` หรือ `startup.py`**
loader จะสแกน `app/plugins/*/plugin.yaml` ตอนเปิดเซิร์ฟเวอร์แล้วลงทะเบียนให้เอง

### สร้างโครงปลั๊กอิน

```bash
./scripts/add-plugin voc            # สร้างโครงใต้ app/plugins/voc/
./scripts/add-plugin voc --preview  # ดูผลลัพธ์ก่อนโดยไม่เขียนไฟล์
```

ได้ 3 ไฟล์: `plugin.yaml`, `factory.py`, `__init__.py`

**ใช้ชื่ออะไรก็ได้** เช่น `./scripts/add-plugin billing` สำหรับ REST ตัวใหม่ที่ยังไม่มีใน contracts

- ถ้าเครื่องมือนั้น**ประกาศไว้แล้ว** ใน `app/contracts.py` script จะ generate `operations` ให้ครบ
  ทั้งรายการ action, `inputContract`/`outputContract`, คู่ `prepare_* → submit_*`
  และตั้ง `exposure: internal` ให้ทุก `submit_*` อัตโนมัติ — จึงไม่มีทาง drift จาก Pydantic
- ถ้าเป็น**ชื่อใหม่** จะได้โครง `operations` พร้อมคำแนะนำไว้ให้ (`enabled: false`)
  เพิ่ม contract แล้วรัน `--force` ซ้ำเพื่อ generate ของจริงทับ

### ขั้นตอนหลังจากนั้น

1. (เฉพาะเครื่องมือใหม่) ประกาศใน `app/contracts.py`: `ToolName`, `ToolAction`, `TOOL_ACTIONS`,
   `INPUT_MODELS`, `OUTPUT_MODELS` และ `PREPARE_TO_SUBMIT` ถ้ามี write flow
   แล้วรัน `./scripts/add-plugin <ชื่อ> --force` ซ้ำ
2. เขียนคลาสเครื่องมือใน `app/tools/<id>_tool.py` — รับผิดชอบ HTTP, authentication, error mapping
3. เติม `description` ทุกจุดที่เป็น `TODO` ใน `plugin.yaml` (ข้อความนี้คือสิ่งที่ LLM ใช้เลือกเครื่องมือ)
4. เพิ่ม `demo.py`/`response.py` เมื่อ plugin ต้องมี deterministic demo planning หรือข้อความผลลัพธ์เฉพาะระบบ
5. แก้ `factory.py` ให้คืน `PluginRuntime(tool=..., response_policy=..., demo_behavior=...)` และส่ง configuration ที่ต้องใช้จริง
6. ตั้ง `enabled: true` แล้ว **restart เซิร์ฟเวอร์**
7. `.venv/bin/python -m pytest -q`

### เปิด/ปิดปลั๊กอิน

แก้บรรทัดเดียวใน `app/plugins/<id>/plugin.yaml`:

```yaml
metadata:
  enabled: true    # false = ข้ามตั้งแต่ก่อน validate/import ไม่กระทบ startup เลย
```

ต้อง restart ทุกครั้ง เพราะ loader อ่าน manifest ครั้งเดียวตอน startup (ไม่มี hot reload โดยตั้งใจ)

โครงที่ยังเขียนไม่เสร็จอยู่ใน repo ได้อย่างปลอดภัย ตราบใดที่ `enabled: false` — loader จะข้ามก่อน
ตรวจความถูกต้อง แต่ถ้าตั้ง `enabled: true` ทั้งที่ manifest ยังไม่สมบูรณ์ **startup จะล้มทันที** (fail closed)

### หน้าที่ของแต่ละส่วน

| ส่วน | หน้าที่ | **ไม่ใช่** หน้าที่ |
|---|---|---|
| `plugin.yaml` | discovery, metadata, ประกาศ operation, ชี้ชื่อ env var | ยิง HTTP, ถือ schema, เก็บ secret |
| `factory.py` | ประกอบ `PluginRuntime` จาก settings | business logic |
| `demo.py` / `response.py` | deterministic demo planning และการแสดงผลเฉพาะ plugin | HTTP/write state machine |
| `app/tools/*.py` | HTTP, authentication, payload/error mapping | planning/presentation |
| `app/contracts.py` | **source of truth เดียว** ของ schema | — |

YAML เก็บเพียง *ชื่อ* คลาส contract (เช่น `inputContract: OmsGetOutageByCaInput`) แล้ว loader
ตรวจกับ Pydantic จริงตอน startup — ถ้าไม่ตรงจะ **fail closed** ทันที จึงไม่มี JSON Schema ชุดที่สอง

### สิ่งที่ระบบบังคับให้เสมอ (write safety)

- `submit_*` ที่เป็น `exposure: internal` **ไม่ถูกส่งเข้าแค็ตตาล็อกของ LLM** โมเดลจึงเรียกเองไม่ได้
- write state machine ยังเป็น `prepare_* → confirm endpoint → submit_*` เหมือนเดิม manifest ข้ามไม่ได้
- `runtime.factory` ต้องอยู่ใต้ `app.plugins.` เท่านั้น ไม่มี `eval`/`exec` ไม่โหลดโค้ดจากภายนอก
- manifest เก็บเพียง *ชื่อ* environment variable ไม่เก็บค่า secret

> **ข้อจำกัดที่ควรรู้:** ระบบนี้ไม่ใช่ Generic REST Engine — YAML บอกได้แค่ว่า *มีอะไร*
> ส่วน *ยิง HTTP อย่างไร* ยังต้องเขียน Python เอง เพราะทุก API มีรูปแบบต่างกัน
> สิ่งที่หายไปคือ **ต้นทุนคงที่** ของการต่อเครื่องมือเข้าระบบ ไม่ใช่ต้นทุนการเขียน adapter

---

## นโยบายข้อความตอบของ Main Agent (direct response และ follow-up)

Main Agent **ไม่ปล่อยข้อความอิสระของโมเดลออกไปโดยตรง** ข้อความที่ผู้ใช้เห็นมาจาก 3 ทางเท่านั้น:

1. **ข้อเท็จจริงจาก tool result** — สถานะเหตุ, เลขอ้างอิง, คำตอบ Knowledge ที่มี citation
   จัดรูปแบบโดย `_authoritative_message` ใน `app/agent/main_agent.py` (แม่แบบต่อ action)
2. **แม่แบบ direct response** — โมเดลเลือก "ป้าย" เช่น `oms_ca_number`, `unsupported`
   แล้ว Main Agent แทนที่ด้วยข้อความ fix ใน `_DIRECT_RESPONSE_MESSAGES` (ไม่เชื่อข้อความโมเดล)
3. **ข้อความของโมเดลเอง (grounded follow-up)** — เฉพาะคำถามต่อเนื่องหลัง `oms_tool.get_outage_by_ca`
   **สำเร็จ** ในบทสนทนาเดียวกัน เช่น "แสดงว่าช่างกำลังมาใช่ไหม" เพราะไม่มีแม่แบบตอบตรง
   และบทสนทนามีหลักฐาน (typed OMS result) ใน history แล้ว

### กติกาลำดับความสำคัญใน `_safe_direct_message`

- ตรวจ output policy (chain-of-thought/secret) ก่อนเสมอ → ถ้าโดนจับ ตอบด้วยข้อความ fix
- ป้าย direct response **ยกเว้น `oms_ca_number`** → ใช้แม่แบบทันที
- ป้าย `oms_ca_number` → ถ้าบทสนทนามีผล OMS สำเร็จแล้ว (`allow_grounded_followup`) และ
  โมเดลมีข้อความตอบ (≤ 500 ตัวอักษร) → ใช้ข้อความโมเดล เพราะโมเดลมักติดป้ายนี้ผิดบน
  คำถามต่อเนื่อง ทำให้ผู้ใช้ถูกถามหมายเลขผู้ใช้ไฟซ้ำ ถ้าไม่เข้าเงื่อนไข → ใช้แม่แบบ
- ไม่มีป้าย ไม่มีผล OMS สำเร็จ → ข้อความความสามารถ fix (fail closed)

### ถ้าต้องการปรับพฤติกรรมนี้ — แก้จุดเดียว

ทั้งหมดอยู่ที่ `app/agent/main_agent.py`: แม่แบบใน `_DIRECT_RESPONSE_MESSAGES`,
ลำดับความสำคัญใน `_safe_direct_message` และเงื่อนไข grounding ที่ `_oms_grounded_conversations`
(ตอนนี้เติมเฉพาะเมื่อ `OMS_GET_OUTAGE_BY_CA` สำเร็จ — ถ้าอยากให้ plugin อื่น เช่น VOC
มี follow-up แบบเดียวกัน ให้เติมเซ็ตนี้เมื่อ action ของ plugin นั้นสำเร็จ)
เทสครอบพฤติกรรมนี้ไว้ใน `tests/test_agent_orchestration.py`
(`test_followup_after_outage_check_does_not_ask_for_the_ca_again`,
`test_mislabeled_oms_ca_followup_after_outage_check_uses_model_text`,
`test_free_text_without_grounded_outage_still_uses_safe_template`)

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

- โปรเจกต์เป็น **ระบบสาธิต** — ผลลัพธ์ OMS และ VOC ระบุ `simulation: true` เสมอ ส่วน Sabuy ยังไม่เปิดใช้งาน
- **ระบบปลั๊กอินไม่ใช่ Generic REST Engine** — เพิ่ม API ใหม่ยังต้องเขียน Python adapter เอง
  YAML รับผิดชอบเพียง discovery และ metadata; ไม่มี hot reload (แก้ manifest แล้วต้อง restart)
- **สถานะการเผยแพร่: NOT READY** — ก่อนเผยแพร่ต้องให้เจ้าของข้อมูลยืนยันว่า Markdown ทั้ง 44 ไฟล์
  ใต้ `knowledge/source/` เป็นเอกสารที่อนุมัติแล้ว และรันชุดประเมิน knowledge แบบสดครบทุกกรณี
- โมเดล Gemini Live เป็น **Preview** — พฤติกรรมและเสียงอาจเปลี่ยนได้โดยไม่แจ้งล่วงหน้า
- ยังไม่มีการทดสอบไมโครโฟน/ลำโพงจริงแบบอัตโนมัติใน CI — ต้องซ้อมสดด้วยมือก่อนนำเสนอ
- การยืนยัน/ปฏิเสธรายการด้วยเสียงผูกกับเซสชัน — ระบบเลือก "รายการปัจจุบัน" ให้เอง
  (โมเดลไม่ได้รับ `pendingActionId` และห้ามยืนยัน/ปฏิเสธเอง)

---

ดูรายละเอียดเชิงเทคนิคเพิ่มเติมได้ที่:

- [`knowledge/README.md`](knowledge/README.md) — สเปกและนโยบายคลังความรู้
- [`web/README.md`](web/README.md) — ส่วนติดต่อผู้ใช้และโหมดเสียง
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — สถาปัตยกรรม รวมรายละเอียดระบบปลั๊กอินและขอบเขตความรับผิดชอบ
- [`CONTRACTS.md`](CONTRACTS.md) — สัญญา API และช่องเสียง `/ws/live`
- [`docs/integration_report.md`](docs/integration_report.md) — หลักฐานการผสานระบบและเกณฑ์อนุมัติการเผยแพร่
