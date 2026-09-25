# PEA Knowledge Voice Agent

ผู้ช่วยเสียงภาษาไทยที่ตอบคำถามบริการของ กฟภ. (PEA) **จากเอกสารความรู้ที่ได้รับอนุมัติเท่านั้น**
ADK + Gemini Live เป็นโมเดลสนทนาเดียว และความสามารถทางธุรกิจเดียวคือการดึงเอกสาร Markdown
ในเครื่องแบบ deterministic

```text
ไมโครโฟน (browser) → WS /ws/live → ADK Runner.run_live() → Gemini Live
  → get_knowledge_documents → knowledge/source/*.md (ฉบับเต็ม) → Gemini Live session เดิม → ลำโพง
```

ไม่มีแชตแบบพิมพ์, LINE, OMS/VOC, การคำนวณค่าไฟ, pending action หรือ REST API ทางธุรกิจ
ดู [ARCHITECTURE.md](ARCHITECTURE.md) และ [CONTRACTS.md](CONTRACTS.md)

## สิ่งที่ต้องมี

| สิ่งที่ต้องมี | รายละเอียด |
| --- | --- |
| Python 3.11+ | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `GEMINI_API_KEY` | จาก [Google AI Studio](https://aistudio.google.com/apikey) — จำเป็นสำหรับโหมดเสียงเท่านั้น |
| เบราว์เซอร์ | Chrome/Edge รุ่นล่าสุด (AudioWorklet + สิทธิ์ไมโครโฟน) |

## ติดตั้งและรัน

```bash
git clone https://github.com/Armboy122/wsc2026.git
cd wsc2026
uv sync --frozen --extra dev --extra voice --extra adk
cp .env.example .env          # แล้วใส่ GEMINI_API_KEY=...
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

เปิด <http://127.0.0.1:8000> กดปุ่มไมโครโฟน อนุญาตสิทธิ์ แล้วถาม เช่น
*"ขอใช้ไฟฟ้าใหม่ต้องใช้เอกสารอะไรบ้าง"* หน้าจำลองโทรศัพท์อยู่ที่ `/phone.html`

ตรวจสถานะ: `curl http://127.0.0.1:8000/health` (ดูความหมายฟิลด์ใน CONTRACTS.md)

## การตั้งค่า (`.env`)

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
| --- | --- | --- |
| `APP_ENV` | `development` | ป้ายสภาพแวดล้อม |
| `LOG_LEVEL` | `info` | ระดับ log |
| `GEMINI_API_KEY` | — | คีย์ Gemini (ห้าม commit, ห้ามใส่ใน `web/`) |
| `GEMINI_LIVE_MODEL` | `gemini-3.8-live` | โมเดล Gemini Live |
| `GEMINI_LIVE_VOICE` | `Puck` | เสียงสังเคราะห์ |
| `KNOWLEDGE_SOURCE_ROOT` | `knowledge/source` | root ของเอกสารความรู้ |

## เอกสารความรู้

- `knowledge/source/*.md` — เอกสารบริการ/ประกาศที่อนุมัติ และ `knowledge/source/qa/*.md` — Q&A ที่อนุมัติ
  (catalog ปัจจุบัน 45 ไฟล์; README ไม่นับเป็นความรู้)
- `knowledge/aliases/*.md` — คำพ้องที่ผู้ดูแลกำหนด แสดงใน catalog เพื่อช่วยโมเดลเลือกเอกสาร
- `docs/research/electricity-tariff-sep-2569.md` — บันทึกค้นคว้าอัตราค่าไฟ (เก็บไว้เป็นข้อมูลอ้างอิง ไม่อยู่ใน catalog runtime)

รายละเอียดนโยบายอยู่ใน [knowledge/README.md](knowledge/README.md) เพิ่ม/แก้เอกสารแล้วต้อง restart server

## ทดสอบ

```bash
.venv/bin/python -m pytest -q
node --check web/app.js web/gemini-live-client.js web/phone.js web/media-handler.js web/pcm-processor.js
```

เทสต์ทั้งหมดไม่เรียก Gemini จริง

## สถานะการตรวจรับ (ตามจริง)

- ✅ เทสต์อัตโนมัติ: health, route surface, wire protocol (ด้วย event จำลอง), เครื่องมือ Knowledge, catalog, สถาปัตยกรรม
- ⏳ **ยังไม่ได้ทำ**: ทดสอบเสียงจริงกับ Gemini Live, ไมโครโฟนจริง, คุณภาพเสียงภาษาไทย, การพูดแทรก (barge-in)
- ⏳ **ยังไม่ได้วัด**: latency/ประสิทธิภาพใด ๆ — ไม่มีตัวเลขที่ยืนยันแล้ว

### Checklist ทดสอบเสียงด้วยมือ (pending)

1. ตั้ง `GEMINI_API_KEY` แล้วรัน server; `/health` ต้องได้ `status: ok`
2. เปิด `/` กดไมโครโฟน อนุญาตสิทธิ์ → สถานะเปลี่ยนเป็นกำลังฟัง
3. ถามคำถามที่มีในเอกสาร (เช่น ขอคืนเงินประกันการใช้ไฟฟ้า) → ได้ยินคำตอบภาษาไทยที่ตรงกับเอกสาร และเห็น transcript
4. ถามต่อเนื่องโดยไม่ระบุหัวข้อซ้ำ → โมเดลใช้บริบทเดิม
5. ถามเรื่องที่ไม่มีในเอกสาร → โมเดลบอกข้อจำกัด ไม่แต่งข้อมูล
6. พูดแทรกระหว่างโมเดลตอบ → เสียงหยุดและรับคำถามใหม่
7. ทำซ้ำข้อ 2–3 ที่ `/phone.html`
8. บันทึก latency ที่สังเกตได้ (ยังไม่มีเกณฑ์ที่วัดแล้ว)

## ข้อจำกัดกับ provider จริง

- ต้องใช้ `GEMINI_API_KEY` และเครือข่ายไปยัง Gemini Live; ไม่มีโหมด offline สำหรับเสียง
- ชื่อโมเดล/เสียงขึ้นกับบัญชีและรุ่น API (`v1alpha`) ที่ใช้; ถ้าเชื่อมต่อไม่ได้ browser จะได้ event `error`
- session อยู่ในหน่วยความจำ (InMemorySessionService) — เชื่อมต่อใหม่ = บทสนทนาใหม่
- เอกสารที่เลือกรวมกันต้องไม่เกิน 5 ไฟล์ / 120,000 ตัวอักษรต่อการเรียกหนึ่งครั้ง
- ระบบนี้เป็นเดโม ไม่เชื่อมต่อระบบจริงของ กฟภ. และไม่เข้าถึงข้อมูลลูกค้า
