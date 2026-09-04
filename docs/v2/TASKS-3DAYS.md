# V2 — แผน 3 วัน สำหรับเดโมกรรมการ

> **นี่คือแผนที่ตัดแล้ว ไม่ใช่แผนเต็ม** — แผนเต็มอยู่ที่ `docs/v2/TASKS.md` (43 งาน ≈ 8.5 วัน)
> เอกสารนี้ตัดเหลือ **สิ่งที่กรรมการเห็นและตัดสินได้** ภายใน 3 วัน
> สถาปัตยกรรมและสัญญาไม่เปลี่ยน — อ่าน `ARCHITECTURE-V2.md` และ `CONTRACTS-V2.md` เหมือนเดิม

---

## หลักการตัด

กรรมการตัดสินจาก **สิ่งที่เห็นบนจอ** ไม่ใช่จำนวนโมดูลที่ refactor
งานที่ไม่มีใครเห็นในห้องเดโม = เลื่อนไปเฟสหน้า แม้จะถูกต้องทางวิศวกรรม

**ของที่มีอยู่แล้วและทำงานได้ ห้ามแตะ**: LINE bridge · voice · knowledge grounding · `prepare→confirm→submit` · เทส 307 ตัวที่รันผ่านใน 1.7 วินาที

---

## สิ่งที่กรรมการจะได้เห็น (เป้าหมายของ 3 วันนี้)

| # | สาธิต | ทำไมกรรมการสนใจ |
|---|---|---|
| 1 | **เพิ่ม tool ใหม่จากหน้าเว็บ แล้ว AI ใช้ได้ทันทีโดยไม่ deploy** | คือหัวใจของ V2 และเป็นภาพที่จำได้ |
| 2 | **แก้ prompt จากหน้าเว็บ แล้วเห็นผลในเทิร์นถัดไป** | พิสูจน์ว่าไม่ต้องแตะโค้ดเพื่อปรับพฤติกรรม |
| 3 | **ใส่ URL อันตราย (`169.254.169.254`) แล้วระบบปฏิเสธพร้อมบอกเหตุผล** | พิสูจน์ว่าเปิดกว้างแต่ไม่ประมาท |
| 4 | **`grep ToolName app/agent/main_agent.py` ได้ 0 บรรทัด** | หลักฐานที่เถียงไม่ได้ว่า agent แยกจาก tool จริง |
| 5 | เส้นทางเดิมทั้งหมดยังทำงาน (knowledge · OMS · LINE · voice) | ไม่ได้พังของเก่าเพื่อสร้างของใหม่ |

---

## สิ่งที่ตัดออก (และเหตุผลที่ตัดได้)

| ตัดออก | เหตุผล |
|---|---|
| **Telegram adapter** | LINE ทำงานได้แล้ว — channel ที่สองไม่พิสูจน์อะไรที่ LINE ยังไม่พิสูจน์ กรรมการเห็นความต่างไม่ออก |
| **trace/pending → SQLite** | ยังอยู่ RAM ต่อ · เดโมไม่รีสตาร์ตกลางทาง · trace panel ที่มีอยู่ยังทำงานเหมือนเดิม |
| **Public API + API key** | ไม่มีระบบภายนอกมายิงในวันเดโม |
| **เสียง read-back + โหมดแก้ไข** | voice ทำงานได้อยู่แล้ว การเปลี่ยน flow ตอนนี้เสี่ยงพังของที่โชว์ได้ |
| **ย้าย `voc` และ `knowledge`** | ยังใช้ทางเดิมผ่าน alias — ระบบทำงานครบ กรรมการไม่รู้ว่าตัวไหนย้ายแล้ว |
| **draft/publish + version history** | save แล้วมีผลเลย · rollback ไม่ใช่สิ่งที่เดโม 10 นาทีต้องการ |
| **retention job** | ไม่มีใครรัน 90 วันในห้องเดโม |

⚠️ **สิ่งที่ห้ามตัด**: policy enforcement · SSRF check · schema validation · admin auth
สี่อันนี้ถ้าตัด กรรมการถามคำถามเดียวก็จบ (*"แล้วถ้ามีคนใส่ URL มั่ว ๆ ล่ะ"*)

---

## วันที่ 1 — ฐานและ policy layer

### D1.1 เพิ่ม `jsonschema[format]`
`pyproject.toml` + `uv.lock` · ยืนยัน `import jsonschema` ผ่าน
**เสร็จเมื่อ**: `pytest` 307 ตัวยังผ่านครบ

### D1.2 🔒 validator ของ JSON Schema subset
- ตรวจ allowlist ตาม `CONTRACTS-V2.md` §2.1 · reject list §2.2
- `check_schema()` ก่อนเสมอ · error ภาษาไทยบอก keyword และ path
- **เทส**: รับของที่ควรรับ · reject `oneOf`/`pattern`/`uniqueItems` · จับ typo `{"type":"objct"}` · ลึก 6 ชั้น = reject

### D1.3 🔒 นโยบายเครือข่ายขาออก
- โหมดจาก `APP_ENV`: `development` ไม่จำกัด / `production` allowlist + HTTPS + blocklist
- `ipaddress` stdlib **ห้ามเขียน parser เอง**
- `follow_redirects=False` · timeout 5s · response 1 MB · **retry 0**
- **เทส**: บล็อก `169.254.169.254` · บล็อก private range · `http://` บน production = reject · localhost บน development = ผ่าน

### D1.4 policy 4 แบบ + `limits` + `clientContext`
นิยาม `grounded_answer` / `write_confirm` / `guided_flow` / `plain_read` · `clientContext` เป็น enum ปิด (`lat`, `lon`)

### D1.5 🔒 ถอด 12 จุด hardcode ออกจาก `main_agent.py`
ตาม `ARCHITECTURE-V2.md` §4.4 — ทำเป็น 3 กลุ่ม:
- 194, 202 → `limits`
- 543, 624, 663, 676, 790, 798, 803, 811 → `grounded_answer`
- 487–488 → `clientContext`

**เสร็จเมื่อ**:
```bash
grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py   # = 0
.venv/bin/python -m pytest -q                                 # ผ่านครบ
./scripts/evaluate http://127.0.0.1:8000                      # ผ่าน
```

### D1.6 🔒 การตรวจสอบข้าม policy
- save/startup: `submitAction` + `plain_read` = reject · `mode:submit` ที่ไม่ internal = reject
- runtime: `grounded_answer` ไม่มี citation = ปฏิเสธผล · `plain_read` สร้าง pending = ปฏิเสธ
- default = `plain_read` + `exposure: internal`

**🎯 จบวันที่ 1 ต้องพูดได้ว่า**: *"agent ไม่รู้จักชื่อ tool แล้ว และพิสูจน์ด้วย grep"*

---

## วันที่ 2 — tool เป็นข้อมูลจริง

### D2.1 SQLite แบบบางที่สุด (**5 ตาราง ไม่ใช่ 10**)
```sql
tool             slug, display_name, description, enabled, source, created_at
tool_operation   tool_id, action, policy, input_schema, output_schema,
                 exposure, mode, submit_action, limits, client_context
tool_auth        tool_id, type, secret_ref
prompt           key, content, updated_at
domain_allowlist domain, enabled
```
- `sqlite3` stdlib + `asyncio.to_thread` · WAL · connection เดียว
- migration = `001_init.sql` + ตาราง `schema_version`
- **ตัด**: `tool_version` · `channel_profile` · `api_key` · `pending_action` · `trace_event` (ทั้งหมดอยู่ใน RAM ต่อ)

⚠️ **ผลของการตัด `tool_version`**: trace อ้าง `config_version` ไม่ได้ — ยอมรับได้เพราะ trace ยังอยู่ RAM และเดโมไม่ได้สอบสวนย้อนหลัง
**แต่ยังทำ soft delete** (`enabled=false`) เพื่อไม่ให้ต้อง migrate ตอนเติม `tool_version` ทีหลัง

### D2.2 `plugin.yaml` ใช้ `inputSchema` แทนชื่อคลาส
- ลบ `_check_contracts` ที่เทียบ `INPUT_MODELS[action].__name__`
- แก้ manifest ของ oms/voc ให้ฝัง JSON Schema
- **เทส**: manifest ที่ schema ผิด = startup ล้ม (fail closed คงเดิม)

### D2.3 registry รูปเดียวสองชั้น
shape ตาม `ARCHITECTURE-V2.md` §3.4 · `source` ห้ามใช้ตัดสินใจตอน dispatch · รับทั้งสองแบบพร้อมกัน

### D2.4 🔒 executor กลางของ declarative tool
- ยิง httpx ผ่านนโยบาย D1.3 **ทุกครั้ง ไม่มีทางลัด**
- ฉีด secret จาก env ตอน execute เท่านั้น
- **เทส**: executor ที่ยิงไป private IP บน production = ถูกบล็อก

### D2.5 `ToolName`/`ToolAction` → string + alias
- `TOOL_ACTIONS` / `PREPARE_TO_SUBMIT` เป็น data ต่อ tool
- **คง enum เป็น alias** (ไม่ลบใน 3 วันนี้ เพราะ voc/knowledge ยังใช้)

### D2.6 ย้าย `sabuy` เป็น declarative (**ตัวพิสูจน์**)
สร้างจาก DB ล้วน · dormant อยู่แล้ว พังก็ไม่กระทบ
**นี่คือจุดที่รู้ว่า contract ใช้ได้จริงไหม — ถ้าติดให้หยุดแล้วทบทวน อย่าดันต่อ**

### D2.7 ย้าย `oms`
พิสูจน์ `clientContext` + `write_confirm`
**เสร็จเมื่อ**: แจ้งไฟดับแบบไม่ทราบ CA ยังเติมพิกัดได้ โดย agent ไม่รู้ว่าเป็น OMS

**🎯 จบวันที่ 2 ต้องพูดได้ว่า**: *"เพิ่ม tool ใหม่ได้โดยไม่แตะโค้ด และมี tool จริงที่รันจาก DB แล้ว"*

---

## วันที่ 3 — หน้า admin (สิ่งที่กรรมการเห็น)

### D3.1 🔒 auth หน้า admin
`ADMIN_PASSWORD` จาก env + session cookie
**ห้ามข้าม** — หน้านี้สร้าง tool ที่ยิง HTTP ได้ = ยึดระบบได้ทั้งระบบ

### D3.2 `SYSTEM_PROMPT` → DB แล้วลบ `app/prompts/*.md`
- seed จากค่าปัจจุบันใน `app/llm/prompting.py`
- **ลบ 4 ไฟล์ `.md` ที่ไม่ถูกโหลดตอน runtime**
- **เสร็จเมื่อ**: แก้ prompt จาก DB แล้วมีผลในเทิร์นถัดไป

### D3.3 หน้ารายการ tool
- แสดงชื่อ · สถานะ · ชนิด (declarative/python) · policy ของแต่ละ operation
- Python plugin อยู่รายการเดียวกัน **ช่องที่แก้ไม่ได้ถูก disable พร้อมบอกเหตุผล**
- แสดง tool ที่ปิดตัวเองพร้อมเหตุผล (กันไม่ให้ "หายเงียบ")

### D3.4 ฟอร์มสร้าง/แก้ declarative tool
- **form builder** — กดเพิ่ม field ทีละตัว (ชื่อ/ชนิด/จำเป็น/คำอธิบาย) → gen JSON Schema
- JSON เป็น read-only preview
- แสดงจำนวนตัวอักษรของ description
- error ตอน save บอกชัดว่าผิดตรงไหน
- **save แล้วมีผลเลย** (ตัด draft/publish)

### D3.5 🔒 ปุ่ม "ลองยิงดู"
- ยิงจริง · ซ่อน secret · แสดง request/response/เวลา
- **ต้องผ่านนโยบาย D1.3 ทุกประการ ห้ามเป็นทางลัด**
- **เทส**: ปุ่มนี้ยิงไป `127.0.0.1` บน production ไม่ได้

> 💡 ปุ่มนี้คือช็อตที่ดีที่สุดในการเดโม — กรอก URL → กดลอง → เห็น response จริง → เปิดใช้ → ถาม AI → AI เรียก tool นั้น จบใน 60 วินาที

### D3.6 หน้าแก้ prompt
แก้ `SYSTEM_PROMPT` · มี preview · save แล้วมีผลเทิร์นถัดไป

### D3.7 ซ้อมเดโม + ตรวจครั้งสุดท้าย
```bash
grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py   # = 0
ls app/prompts/                                               # ต้องไม่มีแล้ว
.venv/bin/python -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```
เดินเส้นทางเดโมทั้งหมดจริง: ถามความรู้ · แจ้งไฟดับ (prepare→confirm) · LINE · voice · **สร้าง tool ใหม่จากหน้า admin**

**🎯 จบวันที่ 3**: เดโมได้ครบ 5 ข้อในตาราง "สิ่งที่กรรมการจะได้เห็น"

---

## เทสที่ต้องมี — 6 อัน (ไม่ใช่ 14)

| งาน | เทสอะไร | ถ้าไม่มีจะเกิดอะไร |
|---|---|---|
| D1.2 | schema subset validation | admin กรอกอะไรก็ได้ ระบบพังตอนเดโม |
| D1.3 | SSRF blocking | กรรมการถาม "ถ้าใส่ URL มั่วล่ะ" แล้วตอบไม่ได้ |
| D1.5/D1.6 | policy enforcement | LLM ส่ง write เองได้ = จุดขายหลักพัง |
| D2.4 | executor ผ่านนโยบายเครือข่าย | ทางลัดเดียวก็ทำลาย D1.3 ทั้งหมด |
| D3.1 | admin auth | ใครก็เข้ามาสร้าง tool ที่ยิง HTTP ได้ |
| D3.5 | ปุ่มทดสอบไม่ข้าม SSRF | ช่องโหว่ที่ซ่อนอยู่หลังปุ่มที่ดูปลอดภัย |

**ที่เหลือไม่ต้องเขียนเทส** — `AGENTS.md` บอกไว้ชัด: *"Test where failure is expensive"*
เทส 307 ตัวที่มีอยู่รันใน 1.7 วินาที ⇒ รันบ่อย ๆ ระหว่างทางแทนการเขียนเทสใหม่ทุกฟังก์ชัน

---

## ถ้าเวลาไม่พอ ตัดตามลำดับนี้

```
1. D3.6 หน้าแก้ prompt        (แก้ผ่าน DB ตรง ๆ ในเดโมได้)
2. D2.7 ย้าย oms              (sabuy อย่างเดียวก็พิสูจน์ contract แล้ว)
3. D3.3 หน้ารายการ tool       (มีแค่ฟอร์มสร้างก็เดโมได้)
```

**ห้ามตัด**: D1.2 · D1.3 · D1.5 · D2.4 · D3.1 · D3.5
ตัดอันไหนในหกอันนี้ = ตอบคำถามกรรมการไม่ได้

---

## สคริปต์เดโม 8 นาที (ร่างไว้ให้ซ้อม)

| นาที | ทำอะไร | ประโยคที่พูด |
|---|---|---|
| 0–1 | ถามความรู้ผ่านเว็บ ชี้ citation | "ทุกคำตอบมีหลักฐานที่ตรวจกับไฟล์จริง" |
| 1–2 | แจ้งไฟดับ → เห็นหน้ายืนยัน → กดยืนยัน | "แชตทำได้แค่เตรียม มนุษย์เป็นคนยืนยันเสมอ" |
| 2–4 | **เปิดหน้า admin สร้าง tool ใหม่ กด "ลองยิงดู" เห็น response** | "เพิ่มความสามารถใหม่โดยไม่ต้อง deploy" |
| 4–5 | กลับมาแชต ถามคำถามที่ต้องใช้ tool ใหม่ AI เรียกได้เลย | "ระบบรู้จัก tool ใหม่ทันทีในเทิร์นถัดไป" |
| 5–6 | ลองใส่ URL `169.254.169.254` → ระบบปฏิเสธพร้อมเหตุผล | "เปิดกว้างแต่ไม่ประมาท" |
| 6–7 | `grep ToolName app/agent/main_agent.py` → 0 | "agent ไม่รู้จักชื่อ tool แม้แต่ตัวเดียว" |
| 7–8 | รัน `pytest` 307 ตัวใน 2 วินาที | "ของเดิมไม่พังสักตัว" |

---

## ความเสี่ยงที่ต้องรู้ล่วงหน้า

| ความเสี่ยง | สัญญาณเตือน | ทำยังไง |
|---|---|---|
| **D1.5 ยากกว่าที่คิด** (`main_agent.py` 872 บรรทัด) | เย็นวันที่ 1 ยังเหลือ >4 จุด | ยอมเหลือจุด `clientContext` ไว้ ทำ 11/12 จุดพอ — ยังพูดได้ว่าเหลือจุดเดียว |
| **D2.6 sabuy ติดปัญหา contract** | เที่ยงวันที่ 2 ยังรันไม่ได้ | **หยุดแล้วทบทวน contract** อย่าดันต่อไป oms — นี่คือสัญญาณว่าสเปกมีจุดบอด |
| **หน้า admin กินเวลาเกิน** | บ่ายวันที่ 3 ฟอร์มยังไม่เสร็จ | ตัด D3.3/D3.6 เหลือแค่ฟอร์มสร้าง + ปุ่มลองยิง |
| **เดโมพังตอนซ้อม** | D3.7 ไม่ผ่าน | revert ไปคอมมิตล่าสุดที่ `evaluate` ผ่าน — **commit บ่อย ๆ ทุกงานย่อย** |

---

## สิ่งที่ต้องบอกกรรมการตามตรง

`PRD.md` §14 บังคับว่า *"ข้อจำกัดและ capability ที่ยังไม่เปิดใช้ถูกสื่อสารตรงตามจริง"*

- Telegram · public API · trace ลง DB — **ออกแบบครบแล้วแต่ยังไม่ implement** (ชี้ `docs/v2/TASKS.md`)
- `voc` และ `knowledge` ยังใช้ทางเดิม — ย้ายแล้ว 2 จาก 4 ตัว
- trace ยังอยู่ใน RAM — รีสตาร์ตแล้วหาย
- OMS ยังเป็น simulation ตามเดิม

**การมีแผนเต็มที่ตัดสินใจครบแล้วเป็นข้อได้เปรียบ ไม่ใช่ข้อแก้ตัว** — บอกว่า "เหลืออีก 5 เฟส แต่ละเฟสมีสเปกและเกณฑ์เสร็จแล้ว" ดูดีกว่า "ยังไม่ได้คิด"
