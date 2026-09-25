# CONTRACTS — PEA Knowledge Voice Agent

สัญญาสาธารณะของระบบมีเพียงสามส่วน: `GET /health`, `WS /ws/live` และเครื่องมือ ADK
`get_knowledge_documents` ที่ Gemini Live เรียกได้ นอกจากนี้คือไฟล์ static ของหน้าเว็บเสียงใน `web/`
(เสิร์ฟที่ `/`, เช่น `/index.html`, `/phone.html`)

Python primitives ที่ใช้ร่วมกันอยู่ใน `app/contracts.py` (`FrozenModel`, `ToolErrorCode`,
`HealthResponse`) — ถ้าแก้ไฟล์นี้หรือเอกสารนี้ ต้องแก้ให้สอดคล้องกันและระบุการเปลี่ยนแปลงให้ชัด

ไม่มี REST API สำหรับแชต, pending action, trace, reset, LINE webhook, OMS/VOC หรือการคำนวณค่าไฟ
และปิด `/docs`, `/redoc`, `/openapi.json` ไว้ทุก environment

## 1. `GET /health`

ตอบ `200` เสมอ (JSON, camelCase):

```json
{ "status": "ok", "knowledgeBackend": "ready", "liveVoice": "configured" }
```

| ฟิลด์ | ค่า | ความหมาย |
| --- | --- | --- |
| `status` | `ok` \| `degraded` | `ok` เมื่อ catalog มีเอกสารอย่างน้อยหนึ่งไฟล์ **และ** ตั้ง `GEMINI_API_KEY` แล้ว |
| `knowledgeBackend` | `ready` \| `unavailable` | catalog ความรู้โหลดได้และไม่ว่าง |
| `liveVoice` | `configured` \| `not_configured` | มี `GEMINI_API_KEY` หรือไม่ (ไม่ได้เรียก provider จริง) |

health ไม่เปิดเผยคีย์, path แบบ absolute หรือรายละเอียดข้อผิดพลาดของ provider

## 2. `WS /ws/live`

หนึ่ง connection = หนึ่ง ADK Live session (conversation ใหม่ทุกครั้งที่เชื่อมต่อ)

### Browser → Server

- **Binary frame เท่านั้น**: PCM16 little-endian mono 16 kHz, ความยาวเป็นเลขคู่, ไม่ว่าง,
  ไม่เกิน 32,000 bytes ต่อ frame; frame ผิดรูปแบบจะปิด session พร้อม event `error`
- Text/JSON frame จาก browser ถูกเพิกเฉย ไม่สามารถเรียกเครื่องมือหรือสั่งงานใด ๆ ได้

### Server → Browser

- **Binary frame**: เสียงตอบกลับ PCM16 24 kHz จาก Gemini Live (ไม่ส่งระหว่าง interrupted)
- **JSON event**:

| `type` | ฟิลด์อื่น | เมื่อใด |
| --- | --- | --- |
| `session.ready` | — | สร้าง session แล้ว พร้อมรับเสียง |
| `transcript.user` / `transcript.assistant` | `role` (`user`/`assistant`), `text`, `final` (bool), `replace` (bool) | ข้อความถอดเสียง; เมื่อ `final=true` ข้อความคือข้อความสะสมทั้งหมด (`replace=true`) ไม่ใช่ delta |
| `audio.interrupted` | — | ผู้ใช้พูดแทรก ให้หยุดเล่นเสียงที่ค้างอยู่ |
| `state` | `state: "thinking"` | โมเดลกำลังเรียกเครื่องมือ Knowledge |
| `turn.complete` | — | จบหนึ่งรอบคำตอบ |
| `error` | `message` (ข้อความภาษาไทยที่ปลอดภัย) | ไม่ได้ตั้งค่าเสียง, dependency เสียงไม่พร้อม หรือ session ล้มเหลว; server จะปิด connection ต่อ (`1011` สำหรับกรณีไม่ได้ตั้งค่า/ไม่พร้อม) |

ไม่มี raw ADK event, thought, tool payload หรือข้อผิดพลาดของ provider ส่งถึง browser

## 3. เครื่องมือ ADK `get_knowledge_documents`

เป็นเครื่องมือเดียวที่ agent (`app/agent/adk_agent.py`) เปิดให้ Gemini Live เรียก
Gemini Live เลือก `sourceId` จาก catalog ที่ฝังอยู่ใน instruction (ฟิลด์ `sourceId`, `title`,
`headings` ≤ 12, `aliases` ถ้ามี — ไม่มีเนื้อหาเอกสาร) แล้วเรียกเครื่องมือเพื่อรับเอกสารฉบับเต็ม

เครื่องมือไม่ค้นหาจากคำถาม ไม่ตอบคำถาม และไม่เรียก model ใด ๆ (deterministic)

### Input

```json
{ "source_ids": ["PEA_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.md"] }
```

- `source_ids`: array ของ string (1–5 รายการ, แต่ละรายการ ≤ 300 ตัวอักษร) ต้องเป็น `sourceId`
  ที่อยู่ใน catalog เท่านั้น (relative path, ห้าม absolute/`..`/ไฟล์ซ่อน); ห้ามมี key อื่น

### Success

```json
{
  "status": "success",
  "documents": [
    { "sourceId": "…", "title": "…", "uri": "knowledge://source/<sourceId>", "content": "<Markdown ทั้งไฟล์>" }
  ],
  "sources": [ { "sourceId": "…", "title": "…", "uri": "knowledge://source/…" } ]
}
```

เนื้อหาส่งทั้งไฟล์ ไม่ตัดทอน ไม่แบ่ง chunk

### Error

```json
{ "status": "error", "error": { "code": "invalid_input", "message": "<ข้อความภาษาไทยที่ปลอดภัย>" } }
```

| `code` | เมื่อใด |
| --- | --- |
| `invalid_input` | ว่าง, รูปแบบผิด, ไม่อยู่ใน catalog, เกิน 5 เอกสาร หรือรวมกันเกิน 120,000 ตัวอักษร (ไม่ตัดทอนเอง) |
| `unavailable` | อ่านไฟล์ที่เลือกไม่ได้ |
| `internal` | ข้อผิดพลาดที่ไม่คาดคิดในเครื่องมือ |

## 4. การตั้งค่า (environment)

| ตัวแปร | ค่าเริ่มต้น | หมายเหตุ |
| --- | --- | --- |
| `APP_ENV` | `development` | ป้ายสภาพแวดล้อม |
| `LOG_LEVEL` | `info` | |
| `GEMINI_API_KEY` | — | จำเป็นสำหรับโหมดเสียง ห้าม commit หรือ log |
| `GEMINI_LIVE_MODEL` | `gemini-3.8-live` | |
| `GEMINI_LIVE_VOICE` | `Puck` | |
| `KNOWLEDGE_SOURCE_ROOT` | `<repo>/knowledge/source` | root ของเอกสารความรู้ที่อนุมัติ |
