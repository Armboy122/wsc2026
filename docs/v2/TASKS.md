# V2 — ลำดับงานสำหรับลงมือ (แผนเต็ม)

> ⚠️ **สำหรับเดโมกรรมการภายใน 3 วัน ให้ใช้ `docs/v2/TASKS-3DAYS.md` แทน**
> เอกสารนี้คือแผนเต็ม 43 งาน ≈ 8.5 วัน ใช้เป็นแหล่งอ้างอิงของงานที่ถูกเลื่อนออกไป


> อ่าน `ARCHITECTURE-V2.md` และ `CONTRACTS-V2.md` ก่อนเริ่มทุกงาน
> **ทุกการตัดสินใจปิดครบแล้ว** — งานในเอกสารนี้คือการลงมือ ไม่ใช่การออกแบบ
> ถ้าเจอเรื่องที่ต้องตัดสินใจใหม่ระหว่างทาง = เปิด ticket ใหม่ ห้ามเดาเอง

## กติกาที่ใช้ตลอดทุกเฟส

```bash
.venv/bin/python -m pytest -q                    # ต้องผ่านทุกครั้ง
./scripts/evaluate http://127.0.0.1:8000         # ต้องผ่านก่อนขึ้นเฟสถัดไป
```

1. **เดโมต้องรันได้ตลอด** — ไม่มีจังหวะไหนที่ระบบใช้ไม่ได้
2. **หนึ่ง PR ต่อหนึ่งงาน** ไม่รวบ
3. **ไม่ refactor นอกขอบเขตของงานนั้น**
4. เทสเพิ่มเฉพาะ 3 กลุ่ม: schema validation · policy enforcement · channel mapping
5. งานที่มีเครื่องหมาย 🔒 คือ **security boundary** ต้องมีเทสเสมอ

---

## เฟส 0 — พื้นฐาน (ไม่กระทบพฤติกรรมที่มีอยู่)

งานเฟสนี้ทั้งหมด **เพิ่มของใหม่โดยไม่แตะทางเดินเดิม** ⇒ เดโมทำงานเหมือนเดิม 100%

### T0.1 เพิ่ม dependency `jsonschema[format]`
- `pyproject.toml` + `uv.lock`
- ยืนยันว่า `.venv/bin/python -c "import jsonschema"` ผ่าน
- **เกณฑ์เสร็จ**: pytest เดิมผ่านครบ

### T0.2 🔒 ชั้น validate JSON Schema subset
- โมดูลใหม่: ตรวจ allowlist ตาม `CONTRACTS-V2.md` §2.1 / reject list §2.2
- เรียก `jsonschema.Draft202012Validator.check_schema()` ก่อนเสมอ
- ข้อความ error เป็นภาษาไทย บอกว่า **keyword ไหน** ผิดที่ **path ไหน**
- **เทสบังคับ**: รับของที่ควรรับ · reject ทุก keyword ใน §2.2 · จับ typo `{"type":"objct"}` · schema ลึก 6 ชั้น = reject

### T0.3 ชั้นเข้าถึง SQLite
- `sqlite3` stdlib + `asyncio.to_thread` · WAL · connection เดียว · lock เดียว
- `DB_PATH` จาก env ค่าเริ่มต้น `data/pea.db`
- migration runner: `001_init.sql` + ตาราง `schema_version` รันตามลำดับตอน startup
- **เกณฑ์เสร็จ**: startup สร้างไฟล์ DB ได้ · รันซ้ำไม่ migrate ซ้ำ

### T0.4 ตารางทั้ง 10 ตาราง
- ตาม `CONTRACTS-V2.md` §10.1 · `UNIQUE(trace_id, sequence)` ต้องมี
- ยังไม่มีใครเขียนอ่านจริงในเฟสนี้

### T0.5 🔒 นโยบายเครือข่ายขาออก
- โหมดจาก `APP_ENV` (`development` = ไม่จำกัด / `production` = allowlist + HTTPS + blocklist)
- ตรวจด้วย `ipaddress` stdlib **ห้ามเขียน parser IP เอง**
- `follow_redirects=False` · timeout 5s (แข็ง 30) · response 1 MB (แข็ง 10 MB) · **retry 0**
- **เทสบังคับ**: บล็อก `169.254.169.254` · บล็อก private range · ปฏิเสธ `http://` บน production · อนุญาต localhost บน development · 3xx = error

---

## เฟส 1 — Policy layer (ถอด hardcode ออกจาก agent)

### T1.1 policy 4 แบบ + `limits` + `clientContext`
- นิยาม `grounded_answer` / `write_confirm` / `guided_flow` / `plain_read`
- `limits.maxCallsPerTurn` · `limits.dedupeIdenticalInput`
- `clientContext` เป็น enum ปิด (`lat`, `lon`)

### T1.2 🔒 การตรวจสอบข้าม policy
- ตอน save/startup: 6 เงื่อนไขใน `CONTRACTS-V2.md` §3.5
- ตอน runtime: 4 เงื่อนไข ปฏิเสธผล + บันทึก `POLICY_REJECTED`
- **เทสบังคับ**: `submitAction` + `plain_read` = reject · `mode:submit` ที่ไม่ internal = reject · `grounded_answer` ไม่มี citation = ปฏิเสธผล · `plain_read` สร้าง pending = ปฏิเสธ

### T1.3 ย้าย 12 จุด hardcode ออกจาก `main_agent.py`
ตามตารางใน `ARCHITECTURE-V2.md` §4.4 — ทำทีละกลุ่ม:
- 194, 202 → `limits`
- 543, 624, 663, 676, 790, 798, 803, 811 → `grounded_answer`
- 487–488 → `clientContext`

**เกณฑ์เสร็จ**: `grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py` = **0**

### T1.4 default = `plain_read` + `exposure: internal`
- operation ที่ไม่ประกาศ policy ต้องมองเห็นได้แต่ LLM เรียกไม่ได้
- **เทสบังคับ**: operation ที่ไม่มี policy ไม่โผล่ในแคตตาล็อกที่ส่งให้ LLM

---

## เฟส 2 — Tool registry (schema เป็นข้อมูล)

### T2.1 `plugin.yaml` ใช้ `inputSchema` แทนชื่อคลาส
- ลบ `_check_contracts` ที่เทียบ `INPUT_MODELS[action].__name__`
- แก้ manifest ของ oms/voc ให้ฝัง JSON Schema
- **เทสบังคับ**: manifest ที่ schema ผิด = startup ล้ม (fail closed คงเดิม)

### T2.2 registry รูปเดียวสองชั้น
- shape ตาม `ARCHITECTURE-V2.md` §3.4
- `source: "db" | "code"` ห้ามใช้ตัดสินใจตอน dispatch
- รับทั้งสองแบบพร้อมกัน (ช่วง migration)

### T2.3 🔒 executor กลางสำหรับ declarative tool
- ยิง httpx ผ่านนโยบาย T0.5 **ทุกครั้ง ไม่มีทางลัด**
- ฉีด secret จาก env ตอน execute เท่านั้น — ห้ามแตะ schema/description/trace

### T2.4 `ToolName`/`ToolAction` → string
- `TOOL_ACTIONS` / `PREPARE_TO_SUBMIT` กลายเป็น data ต่อ tool
- คง enum เดิมเป็น **alias ชั่วคราว** (ลบใน T5.5)
- `ToolCall.action_belongs_to_tool` → ตรวจกับ registry ตอน dispatch

---

## เฟส 3 — Trace และ pending action ลง SQLite

### T3.1 🔒 `TraceStore` → SQLite
- ฟิลด์ใหม่: `tool_slug` · `action` · `config_version` · `policy` · `channel`
- kind ใหม่: `POLICY_REJECTED` · `RESPONSE_DEGRADED` · `TOOL_DISABLED`
- **`redact()` ทำงานตอนเขียน**
- เขียนอย่างเดียว ห้าม UPDATE/DELETE รายแถว · อ่านเรียงตาม `sequence`
- **เทสบังคับ**: `UNIQUE(trace_id, sequence)` บังคับจริง · ลำดับถูกต้องเมื่อเขียนถี่ · redact ทำงานก่อนแตะดิสก์

### T3.2 🔒 `PendingActionStore` → SQLite
- `toolSlug` เป็น string · terminal rejection ยัง terminal
- **เทสบังคับ**: pending action รอดข้ามการรีสตาร์ต · idempotency ยังกันส่งซ้ำ · reject แล้ว confirm ไม่ได้

### T3.3 HTTP call logging
- เก็บ method/host/path/status/เวลา/ขนาด — **ไม่เก็บ query string/header/body**
- **เทสบังคับ**: query string ที่มี `?api_key=xxx` ต้องไม่ปรากฏใน trace

### T3.4 retention job
- 90 วันทั่วไป · trace ที่มี `action_submitted`/`action_rejected` = ถาวร

---

## เฟส 4 — Channel adapter

### T4.1 เติม `simulation` + `actions[]` ใน `ChatResponse`
- เป็นการ **เติมฟิลด์** ⇒ client เก่าไม่พัง

### T4.2 ยกของกลางออกจาก `line/service.py`
- `_split_text` · `_truncate_button_label` · logic ปุ่มยืนยัน · จัดรูป citation · แนบข้อความ simulation
- helper กลางแปลง `pendingAction` และ `choicePrompt` → `Action[]`
- **เกณฑ์เสร็จ**: LINE ทำงานเหมือนเดิมทุกประการ (`evaluate` ผ่าน)

### T4.3 capability declaration
- ค่าตาม `CONTRACTS-V2.md` §5.4
- **เทสบังคับ**: LINE ตัดที่ 1900 · Telegram ตัดที่ 4096 · web ไม่ตัด · API ไม่มีปุ่มแล้ว degrade เป็นข้อความ + id

### T4.4 🔒 Telegram adapter
- webhook + `secret_token` (`compare_digest`) ⚠️ ไม่ผูก body — ต้อง HTTPS เสมอ
- inline keyboard · `callback_data` ≤64 bytes · **เรียก `answerCallbackQuery` ทุกครั้ง**
- `editMessageReplyMarkup` ปิดปุ่มหลังยืนยัน
- handle `migrate_to_chat_id`
- ยิง httpx ตรง **ไม่เพิ่ม library**
- **เทสบังคับ**: secret ผิด = ปฏิเสธ · `callback_data` ยาวเกิน 64 bytes = ไม่ส่ง · กดยืนยันซ้ำไม่สร้างรายการซ้ำ

---

## เฟส 5 — ย้าย tool เดิม (ทีละตัว ตามลำดับ)

> **ห้ามข้ามลำดับ** — เรียงจาก "พังแล้วไม่มีใครเดือดร้อน" ไป "พังแล้วเดโมล่ม"
> ทุกขั้นต้องผ่าน `pytest` + `evaluate` ก่อนไปขั้นถัดไป

### T5.1 `sabuy_tool` → declarative (ตัวพิสูจน์)
- สร้างจาก DB ล้วน · dormant อยู่แล้ว พังก็ไม่กระทบ
- **นี่คือจุดที่จะรู้ว่า contract ใหม่ใช้ได้จริงหรือไม่** — ถ้าติดตรงไหนให้หยุดแล้วทบทวน อย่าดันต่อ

### T5.2 `oms_tool`
- พิสูจน์ `clientContext` + `write_confirm`
- **เกณฑ์เสร็จ**: แจ้งไฟดับแบบไม่ทราบ CA ยังเติมพิกัดได้โดย agent ไม่รู้ว่าเป็น OMS

### T5.3 `voc_tool`
- พิสูจน์ `guided_flow` · `ChoicePrompt` ต้องข้าม channel ได้

### T5.4 `knowledge_tool`
- พิสูจน์ `grounded_answer` · citation validation ต้องทำงานผ่าน policy ไม่ใช่ชื่อ tool
- **ยากสุด กระทบเดโมมากสุด — ทำเป็นตัวสุดท้ายเสมอ**

### T5.5 ลบ alias
- ลบ `ToolName` / `ToolAction` enum ทิ้ง
- `BoundDemoBehavior` → seed data หรือปิดชั่วคราว
- `VOICE_TOOLS` → channel profile ใน DB
- **เกณฑ์เสร็จ**: `grep -rn "ToolName\." app/ --include=*.py | grep -v tests` = ว่าง

---

## เฟส 6 — เสียง

### T6.1 🔒 read-back + ยืนยันด้วยเสียง
- อ่านทวนทุก field ที่จะบันทึกก่อนถามยืนยัน
- จับคำแบบกำหนดตายตัว · **ตรวจชุดปฏิเสธก่อนชุดยืนยัน**
- ไม่ตรง = ถามซ้ำ มีเพดาน
- **เทสบังคับ**: "ไม่ใช่ครับ" ต้องไม่ถูกนับเป็นยืนยัน · LLM ไม่มีทางตัดสินคำยืนยัน

### T6.2 คำปฏิเสธ = เข้าโหมดแก้ไข
- ถามว่าแก้ช่องไหน · รายการช่องมาจาก `inputSchema`
- **สร้าง pending action ใหม่** ห้ามปลุกของเดิม
- มีเพดานรอบการแก้ไข
- **เทสบังคับ**: action เดิมยัง terminal หลังเข้าโหมดแก้ไข

### T6.3 `voiceConfirm` + citation degrade
- default `true` · Sabuy payment = `false`
- เสียง**ไม่พูดอ้างอิงเลย** แต่ trace บันทึก citation ครบ + `RESPONSE_DEGRADED`

### T6.4 หลักฐานการยืนยัน
- read-back text + ถอดเสียงคำยืนยัน ลง `ACTION_CONFIRMED` · **ไม่เก็บไฟล์เสียง**

### T6.5 handoff ส่งลิงก์ (ทำทีหลังได้)
- เป็น tool ที่ผ่าน `write_confirm` · ลิงก์ครั้งเดียว/อายุสั้น/ไม่โชว์ PII · **ไม่ใช้ OTP**
- ⚠️ ต้องมี SMS gateway ก่อน — ถ้ายังไม่พร้อม **ข้ามได้** เพราะไม่ใช่ทางหลักแล้ว

---

## เฟส 7 — Prompt และหน้า admin

### T7.1 `SYSTEM_PROMPT` → DB แล้วลบไฟล์ `.md`
- seed จากค่าปัจจุบันใน `app/llm/prompting.py`
- **ลบ `app/prompts/*.md` ทั้ง 4 ไฟล์** (ไม่ถูกโหลดตอน runtime อยู่แล้ว)
- **เกณฑ์เสร็จ**: แก้ prompt จาก DB แล้วมีผลในเทิร์นถัดไป

### T7.2 🔒 auth หน้า admin
- `ADMIN_PASSWORD` + session cookie · แยกจาก API key
- ย้าย `/traces/{id}` และ `/reset` มาอยู่หลัง auth
- **แก้ `web/` ที่เรียก `/traces` ให้ใช้เส้นทางใหม่** (ไม่งั้น trace panel พัง)

### T7.3 หน้ารายการ tool
- แสดงสถานะ · ชนิด · แก้ล่าสุด · **สถานะ disabled พร้อมเหตุผล**
- Python plugin อยู่รายการเดียวกัน ช่องที่แก้ไม่ได้ถูก disable พร้อมข้อความบอกเหตุผล

### T7.4 ฟอร์มแก้ tool + form builder
- กดเพิ่ม field ทีละตัว → gen JSON Schema · JSON เป็น read-only preview
- แสดงจำนวนตัวอักษร/ประมาณ token ของ description
- draft / publish → สร้าง `tool_version` ใหม่ + ย้อนเวอร์ชันได้

### T7.5 🔒 ปุ่ม "ลองยิงดู"
- ยิงจริง · ซ่อน secret · แสดง request/response/เวลา
- **ต้องผ่านนโยบาย T0.5 ทุกประการ ห้ามเป็นทางลัด**
- **เทสบังคับ**: ปุ่มนี้ยิงไป `127.0.0.1` บน production ไม่ได้

### T7.6 หน้าแก้ prompt
- แก้ `SYSTEM_PROMPT` · มี preview · มีประวัติเวอร์ชัน

---

## เฟส 8 — Public API

### T8.1 🔒 API key
- ตาราง `api_key` · เก็บ hash · แสดงค่าจริงครั้งเดียว · เพิกถอนได้ · `tenant_id = 'default'`
- **เทสบังคับ**: key ที่ถูกเพิกถอนใช้ไม่ได้ · ไม่มี key = 401

### T8.2 🔒 conversation ownership
- server ออก id เสมอ · ส่ง id ของ key อื่น = **404**
- **เทสบังคับ**: key A เข้าถึง conversation ของ key B ไม่ได้ และได้ 404 ไม่ใช่ 403

### T8.3 error contract
- `{error:{code,message,traceId}}` · code เป็นชุดปิด
- **เทสบังคับ**: error ไม่มี stack trace / ชื่อ tool / URL ปลายทาง

### T8.4 rate limit
- ตัวนับใน memory ต่อ key ต่อนาที · เกิน = 429

---

## เฟส 9 — ปิดงาน

### T9.1 อัปเดตเอกสาร
- `ARCHITECTURE.md` / `CONTRACTS.md` → ชี้ไปที่ V2 หรือรวมเข้าด้วยกัน
- `README.md` · `.env.example` (`DB_PATH`, `ADMIN_PASSWORD`, `TELEGRAM_*`)

### T9.2 ตรวจครั้งสุดท้าย
```bash
grep -rn "ToolName\.\|ToolAction\." app/ --include=*.py | grep -v tests   # ต้องว่าง
ls app/prompts/                                                            # ต้องไม่มีแล้ว
.venv/bin/python -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

### T9.3 ทดสอบ end-to-end ทุก channel
Web · LINE · Telegram · Voice · Public API — ทั้งเส้นอ่านความรู้และเส้น write ที่ต้องยืนยัน

---

## สรุปงานที่ต้องมีเทสแน่นอน (🔒)

| งาน | เทสอะไร |
|---|---|
| T0.2 | schema subset validation |
| T0.5 | SSRF blocking |
| T1.2 | policy enforcement |
| T2.3 | executor ผ่านนโยบายเครือข่าย |
| T3.1 | trace ordering + redaction |
| T3.2 | pending action state machine + idempotency |
| T4.4 | Telegram webhook auth + callback |
| T6.1 | การจับคำยืนยัน/ปฏิเสธ |
| T6.2 | terminal rejection ไม่ถูกปลุก |
| T7.2 | admin auth |
| T7.5 | ปุ่มทดสอบไม่ข้าม SSRF |
| T8.1 | API key |
| T8.2 | conversation ownership |
| T8.3 | error ไม่รั่วข้อมูลภายใน |

**ไม่ต้องเขียนเทสสำหรับ**: หน้า UI · การจัดถ้อยคำ · wrapper บาง ๆ · โค้ดสำรวจที่จะถูกแทน
