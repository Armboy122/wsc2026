# V2 — Prompt สำหรับลงมือทีละขั้น (ระบบ plugin เต็มรูปแบบ)

> **วิธีใช้**: ก๊อปปี้เนื้อหาในบล็อก `PROMPT` ของแต่ละขั้นไปวางเป็นคำสั่งใหม่ทีละขั้น
> **ห้ามข้ามลำดับ** — ขั้นหลังพึ่งพาโครงที่ขั้นก่อนวางไว้
> ทุกขั้นจบด้วย 1 commit และ full pytest ต้องเขียว
>
> **ลำดับที่ตกลงกันไว้**: เดโมก่อน (P1–P4) → ปิด D3.7 (P5) → ของยาก (P6–P11)

---

## สถานะจริงของ V2 ณ วันที่เขียนเอกสารนี้

ตรวจจาก DB และไฟล์จริง ไม่ใช่จากเอกสาร:

| เฟส | สถานะ | หลักฐาน |
|---|---|---|
| 0–2 พื้นฐาน / policy / registry | ✅ เสร็จ | `schema_version`, `domain_allowlist`, executor, `grep ToolName\.` = 0 |
| 3 trace/pending → SQLite | ❌ ยังไม่ทำ | ตารางมีแค่ 7 ตัว ไม่มี `trace` / `pending_action` — ยังอยู่ใน RAM |
| 4 Telegram adapter | ❌ ยังไม่ทำ | ไม่มี `app/api/telegram.py` |
| 5 ย้าย tool | ⚠️ 2/4 | `sabuy` ลบแล้ว · `oms_tool` เป็น declarative แล้ว · **`voc` ยังเป็น plugin** · **`knowledge` ยังเป็น code tool** |
| 6 voice read-back | ❌ ยังไม่ทำ | — |
| 7 prompt + admin | ✅ เสร็จ | D3.1–D3.6 |
| 8 Public API | ❌ ยังไม่ทำ | ไม่มีตาราง `api_key` |
| 9 ปิดงาน | ⚠️ เหลือ D3.7 | — |

ตารางใน `data/pea.db` ปัจจุบัน:
`domain_allowlist`, `prompt`, `schema_version`, `sqlite_sequence`, `tool`, `tool_auth`, `tool_operation`

---

## บล็อกกติกาที่ใช้ซ้ำทุกขั้น

ทุก PROMPT ด้านล่างมีบล็อกนี้อยู่แล้ว เก็บไว้อ้างอิงเวลาต้องแก้:

```text
# กติกาบังคับ
1. โหลด skill ชื่อ `implement` ด้วย tool `skill` ก่อนเริ่มงาน แล้วทำตามคำสั่งของมันเต็มรูปแบบ
   (ใช้ /tdd ที่ seam ที่เหมาะสม, รันเทสไฟล์เดียวบ่อย ๆ, รัน full suite ตอนจบ,
    แล้วรีวิวงานตัวเองด้วย /code-review ก่อน commit)
2. อ่าน `AGENTS.md` ที่ root ก่อนแก้โค้ด และทำตามอย่างเคร่งครัด
   AGENTS.md ของ repo มีอำนาจเหนือกว่าคำแนะนำทั่วไปทุกกรณี
3. อ่าน `ARCHITECTURE-V2.md` และ `CONTRACTS-V2.md` ส่วนที่เกี่ยวข้องก่อนแก้ contract
4. ห้าม `git add -A`, `git add -a`, `git add .`, `git commit -a` เด็ดขาด
   ให้ `git add` ระบุ path ทีละไฟล์ที่ตัวเองแก้เท่านั้น
5. commit หนึ่ง commit เดียว ข้อความภาษาไทย ขึ้นต้นด้วย conventional prefix (ดู `git log` เป็นตัวอย่าง)
6. รัน `.venv/bin/python -m pytest -q` ก่อน commit — ต้องเขียวและจำนวนเทสต้องไม่ลดลง
   ถ้าแดง ห้าม commit ให้รายงานกลับมาแทน
   หมายเหตุ: pytest อยู่ใน virtualenv ของโปรเจกต์เท่านั้น `python3 -m pytest` ตรง ๆ จะไม่เจอ module
7. แตะได้เฉพาะไฟล์ใน "ขอบเขตไฟล์" ถ้าจำเป็นต้องออกนอกขอบเขต ให้หยุดแล้วรายงาน
8. อย่าแตะ unrelated dirty changes ที่ค้างอยู่ใน working tree
9. อย่าอ้างว่าผ่านถ้าไม่ได้รันจริง รายงานคำสั่งที่รันและผลลัพธ์จริง
10. ห้ามเขียนเทสที่ผ่านโดยไม่ได้พิสูจน์อะไร (vacuous test) — ก่อน commit ให้ทำ mutation test
    อย่างน้อย 1 เคส: แก้โค้ด production ให้พังชั่วคราว → เทสต้องแดง → คืนไฟล์ → เขียว
    รายงานผล mutation test มาด้วย
```

> **บทเรียนจริงจากงาน D3**: เคยจับเทสหลอกได้ 2 ครั้ง
> ครั้งแรกเทสป้อน input ในอุดมคติเข้า pure function ทั้งที่ DOM จริงผลิตค่านั้นไม่ได้
> ครั้งที่สอง `caplog` จับ log record ไม่ได้เลยเพราะ `configure_logging()` เขียนทับ `root.handlers`
> ทำให้ `assert secret not in caplog.text` เป็นจริงเสมอ — ข้อ 10 มีไว้เพราะเรื่องนี้

---

# ส่วนที่ 1 — ปลดล็อกเดโม (P1–P5)

---

## P1 — auth ของ declarative tool เก็บใน DB ได้ทุกแบบ

### บริบทของบั๊ก (ยืนยันด้วยการรันจริงแล้ว)

แจ้งไฟดับไม่ได้เพราะ OMS ตอบ `401`:

```bash
$ curl -s -i http://127.0.0.1:8080/api/v1/oms/outages/by-ca/123456789012
HTTP/1.1 401 Unauthorized
{"error":{"code":"UNAUTHORIZED","message":"missing or invalid X-API-Key"}}
```

มีปัญหาซ้อนกัน 2 ชั้น:

**ชั้นที่ 1** — `oms_tool` ใน DB ไม่มีแถว `tool_auth` เลย ทั้งที่ `.env` มี `OMS_API_KEY`
`app/db/bootstrap_oms.py` seed แค่ `tool` + `tool_operation` ไม่เคย insert `tool_auth`

**ชั้นที่ 2 (ร้ายกว่า)** — ต่อให้ใส่ auth ก็ยังพัง เพราะ header ถูก hardcode:

```python
# app/tools/declarative_executor.py
class DeclarativeToolAuth:
    env_var: str
    header_name: str = "Authorization"   # hardcode
    scheme: str = "Bearer"               # hardcode
```

และตาราง `tool_auth` มีแค่ `id, tool_id, type, secret_ref` — ไม่มีที่เก็บ header name/scheme

พิสูจน์แล้วว่า OMS ต้องการ `X-API-Key` ไม่ใช่ `Authorization: Bearer`:

```bash
$ curl -H "Authorization: Bearer <key>" .../outages/by-ca/123456789012   # 401
$ curl -H "X-API-Key: <key>"            .../outages/by-ca/123456789012   # 404 (ผ่าน auth แล้ว)
```

แปลว่า declarative tool ปัจจุบันยิง API ที่ใช้ `X-API-Key` ไม่ได้เลย ซึ่งขัดกับจุดขาย
"เพิ่ม tool อะไรก็ได้จากหน้าเว็บ"

### PROMPT

```text
/implement ทำให้ auth ของ declarative tool เก็บใน DB ได้ทุกแบบ และแก้ OMS 401

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# ปัญหา
แจ้งไฟดับไม่ได้เพราะ OMS ตอบ 401 missing or invalid X-API-Key
มีสองชั้นซ้อนกัน:
1. `app/db/bootstrap_oms.py` seed แค่ tool + tool_operation ไม่เคย insert tool_auth
   ทั้งที่ .env มี OMS_API_KEY อยู่
2. `DeclarativeToolAuth` ใน `app/tools/declarative_executor.py` hardcode
   header_name="Authorization" scheme="Bearer" และตาราง tool_auth มีแค่
   (id, tool_id, type, secret_ref) ไม่มีที่เก็บ header name/scheme
   แต่ OMS ต้องการ `X-API-Key: <key>` — ยืนยันแล้วว่า Bearer ได้ 401 ส่วน X-API-Key ได้ 404

# ข้อกำหนด
- เพิ่ม migration ใหม่ `app/db/migrations/003_*.sql` เพิ่มคอลัมน์ให้ tool_auth เก็บ
  header name และ scheme ได้ พร้อม DEFAULT ที่ทำให้ tool เดิมพฤติกรรมไม่เปลี่ยน
  (Authorization / Bearer) — migration ต้อง idempotent และรันซ้ำได้
  ดูรูปแบบจาก `002_add_http_columns.sql` ที่มีอยู่แล้ว
- `DeclarativeToolAuth` ต้องรับ header_name/scheme จาก DB แทน hardcode
  scheme ว่าง = ส่งค่า secret ตรง ๆ ไม่มี prefix (กรณี X-API-Key)
- `seed_oms_tool` ต้อง seed tool_auth ให้ OMS: secret_ref=OMS_API_KEY,
  header_name=X-API-Key, scheme ว่าง — ต้อง idempotent เหมือนเดิม
  และต้องไม่ทับค่าที่ผู้ใช้แก้เองไว้แล้ว
- หน้า admin เพิ่มช่องเลือก header name และ scheme ต่อยอดจาก auth semantics เดิม
  (ไม่ส่ง authEnvVar = preserve, string = replace, null = remove — ห้ามทำ semantics นี้พัง)
- ห้ามคืนค่า secret หรือชื่อ env var กลับทาง API เด็ดขาด — GET ยังคืนแค่ hasAuth
  แต่ header_name/scheme คืนได้เพราะไม่ใช่ความลับ
- redaction เดิมของปุ่ม "ลองยิงดู" ต้องยัง redact secret ครบทุกช่องทาง

# ขอบเขตไฟล์
- app/db/migrations/003_*.sql (ใหม่)
- app/db/bootstrap_oms.py
- app/db/tool_repository.py
- app/tools/declarative_executor.py
- app/agent/declarative_tools.py
- app/core/tool_admin.py
- app/api/admin.py, app/contracts.py
- web/admin.js, web/admin.html, web/admin-form.js
- CONTRACTS.md / CONTRACTS-V2.md เฉพาะส่วน auth
- tests/ ไฟล์ใหม่ตามความเหมาะสม

# เทสที่ต้องมี
1. migration รันซ้ำได้ และ tool เดิมที่ไม่มี header_name ยังใช้ Authorization/Bearer เหมือนเดิม
2. tool ที่ตั้ง X-API-Key ส่ง header ถูกต้อง (ตรวจ header ที่ executor สร้างจริง)
3. scheme ว่าง = ไม่มี prefix นำหน้าค่า secret
4. auth semantics preserve/replace/remove ยังทำงานครบหลังเพิ่มฟิลด์ใหม่
5. secret และชื่อ env var ไม่รั่วออกทาง response/log
6. seed_oms_tool idempotent และไม่ทับค่าที่ผู้ใช้แก้เอง

# เกณฑ์เสร็จที่ต้องพิสูจน์ด้วยการรันจริง
สตาร์ต server (ไม่มี --reload) แล้วยิง GET by-ca ผ่านปุ่ม "ลองยิงดู" หรือผ่าน API
ต้องไม่ได้ 401 อีก — รายงาน HTTP status ที่ได้จริง
```

---

## P2 — ปุ่มลิงก์ไปหน้าแอดมิน + จัดการช่อง "การตรวจสอบ"

### บริบท

`web/index.html` ไม่มีลิงก์ไป `admin.html` เลย ต้องพิมพ์ URL เองซึ่งไม่เหมาะกับการเดโมสด

ส่วนช่อง "การตรวจสอบ" (trace panel) ผู้ใช้บอกว่าอ่านยาก แต่ **PRD ผูกไว้หลายจุด**:
- PRD บรรทัด 44 — กรรมการต้องเห็น critical path ที่ตรวจสอบได้
- PRD บรรทัด 76 — หน้าเว็บต้องแสดง trace
- PRD บรรทัด 171 — ผู้สาธิตเปิดดู trace ที่เรียงลำดับและปกปิดข้อมูลแล้ว
- PRD หลักการข้อ 7 — "Auditable, not introspective"

จึงไม่ควรลบทิ้ง ให้ซ่อนหลัง flag แทน

### PROMPT

```text
/implement เพิ่มทางเข้าหน้าแอดมิน และเก็บ trace panel ไว้หลัง flag

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# ปัญหา
1. web/index.html ไม่มีลิงก์ไป admin.html ต้องพิมพ์ URL เอง — ไม่เหมาะกับการเดโมสด
2. ช่อง "การตรวจสอบ" (trace panel) รกหน้าจอตอนเดโม แต่ลบทิ้งไม่ได้เพราะ PRD ผูกไว้
   (PRD บรรทัด 44, 76, 171 และหลักการข้อ 7 "Auditable, not introspective")

# ข้อกำหนด
- เพิ่มปุ่ม/ลิงก์ไปหน้าแอดมินที่ header ของ web/index.html
  ถ้า ADMIN_PASSWORD ไม่ได้ตั้งค่า admin จะถูกปิดอยู่แล้ว (fail closed ตอบ 503)
  ให้ตัดสินใจว่าจะซ่อนลิงก์หรือแสดงแล้วให้หน้า admin จัดการเอง แล้วอธิบายเหตุผล
- trace panel: ซ่อนปุ่ม "การตรวจสอบ" เป็นค่าเริ่มต้น เปิดได้ด้วย query string
  (เช่น ?trace=1) เพื่อให้เดโมสะอาดแต่ยังโชว์ได้ทันทีเมื่อกรรมการถาม
- ห้ามลบโค้ด trace หรือ endpoint /traces/{id} ทิ้ง
- ต้องมีวิธีให้ผู้ใช้รู้ว่าเปิดยังไง (เช่นเขียนใน README หรือ tooltip)

# ขอบเขตไฟล์
- web/index.html, web/app.js, web/styles.css
- README.md เฉพาะส่วนที่อธิบายวิธีเปิด trace panel
- tests/ ไฟล์ใหม่ถ้าจำเป็น
- ห้ามแตะ app/** ทั้งหมด

# เทสที่ต้องมี
- ค่าเริ่มต้นไม่แสดงปุ่ม trace / เปิดด้วย flag แล้วแสดง
- ลิงก์ไปหน้าแอดมินมีอยู่จริงใน markup
(ทดสอบด้วยการอ่าน HTML/JS จริง หรือ node ตามแพตเทิร์น tests/test_frontend_linkify.py)
```

---

## P3 — ย้าย `voc` เป็น declarative tool ใน DB

### บริบท

`docs/v2/TASKS.md` T5.3 — พิสูจน์ `guided_flow` และ `ChoicePrompt` ต้องข้าม channel ได้

`app/plugins/voc/` มี 4 action: `list_categories`, `prepare_case`, `submit_case`, `get_case`
และมีไฟล์ที่ไม่ใช่แค่ HTTP: `flow.py`, `intake.py`, `prefill.py`, `response.py`

> ⚠️ **ขั้นนี้เสี่ยงกว่าที่เห็น** — `guided_flow` และ `prefill` ไม่ใช่แค่การยิง HTTP
> ต้องประเมินก่อนว่าย้ายได้ทั้งหมดหรือย้ายได้เฉพาะส่วน HTTP
> ถ้าประเมินแล้วว่าย้ายทั้งหมดไม่ได้ **ให้หยุดและรายงาน อย่าฝืนย้าย**

### PROMPT

```text
/implement ย้าย voc เป็น declarative tool ใน DB (V2 T5.3)

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# เป้าหมาย
ตาม docs/v2/TASKS.md T5.3 — ย้าย voc จาก Python plugin เป็น declarative tool ใน DB
เพื่อให้แก้จากหน้า admin ได้ พิสูจน์ว่า guided_flow และ ChoicePrompt ยังข้าม channel ได้

# ขั้นตอนที่ต้องทำก่อนแก้โค้ด (สำคัญ)
อ่านให้ครบก่อน: app/plugins/voc/{plugin.yaml,flow.py,intake.py,prefill.py,response.py,factory.py}
แล้วประเมินและรายงานก่อนลงมือ:
- action ไหนเป็น HTTP ล้วน (ย้ายเป็น declarative ได้ตรง ๆ)
- ส่วนไหนเป็น logic ที่ declarative contract ปัจจุบันแทนไม่ได้
  (guided_flow, prefill, ChoicePrompt, response policy)
- ถ้าย้ายทั้งหมดไม่ได้ ให้เสนอขอบเขตที่ย้ายได้จริงแบบ MVP แล้ว **หยุดรอ** อย่าฝืนย้ายทั้งก้อน

# ข้อกำหนดเมื่อได้ขอบเขตแล้ว
- ใช้ oms_tool เป็นแบบอ้างอิง (app/db/bootstrap_oms.py + app/plugins/oms/declarative_shape.py)
- seed ต้อง idempotent และไม่ทับค่าที่ผู้ใช้แก้เองจากหน้า admin
- พฤติกรรมที่ผู้ใช้เห็นต้องไม่เปลี่ยน — เส้นทาง VOC เดิมต้องยังทำงานครบ
- prepare → confirm → submit ต้องยังทำงาน รวม idempotency และ terminal rejection
- ถ้ายังต้องเหลือ Python plugin ไว้บางส่วน ให้อธิบายชัดว่าเหลืออะไรและทำไม

# ขอบเขตไฟล์
- app/db/ (bootstrap ใหม่สำหรับ voc + migration ถ้าจำเป็น)
- app/plugins/voc/**
- app/main.py เฉพาะส่วนประกอบ registry
- tests/

# เทสที่ต้องมี
1. เส้นทาง VOC เดิมทำงานครบหลังย้าย (regression)
2. prepare → confirm → submit + idempotency + terminal rejection
3. guided_flow / ChoicePrompt ยังข้าม channel ได้
4. seed idempotent และไม่ทับค่าที่ผู้ใช้แก้เอง
5. voc ปรากฏในหน้ารายการ tool ของ admin พร้อมสถานะที่ถูกต้อง
```

---

## P4 — เปิด/ปิด code tool จากหน้าเว็บได้จริง

### บริบท

ตอนนี้ `app/core/tool_admin.py` กัน code tool ไว้:

```python
async def set_enabled(self, slug: str, enabled: bool) -> None:
    if slug in self._code_tool_slugs:
        raise NotFoundException(
            detail="tool จากโค้ด (Python) เปิด/ปิดจากหน้าเว็บไม่ได้ — แก้ที่โค้ดแล้ว deploy แทน"
        )
```

เหตุผลเดิมคือ code tool ถูก instantiate ตอน import `app/main.py` และผูกเข้า `ToolRegistry`
ตั้งแต่ boot การ toggle จาก DB จึงไม่มีผลกับ object ที่รันอยู่ ถ้าปล่อยให้กดได้ UI จะโกหกผู้ใช้

> ⚠️ **ต้องแก้ที่ registry ให้เช็ค enabled ตอน dispatch จริง** ไม่ใช่แค่ปลดล็อกปุ่ม
> ถ้าปลดล็อกปุ่มเฉย ๆ = UI โกหก ซึ่งแย่กว่าเดิม

### PROMPT

```text
/implement ให้เปิด/ปิด code tool จากหน้าแอดมินได้จริง

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# ปัญหา
หน้ารายการ tool เปิด/ปิดได้เฉพาะ declarative tool (oms_tool, cat_fact_tool)
ส่วน code tool (knowledge, voc) ปุ่มถูก disable เพราะ
`ToolAdminService.set_enabled` โยน NotFoundException สำหรับ code tool

เหตุผลเดิม: code tool ถูก instantiate ตอน import app/main.py และผูกเข้า ToolRegistry
ตั้งแต่ boot การ toggle จาก DB จึงไม่มีผลกับ object ที่รันอยู่

# ข้อกำหนด
- **ห้ามปลดล็อกปุ่มเฉย ๆ** — ต้องทำให้ enabled มีผลจริงตอน dispatch
  ให้ ToolRegistry ตรวจสถานะ enabled ตอน execute/สร้าง catalogue
  ถ้า tool ถูกปิด: ต้องไม่อยู่ใน catalogue ที่ส่งให้ LLM และถ้ามีการเรียกต้องถูกปฏิเสธอย่างชัดเจน
- สถานะเปิด/ปิดของ code tool ต้องเก็บใน DB (persist ข้าม restart)
  ออกแบบว่าจะใช้ตาราง tool เดิมหรือเพิ่มตารางใหม่ แล้วอธิบายเหตุผล
- ต้องมี guard ไม่ให้ปิด tool จนระบบใช้งานไม่ได้ หรืออย่างน้อยเตือนให้ชัดบน UI
- เส้นทาง knowledge ที่กำลังจะใช้เดโมต้องไม่พัง
- หน้า admin: ปุ่มเปิด/ปิดของ code tool ใช้งานได้ ส่วนปุ่ม "แก้ไข" ยัง disable
  พร้อมเหตุผล (แก้ definition ของ code tool จากเว็บยังทำไม่ได้)

# ขอบเขตไฟล์
- app/agent/registry.py
- app/core/tool_admin.py
- app/db/ (migration + repository ถ้าจำเป็น)
- app/main.py, app/live/scoped_agent.py เฉพาะส่วนประกอบ registry
- web/admin.js, web/admin.html
- tests/

# เทสที่ต้องมี
1. ปิด code tool แล้ว tool นั้นหายจาก catalogue ที่ส่งให้ LLM จริง
2. ปิดแล้วเรียกใช้ ต้องถูกปฏิเสธอย่างชัดเจน ไม่ใช่ทำงานเงียบ ๆ ต่อ
3. สถานะคงอยู่ข้าม restart (persist ใน DB)
4. เปิดกลับแล้วใช้งานได้เหมือนเดิม
5. declarative tool เปิด/ปิดยังทำงานเหมือนเดิม (ไม่ regress)
6. app/live/scoped_agent.py ที่สร้าง ToolRegistry อีกที่ไม่พัง
```

---

## P5 — ปิด D3.7 (ตรวจครั้งสุดท้าย + บันทึกหลักฐานเดโม)

### บริบท

ขั้นนี้ **ต้องมีมนุษย์อยู่ด้วย** เพราะมี LINE, voice, และ `./scripts/evaluate` ที่ต้องยิงของจริง

แบ่งเป็น 2 กอง:

**กองที่ agent รันเองได้:**
```bash
grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py   # ต้อง = 0
ls app/prompts/                                               # ต้องไม่มีแล้ว
.venv/bin/python -m pytest -q
# SSRF: ยิง 127.0.0.1 และ 169.254.169.254 ผ่าน /admin/tools/try ใน APP_ENV=production
```

**กองที่ต้องมีมนุษย์:** `./scripts/evaluate`, เส้นทาง knowledge, แจ้งไฟดับ prepare→confirm,
LINE (ต้องมี channel secret/token), voice (ต้องมีไมโครโฟนจริง),
สร้าง tool ใหม่จากหน้า admin → ลองยิง → เปิดใช้ → ให้ AI เรียก

> ⚠️ `.env` ปัจจุบันยังไม่ได้ตั้ง `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN`
> ถ้าไม่ใส่ ต้องบันทึกเป็นข้อจำกัดว่า "ไม่ได้ทดสอบ" ห้ามเขียนว่าผ่าน

**หมายเหตุสำคัญ**: uvicorn ต้องรัน **ไม่มี `--reload`** เพราะ `app/main.py` เรียก
`asyncio.run()` ที่ระดับ module (บรรทัด 132, 150) ซึ่งพังเมื่อ `--reload` โหลดแอปใน event loop
ดู P9 สำหรับการแก้เรื่องนี้

### PROMPT

```text
/implement ทำ D3.7 final verification และบันทึกหลักฐานการซ้อมเดโม โดยไม่เพิ่ม feature ใหม่

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# ขอบเขต — ทำตาม docs/v2/TASKS-3DAYS.md D3.7

## กองที่ให้รันเองทันที
- grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py   (ต้อง = 0)
- ls app/prompts/                                              (ต้องไม่มีแล้ว)
- .venv/bin/python -m pytest -q
- ทดสอบ SSRF: ใน APP_ENV=production ยิง 127.0.0.1 และ 169.254.169.254
  ผ่าน /api/v1/admin/tools/try ต้องถูกปฏิเสธพร้อมเหตุผล

## กองที่ต้องให้มนุษย์เดินเอง — เตรียมช่องว่างไว้ในเอกสาร ห้ามกรอกผลเอง
- ./scripts/evaluate http://127.0.0.1:8000
- เดินเส้นทาง knowledge
- แจ้งไฟดับ prepare→confirm
- LINE
- voice
- สร้าง tool ใหม่จากหน้า admin → ลองยิง → เปิดใช้ → ให้ AI เรียก

# ข้อกำหนด
- สร้างเอกสาร demo verification ที่เหมาะสม (เช่น docs/v2/DEMO-VERIFICATION.md)
- บันทึกคำสั่งจริง ผลลัพธ์จริง และข้อจำกัด
- **ห้ามเขียนว่า "ผ่าน" ถ้าไม่ได้รันจริง** — สิ่งที่ยังไม่ได้รันให้เขียนว่า "รอมนุษย์ยืนยัน"
- .env ปัจจุบันไม่มี LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN
  ถ้ายังไม่มี ให้บันทึกเป็นข้อจำกัด "ไม่ได้ทดสอบ" อย่างตรงไปตรงมา
- หมายเหตุ: uvicorn ต้องรันแบบไม่มี --reload (app/main.py มี asyncio.run ระดับ module)
- ห้ามเพิ่ม feature ใหม่ในขั้นนี้

# ขอบเขตไฟล์
- docs/v2/DEMO-VERIFICATION.md (ใหม่)
- docs/v2/TASKS-3DAYS.md เฉพาะการติ๊กสถานะ
- ห้ามแตะโค้ด production
```

---

# ส่วนที่ 2 — งานหนักหลังเดโม (P6–P11)

---

## P6 — knowledge เป็น declarative tool (V2 T5.4)

> ⚠️ `docs/v2/TASKS.md` เขียนไว้เองว่า **"ยากสุด กระทบเดโมมากสุด — ทำเป็นตัวสุดท้ายเสมอ"**
> ห้ามทำก่อนเดโมผ่าน

### PROMPT

```text
/implement ย้าย knowledge เป็น declarative tool (V2 T5.4)

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# คำเตือนจากเอกสารแผนเอง
docs/v2/TASKS.md T5.4 ระบุว่า "ยากสุด กระทบเดโมมากสุด — ทำเป็นตัวสุดท้ายเสมอ"
ห้ามเริ่มขั้นนี้ถ้า D3.7 ยังไม่ผ่าน

# เป้าหมาย
พิสูจน์ว่า grounded_answer และ citation validation ทำงานผ่าน policy ไม่ใช่ชื่อ tool

# ขั้นตอนที่ต้องทำก่อนแก้โค้ด
อ่าน app/tools/knowledge_tool.py และ backend ที่มันเรียก แล้วประเมินและรายงานก่อน:
- KnowledgeTool ไม่ใช่ HTTP tool — มันเรียก knowledge backend ในโปรเซส
  (full_document routing + Gemini long context)
- declarative contract ปัจจุบันรองรับแต่ HTTP
- **ประเมินว่าย้ายได้จริงไหม** ถ้าต้องขยาย contract ให้รองรับ tool ที่ไม่ใช่ HTTP
  ให้เสนอทางเลือกพร้อมข้อดีข้อเสีย แล้ว **หยุดรอ** อย่าฝืนทำ

# ข้อกำหนดที่ห้ามละเมิดไม่ว่าจะเลือกทางไหน
- คำตอบต้องยัง grounded จากเอกสารจริงพร้อม citation ที่ตรวจสอบได้
- ห้ามเพิ่ม vector search / embedding / chunk retrieval / RAG architecture ใหม่
  (AGENTS.md ห้ามไว้ชัดเจน)
- ห้ามแก้เอกสารต้นฉบับใน knowledge/source
- เส้นทาง knowledge ต้องยังทำงานครบ รวม follow-up ที่เพิ่งแก้ไป
  (conversation ที่ได้ grounded answer ต้องถามต่อได้)

# เทสที่ต้องมี
1. เส้นทาง knowledge ทำงานครบหลังย้าย
2. citation validation ยังทำงานผ่าน policy
3. follow-up หลังคำตอบ knowledge ยังทำงาน (ไม่ regress จาก fix ก่อนหน้า)
4. grep ToolName./ToolAction. ใน app/agent/main_agent.py ยังเป็น 0
```

---

## P7 — trace และ pending action ลง SQLite (V2 เฟส 3)

### บริบท

ตอนนี้ trace และ pending action อยู่ใน RAM (`app/agent/stores.py`) — restart แล้วหาย
`docs/v2/TASKS.md` T3.1 และ T3.2 เป็นงานที่มีเครื่องหมาย 🔒 = ต้องมีเทสแน่นอน

### PROMPT

```text
/implement ย้าย trace และ pending action ลง SQLite (V2 T3.1 + T3.2)

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# บริบท
ตอนนี้ TraceStore และ PendingActionStore อยู่ใน RAM (app/agent/stores.py)
restart แล้วข้อมูลหาย — PRD ยอมรับข้อจำกัดนี้ชั่วคราวแต่ V2 วางแผนย้ายลง SQLite ไว้แล้ว
docs/v2/TASKS.md T3.1/T3.2 ทั้งคู่มีเครื่องหมาย 🔒 = ต้องมีเทสแน่นอน

# ข้อกำหนด
- migration ใหม่สำหรับตาราง trace และ pending_action
- **trace ordering ต้องคงที่และถูกต้อง** (เทสบังคับ)
- **redaction ต้องทำงานเหมือนเดิมทุกประการ** — ห้ามมี secret หรือ chain-of-thought ลง DB
- **pending action state machine ต้องคงเดิม**: prepare → confirm → submit
  รวม idempotency และ terminal rejection (เทสบังคับ)
- interface ของ store ไม่ควรเปลี่ยนจนกระทบผู้เรียก ถ้าต้องเปลี่ยนให้อธิบายเหตุผล
- ตาราง trace จะโตเรื่อย ๆ — พิจารณา retention (T3.4) ว่าจะทำในขั้นนี้หรือแยก
  ถ้าแยกให้บันทึกไว้ชัดเจน

# ขอบเขตไฟล์
- app/db/migrations/, app/db/
- app/agent/stores.py
- app/main.py, app/core/di.py เฉพาะส่วน wiring
- tests/

# เทสที่ต้องมี (บังคับตาม 🔒)
1. trace ordering ถูกต้องและคงที่
2. redaction ทำงาน — ไม่มี secret / chain-of-thought ใน DB
3. pending action state machine: prepare → confirm → submit
4. idempotency: submit ซ้ำด้วย key เดิมไม่สร้างรายการซ้ำ
5. terminal rejection: action ที่ถูก reject แล้วปลุกกลับไม่ได้
6. ข้อมูลอยู่รอดข้าม restart จริง
```

---

## P8 — Public API (V2 เฟส 8)

### PROMPT

```text
/implement ทำ Public API ตาม V2 เฟส 8 (T8.1–T8.4)

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# เป้าหมาย — docs/v2/TASKS.md เฟส 8 ทั้งหมดมีเครื่องหมาย 🔒 สามในสี่ข้อ

## T8.1 API key
- ตาราง api_key เก็บ hash ไม่เก็บค่าจริง
- แสดงค่าจริงครั้งเดียวตอนสร้าง
- เพิกถอนได้ · tenant_id = 'default'

## T8.2 conversation ownership
- server ออก id เสมอ
- ส่ง id ของ key อื่น = **404 ไม่ใช่ 403** (ห้ามเปิดเผยว่ามี resource นั้นอยู่)

## T8.3 error contract
- {error:{code,message,traceId}} · code เป็นชุดปิด
- error ห้ามมี stack trace / ชื่อ tool / URL ปลายทาง

## T8.4 rate limit
- ตัวนับใน memory ต่อ key ต่อนาที · เกิน = 429

# ข้อกำหนด
- อ่าน CONTRACTS-V2.md ส่วน public API ก่อนเขียน แล้วทำให้ตรง
- ห้ามกระทบเส้นทาง web/LINE/voice ที่มีอยู่
- อัปเดต CONTRACTS.md และ .env.example ตามที่เปลี่ยนจริง

# เทสที่ต้องมี (บังคับตาม 🔒)
1. key ที่ถูกเพิกถอนใช้ไม่ได้ · ไม่มี key = 401
2. key A เข้าถึง conversation ของ key B ไม่ได้ และได้ 404 ไม่ใช่ 403
3. error ไม่มี stack trace / ชื่อ tool / URL ปลายทาง
4. เกิน rate limit ได้ 429
5. hash ของ key ไม่ย้อนกลับเป็นค่าจริง และค่าจริงไม่ถูก log
```

---

## P9 — แก้ bootstrap ให้ `--reload` ใช้งานได้

### บริบทของบั๊ก (ยืนยันแล้ว)

```bash
$ uvicorn app.main:app --reload
RuntimeError: asyncio.run() cannot be called from a running event loop
```

**สาเหตุ** — `app/main.py` เรียก `asyncio.run()` ที่ระดับ module (บรรทัด 132 และ 150)

- **ไม่มี `--reload`**: `uvicorn/main.py:609` เรียก `config.load_app()` ก่อน `server.run()`
  → import ตอนยังไม่มี event loop → ผ่าน
- **มี `--reload`**: ข้าม `load_app()` ไปเข้า `ChangeReload` → subprocess เรียก `Server.run()`
  → `asyncio_run(self.serve(...))` → เข้า loop แล้ว → `_serve` ค่อย `config.load()`
  (`uvicorn/server.py:88`) → import ตอนอยู่ใน loop → ระเบิด

พิสูจน์แล้ว: import `app.main` ใน running loop = FAILED, นอก loop = OK

### PROMPT

```text
/implement แก้ bootstrap ของ app/main.py ให้รองรับ uvicorn --reload

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# ปัญหา (ยืนยันด้วยการรันจริงแล้ว)
`uvicorn app.main:app --reload` พังด้วย
RuntimeError: asyncio.run() cannot be called from a running event loop

สาเหตุ: app/main.py เรียก asyncio.run() ที่ระดับ module (บรรทัด 132 seed_system_prompt
และบรรทัด 150 _load_declarative_catalogue)

- ไม่มี --reload: uvicorn/main.py:609 เรียก config.load_app() ก่อน server.run()
  → import ตอนยังไม่มี event loop → ผ่าน
- มี --reload: ข้าม load_app() ไปเข้า ChangeReload → subprocess เรียก Server.run()
  → asyncio_run(self.serve(...)) → เข้า loop แล้ว → _serve ค่อย config.load()
  (uvicorn/server.py:88) → import ตอนอยู่ใน loop → ระเบิด

คอมเมนต์ที่ app/main.py:126 เขียนว่า "asyncio.run ปลอดภัยตรงนี้เพราะยังไม่มี event loop
ทำงานอยู่ตอน import" — สมมติฐานนี้ผิดสำหรับ --reload

# ข้อกำหนด
- ย้าย seed_system_prompt และ _load_declarative_catalogue จาก module level
  ไปทำใน FastAPI lifespan (หรือกลไก startup ที่เหมาะสม)
- ความยากคือ tool_registry, main_agent, app.state.tool_admin ผูกกับ declarative_bundle
  ที่ถูกสร้างตอน import ทั้งหมด → ต้องออกแบบลำดับ bootstrap ใหม่
- **พฤติกรรมตอนรันปกติ (ไม่มี --reload) ต้องไม่เปลี่ยน**
- app/live/scoped_agent.py ก็สร้าง ToolRegistry อีกที่ — ต้องไม่พัง
- เทสทั้งหมดที่ import app.main หรือใช้ TestClient ต้องยังทำงาน

# เกณฑ์เสร็จที่ต้องพิสูจน์ด้วยการรันจริง
1. `uvicorn app.main:app --reload` สตาร์ตได้ และ /health ตอบ 200
2. `uvicorn app.main:app` (ไม่มี --reload) ยังทำงานเหมือนเดิม
3. full pytest เขียว
รายงานผลการรันทั้งสามข้อ

# ขอบเขตไฟล์
- app/main.py, app/core/startup.py
- app/live/scoped_agent.py เฉพาะที่จำเป็น
- tests/
```

---

## P10 — Telegram adapter (V2 เฟส 4)

### PROMPT

```text
/implement ทำ Telegram adapter ตาม V2 T4.1–T4.4

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# เป้าหมาย — docs/v2/TASKS.md เฟส 4
- T4.1 เติม simulation + actions[] ใน ChatResponse
- T4.2 ยกของกลางออกจาก line/service.py เป็นชั้น channel adapter ที่ใช้ร่วมกัน
- T4.3 capability declaration ของแต่ละ channel
- T4.4 🔒 Telegram adapter

# ข้อกำหนด
- อ่าน app/api/line.py เป็นแบบอ้างอิงว่า channel adapter ปัจจุบันทำงานอย่างไร
- **เส้นทาง LINE เดิมต้องไม่พัง** — นี่คือความเสี่ยงหลักของขั้นนี้
- ตรวจลายเซ็น webhook อย่างถูกต้อง (ดู tests/test_line_signature.py เป็นแบบ)
- ไม่ตั้ง token = ปิดช่องทางแบบ fail closed เหมือน LINE
- อัปเดต .env.example และ README

# เทสที่ต้องมี (บังคับตาม 🔒)
1. Telegram webhook auth — ลายเซ็น/token ผิดต้องถูกปฏิเสธ
2. callback ทำงานถูกต้อง
3. LINE เดิมไม่ regress
4. ไม่ตั้ง token = ช่องทางถูกปิด ไม่ใช่ crash
```

---

## P11 — voice read-back และยืนยันด้วยเสียง (V2 เฟส 6)

### PROMPT

```text
/implement ทำ voice read-back และการยืนยันด้วยเสียง (V2 T6.1–T6.4)

# กติกาบังคับ
[วางบล็อกกติกาจากหัวเอกสาร]

# เป้าหมาย — docs/v2/TASKS.md เฟส 6

## T6.1 🔒 read-back + ยืนยันด้วยเสียง
- อ่านทวนทุก field ที่จะบันทึกก่อนถามยืนยัน
- จับคำแบบกำหนดตายตัว · **ตรวจชุดปฏิเสธก่อนชุดยืนยัน**
- ไม่ตรง = ถามซ้ำ มีเพดาน

## T6.2 🔒 คำปฏิเสธ = เข้าโหมดแก้ไข
- ถามว่าแก้ช่องไหน · รายการช่องมาจาก inputSchema
- **สร้าง pending action ใหม่ ห้ามปลุกของเดิม**
- มีเพดานรอบการแก้ไข

## T6.3 voiceConfirm + citation degrade
## T6.4 หลักฐานการยืนยัน

# ข้อกำหนดความปลอดภัยที่ห้ามละเมิด
- **LLM ต้องไม่มีทางตัดสินคำยืนยัน** — ต้องเป็น deterministic matching เท่านั้น
- ตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ (ไม่งั้น "ไม่ใช่ครับ" จะถูกนับเป็นยืนยัน)

# เทสที่ต้องมี (บังคับตาม 🔒)
1. "ไม่ใช่ครับ" ต้องไม่ถูกนับเป็นยืนยัน
2. LLM ไม่มีทางตัดสินคำยืนยัน (พิสูจน์ด้วยโครงสร้างโค้ด ไม่ใช่แค่ prompt)
3. action เดิมยัง terminal หลังเข้าโหมดแก้ไข
4. เพดานรอบการแก้ไขทำงาน
```

---

# ภาคผนวก — สิ่งที่ควรรู้ก่อนเริ่ม

## คำสั่งที่ใช้บ่อย

```bash
.venv/bin/python -m pytest -q                                    # full suite
uvicorn app.main:app --host 127.0.0.1 --port 8000                # ไม่มี --reload (ดู P9)
./scripts/evaluate http://127.0.0.1:8000                         # ต้องมี server รันอยู่
grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py       # ต้อง = 0
```

## กับดักที่เคยเจอจริงในโปรเจกต์นี้

| กับดัก | อาการ | ทางกัน |
|---|---|---|
| เทสหลอกจาก input ในอุดมคติ | เทสเขียวแต่ของจริงพัง | เทสต้องผ่านเส้นทางเดียวกับ production |
| `caplog` จับ log ไม่ได้ | `assert x not in caplog.text` จริงเสมอ | `configure_logging()` เขียนทับ root handlers — ติดตั้ง handler เองหลังสร้าง app |
| CSS `[hidden]` ถูก class ทับ | ล็อกอินสำเร็จแต่หน้าจอไม่เปลี่ยน | class มี specificity สูงกว่า `[hidden]` ของเบราว์เซอร์ |
| `asyncio.run()` ระดับ module | `--reload` พัง | ดู P9 |
| baseline จับคู่ด้วย index | metadata ย้ายไปผิด operation | จับคู่ด้วย key ที่มีความหมาย (action) |
| payload merge baseline ทั้งก้อน | 422 extra inputs not permitted | กรองให้เหลือเฉพาะฟิลด์ที่ contract รับ |

## เอกสารอ้างอิง

- `AGENTS.md` — ลำดับความสำคัญและ Definition of Done (มีอำนาจสูงสุด)
- `ARCHITECTURE-V2.md` — ขอบเขตโมดูลและ ownership
- `CONTRACTS-V2.md` — สัญญา API และ tool
- `docs/v2/TASKS.md` — แผนเต็ม 9 เฟส
- `docs/v2/TASKS-3DAYS.md` — แผนเร่งรัดและเกณฑ์เดโม
- `PRD.md` — ขอบเขตผลิตภัณฑ์และสิ่งที่ต้องสื่อสารตามตรง
