# PEA One Agent — สัญญาที่ตรึงไว้ (v1)

สัญญาเหล่านี้เป็นข้อกำหนดอ้างอิงสูงสุดสำหรับการผสานระบบในงานแฮกกาธอน นิยาม Pydantic v2 ที่สอดคล้องกันอยู่ใน `app/contracts.py` การเปลี่ยนแปลงต้องได้รับอนุมัติจากผู้รับผิดชอบหลักและดำเนินการผ่านการย้ายเวอร์ชัน ผู้ปฏิบัติงานต้องไม่เพิ่มฟิลด์โดยพลการ (`extra="forbid"`) ตัวระบุทั้งหมดเป็นสตริง UUID แบบ opaque เว้นแต่จะระบุไว้เป็นอย่างอื่น การประทับเวลาเป็นสตริง UTC ตาม RFC 3339

## กฎทั่วไป

- ฟิลด์ JSON ใช้ `camelCase` ที่รอยต่อของ HTTP และ tool/LLM ส่วนโมเดล Python ใช้ `snake_case` พร้อม alias ของ Pydantic
- เพย์โหลดสำหรับการเขียนทั้งหมดที่ไคลเอนต์ส่งมาต้องมี `idempotencyKey` ที่ไม่ว่าง (สูงสุด 128 อักขระ)
- ผลลัพธ์ Sabuy, VOC และ OMS ทุกรายการต้องมี `simulation` และมีค่าเป็น `true`
- การเรียกเครื่องมือมี `callId` ที่ระบบสร้างขึ้น โดยเครื่องมือไม่รับ call id ที่ไคลเอนต์เป็นผู้กำหนด
- `ToolResult.status` เป็น `success` หรือ `error` โดยข้อผิดพลาดต้องมีชนิดชัดเจน ปลอดภัยสำหรับผู้ใช้ และต้องไม่มีข้อมูลรับรอง
- `Citation` ปรากฏเฉพาะในการสืบค้นองค์ความรู้ ข้อเท็จจริงจำลองจะไม่แสดงในรูปแบบการอ้างอิง
- ข้อมูลอินพุต/เอาต์พุตของเครื่องมือจะได้รับการตรวจสอบด้วยโมเดลเฉพาะแอ็กชันด้านล่างเพิ่มเติมจาก envelope ที่ตรึงไว้

## อินเทอร์เฟซ HTTP สาธารณะ

### `POST /api/v1/chat`

คำขอ (`ChatRequest`):

```json
{
  "conversationId": "optional UUID; server creates one when omitted",
  "message": "required non-empty text, max 4000 characters",
  "requestId": "optional UUID for client correlation"
}
```

การตอบกลับ (`ChatResponse`):

```json
{
  "conversationId": "UUID",
  "traceId": "UUID",
  "message": "assistant text",
  "citations": [],
  "pendingAction": null,
  "toolResults": []
}
```

`pendingAction` จะไม่เป็น null เฉพาะหลังจากแอ็กชันเครื่องมือแบบ `prepare_*` สำเร็จเท่านั้น การสนทนาจะไม่ส่งคำสั่งเขียน

### `POST /api/v1/actions/{pending_action_id}/confirm`

คำขอ (`ConfirmActionRequest`):

```json
{ "confirmationNote": "optional text, max 500 characters" }
```

การตอบกลับ (`ActionDecisionResponse`):

```json
{
  "pendingAction": { "...": "PendingAction" },
  "toolResult": { "...": "ToolResult or null when submit failed before a result" },
  "traceId": "UUID"
}
```

เส้นทางนี้ส่งแอ็กชันภายในแบบ `submit_*` ที่สอดคล้องกันหนึ่งครั้ง การยืนยันซ้ำจะคืนการตอบกลับเดิมที่เสร็จสมบูรณ์แล้ว โดยไม่ก่อให้เกิดผลกับระบบเบื้องหลังเป็นครั้งที่สอง การยืนยันแอ็กชันที่ถูกปฏิเสธจะคืนค่า 409

### `POST /api/v1/actions/{pending_action_id}/reject`

คำขอ (`RejectActionRequest`):

```json
{ "reason": "required non-empty text, max 500 characters" }
```

การตอบกลับใช้ `ActionDecisionResponse` โดยมี `pendingAction.status = "rejected"` และ `toolResult = null` การปฏิเสธซ้ำจะคืนผลลัพธ์สถานะสิ้นสุดเดิม การปฏิเสธแอ็กชันที่ได้รับการยืนยัน/ส่งแล้วจะคืนค่า 409

### `GET /api/v1/traces/{trace_id}`

คืนค่า `TraceResponse`:

```json
{ "traceId": "UUID", "events": [] }
```

เหตุการณ์เรียงตามลำดับเวลาโดย `sequence` ข้อความคำขอและฟิลด์เพย์โหลดที่ทำเครื่องหมายว่าเป็นข้อมูลละเอียดอ่อนจะถูกปกปิดก่อนจัดเก็บ

### `POST /api/v1/reset`

คืนค่า `ResetResponse`:

```json
{ "reset": true }
```

ล้าง conversation ทั้งหมดใน process, pending action, สถานะ backend จำลอง และข้อมูล trace endpoint นี้ใช้สำหรับสภาพแวดล้อมสาธิตที่มีการจัดการเท่านั้น

### `GET /health`

คืนค่า `HealthResponse`:

```json
{
  "status": "ok",
  "llmAdapter": "ready",
  "knowledgeBackend": "ready",
  "simulationMode": true
}
```

ห้ามเปิดเผย credential, URL ของ endpoint, หมายเลขบัญชี หรือข้อมูลลูกค้า

## โมเดลโดเมนที่ตรึงไว้

### `Citation`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `sourceId` | string | พาธสัมพัทธ์หรือรหัสคงที่ของไฟล์ที่ Document Router เลือกจาก `knowledge/source/` |
| `title` | string | ชื่อไฟล์หรือชื่อเอกสารจริงที่ไม่ว่าง |
| `uri` | string | logical URI ที่ไม่เปิดเผย absolute path เช่น `knowledge://source/<encoded-relative-path>` และต้องไม่ว่าง |
| `snippet` | string | ข้อความหลักฐานจากไฟล์ฉบับเต็มที่ใช้ตอบและตรวจสอบได้ว่าอยู่ในไฟล์นั้น สูงสุด 1,000 อักขระ |
| `page` | integer/null | ต้องเป็นค่าบวกเมื่อระบุ |

### `ToolCall`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `callId` | UUID | สร้างโดย agent/runtime |
| `name` | enum | ต้องเป็นหนึ่งในชื่อ tool ระดับบนสุดทั้งสี่รายการเท่านั้น |
| `action` | enum | หนึ่งใน action ที่อยู่ในตารางด้านล่าง |
| `input` | object | schema ที่ตรึงไว้และเฉพาะเจาะจงตาม action |

Tool จะปฏิเสธการเรียกที่ `name` ไม่ได้เป็นเจ้าของ `action` ที่ระบุ

### `ToolResult`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `callId` | UUID | เท่ากับ call ต้นทาง |
| `name` | `ToolName` | เท่ากับ call ต้นทาง |
| `action` | `ToolAction` | เท่ากับ call ต้นทาง |
| `status` | `success` / `error` | ผลลัพธ์สถานะสิ้นสุดของ tool |
| `data` | object/null | output เฉพาะ action ซึ่งมีอยู่เมื่อสำเร็จ |
| `error` | `ToolError`/null | มีอยู่เมื่อเกิด error |
| `citations` | `Citation[]` | เฉพาะผลลัพธ์ knowledge ที่สำเร็จเท่านั้นที่มีรายการได้ |
| `simulation` | boolean | เป็น `false` เฉพาะผลลัพธ์ knowledge |

`ToolError` มี `code` (`invalid_input`, `not_found`, `unavailable`, `conflict`, `internal`) และ `message` ที่ปลอดภัยสำหรับผู้ใช้ (สูงสุด 500 อักขระ)

### `PendingAction`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `pendingActionId` | UUID | สร้างโดย server |
| `conversationId` | UUID | conversation ที่เป็นเจ้าของ |
| `toolName` | `sabuy_tool` / `voc_tool` / `oms_tool` | knowledge ไม่สามารถเขียนได้ |
| `prepareAction` | prepare action enum | action ต้นฉบับที่ผ่านการตรวจสอบแล้ว |
| `submitAction` | submit action enum | ใช้ได้เฉพาะ mapping ที่กำหนดไว้ล่วงหน้า |
| `preparedInput` | object | สำเนาที่ปกปิดข้อมูลแล้ว และไม่จัดเก็บ payment token |
| `summary` | string | ผลที่เสนอในรูปแบบที่มนุษย์อ่านได้ สูงสุด 500 อักขระ |
| `status` | `pending_confirmation`, `confirmed`, `submitted`, `rejected`, `failed` | ถูกจำกัดตาม state machine |
| `idempotencyKey` | string | คัดลอกจากคำขอเขียน |
| `createdAt`, `updatedAt` | UTC datetime | กำหนดโดย server |
| `submissionResult` | `ToolResult`/null | กำหนดหลังการส่ง |

### `TraceEvent`

| ฟิลด์ | ชนิด | กฎ |
|---|---|---|
| `eventId` | UUID | สร้างโดยระบบ |
| `traceId` | UUID | trace ของคำขอ |
| `sequence` | positive integer | เพิ่มขึ้นอย่างเคร่งครัดในแต่ละ trace |
| `at` | UTC datetime | กำหนดโดย server |
| `kind` | enum | `chat_received`, `llm_requested`, `llm_responded`, `tool_called`, `tool_result`, `action_prepared`, `action_confirmed`, `action_rejected`, `action_submitted`, `error` |
| `data` | object | ข้อมูลวินิจฉัยแบบมีโครงสร้างที่ปกปิดข้อมูลแล้ว สูงสุด 20 key |

## รายการ tool และ schema ของ action ที่แน่นอน

### 1. `knowledge_tool`

**ระบบเบื้องหลัง:** Document Routing + Full-file Gemini Long Context โดย `simulation = false` และ **ไม่ใช้ RAG/Gemini File Search**

| การดำเนินการ | ข้อมูลนำเข้า | ข้อมูลเมื่อสำเร็จ |
|---|---|---|
| `search` | `{ "query": string(1..1000), "maxResults": integer(1..5, default 3) }`; `maxResults` คือจำนวนไฟล์ฉบับเต็มสูงสุดที่เลือกได้ | `{ "answerContext": string(1..4000), "resultCount": integer(0..5) }`; `resultCount` คือจำนวนไฟล์ฉบับเต็มที่ใช้ตอบ พร้อม `Citation` อย่างน้อยหนึ่งรายการต่อไฟล์ที่ใช้เมื่อ `resultCount > 0` |

กฎการทำงานที่บังคับใช้:

1. Document Router เห็นเฉพาะคำถามและ catalog ระดับไฟล์ ได้แก่ `sourceId`, ชื่อไฟล์ และหัวข้อเอกสาร แล้วเลือกรหัสไฟล์จาก allowlist ไม่เกิน `maxResults`
2. backend ต้องโหลดและแปลงข้อความ **ทั้งไฟล์** ของทุกไฟล์ที่เลือก แล้วส่งข้อความฉบับเต็มพร้อมคำถามให้ Gemini Long Context ห้ามเลือก ตัด หรือจัดอันดับ chunk
3. ต้องเลือกชุดไฟล์ที่เล็กที่สุดซึ่งครอบคลุมคำถาม ห้ามส่งทั้ง corpus เมื่อมีเพียงบางไฟล์ที่เกี่ยวข้อง
4. หากคำถามครอบคลุมหลายบริการ สามารถเลือกหลายไฟล์ฉบับเต็มได้ หากคำถามกำกวมหรือไม่มีไฟล์ตรง ให้คืน no-evidence เพื่อให้ Main Agent ถามกลับหรือแจ้งข้อจำกัด
5. `answerContext` คือคำตอบที่ครบและตรงคำถามซึ่งสร้างจากข้อความฉบับเต็ม ไม่ใช่หัวเอกสาร รายการลิงก์ หรือ citation snippet ดิบ
6. citation ทุกตัวต้องอ้างถึงไฟล์ที่เลือกจริง และ `snippet` ต้องเป็นข้อความหลักฐานที่ตรวจสอบได้ว่าอยู่ในไฟล์ฉบับเต็มนั้น
7. หากชุดไฟล์ที่เลือกเกิน context budget ห้ามตัดข้อความท้ายไฟล์โดยเงียบ ต้องลดขอบเขตด้วยคำถามชี้แจงหรือคืน typed failure
8. เมื่อไม่มีไฟล์หรือหลักฐานตรงกัน tool ต้องคืน `answerContext` ว่าง, `resultCount = 0` และไม่มี citation โดยห้ามใช้ความจำของโมเดลตอบแทน

### 2. `sabuy_tool`

**ระบบเบื้องหลัง:** `SimulatedSabuyBackend` โดย output ทุกรายการประกาศ `simulation: true`

| การดำเนินการ | ข้อมูลนำเข้า | ข้อมูลเมื่อสำเร็จ |
|---|---|---|
| `get_account_summary` | `{ "accountRef": string(1..64) }` | `{ "accountRef": string, "customerDisplayName": string, "outstandingBalanceThb": decimal-string, "dueDate": date/null, "paymentStatus": "current"\|"overdue"\|"paid" }` |
| `prepare_payment` | `{ "accountRef": string(1..64), "amountThb": decimal-string > 0, "paymentMethod": "demo_card"\|"demo_bank", "idempotencyKey": string(1..128) }` | `{ "accountRef": string, "amountThb": decimal-string, "paymentMethod": enum, "summary": string }` |
| `submit_payment` | สำหรับใช้ภายในเท่านั้น: `{ "pendingActionId": UUID, "idempotencyKey": string }` | `{ "receiptId": string, "accountRef": string, "amountThb": decimal-string, "status": "accepted" }` |

Main Agent เรียกใช้ `submit_payment` ได้หลังการยืนยันเท่านั้น และต้องขจัดรายการซ้ำด้วย `idempotencyKey`

### 3. `voc_tool`

**ระบบเบื้องหลัง:** `SimulatedVocBackend` โดย output ทุกรายการประกาศ `simulation: true`

| การดำเนินการ | ข้อมูลนำเข้า | ข้อมูลเมื่อสำเร็จ |
|---|---|---|
| `list_categories` | `{}` | `{ "categories": [{ "code": "billing"\|"service"\|"safety"\|"other", "label": string }] }` |
| `prepare_case` | `{ "category": enum, "subject": string(1..140), "detail": string(1..2000), "contactName": string(1..100), "contactPhone": string(1..32), "location": string(1..500), "contactChannel": "phone"\|"email"\|"none", "idempotencyKey": string(1..128) }` | `{ "category": enum, "subject": string, "summary": string }` |
| `submit_case` | สำหรับใช้ภายในเท่านั้น: `{ "pendingActionId": UUID, "idempotencyKey": string }` | `{ "caseId": string, "vocId": string, "trackingKey": string, "status": "submitted", "category": enum }` |
| `get_case` | `{ "vocId": string(1..64), "trackingKey": string(1..64) }` | `{ "vocId": string, "status": "submitted", "category": enum, "createdAt": UTC datetime, "updatedAt": UTC datetime }` |

กรณี VOC ที่จัดเตรียมไว้เป็นเพียงฉบับร่างเท่านั้น และจะยังไม่สร้างกรณีจำลองจนกว่าจะ submit

การแจ้งเรื่องร้องเรียนต้องเก็บข้อมูลให้ครบ (หมวดหมู่ หัวข้อ รายละเอียด ชื่อผู้แจ้ง เบอร์โทรติดต่อ สถานที่) ก่อน `prepare_case` โดย Main Agent ต้องถามข้อมูลที่ขาดทีละขั้นเหมือนฟอร์มบนเว็บ และห้ามสร้างค่าฟิลด์ขึ้นเอง

การติดตามเรื่อง (`get_case`) ต้องใช้ `vocId` และ `trackingKey` ที่ผู้ใช้ได้รับหลัง `submit_case` ตรงกันทั้งคู่ มิฉะนั้นล้มเหลวแบบ fail-closed โดยไม่เปิดเผยว่า `vocId` มีอยู่จริงหรือไม่

### 4. `oms_tool`

**ระบบเบื้องหลัง:** `SimulatedOmsBackend` โดย output ทุกรายการประกาศ `simulation: true`

| การดำเนินการ | ข้อมูลนำเข้า | ข้อมูลเมื่อสำเร็จ |
|---|---|---|
| `get_outage_status` | `{ "areaCode": string(1..32) }` | `{ "areaCode": string, "status": "normal"\|"planned_outage"\|"unplanned_outage", "updatedAt": UTC datetime, "estimatedRestoreAt": UTC datetime/null, "safetyMessage": string }` |
| `prepare_outage_report` | `{ "areaCode": string(1..32), "locationNote": string(1..500), "symptoms": string(1..1000), "idempotencyKey": string(1..128) }` | `{ "areaCode": string, "summary": string, "safetyMessage": string }` |
| `submit_outage_report` | สำหรับใช้ภายในเท่านั้น: `{ "pendingActionId": UUID, "idempotencyKey": string }` | `{ "reportId": string, "status": "submitted", "areaCode": string }` |

output เหตุไฟฟ้าขัดข้องของ OMS ต้องมี `safetyMessage` เสมอ และ Main Agent ต้องแสดงข้อความนี้ก่อนคำอธิบายเพิ่มเติมจากโมเดล

## การตรวจสอบ model-to-action ที่จำเป็น

runtime ตรวจสอบ input ผ่านโมเดล Pydantic `*Input` ที่ตรงกันก่อนเรียกใช้ tool และตรวจสอบข้อมูลความสำเร็จผ่านโมเดล `*Output` ที่ตรงกันก่อนสร้าง `ToolResult` โดยมี mapping ขั้นต่ำดังนี้:

```text
knowledge_tool.search                    KnowledgeSearchInput/Output
sabuy_tool.get_account_summary           SabuyAccountSummaryInput/Output
sabuy_tool.prepare_payment               SabuyPreparePaymentInput/Output
sabuy_tool.submit_payment                SubmitPreparedActionInput/SabuyPaymentReceiptOutput
voc_tool.list_categories                 EmptyInput/VocCategoryListOutput
voc_tool.prepare_case                    VocPrepareCaseInput/Output
voc_tool.submit_case                     SubmitPreparedActionInput/VocCaseOutput
voc_tool.get_case                        VocGetCaseInput/VocGetCaseOutput
oms_tool.get_outage_status               OmsOutageStatusInput/Output
oms_tool.prepare_outage_report           OmsPrepareOutageReportInput/Output
oms_tool.submit_outage_report            SubmitPreparedActionInput/OmsOutageReportOutput
```

## สิ่งที่ไม่ใช่เป้าหมายอย่างชัดเจน

- ไม่มีการชำระเงิน การดำเนินการกับลูกค้า เหตุไฟฟ้าขัดข้อง CRM หรือ OMS ของ PEA จริง
- ไม่มี tool อื่นนอกเหนือจาก tool ระดับบนสุดสี่รายการที่ระบุไว้
- ไม่มีการยืนยันอัตโนมัติ การส่งในเบื้องหลัง หรือการยืนยันผ่านข้อความแชต
- ไม่มี Gemini File Search, vector database, embedding pipeline, document chunker, chunk retrieval หรือ RAG สำรอง; Knowledge ใช้เฉพาะการเลือกไฟล์ระดับ document แล้วส่งข้อความฉบับเต็มของไฟล์ที่เลือกเข้า Long Context
- ไม่มีการจัดเก็บถาวรสำหรับ production แบบหลายผู้ใช้ authentication, payments หรือการเสริมความแข็งแกร่งสำหรับ deployment
