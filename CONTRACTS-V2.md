# PEA One Agent V2 — สัญญาที่ตรึงไว้

> เอกสารนี้ตรึง **สัญญาข้อมูล** ของ V2 · เหตุผลเบื้องหลังอยู่ใน `ARCHITECTURE-V2.md`
> ที่มา: ticket #2–#14 ที่ปิดครบแล้ว 12 ใบ · ทบทวนยืนยัน 2026-09-04
>
> `CONTRACTS.md` (V1) **ยังเป็นความจริงของระบบที่รันอยู่** จนกว่าการย้ายตาม §12 ของ `ARCHITECTURE-V2.md` จะเสร็จ

---

## กฎทั่วไป

1. JSON ทุกจุดเชื่อมต่อภายนอกใช้ **camelCase** · เวลาเป็น **UTC ISO-8601**
2. **ไม่มี field ส่วนเกิน** — `extra="forbid"` ทุก model ที่รับจากภายนอก
3. **ไม่เปิดเผย** credential · API key · access token · payment token · absolute path · hidden prompt · ชื่อ tool ภายในใน error ที่คนนอกเห็น
4. `submit` **ต้องเป็น `internal` เสมอ** ไม่ว่าจะประกาศจากที่ไหน
5. สิ่งที่ **LLM เห็น = public** — secret ห้ามอยู่ใน schema, description, หรือ URL ที่ส่งเข้า LLM
6. การเปลี่ยนสัญญาในเอกสารนี้เป็น **integration-level change** ต้องแก้ `ARCHITECTURE-V2.md` และโค้ดให้สอดคล้องพร้อมกัน

---

## 1. Tool identity

### 1.1 `tool`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `slug` | string | **`^[a-z0-9_-]{1,64}$`** — ตัวระบุที่ส่งเข้า LLM API · เข้มกว่าที่ผู้ให้บริการบังคับโดยตั้งใจ (บังคับตัวพิมพ์เล็ก) |
| `displayName` | string | ชื่อสำหรับมนุษย์ **ภาษาไทยได้** · 1–200 อักขระ · **ไม่เคยส่งเข้า LLM API** |
| `description` | string | คำอธิบายที่ LLM เห็นในแคตตาล็อก · 1–1000 อักขระ · นับเป็น input token ทุก request |
| `enabled` | boolean | ต้องเป็น `true` แบบชัดเจนเท่านั้น ค่าที่กำกวมหรือหายไป = ปิด (fail closed) |
| `source` | `db` / `code` | ใช้แสดงในหน้า admin/health **เท่านั้น** ห้ามใช้ตัดสินใจตอน dispatch |
| `createdAt` | UTC datetime | server กำหนด |

⚠️ ชื่อภาษาไทยใน `slug` จะทำให้ยิง LLM API **ไม่ผ่าน** — จึงบังคับแยก `slug` ออกจาก `displayName`

### 1.2 `toolVersion`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `toolId` | ref | ชี้ `tool` |
| `version` | positive integer | เพิ่มทีละ 1 ต่อการ publish |
| `definitionJson` | object | snapshot ของ definition ทั้งชุด ณ เวลานั้น |
| `createdAt` | UTC datetime | server กำหนด |
| `createdBy` | string | ผู้ publish |

**ลบ tool = soft delete** ห้ามลบแถวทิ้ง เพราะ trace อ้าง `configVersion` กลับมาที่ตารางนี้

### 1.3 `toolOperation`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `action` | string | ตัวระบุ operation ภายใน tool · unique ต่อ tool |
| `description` | string | 1–1000 อักขระ |
| `inputSchema` | object | **JSON Schema subset** ตาม §2 |
| `outputSchema` | object | JSON Schema subset ตาม §2 |
| `exposure` | `llm` / `internal` | `internal` = LLM เรียกไม่ได้ |
| `mode` | `read` / `prepare` / `submit` | บทบาทใน write state machine |
| `submitAction` | string/null | **required** เมื่อ `mode: prepare` · **ต้องเป็น null** เมื่อ mode อื่น |
| `policy` | enum 4 ค่า | ตาม §3 |
| `limits` | object/null | ตาม §3.3 |
| `clientContext` | object/null | ตาม §3.4 |
| `voiceConfirm` | boolean | **default `true`** ตาม §5.2 |
| `httpMethod` | `GET`/`POST`/`PUT`/`PATCH`/`DELETE` / null | **required** เมื่อ `source: db` และ `mode != prepare` · **ต้องเป็น null** เมื่อ `source: code` หรือ `mode: prepare` |
| `urlTemplate` | string/null | **required** เมื่อ `source: db` และ `mode != prepare` · **ต้องเป็น null** เมื่อ `mode: prepare` · placeholder `{fieldName}` ดึงจาก `input` — กลไก "LLM เติมค่า" เดียวที่ระบบรับ ดู ARCHITECTURE-V2.md §3.4.1 |

⚠️ **เติมใน D2.6**: ฉบับก่อนหน้าตารางนี้มีแค่ policy/mode/schema แต่ไม่เคยระบุว่า declarative
tool รู้ URL/method ปลายทางจากไหน — ค้นพบตอนสร้าง declarative tool ตัวแรกที่ยิง REST จริง
(TASKS-3DAYS.md D2.6) `httpMethod`+`urlTemplate` คือฟิลด์ที่เติมเพื่อปิดช่องนี้

⚠️ **แก้ไขใน D2.7**: ตารางเดิมบังคับ `httpMethod`/`urlTemplate` ให้ไม่เป็น null ทุก operation
ของ `source: db` โดยไม่แยกตาม `mode` — ค้นพบตอนย้าย `oms_tool` ขึ้น contract นี้ว่า
`mode: prepare` ของ `write_confirm` **ต้องไม่มี side effect จริงตามสัญญา** (§3.1) จึงไม่ยิง
HTTP เลย (เก็บ payload รอ `submit` ในหน่วยความจำของ tool แทน เหมือนที่ Python plugin เดิม
ทำกับ draft ภายใน process) มีแต่ `mode: submit` เท่านั้นที่ยิงจริงและต้องมีทั้งสองฟิลด์เสมอ

---

## 2. JSON Schema subset ที่ระบบยอมรับ

**นี่คือ allowlist — สิ่งที่ไม่อยู่ในรายการ "รับ" จะถูก reject ตอน save**

### 2.1 รับ

| กลุ่ม | รายละเอียด |
|---|---|
| root | `type: object` **เท่านั้น** |
| type | `string` · `number` · `integer` · `boolean` · `null` · `object` · `array` |
| ค่า | `enum` (primitive เท่านั้น) · `const` |
| โครงสร้าง | `anyOf` · `$defs` / `$ref` **ภายในไฟล์เดียวกันเท่านั้น** |
| array | `items` · `minItems` **เฉพาะค่า 0 หรือ 1** |
| อื่น | `required` · `description` · `default` |
| บังคับ | **`additionalProperties: false` ทุก object** |
| ความลึก | **ไม่เกิน 5 ชั้น** |

### 2.2 ปฏิเสธ (reject ตอน save พร้อมข้อความบอกว่าผิดตรงไหน)

`oneOf` · `not` · `if`/`then`/`else` · `patternProperties` · `dependentRequired` · `unevaluatedProperties` · `contains` · `uniqueItems` · `pattern` · `minimum` · `maximum` · `exclusiveMinimum` · `exclusiveMaximum` · `multipleOf` · `minLength` · `maxLength` · `$ref` ภายนอก · recursive schema · `additionalProperties` ที่ไม่ใช่ `false`

### 2.3 การ validate

| จังหวะ | ทำอะไร |
|---|---|
| **save** | `jsonschema.Draft202012Validator.check_schema()` + ตรวจ allowlist §2.1 + ตรวจ reject list §2.2 · **ผิด = ไม่ persist** |
| **execute** | validate `input` ด้วย `jsonschema` ก่อนเรียก executor เสมอ |

- ใช้ **`jsonschema` library เท่านั้น** — ห้ามสร้าง Pydantic model จาก JSON Schema ตอน runtime (ทำไม่ได้จริง และ constraint หายเงียบ)
- ต้องติดตั้ง **`jsonschema[format]`** ไม่งั้น `format` ไม่ validate อะไรเลยและไม่มี error
- constraint ที่ถูก reject (`pattern`, `minimum`) ที่จำเป็นจริง ให้ตรวจในชั้น business validation ของ executor

---

## 3. Policy

### 3.1 ค่าที่ยอมรับ (4 ค่า ห้ามเพิ่ม)

| policy | รับประกัน |
|---|---|
| `grounded_answer` | ผลต้องมี `citations` ที่ไม่ว่าง มิฉะนั้น**ปฏิเสธผล**และแทนด้วยข้อความ escalation |
| `write_confirm` | `prepare → confirm → submit` · `submit` ต้อง `exposure: internal` · ผล prepare หยุด agent loop |
| `guided_flow` | tool รับ turn แทน planner ชั่วคราว · คืน `choicePrompt` ที่มี `promptId` |
| `plain_read` | ไม่มี side effect · executor **ห้ามสร้าง pending action** |

### 3.2 default

operation ที่ไม่ประกาศ `policy` → `plain_read` **และถูกบังคับเป็น `exposure: internal`**
⇒ ระบบเห็น แต่ LLM เรียกไม่ได้จนกว่าจะประกาศชัด · หน้า admin ต้องแสดงสถานะนี้ ห้ามเงียบ

### 3.3 `limits`

| ฟิลด์ | ชนิด | default |
|---|---|---|
| `maxCallsPerTurn` | positive integer / null | ไม่จำกัด |
| `dedupeIdenticalInput` | boolean | `true` สำหรับ `plain_read` / `grounded_answer` · **`false` สำหรับ `write_confirm`** |

### 3.4 `clientContext`

map จาก **ชื่อ context ที่ระบบรู้จัก** → **ชื่อ field ใน `input`**

```yaml
clientContext:
  lat: lat
  lon: lon
```

- ชุด context เป็น **enum ปิด** — ปัจจุบัน `lat`, `lon` เท่านั้น · อ้างค่านอกรายการ = reject ตอน save
- agent เติมด้วย `setdefault` **ไม่ทับค่าที่ LLM ใส่มาเอง**
- agent เติมตามใบสั่งโดยไม่รู้ว่าเป็น tool ตัวไหน

### 3.5 การตรวจสอบข้าม (policy ที่ประกาศเอง = untrusted)

**ตอน save / startup — ผิด = reject**

| เงื่อนไข | ผล |
|---|---|
| มี `submitAction` แต่ `policy != write_confirm` | reject |
| `mode: submit` แต่ `exposure != internal` | reject |
| `policy: write_confirm` แต่ไม่มีคู่ prepare→submit | reject |
| `clientContext` อ้าง context นอก enum ปิด | reject |
| `mode: prepare` แต่ไม่มี `submitAction` | reject |
| `mode != prepare` แต่มี `submitAction` | reject |
| `source: db` และ `mode != prepare` แต่ `httpMethod`/`urlTemplate` เป็น null | reject |
| `source: db` และ `mode: prepare` แต่ `httpMethod`/`urlTemplate` ไม่เป็น null | reject |

**ตอน runtime — ผิด = ปฏิเสธผล (ไม่ใช่แค่เตือน) และบันทึก `POLICY_REJECTED`**

| เงื่อนไข | ผล |
|---|---|
| `grounded_answer` แต่ผลไม่มี `citations` | แทนด้วยข้อความ escalation ไม่ส่งเป็นคำตอบ |
| `plain_read` แต่ executor สร้าง pending action | ปฏิเสธผล บันทึกเป็น error |
| `submit` ถูกเรียกโดยไม่มี pending action ที่ยืนยันแล้ว | ปฏิเสธ |
| `action` ไม่ได้อยู่ใน tool ที่ระบุ | ปฏิเสธ (ตรวจกับ registry ตอน dispatch แทน enum เดิม) |

---

## 4. Tool call และ result

### 4.1 `ToolCall`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `callId` | UUID | สร้างโดย runtime |
| `toolSlug` | string | **string ไม่ใช่ enum** · ต้องมีอยู่ใน registry |
| `action` | string | **string ไม่ใช่ enum** · ต้องเป็นของ tool นั้น |
| `input` | object | ผ่าน `inputSchema` แล้ว · **ค่าทุกฟิลด์ต้องเป็นชนิด JSON ล้วน** (str/int/float/bool/null/object/array) ห้ามมี `UUID` หรือ Python object อื่นหลงเหลือ |

⚠️ **เติมใน D2.7**: ตอนสร้าง `ToolCall` ของ `submit_*` จาก `pendingActionId`/`idempotencyKey`
ภายใน (`SubmitPreparedActionInput(...).model_dump(...)`) ต้องเรียกด้วย `mode="json"` เสมอ —
ไม่งั้น `pendingActionId` เหลือเป็น `uuid.UUID` แทนที่จะเป็น string ปลั๊กอิน Python เดิม
รอดมาตลอดเพราะ validate ด้วย Pydantic model ก่อนใช้งานเสมอ (Pydantic ยอมรับ `UUID` object
สำหรับ field ชนิด `UUID`) แต่ declarative tool ตรวจ `input` กับ `jsonschema` ตรง ๆ ซึ่งถือว่า
`UUID` object ไม่ใช่ `string` ที่ถูกต้อง — พบตอนย้าย `oms_tool` ขึ้น contract นี้ (`prepare_anonymous_outage`
สำเร็จแต่ `submit_anonymous_outage` ปฏิเสธด้วย `invalid_input` เสมอ)

### 4.2 `ToolResult`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `callId` | UUID | เท่ากับ call ต้นทาง |
| `toolSlug` · `action` | string | เท่ากับ call ต้นทาง |
| `status` | `success` / `error` | สถานะสิ้นสุด |
| `data` | object/null | ผ่าน `outputSchema` เมื่อสำเร็จ |
| `error` | `ToolError`/null | มีเมื่อ error |
| `citations` | `Citation[]` | **ต้องไม่ว่างเมื่อ `policy: grounded_answer` และ status success** |
| `simulation` | boolean | `true` เมื่อผลมาจากระบบจำลอง |

`ToolError.code` เป็นชุดปิด: `invalid_input` · `not_found` · `unavailable` · `conflict` · `confirmation_required` · `internal`
`ToolError.message` ปลอดภัยสำหรับผู้ใช้ สูงสุด 500 อักขระ **ห้ามมี stack trace / URL ปลายทาง / ชื่อ header**

⚠️ **เติมใน D2.7**: declarative tool (source: db) แปล HTTP status code ของปลายทางเป็น
`ToolError.code` ตามธรรมเนียม REST ทั่วไปนี้เสมอ (ไม่ผูกกับ tool ใดตัวหนึ่ง — ข้อความยัง
เป็นข้อความกลางที่ไม่รั่วรายละเอียดปลายทาง response policy ของแต่ละ tool เป็นผู้แปลงเป็น
ข้อความเฉพาะให้ผู้ใช้เห็นอีกชั้นหนึ่งจาก `code` นี้):

| HTTP status | `ToolError.code` |
|---|---|
| 400 | `invalid_input` |
| 404 | `not_found` |
| 409 | `conflict` |
| อื่นทั้งหมด (รวม 5xx, เครือข่าย/นโยบายล้มเหลว) | `unavailable` |

### 4.3 `Citation` — ไม่เปลี่ยนจาก V1

`sourceId` · `title` · `uri` (logical URI ห้ามเปิดเผย absolute path) · `snippet` (≤1000) · `page` (positive/null)

---

## 5. Channel

### 5.1 `ChatResponse` (intent-level response ที่ทุก channel ใช้ร่วมกัน)

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `conversationId` | UUID | server ออกให้เสมอ |
| `traceId` | UUID | อ้างถึง trace ของคำขอนี้ |
| `message` | string | ข้อความเต็ม **agent ไม่ตัด** — adapter ตัดตาม §5.3 |
| `citations` | `Citation[]` | ส่งครบเสมอ adapter ตัดสินว่าจะแสดงยังไง |
| `pendingAction` | `PendingAction`/null | เมื่อมีรายการรอยืนยัน |
| `choicePrompt` | `ChoicePrompt`/null | เมื่อ `guided_flow` ถามคำถาม |
| `toolResults` | `ToolResult[]` | |
| **`simulation`** | boolean | 🆕 **ทุก channel ต้องแสดงคำเตือนเมื่อเป็น `true`** ห้าม hardcode ในไฟล์ของ channel ใด channel หนึ่ง |
| **`actions`** | `Action[]` | 🆕 ตาม §5.2 |

### 5.2 `Action`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `label` | string | ข้อความบนปุ่ม |
| `value` | string | ค่าที่ส่งกลับ ≤64 อักขระ (พอดีกับ `callback_data` 64 bytes ของ Telegram) |
| `kind` | `confirm` / `reject` / `pick` / `link` | |
| `singleUse` | boolean | `true` = ปุ่มควรหาย/ถูกปิดหลังกด |

การแปลของแต่ละ channel:

| channel | `singleUse: true` แปลว่า |
|---|---|
| Telegram | `editMessageReplyMarkup` ลบ/ปิดปุ่มหลังกด |
| LINE | ส่งข้อความใหม่แทน (แก้ bubble เดิมไม่ได้) |
| Web | disable ปุ่มฝั่ง client |
| Public API | คืนค่าใน JSON ให้ client จัดการเอง |

⚠️ `singleUse` เป็น **UI hint เท่านั้น** — การกันกดซ้ำจริงต้องพึ่ง idempotency ฝั่ง server เพราะมี race

### 5.3 `pendingAction` กับ `choicePrompt` แยกกัน

| | `pendingAction` | `choicePrompt` |
|---|---|---|
| side effect | มี | ไม่มี |
| การรับประกัน | state machine · idempotency · terminal rejection | `promptId` กันตอบผิดขั้น |
| policy | `write_confirm` | `guided_flow` |

**ห้ามยุบรวม** แต่ **บังคับให้มี helper กลางตัวเดียว** ที่แปลงทั้งคู่เป็น `Action[]`

### 5.4 capability ของ adapter

| ฟิลด์ | ชนิด |
|---|---|
| `buttons` | boolean |
| `editableMessage` | boolean |
| `richLayout` | boolean |
| `maxTextLength` | integer/null |
| `maxButtons` | integer/null |

**agent ไม่เคยอ่าน capability — adapter อ่านของตัวเองเพื่อ degrade**

ค่าที่ตรึงไว้:

| channel | buttons | editable | maxTextLength | maxButtons |
|---|---|---|---|---|
| Web | ✅ | ✅ | ไม่จำกัด | ไม่จำกัด |
| LINE | ✅ | ❌ | 1900 | 13 |
| Telegram | ✅ | ✅ | 4096 | ตามข้อจำกัด inline keyboard |
| Voice | ❌ | ❌ | — | — |
| Public API | ❌ | ❌ | ไม่จำกัด | — |

### 5.5 สัญญาการตัดข้อความ (ใช้ร่วมกันทุก adapter)

1. ตัดที่ **ขอบเขตคำหรือบรรทัด** ห้ามตัดกลางประโยค
2. ต้องมี **ตัวบ่งชี้ว่ายังมีต่อ**
3. **ห้ามตัดจน citation หรือข้อความยืนยันหาย** — ส่วนเหล่านี้ส่งเป็นข้อความแยกเสมอ
4. การตัดต้องบันทึก `RESPONSE_DEGRADED`

---

## 6. ช่องทางเสียง

### 6.1 `voiceConfirm`

| ค่า | ความหมาย |
|---|---|
| `true` (**default**) | ยืนยันด้วยเสียงได้ |
| `false` | ต้องยืนยันช่องทางอื่น → ตกไปที่ handoff |

ติดธง `false` เฉพาะ operation ที่เกี่ยวกับ **เงิน** หรือ **ข้อมูลส่วนบุคคลที่เปิดเผยไม่ได้ทางเสียง**

### 6.2 flow การยืนยันด้วยเสียง

```text
prepare_* → read-back (อ่านทวนทุก field ที่จะบันทึก) → รอคำพูด
   ├─ คำยืนยัน   → submit_*
   ├─ คำปฏิเสธ   → เข้าโหมดแก้ไข (§6.4)
   └─ ไม่ตรงเลย  → ถามซ้ำ (มีเพดาน เกินแล้วยกเลิก)
```

`write_confirm` **ไม่ถูกยกเว้น** — เปลี่ยนแค่รูปของ "confirm"

### 6.3 การจับคำ

| ชุด | คำ |
|---|---|
| ยืนยัน | `ยืนยัน` · `ตกลง` · `ใช่` (+`ครับ`/`ค่ะ`) · `ถูกต้อง` · `เอาเลย` |
| ปฏิเสธ | `ยกเลิก` · `ไม่ใช่` · `ไม่เอา` · `ผิด` · `แก้ไข` |

**บังคับ**:
- **จับคู่แบบกำหนดตายตัว ห้าม LLM ตีความ** (LLM ตีความ = LLM เป็นคนกด submit)
- **ตรวจชุดปฏิเสธก่อนชุดยืนยันเสมอ** ไม่งั้น "ไม่ใช่ครับ" ถูกนับเป็นยืนยัน
- ไม่ตรงทั้งสองชุด = ถามซ้ำ ห้ามเดา

### 6.4 คำปฏิเสธ = เข้าโหมดแก้ไข

```text
คำปฏิเสธ → ถาม "ต้องการแก้ส่วนไหน" + อ่านรายการช่องที่แก้ได้
   → ผู้ใช้ระบุช่อง หรือพูดว่า "ทั้งหมด"
   → เก็บค่าใหม่ → prepare ใหม่ → read-back ใหม่ → รอยืนยันอีกครั้ง
```

⚠️ **terminal rejection ยังคง terminal** — การแก้ไขคือ **สร้าง pending action ใหม่** ห้ามปลุก action เดิม
รายการช่องที่แก้ได้มาจาก `inputSchema` ของ operation **ไม่ใช่ให้ LLM คิดเอง**
มี **เพดานรอบการแก้ไข** ต่อหนึ่งรายการ เกินแล้วต้องเสนอทางอื่น

### 6.5 citation ในช่องทางเสียง

| ชั้น | พฤติกรรม |
|---|---|
| การบังคับใช้ `grounded_answer` ฝั่ง server | **ไม่เปลี่ยน** — ผลไม่มี citation ยังถูกปฏิเสธ |
| การนำเสนอทางเสียง | **ไม่พูดอ้างอิงเลย** |
| trace | **บันทึก citation ครบ** + `RESPONSE_DEGRADED` ระบุว่าถูกตัดเพราะเป็นช่องทางเสียง |

ผู้ใช้ขอแหล่งอ้างอิง → ส่งเป็นข้อความพร้อมลิงก์ผ่าน handoff

### 6.6 หลักฐานการยืนยันด้วยเสียง

บันทึกใน `ACTION_CONFIRMED`: **ข้อความ read-back ที่พูดออกไป** + **ข้อความถอดเสียงคำยืนยัน** + เวลา
**ไม่เก็บไฟล์เสียง**

---

## 7. เครือข่ายขาออก

### 7.1 โหมด

| `APP_ENV` | โดเมน | IP ภายใน | HTTP |
|---|---|---|---|
| development | ทุกโดเมน | อนุญาต | อนุญาต |
| production | เฉพาะใน `domain_allowlist` | **บล็อก** | **บล็อก** |

**โหมดมาจาก `APP_ENV` เท่านั้น** — หน้า admin เพิ่ม/ลบโดเมนได้ **แต่ปิดโหมดไม่ได้**

### 7.2 blocklist (production)

`10.0.0.0/8` · `172.16.0.0/12` · `192.168.0.0/16` · `127.0.0.0/8` · **`169.254.0.0/16`** · `fc00::/7` · `fe80::/10`

ตรวจด้วย `ipaddress` ใน stdlib **ห้ามเขียน parser IP เอง**

### 7.3 การตรวจ

| จังหวะ | ตรวจ |
|---|---|
| save | โดเมนอยู่ใน allowlist · HTTPS · รูปแบบ URL · ไม่มี credential ใน URL |
| execute | **resolve DNS แล้วเทียบ IP ทุกครั้งก่อนยิง** (กัน DNS rebinding) |

### 7.4 เพดาน

| ค่า | default | admin ตั้งได้ | เพดานแข็ง |
|---|---|---|---|
| timeout | 5 s | ✅ | 30 s |
| response size | 1 MB | ✅ | 10 MB |
| retry | **0** | ❌ | — |
| redirect | **ไม่ตาม** (`follow_redirects=False`) | ❌ | — |

3xx = ถือว่า config ผิด แจ้ง admin ให้แก้ URL

### 7.5 เมื่อถูกบล็อก

บันทึก `POLICY_REJECTED` พร้อมเหตุผลที่อ่านเข้าใจ: `โดเมนไม่อยู่ใน allowlist` · `ปลายทางเป็น IP ภายใน` · `ไม่ใช่ HTTPS` · `พบ redirect` · `เกินขนาด response`

---

## 8. Trace

### 8.1 `TraceEvent`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `eventId` | UUID | server สร้าง |
| `traceId` | UUID | trace ของคำขอ |
| `sequence` | positive integer | **`UNIQUE(traceId, sequence)` ที่ระดับตาราง** |
| `at` | UTC datetime | server กำหนด |
| `kind` | enum | §8.2 |
| `toolSlug` | string/null | 🆕 |
| `action` | string/null | 🆕 |
| `configVersion` | integer/null | 🆕 join กลับที่ `toolVersion` |
| `policy` | string/null | 🆕 |
| `channel` | enum/null | 🆕 `web`/`line`/`telegram`/`voice`/`api` |
| `data` | object | redact แล้ว **สูงสุด 20 key** |

### 8.2 `TraceEventKind`

**เดิม**: `chat_received` · `llm_requested` · `llm_responded` · `tool_called` · `tool_result` · `action_prepared` · `action_confirmed` · `action_rejected` · `action_submitted` · `error`

**เพิ่ม**: `policy_rejected` · `response_degraded` · `tool_disabled`

### 8.3 สิ่งที่บันทึกจาก HTTP call ของ declarative tool

| เก็บ | ไม่เก็บ |
|---|---|
| method · host · path · status · ระยะเวลา · ขนาด response | **query string** · header · request body · response body |

query string อันตรายเป็นพิเศษเพราะ API key มักอยู่ตรงนั้น

### 8.4 immutability และ retention

- **เขียนอย่างเดียว ห้าม UPDATE / DELETE รายแถว** — ลบได้ทางเดียวคือ retention job
- อ่านย้อนเรียงตาม **`sequence`** ไม่ใช่ `at`
- `redact()` ทำงาน **ตอนเขียน** ข้อมูลอ่อนไหวไม่แตะดิสก์

| ประเภท | อายุ |
|---|---|
| ทั่วไป | 90 วัน |
| มี `action_submitted` สำเร็จ | **ถาวร** |
| มี `action_rejected` | **ถาวร** |

---

## 9. HTTP interface

### 9.1 endpoint

| endpoint | auth | หมายเหตุ |
|---|---|---|
| `POST /api/v1/chat` | API key | |
| `POST /api/v1/actions/{id}/confirm` | API key | |
| `POST /api/v1/actions/{id}/reject` | API key | |
| `GET /health` | — | ห้ามบอกรายละเอียดภายใน |
| `GET /api/v1/traces/{id}` | **admin session** | ⚠️ เปลี่ยนจาก V1 ที่เปิดสาธารณะ |
| `POST /api/v1/reset` | **admin session** | ⚠️ เปลี่ยนจาก V1 |
| `/api/admin/*` | admin session | กลุ่มใหม่ |
| `POST /webhook/line` | LINE signature | ไม่เปลี่ยน |
| `POST /webhook/telegram` | `X-Telegram-Bot-Api-Secret-Token` | 🆕 |
| `WS /ws/live` | ตามเดิม | |

**คง `/api/v1` ไม่ขึ้น `/api/v2`** — V2 เติมฟิลด์ ไม่ลบฟิลด์ ⇒ client เก่าไม่พัง

### 9.2 auth

| ประเภท | กลไก |
|---|---|
| Public API | API key ใน header · เก็บ **hash** ใน SQLite · แสดงค่าจริงครั้งเดียวตอนสร้าง · เพิกถอนได้ |
| Admin | `ADMIN_PASSWORD` จาก env + session cookie |
| Telegram webhook | `secret_token` เทียบด้วย `compare_digest` ⚠️ **ไม่ผูก body** (อ่อนกว่า LINE) |
| LINE webhook | HMAC-SHA256 ผูก body (ไม่เปลี่ยน) |

**แยก admin auth ออกจาก API key** เพราะวงจรชีวิตต่างกัน

### 9.3 conversation ownership

server ออก `conversationId` เสมอ · client ส่งกลับได้เฉพาะ id ที่ผูกกับ key ของตัวเอง
ส่ง id ของ key อื่น → **404 ไม่ใช่ 403** (403 ยืนยันว่ามีอยู่จริง)

### 9.4 error contract

```json
{ "error": { "code": "...", "message": "...", "traceId": "..." } }
```

`code` เป็นชุดปิด (ฐานคือ `ToolErrorCode` 6 ค่า) · `message` ภาษาไทยที่ผู้ใช้อ่านรู้เรื่อง
**ห้ามมี**: stack trace · ชื่อ tool ภายใน · URL ปลายทาง · ชื่อ header · ค่า config

### 9.5 rate limit

ตัวนับใน memory ต่อ API key ต่อนาที · เกิน = `429` พร้อม error contract §9.4

---

## 10. Storage

### 10.1 ตาราง

```sql
tool(slug, display_name, description, enabled, source, created_at)
tool_version(tool_id, version, definition_json, created_at, created_by)
tool_operation(tool_id, action, policy, input_schema, output_schema,
               exposure, mode, submit_action, limits, client_context, voice_confirm)
tool_auth(tool_id, type, secret_ref)
prompt(key, content, version, updated_at)
channel_profile(channel, allowed_tool_slugs)
domain_allowlist(domain, enabled, added_by)
api_key(id, name, key_hash, tenant_id, created_at, revoked_at)
pending_action(id, conversation_id, status, summary, payload, trace_id, ...)
trace_event(trace_id, sequence, at, kind, tool_slug, action,
            config_version, policy, channel, data)
            UNIQUE(trace_id, sequence)
```

### 10.2 secret

| `tool_auth.type` | `secret_ref` เก็บอะไร |
|---|---|
| `api_key` | **ชื่อ env var** — ค่าจริงอยู่นอก DB |
| `oauth2` | token ที่เข้ารหัสด้วยคีย์จาก env (**V2 ยังไม่ทำ** แต่คอลัมน์รองรับแล้ว) |

**`secret_ref` ห้ามปรากฏใน**: schema · description · trace · error · response

Admin tool update auth semantics: omitted `authEnvVar` preserves the existing credential reference; a string replaces it; explicit `null` removes it. Tool list/get responses expose only boolean `hasAuth`, never the env var name.

### 10.3 การเข้าถึง

- `sqlite3` stdlib + `asyncio.to_thread`
- **WAL mode · connection เดียวต่อ process · เขียนผ่าน lock เดียว**
- **ประกาศชัดว่ารองรับ single process เท่านั้น**
- migration = raw SQL + ตาราง `schema_version` รันตามลำดับตอน startup

### 10.4 hot-reload

cache ในหน่วยความจำ + invalidate เมื่อ `config_version` เปลี่ยน
⚠️ **หนึ่งเทิร์นใช้ config version เดียวตลอด** — ห้ามเปลี่ยนกลางบทสนทนา

### 10.5 `/reset`

ล้าง: conversation history · pending action ที่ยังไม่ terminal
**ไม่แตะ**: trace · tool config · prompt · api key · domain allowlist

### 10.6 conversation history

**อยู่ใน RAM ไม่ลง DB** ตามที่ล็อกไว้

---

## 11. `PendingAction` (ปรับจาก V1)

| ฟิลด์ | เปลี่ยนจาก V1 |
|---|---|
| `toolName` → **`toolSlug`** | enum → string |
| `prepareAction` · `submitAction` | enum → string |
| ที่เหลือ | ไม่เปลี่ยน |

**กฎที่ไม่เปลี่ยน**:
- `preparedInput` เปิดเผยเฉพาะฟิลด์ที่ผู้ใช้ระบุเอง · `idempotencyKey` เป็น `[redacted]` เสมอ · ไม่เก็บ payment token
- state machine: `pending_confirmation` → `confirmed` → `submitted` / `rejected` / `failed`
- **terminal rejection เป็น terminal ถาวร** — การแก้ไขคือสร้าง action ใหม่
- idempotency กันการส่งซ้ำ

---

## 12. สิ่งที่ไม่ใช่เป้าหมายของ V2

- multi-tenancy เต็มรูปแบบ (แต่ `api_key.tenant_id` เตรียมไว้แล้ว)
- Postgres หรือ infra ระดับ production
- TDD เต็มรูปแบบ / เป้า coverage
- vector search / RAG / chunk retrieval
- การเชื่อมระบบ PEA จริงสำหรับ write
- MCP server / n8n integration
- **OAuth (Google Sheets/Docs/Drive)** — เป้าหมายระยะถัดไป `tool_auth.type` ต้องเติม `oauth2` ได้โดยไม่รื้อตาราง
