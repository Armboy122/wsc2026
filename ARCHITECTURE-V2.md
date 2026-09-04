# PEA One Agent V2 — สถาปัตยกรรม

> เอกสารนี้เป็น **ผลของการตัดสินใจที่ปิดครบแล้ว** ไม่ใช่ข้อเสนอ
> ที่มา: [แผนที่ #1](https://github.com/Armboy122/wsc2026/issues/1) และ ticket #2–#14 ที่ปิดแล้วทั้ง 12 ใบ
> ทบทวนยืนยันโดยเจ้าของแผนที่ 2026-09-04 (64 ข้อยืนยัน / 2 ข้อแก้ไข — บันทึกใน #14)
>
> เอกสารคู่กัน: `CONTRACTS-V2.md` (สัญญาที่ตรึงไว้) และ `docs/v2/TASKS.md` (ลำดับลงมือ)
> เอกสาร V1 (`ARCHITECTURE.md`, `CONTRACTS.md`) **ยังเป็นความจริงของระบบที่รันอยู่** จนกว่าการย้ายจะเสร็จ

---

## 1. เป้าหมายเดียวของ V2

> **Agent ไม่รู้จักชื่อ tool ใด ๆ เลย — แม้แต่ตัวเดียว**

V1 มี 12 จุดใน `app/agent/main_agent.py` ที่อ้าง `ToolName.KNOWLEDGE` / `ToolName.OMS` ตรง ๆ
V2 ต้องเหลือ **0 จุด** ไม่ใช่ "เหลือน้อยลง"

สิ่งที่ตามมาจากเป้าหมายนี้:

| ผลที่ตามมา | รายละเอียด |
|---|---|
| tool เป็น **ข้อมูล** ไม่ใช่โค้ด | schema เก็บใน SQLite เพิ่ม tool ใหม่ได้จากหน้า admin โดยไม่แตะ Python |
| agent รู้จักแค่ **policy กลาง 4 แบบ** | tool เลือก policy เอง — agent ไม่รู้ว่าใครเลือกอะไร |
| channel เป็น **adapter** ที่แปล intent-level response | เพิ่ม Telegram = เขียน adapter ตัวเดียว ไม่แตะ agent |
| config/prompt แก้จาก **หน้า admin** | ไม่ต้อง deploy ใหม่เพื่อแก้คำอธิบาย tool |

### ข้อจำกัดที่ล็อกไว้ตั้งแต่วันแรก (ห้ามรื้อโดยไม่คุยกับเจ้าของแผนที่)

1. **วิวัฒน์ใน `app/` เดิม** ไม่เขียนใหม่ ไม่สร้าง `app/v2/` คู่ขนาน
2. **มี policy กลางเสมอ** ห้ามทำเป็น pure LLM loop ที่ LLM ส่ง write ได้เอง
3. **tool สองชั้น** declarative จาก DB + Python plugin สำหรับ logic พิเศษ
4. **config/prompt อยู่ใน SQLite** ไม่ใช่ไฟล์บนดิสก์ ไม่ใช่ Postgres
5. **channel ได้ intent-level response** ห้ามให้แต่ละ channel เขียน flow เอง
6. **single tenant** แต่เติม `tenant_id` ทีหลังได้ด้วย migration เดียว
7. **pending action + trace ลง SQLite** / conversation history อยู่ RAM
8. **เทสเฉพาะจุดสำคัญ** security + สัญญาข้อมูล ไม่เอา TDD เต็มรูปแบบ ไม่มีเป้า coverage

---

## 2. ภาพรวมของระบบ

```text
   Web        LINE      Telegram    Voice(Live)   Public API
    │          │           │            │             │
    └──────────┴───────────┴────────────┴─────────────┘
                          │
              ┌───────────▼────────────┐
              │   Channel Adapter      │  ประกาศ capability ของตัวเอง
              │   (แปล ChatResponse    │  แล้ว degrade เอง
              │    → UI ของ channel)   │  agent ไม่เคยอ่าน capability
              └───────────┬────────────┘
                          │  ChatResponse (intent-level)
              ┌───────────▼────────────┐
              │      Main Agent        │  ❌ ไม่รู้จักชื่อ tool ใด ๆ
              │  + Policy Layer (4)    │  ✅ รู้จักแค่ policy 4 แบบ
              └───────────┬────────────┘
                          │  ToolCall(tool_slug, action, input)
              ┌───────────▼────────────┐
              │    Tool Registry       │  shape เดียว executor ต่างกัน
              └─────┬────────────┬─────┘
                    │            │
        ┌───────────▼──┐    ┌────▼─────────────┐
        │ Declarative  │    │  Python Plugin   │
        │ (จาก SQLite) │    │  (จากโค้ด)       │
        │ executor =   │    │  executor =      │
        │ HTTP caller  │    │  callable        │
        └───────┬──────┘    └──────────────────┘
                │ ผ่านนโยบาย SSRF เสมอ
                ▼
          ปลายทาง REST ภายนอก

              ┌────────────────────────┐
              │        SQLite          │  tool/config/prompt/pending/trace
              └────────────────────────┘
```

**สิ่งที่ไม่เปลี่ยนจาก V1**: FastAPI โพรเซสเดียว · Main Agent ตัวเดียว · knowledge grounding แบบ full-document · `prepare → confirm → submit` · LINE bridge ที่ทำงานได้อยู่

---

## 3. สัญญา Tool v2 — schema เป็นข้อมูล

**ที่มา: [#2](https://github.com/Armboy122/wsc2026/issues/2) · ข้อเท็จจริงจาก [#6](https://github.com/Armboy122/wsc2026/issues/6)**

### 3.1 ปัญหาที่แก้

V1 เขียน `inputContract: OmsGetOutageByCaInput` ใน `plugin.yaml` แล้ว `manifest.py` ตรวจกับ `INPUT_MODELS` ใน `contracts.py` จริง
⇒ เพิ่ม tool ใหม่ = **ต้องแก้โค้ด Python** ซึ่งขัดกับเป้าหมายทั้งหมด

### 3.2 schema คือ JSON Schema subset ที่ allowlist ไว้

เก็บเป็น JSON object ใน SQLite และ **ไม่รับ JSON Schema เต็มสเปก**

| รับ | ปฏิเสธตั้งแต่ตอน save |
|---|---|
| `type: object` ที่ root เท่านั้น | recursive schema, external `$ref` |
| string / number / integer / boolean / null | `pattern`, `minimum`, `maximum`, `multipleOf` |
| `enum` (primitive), `const` | `minLength`, `maxLength` |
| `array` + `items` + `minItems` เฉพาะ 0/1 | `oneOf`, `not`, `if/then/else` |
| `anyOf`, `$defs`/`$ref` ภายในไฟล์ | `patternProperties`, `dependentRequired` |
| `required`, `description`, `default` | `unevaluatedProperties`, `contains`, `uniqueItems` |
| **บังคับ** `additionalProperties: false` ทุก object | ลึกเกิน **5 ชั้น** |

**เหตุผล**: keyword นอกรายการนี้ทำให้ Anthropic strict mode ตอบ **400** หรือถูกกลืนเงียบ ถ้าปล่อยให้ admin กรอกได้จะได้ tool ที่ "บันทึกผ่านแต่รันไม่ได้" ซึ่งเป็นบั๊กที่หาสาเหตุยากที่สุด

⚠️ constraint ที่ตัดออก (`pattern`, `minimum`) **ไม่ได้แปลว่าไม่ต้องตรวจ** — ย้ายไปตรวจในชั้น business validation ของ executor เพราะ LLM ไม่บังคับให้อยู่แล้ว

### 3.3 validate ด้วย `jsonschema` ตัวเดียวทุก tool

รับ dependency `jsonschema[format]` (พ่วง `attrs`, `referencing`, `jsonschema-specifications`, `rpds-py`)

**ทำไมไม่ใช้ Pydantic runtime** — ทดสอบจริงแล้ว (pydantic 2.13.5):
- `TypeAdapter({"type":"object",...})` → `SchemaError: Unknown schema type: "object"` เพราะตีความ dict เป็น pydantic-core `CoreSchema` ซึ่งเป็น **คนละภาษา**
- ต่อให้เขียน converter เอง keyword อย่าง `uniqueItems` / `dependentRequired` / `not` **หายเงียบโดยไม่มี error** ⇒ เอกสารที่ schema ต้นฉบับปฏิเสธจะผ่านฉลุย = ช่องโหว่บน security boundary

**บังคับใช้ `check_schema()` ตอน save** เพื่อจับ typo ของ admin (`{"type":"objct"}`) ตั้งแต่ตอนกดบันทึก
**ต้องติดตั้งแบบ `jsonschema[format]`** ไม่งั้น `format` ไม่ validate อะไรเลยและเงียบ

**Pydantic ยังอยู่**: envelope ภายใน (`ToolCall`, `ToolResult`, transport contract, FastAPI request/response) ไม่เปลี่ยน — เปลี่ยนเฉพาะ **input/output ของ tool**

### 3.4 registry เดียว shape เดียว executor ต่างกัน

```text
slug         : ^[a-z0-9_-]{1,64}$        ตัวระบุที่ LLM เห็น
displayName  : ชื่อภาษาไทยสำหรับ UI       ไม่เคยส่งเข้า LLM API
description  : คำอธิบายที่ LLM เห็น
operations[] : { action, description, inputSchema, outputSchema,
                 exposure, mode, submitAction?, policy, limits,
                 clientContext?, voiceConfirm }
executor     : HTTP caller กลาง (declarative) | Python callable (plugin)
source       : "db" | "code"              ใช้แค่ตอน admin/health ไม่ใช่ตอน dispatch
```

**`plugin.yaml` เปลี่ยนจาก `inputContract: <ชื่อคลาส>` เป็น `inputSchema:` JSON Schema ฝังในไฟล์**
⇒ Python plugin พูดภาษาเดียวกับ DB และ `_check_contracts` ที่เทียบ `INPUT_MODELS[action].__name__` หายไปทั้งก้อน

**agent เห็นเฉพาะ** `slug` + `description` + operations ที่ `exposure: llm` — ไม่รู้ว่า executor เป็นอะไร ไม่รู้ว่ามาจาก DB หรือโค้ด

### 3.5 `ToolName` / `ToolAction` enum ถูกทิ้ง

- identity เป็น `tool_slug: str` + `action: str`
- `TOOL_ACTIONS` และ `PREPARE_TO_SUBMIT` กลายเป็น **data ที่มากับ tool definition แต่ละตัว** ไม่ใช่ dict กลางใน `contracts.py`
- validation ที่ `ToolCall.action_belongs_to_tool` เคยทำด้วย enum ย้ายไปตรวจกับ registry ตอน dispatch
- คงค่าคงที่ของ 4 tool เดิมไว้เป็น **alias เฉพาะช่วง migration** แล้วลบทิ้งเมื่อย้ายครบ

**slug เข้มกว่าที่ Anthropic บังคับ** (`^[a-zA-Z0-9_-]{1,64}$`) โดยตั้งใจ — บังคับตัวพิมพ์เล็กเพื่อไม่ให้ `Oms_Tool` กับ `oms_tool` อยู่ร่วมกันได้ · **ชื่อไทยยิง LLM API ไม่ผ่าน** จึงอยู่ที่ `displayName` เท่านั้น

### 3.6 fail closed แบบแยก blast radius

| จังหวะ | พฤติกรรม |
|---|---|
| admin กด save จาก UI | validate เต็ม (allowlist §3.2 + `check_schema()` + SSRF ของ URL) ผิด = **reject ไม่ persist** พร้อมข้อความไทยที่บอกว่าผิดตรงไหน |
| โหลด declarative tool จาก DB ตอน runtime | tool ที่พัง **ปิดตัวเอง** ไม่ทำให้ระบบล้ม + บันทึก `TOOL_DISABLED` + แสดงสถานะที่ health/admin |
| โหลด Python plugin ตอน startup | **fail closed เดิม** — manifest ผิด = startup ล้มทั้งระบบ (เป็นโค้ดที่เรา commit เอง) |

⚠️ **เงื่อนไขบังคับ**: ต้องมีที่ให้เห็นสถานะราย tool ไม่งั้น "ปิดเฉพาะตัว" จะกลายเป็น "หายเงียบ" ซึ่งอันตรายกว่าระบบล้ม เพราะ agent จะบอกผู้ใช้ว่า "ทำรายการไม่ได้" โดยไม่มีใครรู้สาเหตุ

### 3.7 ข้อห้ามที่ไม่ต่อรอง

- **secret ห้ามอยู่ใน schema เด็ดขาด** — schema = สิ่งที่ LLM เห็น = public
- **URL ที่ผู้ใช้กรอก = เครื่อง SSRF** (ดู §7)
- **เลือก mechanism "LLM เติมค่า" อันเดียวตั้งแต่วันแรก** — n8n มีสองอัน (`$fromAI()` + placeholder) แล้วถอยไม่ได้ ทำผู้ใช้พังตอนพยายามรวม
- **description ยาว = กินโควตา token ทุก request** (tool definitions นับเป็น input token) หน้า admin ต้องแสดงจำนวนตัวอักษร

---

## 4. Policy Layer — สิ่งเดียวที่ agent รู้จัก

**ที่มา: [#3](https://github.com/Armboy122/wsc2026/issues/3)**

### 4.1 หลักการ

`main_agent.py` ทุกวันนี้ **ไม่ได้ถามว่า "นี่คือ knowledge ไหม"** จริง ๆ — มันถามว่า *"ผลนี้ต้องมีหลักฐานอ้างอิงไหม"* กับ *"นี่เปลี่ยนสถานะจริงไหม"* แค่บังเอิญเขียนด้วยชื่อ tool

**เปลี่ยนคำถามให้ตรงกับสิ่งที่ตั้งใจถาม = ชื่อ tool หายไปเอง**

### 4.2 policy กลาง 4 แบบ (ห้ามเพิ่มเป็นตัวที่ 5 เพื่อรองรับ tool ตัวใดตัวหนึ่ง)

| policy | รับประกันอะไร | ใครใช้ |
|---|---|---|
| `grounded_answer` | ผลต้องมี citation จริงถึงจะถูกส่งต่อ · ห้าม LLM เรียบเรียงเนื้อหาเอง · ไม่มี citation = แทนด้วยข้อความ escalation | knowledge |
| `write_confirm` | บังคับ `prepare_* → confirm → submit_*` · `submit` ต้อง `exposure: internal` เสมอ · ผล prepare หยุด loop เพื่อรอมนุษย์ | oms, voc, sabuy |
| `guided_flow` | tool ยึดบทสนทนาชั่วคราวเพื่อเก็บข้อมูลทีละขั้น · agent ส่งต่อ turn ให้ flow แทนการวางแผนเอง | voc intake |
| `plain_read` | อ่านแล้วจบ ไม่มีผลข้างเคียง | read operations ทั้งหมด |

**ไม่นับเป็น policy**: result presentation / error presentation — เป็น formatting ที่ `ResponsePolicy` ของ plugin ทำอยู่แล้ว ไม่มีผลด้านความปลอดภัย
ถ้ายกขึ้นมาเป็น policy จะปนกันระหว่าง "กฎที่ละเมิดไม่ได้" กับ "วิธีจัดถ้อยคำ"

### 4.3 ประกาศที่ระดับ operation ไม่ใช่ระดับ tool

```yaml
operations:
  - action: list_categories
    policy: plain_read
  - action: prepare_case
    policy: write_confirm
    submitAction: submit_case
  - action: submit_case
    policy: write_confirm
    exposure: internal
```

`voc_tool` ตัวเดียวมี 3 policy คนละแบบอยู่แล้ว ⇒ ประกาศระดับ tool ผิดตั้งแต่ตั้งต้น
ไม่ให้ override ระดับ tool เพราะ "มีสองที่ให้ตั้งค่า = มีสองที่ให้ตั้งผิด"

**`limits` ต่อ operation** แทนเลข knowledge ที่ hardcode:
```yaml
limits:
  maxCallsPerTurn: 3           # เดิม _MAX_KNOWLEDGE_SEARCHES_PER_TURN
  dedupeIdenticalInput: true   # เดิมเงื่อนไข "knowledge หรือไม่ใช่ prepare"
```
`dedupeIdenticalInput` default = `true` สำหรับ `plain_read`/`grounded_answer` และ **`false` สำหรับ `write_confirm`** (เรียก prepare ซ้ำด้วย input เดิมคือเจตนาที่ต่างจากการอ่านซ้ำ)

### 4.4 การย้าย 12 จุด hardcode

| บรรทัดใน `main_agent.py` | ทำอะไร | ย้ายไปไหน |
|---|---|---|
| 194 | จำกัดจำนวนค้นหา knowledge ต่อเทิร์น | `limits.maxCallsPerTurn` |
| 202 | กันเรียกซ้ำด้วย input เดิม | `limits.dedupeIdenticalInput` |
| 487–488 | เติมพิกัดเบราว์เซอร์ให้ `oms_prepare_anonymous_outage` | **`clientContext`** (ดูล่าง) |
| 543 | ยกเว้น knowledge จากการตัดสิน "อ่านซ้ำ" | `policy is grounded_answer` |
| 624 | สร้าง conversation context ต่อเนื่อง | `grounded_answer` |
| 663, 676 | ยกเว้น knowledge จาก "ตอบไปแล้ว" | `policy is grounded_answer` |
| 790, 798, 803, 811 | บังคับ citation + escalation message | `grounded_answer` |

**จุดที่ต้องออกแบบใหม่มีจุดเดียว** — 487–488 ไม่ใช่ policy แต่เป็น *device state injection* ที่รู้จักชื่อ field เฉพาะของ tool นั้น แก้ด้วยให้ operation ประกาศเอง:

```yaml
clientContext:
  lat: lat      # ชื่อ context ที่ระบบรู้จัก → ชื่อ field ใน input
  lon: lon
```

agent เติมตามใบสั่งโดยไม่รู้ว่าเป็น OMS และคง `setdefault` เดิม (ไม่ทับค่าที่ LLM ใส่มา)
ชุด context ที่ระบบรู้จักเป็น **enum ปิด** (เริ่มที่ `lat`, `lon`) ไม่ใช่ช่องให้ tool ขออะไรก็ได้จาก request

⇒ **เหลือ 0 จุดที่ agent รู้จักชื่อ tool**

### 4.5 default = `plain_read` + `exposure: internal` (fail safe)

operation ที่ไม่ประกาศ `policy` จะได้ `plain_read` **และ** ถูกบังคับเป็น `exposure: internal`
⇒ ระบบเห็น แต่ LLM เรียกไม่ได้จนกว่าจะประกาศชัด

- **ไม่ reject ทั้งระบบ** เพราะจะทำให้ tool ที่กำลังร่างทำ startup ล้ม ขัดกับ `_is_enabled` ที่ยอมให้โครงยังไม่เสร็จอยู่ร่วมใน repo ได้
- **ไม่ปล่อยให้เรียกได้เลย** เพราะ operation ที่ลืมประกาศ `write_confirm` จะยิง write ได้ทันที
- ทิศเดียวกับ MCP ที่ตั้ง `destructiveHint` default = `true`

หน้า admin ต้องแสดงว่า operation นี้ *"ยังไม่เปิดให้ AI ใช้ เพราะยังไม่ได้เลือก policy"* — เงียบไม่ได้

### 4.6 policy ที่ tool ประกาศเอง = untrusted

MCP spec เขียนชัดว่า *"Clients MUST consider tool annotations to be untrusted"* — เรายืมคำศัพท์ ไม่ยืมความไว้ใจ

**ตรวจตอน save / startup (ผิด = reject)**
- operation ที่มี `submitAction` แต่ประกาศ `plain_read`
- `mode: submit` ที่ไม่ใช่ `exposure: internal`
- `write_confirm` ที่ไม่มีคู่ prepare→submit
- `clientContext` ที่อ้าง context นอก enum ปิด

**บังคับตอน runtime (ผิด = ปฏิเสธผล ไม่ใช่แค่เตือน)**
- `grounded_answer` ที่ผลไม่มี citation → แทนด้วยข้อความ escalation ไม่ส่งให้ผู้ใช้เป็นคำตอบ
- `plain_read` ที่ executor สร้าง pending action → ปฏิเสธผลและบันทึกเป็น error (tool โกหกเรื่อง side effect)
- `write_confirm` ที่ submit ถูกเรียกโดยไม่มี pending action ที่ยืนยันแล้ว → ปฏิเสธ

---

## 5. Channel Adapter

**ที่มา: [#4](https://github.com/Armboy122/wsc2026/issues/4) · ข้อเท็จจริง Telegram จาก [#5](https://github.com/Armboy122/wsc2026/issues/5)**

### 5.1 สัญญามีอยู่แล้ว ~80%

`ChatResponse` ปัจจุบันมี `message` / `citations` / `pendingAction` / `choicePrompt` / `traceId` ครบแล้ว
**ปัญหาไม่ใช่ "ไม่มีสัญญา"** แต่คือ `app/line/service.py` (414 บรรทัด) ตีความสัญญานั้นเป็น UI เอง และ Telegram จะ copy ทั้งชุดถ้าไม่แก้ตอนนี้

**เติมแค่ 2 ฟิลด์**:

| ฟิลด์ | ทำไม |
|---|---|
| `simulation` | วันนี้ LINE hardcode `_SIMULATION_NOTICE` ไว้เอง ส่วน web ไม่มีเลย ⇒ ข้อความ "นี่คือระบบจำลอง" ขึ้นกับว่าเข้าทางไหน เป็นเรื่องความถูกต้อง ไม่ใช่การตกแต่ง |
| `actions[]` | บอกว่า "ปุ่มชุดนี้กดได้ครั้งเดียว/ควรหายหลังกด" — Telegram ทำ native ด้วย `editMessageReplyMarkup`, LINE emulate ด้วยข้อความใหม่, API แค่บอก client |

### 5.2 `pendingAction` กับ `choicePrompt` แยกกันต่อไป

| | `pendingAction` | `choicePrompt` |
|---|---|---|
| ความหมาย | "ยืนยันสิ่งที่กำลังจะเกิดขึ้น" | "ตอบคำถามข้อนี้" |
| side effect | มี | ไม่มี |
| การรับประกัน | state machine + idempotency + ปฏิเสธถาวร | `promptId` กันตอบผิดขั้น |
| policy | `write_confirm` | `guided_flow` |

ยุบรวม = adapter ต้องเขียน `if type == confirm` อยู่ดี แต่เสียการรับประกันของ type system ทั้งสองฝั่ง
**แต่บังคับให้มี helper กลางตัวเดียว** แปลงทั้งคู่เป็นโครง `{label, value, kind}` — แยกที่ *สัญญา* แต่รวมที่ *การแปลง*

### 5.3 adapter เป็นคนตัด agent ส่งเต็มเสมอ

| channel | เพดาน | ที่มา |
|---|---|---|
| LINE | 1900 | `_MAX_TEXT_CHARS` ในโค้ดปัจจุบัน (ต่ำกว่า 5000 ที่ LINE ยอม) |
| Telegram | 4096 | Bot API `sendMessage` |
| Web / public API | ไม่จำกัด | — |

ไม่บังคับให้ agent ตัดที่ค่าต่ำสุด เพราะจะทำให้ผู้ใช้ web และ API ได้คำตอบสั้นลงเพราะข้อจำกัดของ LINE ซึ่งไม่มีเหตุผล

**แต่วิธีตัดเป็นสัญญากลาง**: ตัดที่ขอบเขตคำ/บรรทัด · มีตัวบ่งชี้ว่ายังมีต่อ · ห้ามตัดจน citation หรือข้อความยืนยันหาย (ส่งเป็นข้อความแยกเสมอ)

### 5.4 capability declaration

```text
buttons          : bool     API = false
editableMessage  : bool     Telegram = true, LINE = false
richLayout       : bool     LINE Flex = true
maxTextLength    : int
maxButtons       : int      LINE quick reply 13
```

**agent ไม่เคยอ่าน capability — adapter อ่านของตัวเองเพื่อ degrade**
⇒ เพิ่ม channel ใหม่ไม่ต้องแตะ agent เลย และ capability table เป็น **ที่เดียว** ที่บันทึกความรู้แบบ "LINE ได้ 13 ปุ่ม / Telegram `callback_data` 64 bytes / API ไม่มีปุ่ม"

**degrade เมื่อไม่มีปุ่ม** (public API): แสดงตัวเลือกเป็นข้อความ + คืน `pendingActionId` / `promptId` ให้ client เรียก endpoint ยืนยันตรง

### 5.5 ผ่า `line/service.py` เป็นสองชั้น

| ยกขึ้นเป็นของกลาง | เหลืออยู่กับ LINE |
|---|---|
| `_split_text` ตัดข้อความตามเพดาน | JSON ของ Flex / template / confirm |
| `_truncate_button_label` | quick reply กับ postback payload |
| logic ตัดสินว่าเมื่อไหร่ควรมีปุ่มยืนยัน | รูปแบบ event ของ LINE webhook |
| จัดรูป citation → รายการ + ปุ่มเปิดเอกสาร | `X-Line-Signature` (`signature.py` ไม่แตะ) |
| แนบข้อความ simulation | |

เป้า: LINE adapter เหลือ **~150 บรรทัดที่รู้จัก LINE จริง ๆ** และ Telegram adapter เขียนใหม่ขนาดใกล้เคียงกัน

### 5.6 Telegram adapter (ข้อเท็จจริงที่ยืนยันแล้ว)

- **inline keyboard + callback button** สำหรับยืนยัน/ยกเลิก — `callback_data` จำกัด **1–64 bytes** ⇒ UUID ใส่ได้ (~44 bytes รวม prefix) แต่ควรส่ง key สั้นแล้ว map ฝั่ง server เมื่อต้องขยาย
- **ต้องเรียก `answerCallbackQuery` ทุกครั้ง** ไม่งั้นผู้ใช้เห็น spinner ค้างทั้งที่ประมวลผลเสร็จแล้ว
- **ลบ/ปิดปุ่มหลังยืนยันด้วย `editMessageReplyMarkup`** — แต่กัน double-submit จริงต้องพึ่ง idempotency ฝั่ง server เพราะมี race
- **webhook ต้อง HTTPS + `secret_token`** (1–256 chars, header `X-Telegram-Bot-Api-Secret-Token`) ⚠️ **อ่อนกว่า HMAC ของ LINE เพราะไม่ผูก body** — ต้อง `compare_digest` + HTTPS + พร้อมหมุน secret
- **`user.id` เป็น conversation key ได้** แต่ group→supergroup migration เปลี่ยน `chat.id` ⇒ ต้อง handle `migrate_to_chat_id`
- **ไม่เพิ่ม library — ยิง httpx ตรง** ทรงเดียวกับ `app/line/api_client.py` (python-telegram-bot รองรับแค่ Bot API 10.0 vs ปัจจุบัน 10.3 + ดึง tornado + LGPL)

---

## 6. ช่องทางเสียง

**ที่มา: [#14](https://github.com/Armboy122/wsc2026/issues/14) รวมการแก้ไขรอบทบทวน**

### 6.1 เสียงยืนยันด้วยเสียงได้ — read-back คือหลักฐานการรับรู้

```text
ผู้ใช้แจ้งข้อมูลด้วยเสียง → prepare_* → ระบบอ่านทวนสิ่งที่จะบันทึกทั้งหมด
   → ผู้ใช้พูดคำยืนยัน → submit_*
```

`write_confirm` **ไม่ถูกยกเว้น** — ยังบังคับ `prepare → confirm → submit` และ `submit` ยัง `exposure: internal`
สิ่งที่เปลี่ยนคือ **รูปของ "confirm" ในช่องทางเสียงคือคำพูดที่ตามหลัง read-back**

| channel | รูปของ confirm |
|---|---|
| Web | เห็นสรุปแล้วกดปุ่ม |
| LINE | เห็นสรุปแล้วกด postback |
| Telegram | เห็นสรุปแล้วกด inline button |
| **เสียง** | **ได้ยินสรุปแล้วพูดยืนยัน** |

โครงเดียวกันทั้งหมด ต่างกันแค่รูปการนำเสนอ ซึ่งตรงกับ §5 พอดี

> **บันทึกไว้ให้ครบ**: ข้อเสนอตั้งต้นของผู้ช่วยคือ "เสียงเตรียมได้ แต่ต้องยืนยันที่ช่องทางอื่นเสมอ" โดยอ้างว่าต้องยืนยันบนสิ่งที่ *เห็น*
> เจ้าของแผนที่ปฏิเสธด้วยเหตุผลที่ถูกต้องกว่า: ประเด็นของ `write_confirm` คือ **"ผู้ใช้ต้องรับรู้ว่ากำลังยืนยันอะไร"** ไม่ใช่ "ต้องเห็นด้วยตา" — read-back ทำหน้าที่นั้นครบ และเป็นวิธีที่ call center ใช้จริงมาก่อนมี GUI

### 6.2 `voiceConfirm` — ธงระดับ operation, default = อนุญาต

```yaml
- action: prepare_anonymous_outage
  policy: write_confirm
  # ไม่ต้องเขียนอะไร — ยืนยันด้วยเสียงได้โดยปริยาย
- action: prepare_payment
  policy: write_confirm
  voiceConfirm: false   # เงินจริง ฟังผิด = เงินหาย
```

ติดธง `false` เฉพาะ operation ที่เกี่ยวกับ **เงิน** หรือ **ข้อมูลส่วนบุคคลที่เปิดเผยไม่ได้ทางเสียง** — ณ วันนี้มีตัวเดียวคือ Sabuy payment
operation ที่ติดธงนี้ในช่องทางเสียง → ตกไปที่ handoff (§6.5)

### 6.3 คำยืนยันจับคู่ตายตัว ห้าม LLM ตีความ · ปฏิเสธ = เข้าโหมดแก้ไข

**รับเป็นการยืนยัน**: `ยืนยัน`, `ตกลง`, `ใช่` (+`ครับ`/`ค่ะ`), `ถูกต้อง`, `เอาเลย`
**รับเป็นการปฏิเสธ**: `ยกเลิก`, `ไม่ใช่`, `ไม่เอา`, `ผิด`, `แก้ไข`
**ไม่ตรงทั้งสองชุด** → ถามซ้ำ ไม่เดา ไม่ส่งต่อให้ LLM ตัดสิน

⚠️ **ตรวจการปฏิเสธก่อนการยืนยันเสมอ** — ไม่งั้น "ไม่ใช่ครับ" จะถูกนับเป็นยืนยันเพราะมีคำว่า "ใช่" อยู่ข้างใน

**ทำไมห้าม LLM ตีความ**: ขัดกรอบข้อ 2 ตรง ๆ — ถ้า LLM ตัดสินว่าคำนี้แปลว่ายืนยัน = LLM เป็นคนกด submit
ถามซ้ำหนึ่งครั้งเสียเวลา 5 วินาที ตีความผิดหนึ่งครั้งคือใบแจ้งเหตุปลอมที่ต้องตามลบ

**ปฏิเสธ = เข้าสู่โหมดแก้ไข ไม่ใช่ยกเลิกทิ้ง** *(แก้รอบทบทวน)*

```text
read-back → ผู้ใช้พูดคำปฏิเสธ
   → ระบบถาม "ต้องการแก้ส่วนไหนครับ" + อ่านรายการช่องที่แก้ได้
   → ผู้ใช้ระบุช่อง (เช่น "ที่อยู่") หรือพูดว่า "ทั้งหมด"
   → เก็บค่าใหม่เฉพาะช่องนั้น (หรือเริ่มใหม่ทั้งชุด)
   → prepare ใหม่ → read-back ใหม่ → รอคำยืนยันอีกครั้ง
```

⚠️ **ข้อบังคับที่ห้ามละเมิด**: terminal rejection **ยังคง terminal** ตามสัญญาเดิม
⇒ การแก้ไขคือ **สร้าง pending action ใหม่** ไม่ใช่ปลุก action เดิมกลับมา — action เก่าอยู่ใน trace เป็นหลักฐานว่าผู้ใช้ไม่ยอมรับรายการนั้น

**ช่องที่ให้แก้มาจาก schema ของ operation** ไม่ใช่ให้ LLM คิดเอง ⇒ agent ยังไม่รู้จักชื่อ tool
มี**เพดานรอบการแก้ไข** — แก้แล้วแก้อีกไม่จบต้องหยุดแล้วเสนอทางอื่น (ส่งลิงก์ให้กรอกเอง)

### 6.4 หลักฐานการยืนยัน

บันทึกลง trace ใน event ของ `ACTION_CONFIRMED`:
- **ข้อความ read-back ที่ระบบพูดออกไป** — คือ "สิ่งที่ผู้ใช้ได้ยินก่อนตัดสินใจ" เทียบเท่าภาพหน้าจอในช่องทางอื่น
- **ข้อความถอดเสียงของคำยืนยัน** + เวลา
- **ไม่เก็บไฟล์เสียง** — เป็นข้อมูลชีวมิติที่ต้องมีนโยบายเก็บรักษาทั้งชุด ไม่คุ้มในเฟสนี้

### 6.5 เสียงไม่พูดอ้างอิงเลย *(แก้รอบทบทวน)*

| ชั้น | เปลี่ยนไหม |
|---|---|
| การบังคับใช้ `grounded_answer` ฝั่ง server | ❌ **ไม่เปลี่ยน** — ผลที่ไม่มี citation ยังถูกปฏิเสธและแทนด้วย escalation เหมือนเดิมทุกช่องทาง |
| การนำเสนอ citation ในช่องทางเสียง | ✅ **เปลี่ยน — ไม่พูดออกมา** |

นี่ไม่ใช่การยกเว้น policy แต่เป็น **การ degrade ที่ระดับ presentation** ซึ่ง §5 ออกแบบให้ adapter ทำอยู่แล้ว
คำตอบยัง grounded เท่าเดิม เพียงแต่ผู้ฟังไม่ต้องนั่งฟังชื่อระเบียบยาว ๆ ที่จดตามไม่ทันอยู่ดี

**ถ้าผู้ใช้ขอแหล่งอ้างอิง** → ส่งเป็นข้อความพร้อมลิงก์ (handoff เคสที่ 1)
**trace ยังบันทึก citation ครบ** แม้ไม่ถูกพูด ⇒ ตรวจย้อนหลังได้เสมอ · `RESPONSE_DEGRADED` ต้องบอกว่า citation ถูกตัดเพราะช่องทางเป็นเสียง

### 6.6 handoff ส่งลิงก์ — เป็น tool ไม่ใช่ฟิลด์

การส่ง SMS ไปหาเบอร์คือ **side effect จริง** (เสียเงิน ส่งผิดเบอร์ได้ ถูกใช้ยิง spam ได้)
ทำเป็น tool ⇒ ได้ `write_confirm` + rate limit + trace + การตรวจสอบข้ามของ §4.6 ฟรีทันที
ถ้าทำเป็นฟิลด์ใน response มันจะเลี่ยง policy layer ทั้งหมดไป

**เหลือไว้ 3 เคส**: ผู้ใช้ขอเอกสาร/ลิงก์อ้างอิง · operation ที่ติดธง `voiceConfirm: false` · ผู้ใช้ขอเอง

**ความปลอดภัยของลิงก์** — หลักคือ *ทำให้ลิงก์ที่หลุดไม่มีค่า* ไม่ใช่ทำให้ส่งยาก: เปิดได้ครั้งเดียว · อายุสั้น · ไม่แสดง PII จนกว่าจะยืนยันตัวตนอีกชั้น · จำกัดอัตราต่อเบอร์และต่อบทสนทนา · เมื่อมี CA ส่งได้เฉพาะเบอร์ที่ผูกกับหมายเลขผู้ใช้ไฟนั้น

**ไม่ใช้ OTP** — ในบทสนทนาเสียงคือฝันร้าย UX (รอ SMS แล้วพูดเลข 6 หลักให้ ASR ฟังถูก) และไม่ได้กัน spam เบอร์คนอื่นอยู่ดี เพราะ OTP ก็คือ SMS ที่เราส่งไปแล้ว

### 6.7 `VOICE_TOOLS` → channel profile ใน DB

`app/live/scoped_agent.py` วันนี้ hardcode `frozenset({ToolName.KNOWLEDGE, ToolName.OMS})` ซึ่งอยู่ไม่ได้เมื่อทิ้ง enum
แทนด้วย **channel profile ในฐานข้อมูล** แก้ได้จากหน้า admin

**ไม่ให้ tool ประกาศเองว่ารองรับ channel ไหน** เพราะเป็นการตัดสินใจของ *ผู้ดูแลระบบ* ไม่ใช่ของ tool

**คงคุณสมบัติเดิมของ `scoped_agent.py` ไว้ทั้งหมด**: เป็นการ **ลดสิทธิ์เท่านั้น** · ใช้ **store ชุดเดียวกับ agent หลัก** (pending action ที่เตรียมด้วยเสียงยังยืนยันข้ามช่องทางได้ และ trace อ่านที่เดิม) · กรอง `guided_flow` แยกเพราะทำงานก่อน planner

---

## 7. นโยบายเครือข่ายขาออกและ SSRF

**ที่มา: [#13](https://github.com/Armboy122/wsc2026/issues/13)**

> **บันทึกไว้ให้ครบ**: ข้อเสนอตั้งต้นคือ allowlist ตายตัวตั้งแต่วันแรก เจ้าของแผนที่แก้เป็น "ระหว่างพัฒนาต้องยิงได้ทุกที่"
> เหตุผลที่ถูกต้องกว่า: ระหว่างสร้าง tool ใหม่ ปลายทางคือ mock server บนเครื่องตัวเอง ถ้าบล็อก `127.0.0.1` ตั้งแต่วันแรก = สร้าง tool ใหม่ไม่ได้เลย แล้วคนจะปิดการป้องกันทิ้งทั้งชุด ซึ่งแย่กว่าไม่มีตั้งแต่แรก

### 7.1 โหมดสองระดับผูกกับ `APP_ENV` ไม่ใช่ค่าใน DB

| โหมด | พฤติกรรม | ใครเปลี่ยนได้ |
|---|---|---|
| **development** | ยิงได้ทุกโดเมน ทุก IP รวม `localhost`/private range · อนุญาต `http://` | `APP_ENV` (ต้องเข้าถึงเครื่อง) |
| **production** | บังคับ allowlist โดเมน + HTTPS + บล็อก private/link-local/loopback | admin เพิ่ม/ลบโดเมนผ่าน UI ได้ **แต่ปิดโหมดไม่ได้** |

**โหมดต้องมาจาก `APP_ENV`** — ถ้าเป็น toggle ในหน้า admin จะมีวันที่มีคนกดปิดบน production เพื่อแก้ปัญหาเฉพาะหน้าแล้วลืมเปิดคืน
หน้า admin ต้องแสดงโหมดปัจจุบันเด่นชัด

### 7.2 ตรวจด้วย `ipaddress` ใน stdlib

MCP เตือนว่า *"Avoid implementing IP validation manually. Attackers exploit encoding tricks (octal, hex, IPv4-mapped IPv6)"* — คำเตือนนี้หมายถึง **อย่าเขียน parser เอง** ไม่ใช่ "อย่าตรวจเอง"

`ipaddress` จัดการ encoding trick ทั้งหมดให้แล้วและมี `is_private` / `is_link_local` / `is_loopback` / `is_reserved`
⇒ ไม่รับ dependency ใหม่ ไม่ตั้ง egress proxy (เกินความจำเป็นสำหรับระบบที่ยังไม่มี DB ด้วยซ้ำ)

**บน production บล็อก**: `10.0.0.0/8` · `172.16.0.0/12` · `192.168.0.0/16` · `127.0.0.0/8` · **`169.254.0.0/16`** (cloud metadata) · `fc00::/7` · `fe80::/10`

### 7.3 ไม่ตาม redirect ทั้งสองโหมด

`follow_redirects=False` — 3xx = ถือว่า tool config ผิด แจ้ง admin ให้แก้ URL ให้ตรงปลายทางจริง
API ที่ออกแบบดีไม่ redirect endpoint ของตัวเอง — n8n เปิด redirect โดย default แล้วได้ redirect-based SSRF แถมฟรี

### 7.4 ตรวจสองจังหวะ

| จังหวะ | ตรวจอะไร |
|---|---|
| **save** | โดเมนอยู่ใน allowlist (production) · HTTPS (production) · รูปแบบ URL ถูก · ไม่มี credential ฝังใน URL |
| **execute** | resolve DNS แล้วเทียบ IP กับ blocklist **ทุกครั้งก่อนยิง** |

ตรวจแต่ตอน save จะโดน **DNS rebinding** (ตอน save ชี้ IP จริง ตอนยิงชี้ `169.254.169.254`)
ตรวจแต่ตอน execute จะทำให้ admin รู้ว่ากรอกผิดตอน production ล่มแล้ว

### 7.5 เพดานทรัพยากร

| ค่า | default | admin ตั้งได้ | เพดานแข็ง |
|---|---|---|---|
| timeout | 5 วินาที | ✅ | 30 วินาที |
| ขนาด response | 1 MB | ✅ | 10 MB |
| retry | **0** | ❌ | — |

**retry = 0 เสมอ ห้ามตั้งค่า** — tool ที่ทำ write แล้ว retry อัตโนมัติคือการสร้างรายการซ้ำ ระบบมี `prepare → confirm → submit` ที่ให้ผู้ใช้ retry ในระดับที่ถูกต้องอยู่แล้ว
เพดานแข็งจำเป็นเพราะถ้าไม่มี admin จะตั้ง timeout 300 วินาทีแล้ว tool เดียวถ่วงทุกบทสนทนา

### 7.6 เมื่อถูกบล็อก

บันทึก `POLICY_REJECTED` พร้อม **เหตุผลที่อ่านเข้าใจ** (`โดเมนไม่อยู่ใน allowlist` / `ปลายทางเป็น IP ภายใน` / `ไม่ใช่ HTTPS` / `พบ redirect`) และแสดงในหน้า admin
ห้ามคืน error ลอย ๆ — admin ต้องแก้ config ให้ถูกได้โดยไม่ต้องเดา

---

## 8. ชั้นข้อมูล SQLite

**ที่มา: [#7](https://github.com/Armboy122/wsc2026/issues/7)**

### 8.1 ⚠️ ข้อค้นพบ: prompt 4 ไฟล์ไม่ถูกโหลดตอน runtime

ไฟล์ใน `app/prompts/` (`main_agent.md`, `json_planner.md`, `knowledge.md`, `final_response.md`) **ไม่มีโค้ดบรรทัดไหน read มัน**
prompt จริงที่ระบบใช้คือ `SYSTEM_PROMPT` ที่ **hardcode เป็น string ใน `app/llm/prompting.py`** (52 บรรทัด)

`AGENTS.md` เตือนไว้ตรง ๆ ว่า *"verify which prompt is loaded at runtime rather than assuming every Markdown prompt is active"*

⇒ **ย้าย `SYSTEM_PROMPT` ลง DB เป็นแหล่งจริงเดียว แล้วลบ 4 ไฟล์ `.md` ทิ้ง** (seed จากค่าปัจจุบันตอน migrate)
ไฟล์ที่ไม่ถูกโหลดคือหนี้ทางเอกสารที่หลอกทั้งคนและ AI

### 8.2 ตาราง

```sql
tool               slug, display_name, description, enabled, source, created_at
tool_version       tool_id, version, definition_json, created_at, created_by
tool_operation     tool_id, action, policy, input_schema, output_schema,
                   exposure, mode, submit_action, limits, client_context, voice_confirm
tool_auth          tool_id, type, secret_ref
prompt             key, content, version, updated_at
channel_profile    channel, allowed_tool_slugs
domain_allowlist   domain, enabled, added_by
api_key            id, name, key_hash, tenant_id, created_at, revoked_at
pending_action     id, conversation_id, status, summary, payload, trace_id, ...
trace_event        trace_id, sequence, at, kind, tool_slug, action,
                   config_version, policy, channel, data
                   UNIQUE(trace_id, sequence)
```

**เหตุผลที่แยกตาราง**:
- `tool_version` แยกเพราะ §9 บังคับให้ trace join กลับได้ และลบ tool = **soft delete**
- `tool_auth` แยกเพราะ OAuth มีหลาย field (refresh token, expiry, scope) ที่ API key ไม่มี — ยัดรวมใน `tool` = ต้อง migrate ทั้งตารางตอนเติม Google

### 8.3 secret แยกตามชนิด

| ชนิด | เก็บยังไง |
|---|---|
| `api_key` | เก็บ **ชื่อ env var** (pattern `apiKeyEnv` เดิม) — ค่าจริงอยู่นอก DB |
| `oauth2` | เก็บ token ในตารางแบบเข้ารหัสด้วยคีย์จาก env (**ไม่มีทางเลือกอื่น**) |

**V2 ทำแค่ `api_key`** แต่คอลัมน์ `type` + ตาราง `tool_auth` แยกไว้แล้ว ⇒ เติม Google ทีหลัง = เพิ่มแถว ไม่ใช่รื้อตาราง

**เส้นแบ่ง**: config เปลี่ยนได้จาก UI / secret ต้องผ่านคนที่เข้าถึงเครื่องได้
API key เป็นค่าที่มนุษย์ถือ ⇒ อยู่นอก DB ปลอดภัยกว่า · OAuth token เป็นค่าที่เครื่องได้มาเอง ⇒ ต้องอยู่ใน DB

### 8.4 hot-reload

**cache ในหน่วยความจำ + invalidate เมื่อ `config_version` เปลี่ยน และหนึ่งเทิร์นใช้ version เดียวตลอด**

ถ้าโหลดใหม่ทันทีที่ save บทสนทนาที่กำลังดำเนินอยู่จะเปลี่ยน tool กลางคัน — ผู้ใช้เห็น `prepare` จาก config เก่า แล้ว `submit` ด้วย config ใหม่ = **พังสัญญา `write_confirm` ตรง ๆ**
การล็อก version ต่อเทิร์นยังทำให้ `config_version` ใน trace มีความหมายจริง

### 8.5 การเข้าถึงและ concurrency

- **`sqlite3` stdlib + `asyncio.to_thread`** ไม่เพิ่ม dependency (เรียกตรงใน async จะบล็อก event loop / `aiosqlite` ข้างในก็ใช้ thread pool เหมือนกัน)
- **WAL mode + connection เดียวต่อ process + เขียนผ่าน lock เดียว** และ **ประกาศชัดว่ารองรับ single process**
- SQLite ใน WAL อ่านพร้อมกันได้ดี แต่เขียนพร้อมกันคือที่มาของ `database is locked` ซึ่งจะโผล่ตอนสาธิตพอดี — ประกาศข้อจำกัดดีกว่าทำ pool ที่ซ่อนปัญหา

### 8.6 migration

**raw SQL + ตาราง `schema_version`** — ไฟล์ `001_init.sql`, `002_*.sql` รันตามลำดับตอน startup
alembic ดึง SQLAlchemy มาทั้งตัวเพื่อระบบที่มี 10 ตารางและ deps 5 ตัว = หนักกว่าปัญหาที่แก้

### 8.7 `redact()` ทำงานตอนเขียน

ข้อมูลอ่อนไหวไม่เคยแตะดิสก์ — ไฟล์ DB ที่ถูก backup/copy ออกไปต้องไม่มีข้อมูลลูกค้าดิบอยู่ข้างใน

### 8.8 ไฟล์ DB และ `/reset`

- path จาก env `DB_PATH` ค่าเริ่มต้น `data/pea.db`
- `/reset` ล้างเฉพาะ **conversation + pending action ที่ยังไม่ terminal** — **ไม่แตะ trace และไม่แตะ tool config**
- ถ้า `/reset` ลบ config ที่ตั้งไว้ด้วย มันจะกลายเป็นปุ่มทำลายงานตัวเอง

### 8.9 conversation history ยังอยู่ RAM

ตามที่แผนที่ล็อกไว้ — หลักฐานการยืนยันอยู่ใน trace ส่วน pending action มี `summary` ของตัวเองอยู่แล้ว

---

## 9. Trace และ observability

**ที่มา: [#12](https://github.com/Armboy122/wsc2026/issues/12)**

### 9.1 อ้าง tool ด้วย `tool_slug` + `config_version`

trace event เก็บ `tool_slug`, `action`, และ `config_version` ของ definition ที่ใช้ตอนนั้น แล้ว join กับ `tool_version`

- **ไม่เก็บ snapshot เต็มทุก event** — schema จะซ้ำทุกแถวและตารางบวมมหาศาล
- **ไม่เก็บแค่ slug เปล่า** — trace จะไร้ค่าพอดีตอนที่ต้องการมันที่สุด (สอบสวนว่า tool ที่ถูกลบไปแล้วทำอะไรลงไป)

⇒ **ลบ tool = soft delete** ไม่ใช่ลบแถวทิ้ง

### 9.2 HTTP call ของ declarative tool

**เก็บ**: method · host · path · HTTP status · ระยะเวลา · ขนาด response
**ไม่เก็บ**: query string · header · request body · response body

`_SENSITIVE_KEYS` มี 8 คำที่ *เรารู้จัก* แต่ tool ที่ admin สร้างเองจะมี field ชื่ออะไรก็ได้ (`nationalId`, `bankAccount`, `meterNo`) ที่ไม่อยู่ในรายการ ⇒ ข้อมูลลูกค้ารั่วลง trace โดยไม่มีใครรู้ตัว
**query string อันตรายเป็นพิเศษ** เพราะ API key มักอยู่ตรงนั้น

`redact()` ยังอยู่สำหรับ input/output ที่ผ่าน schema ของเราเอง — แต่ไม่ใช่ด่านเดียวสำหรับ payload ที่เราไม่รู้จักรูปร่าง

### 9.3 ฟิลด์และ event kind ใหม่

| ฟิลด์ | ทำไม |
|---|---|
| `tool_slug` + `action` | แทน enum ที่ถูกทิ้ง |
| `config_version` | อ่าน trace ย้อนหลังได้แม้ tool ถูกแก้/ปิด |
| `policy` | บันทึกว่า operation ทำงานภายใต้ policy ไหน |
| `channel` | web / line / telegram / voice / api |

**`TraceEventKind` ที่เพิ่ม**:
- `POLICY_REJECTED` — policy ปฏิเสธผล ⇒ ตอบได้ว่าทำไมผู้ใช้ไม่ได้คำตอบ
- `RESPONSE_DEGRADED` — adapter ตัดข้อความ/ลดปุ่ม/ตัด citation เพราะข้อจำกัดของ channel ⇒ ตอบได้ว่าทำไม LINE เห็นไม่เหมือนเว็บ
- `TOOL_DISABLED` — declarative tool ปิดตัวเองตอน runtime ⇒ **กันไม่ให้ "ปิดเฉพาะตัว" กลายเป็น "หายเงียบ"**

### 9.4 retention

| ประเภท | อายุ |
|---|---|
| trace ทั่วไป | 90 วัน แล้วลบอัตโนมัติ |
| trace ที่มี `ACTION_SUBMITTED` สำเร็จ | **เก็บถาวร** |
| trace ที่มี `ACTION_REJECTED` | **เก็บถาวร** (หลักฐานว่าผู้ใช้ปฏิเสธ) |

trace การอ่าน 10,000 ครั้งไม่มีค่าหลังสามเดือน แต่ *"ใครสั่งแจ้งไฟดับเมื่อไหร่ ผ่านการยืนยันแบบไหน"* คือหลักฐานที่ต้องอยู่ตลอด

### 9.5 ลำดับและความ immutable

- `sequence` บังคับด้วย `UNIQUE(trace_id, sequence)` ที่ระดับตาราง ไม่ใช่ `len()` ของ list ใน RAM
- trace event **เขียนอย่างเดียว ห้าม UPDATE/DELETE รายแถว** — ลบได้ทางเดียวคือ retention job
- อ่านย้อนเรียงตาม `sequence` เสมอ **ไม่ใช่ `at`** (เวลาซ้ำกันได้ในเหตุการณ์ที่เกิดถี่)

### 9.6 การเข้าถึง

`GET /api/v1/traces/{id}` **ปิดสำหรับ public** เปิดเฉพาะ admin ที่ล็อกอิน
ไม่ใช้ "ต้องรู้ `traceId` ก่อน" เป็นการป้องกัน — เป็น security through obscurity และ `traceId` ถูกส่งกลับใน response ทุกครั้งอยู่แล้ว

---

## 10. หน้า Admin

**ที่มา: [#9](https://github.com/Armboy122/wsc2026/issues/9)**

### 10.1 ขอบเขต

3 หน้า: **รายการ tool** · **ฟอร์มแก้ tool** · **แก้ prompt**
หน้าที่เหลือ (channel profile, domain allowlist, trace viewer) เป็นตารางธรรมดาที่ไม่มีอะไรต้องตัดสินใจ เพิ่มทีหลังได้

### 10.2 form builder ไม่ใช่ textarea JSON

กดเพิ่ม field ทีละตัว (ชื่อ · ชนิด · จำเป็นไหม · คำอธิบาย) แล้วระบบ gen JSON Schema ให้ · JSON เป็น **read-only preview**

§3.2 จำกัด schema เป็น subset ที่แคบมากอยู่แล้ว ⇒ **form builder ครอบคลุมได้เกือบ 100% ของสิ่งที่ระบบยอมรับ**
textarea เปิดให้กรอกสิ่งที่ระบบจะ reject แล้วผู้ใช้ไม่รู้ว่าทำไม

### 10.3 prompt กับ description

- `SYSTEM_PROMPT` (ระดับระบบ) → หน้าของตัวเอง
- `description` ของ tool → อยู่ในฟอร์ม tool นั้น (เพราะเป็นส่วนหนึ่งของ tool definition ที่ LLM เห็น)
- **หน้าแก้ description ต้องแสดงจำนวนตัวอักษร / ประมาณ token** เพราะ description นับเป็น input token ทุก request

### 10.4 ปุ่ม "ลองยิงดู"

กรอก input ตัวอย่างแล้วยิงจริง แสดง request ที่ส่ง (**ซ่อน secret**) + response + เวลา

⚠️ **ต้องผ่านนโยบาย SSRF ของ §7 เหมือนการเรียกปกติทุกประการ — ห้ามเป็นทางลัดที่ข้ามการตรวจ**

ถ้าไม่มีปุ่มนี้ ผู้ใช้ต้องเปิด tool ให้ AI ใช้ก่อนถึงจะรู้ว่ากรอก URL ผิด = **ทดสอบบนผู้ใช้จริง**

### 10.5 draft / publish

แก้แล้วเป็น draft จนกดเผยแพร่ ⇒ ได้ `tool_version` ใหม่ + ปุ่มย้อนกลับเวอร์ชันก่อนหน้า
§9 บังคับให้มี `tool_version` อยู่แล้ว ⇒ แทบไม่มีต้นทุนเพิ่ม และตอบเรื่อง rollback ไปพร้อมกัน

### 10.6 Python plugin ในหน้า admin

อยู่ในรายการเดียวกัน มีป้ายกำกับชนิด และ **ช่องที่แก้ไม่ได้ถูก disable พร้อมข้อความว่าทำไม** ("schema มาจากโค้ด แก้ได้ที่ `plugin.yaml`")
ถ้าซ่อนไป คนจะงงว่าทำไม AI ตอบเรื่องความรู้ได้ทั้งที่ไม่เห็น knowledge tool ในรายการ

### 10.7 auth

`ADMIN_PASSWORD` จาก env + session cookie — **แยกจาก API key ของ public API**
หน้านี้แก้ prompt และสร้าง tool ที่ยิง HTTP ได้ = **ยึดระบบได้ทั้งระบบ** ห้ามปล่อยไม่มี auth
"ระบบภายนอกเรียก API" กับ "มนุษย์ล็อกอินหน้าเว็บ" มีวงจรชีวิตต่างกัน (เพิกถอน/หมุนคีย์คนละแบบ)

### 10.8 สไตล์

HTML/JS ธรรมดาต่อยอด `web/index.html` เดิม **ไม่มี build step ไม่เอา React/Vue**
การเพิ่ม framework แปลว่าต้องมี node/bundler/CI ใหม่ทั้งชุดเพื่อหน้า admin 3 หน้า

---

## 11. Public API

**ที่มา: [#8](https://github.com/Armboy122/wsc2026/issues/8)**

### 11.1 ขอบเขต

| endpoint | สถานะ |
|---|---|
| `POST /api/v1/chat` | ✅ เปิด (ต้องมี API key) |
| `POST /api/v1/actions/{id}/confirm` · `/reject` | ✅ เปิด (ต้องมี API key) |
| `GET /api/v1/traces/{id}` | ❌ **ปิด** → หลัง admin auth |
| `POST /api/v1/reset` | ❌ **ปิด** → หลัง admin auth |
| `GET /health` | ✅ เปิด ไม่ต้องมี key (ต้องไม่บอกรายละเอียดภายใน) |
| `/api/admin/*` | 🔒 กลุ่มใหม่ หลัง admin auth |

`/reset` ที่เปิดสาธารณะ = ใครก็ล้างระบบได้ระหว่างสาธิต

### 11.2 API key

เก็บ **hash** ใน SQLite · แสดงค่าจริงครั้งเดียวตอนสร้าง · เพิกถอนได้จากหน้า admin
`name` ต่อ key ทำให้ตอบได้ว่า "ระบบไหนยิงเข้ามา" ซึ่งจำเป็นตอนต้องถอดใครออก
`tenant_id` ใส่ตั้งแต่ตอนนี้ ทุกแถวเป็น `'default'` ⇒ ขึ้น multi-tenant = เพิ่มค่า ไม่ใช่เพิ่มคอลัมน์

### 11.3 conversation id

**server ออกให้เสมอ** — client ส่ง `conversationId` ที่เคยได้รับกลับมาได้ แต่ต้องเป็น id ที่ผูกกับ key ของตัวเอง
ส่ง id ของคนอื่นมา = **404 ไม่ใช่ 403** (403 เท่ากับยืนยันว่ามีอยู่จริง)

### 11.4 response และ versioning

ใช้ `ChatResponse` เดียวกับ channel อื่น — API เป็น channel ที่ `buttons: false` แล้ว degrade ตาม §5.4
**คง `/api/v1` ไม่ขึ้น v2** เพราะสิ่งที่ V2 เพิ่ม (`simulation`, `actions[]`) เป็นการ **เติม** ไม่ใช่ลบ ⇒ client เก่าไม่พัง

⚠️ สิ่งที่ **จะ** พังคือ endpoint ที่ถูกปิด — เดโมปัจจุบันเรียก `/traces` อยู่ ต้องแก้ฝั่ง web ด้วย (อยู่ในลำดับการย้าย §12)

### 11.5 error contract

```json
{ "error": { "code": "...", "message": "...", "traceId": "..." } }
```

`code` เป็นชุดปิดที่ประกาศไว้ (ใช้ `ToolErrorCode` 6 ค่าที่มีอยู่เป็นฐาน) · `message` เป็นภาษาไทยที่ผู้ใช้อ่านรู้เรื่อง
**ห้ามมี stack trace / ชื่อ tool ภายใน / URL ปลายทาง**

`traceId` ทำให้ระบบภายนอกแจ้งปัญหาแล้ว admin ตามดูได้ **โดยไม่ต้องเห็น trace เอง** — สะพานที่ปลอดภัย

### 11.6 rate limit

ตัวนับใน memory ต่อ API key ต่อนาที (ไม่ต้องมี Redis)
ไม่สมบูรณ์แบบ (รีสตาร์ตแล้วรีเซ็ต) แต่กัน 95% ของกรณีจริง — API key ที่หลุดหนึ่งตัวยิงจนโควตา LLM หมดได้ในไม่กี่นาที = **ค่าใช้จ่ายจริง**
เข้ากับ single process ที่ §8.5 ประกาศไว้

---

## 12. แผนการย้าย

**ที่มา: [#10](https://github.com/Armboy122/wsc2026/issues/10)**

### 12.1 แต่ละ tool ไปชั้นไหน

| tool | ชั้น | เหตุผล |
|---|---|---|
| `knowledge_tool` | **Python plugin** | full-document grounding + citation validation (23KB) เป็นโค้ดจริง |
| `voc_tool` | **Python plugin** | guided flow derive คำถามจาก catalog + จับ pattern ภาษาไทย |
| `oms_tool` | **Python plugin** | มี `clientContext` + prepare/submit |
| `sabuy_tool` | **declarative** | dormant ไม่มีใครใช้ พังก็ไม่กระทบเดโม = เคสทดสอบที่สมบูรณ์แบบ |

⚠️ สิ่งที่เปลี่ยนสำหรับ Python plugin **ไม่ใช่ "ย้ายไป DB"** แต่คือ `plugin.yaml` ใช้ `inputSchema:` JSON Schema แทนชื่อคลาส

### 12.2 ลำดับ

```text
1. sabuy      → พิสูจน์ contract ใหม่ทั้งชุด โดยไม่เสี่ยงอะไรเลย
2. oms        → พิสูจน์ clientContext + write_confirm
3. voc        → พิสูจน์ guided_flow
4. knowledge  → พิสูจน์ grounded_answer (ยากสุด กระทบเดโมมากสุด)
```

เรียงจาก "พังแล้วไม่มีใครเดือดร้อน" ไป "พังแล้วเดโมล่ม" ⇒ ถ้า contract ผิดจะรู้ตั้งแต่ขั้นที่ 1

### 12.3 ช่วงอยู่ร่วมกัน

registry รับทั้งสองแบบพร้อมกันตลอดช่วงย้าย — เก็บค่าคงที่ของ 4 tool เดิมเป็น alias จนย้ายครบแล้วลบ
ย้ายทีเดียวจบแปลว่าเดโมใช้ไม่ได้ระหว่างทาง

### 12.4 สิ่งที่จะเสียไป

1. **`BoundDemoBehavior`** — plugin เสนอ tool call เองตอนเดโม ผูกกับ `ToolName` ตรง ๆ ⇒ แปลงเป็น seed data หรือปิดชั่วคราวแล้วเปิดคืน **ไม่ใช่เหตุผลให้ค้าง enum ไว้ทั้งระบบ**
2. `_SUBMIT_ACTIONS` / `PREPARE_TO_SUBMIT` dict กลาง → data ต่อ tool
3. `VOICE_TOOLS` frozenset → channel profile ใน DB

### 12.5 เกณฑ์ว่าย้ายสำเร็จ

**ทุกขั้นต้องผ่านทั้งสองอย่างก่อนไปขั้นถัดไป**:
```bash
.venv/bin/python -m pytest -q
./scripts/evaluate http://127.0.0.1:8000
```

`evaluate` คือสิ่งเดียวที่พิสูจน์ว่า critical path ยังทำงาน · pytest พิสูจน์ contract

### 12.6 เทสที่ต้องเพิ่ม 3 กลุ่ม

| กลุ่ม | ครอบคลุมอะไร |
|---|---|
| **schema validation** | JSON Schema นอก allowlist = reject ตอน save · `check_schema()` จับ typo |
| **policy enforcement** | `grounded_answer` ไม่มี citation = ปฏิเสธผล · `plain_read` สร้าง pending = ปฏิเสธ · `submit` ที่ไม่ internal = reject |
| **channel mapping** | intent → LINE / Telegram / API · การตัดข้อความ · การ degrade |

นี่คือ 3 จุดที่ V2 จะพังจริง: tool ที่สร้างจาก UI แล้ว schema ไม่ตรง · policy ที่ประกาศแล้วไม่ถูกบังคับ · channel ที่แปล response ผิด
ตรงกับกรอบข้อ 8 (security + สัญญาข้อมูล ไม่เอา TDD เต็มรูปแบบ)

---

## 13. สิ่งที่อยู่นอกขอบเขต V2

| เรื่อง | สถานะ |
|---|---|
| **Multi-tenancy เต็มรูปแบบ** | ตัดออก — ออกแบบให้เติมทีหลังได้ (`tenant_id` ใน `api_key`) แต่ไม่สร้างตอนนี้ |
| **Postgres / infra ระดับ production** | ตัดออก — SQLite พอสำหรับเฟสนี้ |
| **TDD เต็มรูปแบบและเป้า coverage** | ตัดออกอย่างชัดเจน |
| **vector search / RAG** | ตัดออก — `AGENTS.md` ห้าม และ full-document grounding ทำงานได้ |
| **เชื่อมระบบ PEA จริงสำหรับ write** | ตัดออก — ยังต้อง simulated |
| **MCP server / n8n integration** | ตัดออกในเฟสนี้ — ยืมเฉพาะคำศัพท์ `ToolAnnotations` |
| **OAuth / Google Sheets-Docs-Drive** | **นอกขอบเขต V2 แต่เป็นเป้าหมายระยะถัดไป** — `tool_auth.type` ต้องเติม `oauth2` ได้โดยไม่รื้อตาราง |

### หมอกที่ยังเหลือ (ยังตั้งคำถามให้คมไม่ได้)

- **เส้นทางขึ้น multi-tenant** — รู้ว่าจะเติมยังไง แต่ยังไม่ถึงเวลา
- **Deployment / migration runbook** — ย้ายจาก V1 ที่รันอยู่ไป V2 โดยไม่ล้มเดโม

---

## 14. ที่มาของทุกการตัดสินใจ

| ticket | เรื่อง | หมายเหตุ |
|---|---|---|
| [#2](https://github.com/Armboy122/wsc2026/issues/2) | สัญญา Tool v2 | หัวใจของแผนที่ |
| [#3](https://github.com/Armboy122/wsc2026/issues/3) | policy กลางของ Agent | |
| [#4](https://github.com/Armboy122/wsc2026/issues/4) | Channel Adapter | |
| [#5](https://github.com/Armboy122/wsc2026/issues/5) | ค้น: Telegram Bot API | `docs/research/telegram-bot-api.md` |
| [#6](https://github.com/Armboy122/wsc2026/issues/6) | ค้น: declarative HTTP tool | branch `research/declarative-tools` |
| [#7](https://github.com/Armboy122/wsc2026/issues/7) | ชั้นข้อมูล SQLite | |
| [#8](https://github.com/Armboy122/wsc2026/issues/8) | Public API | |
| [#9](https://github.com/Armboy122/wsc2026/issues/9) | ต้นแบบหน้า Admin | |
| [#10](https://github.com/Armboy122/wsc2026/issues/10) | แผนย้าย tool เดิม | |
| [#12](https://github.com/Armboy122/wsc2026/issues/12) | สัญญา trace | |
| [#13](https://github.com/Armboy122/wsc2026/issues/13) | นโยบาย SSRF | ⚠️ เจ้าของแผนที่แก้ข้อเสนอตั้งต้น |
| [#14](https://github.com/Armboy122/wsc2026/issues/14) | ช่องทางเสียง | ⚠️ เจ้าของแผนที่แก้ข้อเสนอตั้งต้น + แก้เพิ่ม 2 ข้อรอบทบทวน |

**ทบทวนยืนยัน**: `docs/v2/decision-review.html` — 64 ข้อยืนยัน / 2 ข้อแก้ไข (14.3 และ 14.6)
