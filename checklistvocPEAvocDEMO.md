# VOC PEA Demo Integration Checklist

เอกสารนี้เป็น checklist สำหรับเชื่อม `PEA One Agent` กับ VOC Demo API ของ
`wsc2026-be` และใช้ตรวจผลกระทบเมื่อ API เปลี่ยนแปลง

## Source of truth

ลำดับความสำคัญของ contract:

1. `wsc2026-be/spec/voc.openapi.yaml` — **API contract หลักที่ต้องส่งจริง**
2. `wsc2026-be/internal/voc/validate.go` และ `handler.go` — validation/HTTP behavior จริง
3. `voc.pea.co.th` — reference ของ UX และความหมายของข้อมูล
4. `app/contracts.py` — typed contract ภายใน Agent ซึ่งต้องสอดคล้องกับข้อ 1

> หน้าเว็บอาจแสดงหรือบังคับกรอกน้อยกว่า API gateway แต่ Agent ห้ามส่งค่าที่ API
> บังคับโดยการเดาหรือเติมค่าเอง ต้องถามผู้ใช้แทน

## Endpoint checklist

| Operation ใน Agent | HTTP method | Endpoint | HTTP | หมายเหตุ |
|---|---:|---|---:|---|
| `list_categories` / catalog | GET | `/api/v1/voc/catalog` | 200 | อ่าน catalog authoritative; ไม่มี body |
| `prepare_case` | ไม่มี HTTP | local only | - | เก็บ draft และตรวจข้อมูลก่อนยืนยัน |
| `submit_case` | POST | `/api/v1/voc/cases` | 201 | เรียกหลัง explicit confirmation เท่านั้น |
| `get_case` | POST | `/api/v1/voc/cases/lookup` | 200 | ใช้ `vocNumber` + `keyCode`; ห้ามใส่ key ใน URL |

### Headers

- ทุก endpointของ gateway ต้องส่ง `X-API-Key` ตาม environment configuration
- `POST /cases` ต้องส่ง `Idempotency-Key` ยาว 1–128 ตัวอักษร
- ห้ามเขียน API key, Idempotency-Key, Key Code หรือข้อมูลส่วนตัวลง log/trace ดิบ

## Field comparison: website vs Demo API

| กลุ่มข้อมูล | หน้าเว็บ VOC ที่สังเกตได้ | Demo API | สถานะ Agent |
|---|---|---|---|
| ประเภทเรื่อง | แสดง 6 journeys/cards | `journeyCode` 6 ค่า | ต้อง map อย่าง explicit |
| Request type | เลือกตาม hierarchy | `classification.requestTypeCode` required | ต้องใช้จาก catalog |
| Topic | เลือกตาม hierarchy | `classification.topicCode` required | ต้องใช้จาก catalog |
| Issue | เลือกตาม hierarchy | `classification.issueCode` required | ต้องใช้จาก catalog |
| Sub-issue | ขึ้นกับ journey | required ใน Power/Service/Praise | ห้ามเดา; ถามเมื่อ journey บังคับ |
| Reporter | บาง flow required, tip อาจ optional | required ทุก journeyยกเว้น `TIP_OFF` | ต้องแยก prefix/ชื่อ/นามสกุล/โทร |
| CA number | มีในบาง flow | optional | ส่งเมื่อผู้ใช้ให้มาและรูปแบบถูกต้อง |
| Meter number | มีในบาง flow | optional | ส่งเมื่อผู้ใช้ให้มา |
| Contact address | หน้าเว็บรองรับละเอียด | API รองรับใน reporter แต่ไม่จำเป็นขั้นต่ำ | ยังไม่ถามถ้าไม่จำเป็น |
| Incident location | จังหวัด/อำเภอ/ตำบล/สำนักงาน/รายละเอียด | `incident` และ field หลักทั้ง 5 ค่า required | ต้องถามครบ ห้ามใช้ free text แทน code |
| Frequency | ใช้ใน flow ที่เกี่ยวข้อง | required สำหรับ `POWER_QUALITY`, `SERVICE_ISSUE` | ใช้ code จาก catalog เช่น `IIT03` |
| Severity | ระดับ 1–5 | required สำหรับ `POWER_QUALITY`, `SERVICE_ISSUE` | ใช้ตัวเลข 1–5 |
| Detail | หน้าเว็บมีรายละเอียดเหตุการณ์ | `detail` required, max 2000 | ส่งข้อความผู้ใช้โดยไม่เติมเนื้อหา |
| Subject | อาจมีใน UX บางส่วน | **ไม่มีใน API create payload** | เป็น local review field เท่านั้น |
| Contact channel | ไม่ใช่ field หลักที่พบในเว็บ | API consent ใช้ `CHAT`/`VOICE` | ห้ามส่ง local `phone/email/none` เป็น API field |
| PDPA consent | มี modal/checkbox | `consent.accepted=true`, notice version, timestamp, channel required | ต้องขอ consent แยกจาก confirm |
| CAPTCHA | เว็บมี anti-bot | ไม่อยู่ใน Demo API contract | ห้ามสร้าง field เอง |
| Attachments | เว็บรองรับ | ไม่อยู่ใน Demo API contract | ยังไม่ส่งไฟล์ใน MVP |

## Six journeys and minimum API rules

| `journeyCode` | Reporter | Frequency | Severity | Sub-issue | Root request types |
|---|---|---|---|---|---|
| `POWER_QUALITY` | required | required | required | required | `REQUEST_6` |
| `SERVICE_ISSUE` | required | required | required | required | `REQUEST_1`, `REQUEST_2` |
| `PRAISE` | required | optional | optional | required | `REQUEST_3` |
| `TIP_OFF` | optional | optional | optional | optional | `REQUEST_4` |
| `STAKEHOLDER_ISSUE` | required | optional | optional | optional | `REQUEST_7` |
| `STAKEHOLDER_FEEDBACK` | required | optional | optional | optional | `REQUEST_8` |

สำหรับทุก journey ใน Demo API ต้องมี `incident`, `classification`, `detail` และ
`consent` ตาม schema และ validation ของ gateway

## Response mapping

### Submit response

| API field | Agent meaning |
|---|---|
| `caseId` | internal case identifier |
| `vocNumber` | เลขติดตามที่ให้ผู้ใช้เก็บไว้ |
| `keyCode` | รหัสติดตามลับ; แสดงเฉพาะเท่าที่จำเป็น |
| `status` | เริ่มต้นเป็น `SUBMITTED` |
| `journeyCode` | ประเภท journey ที่ส่ง |
| `createdAt` | เวลาที่สร้างจาก API |
| `simulation` | ต้องเป็น `true` ใน Demo |

ภายใน legacy facade อาจ map `vocNumber → vocId` และ `keyCode → trackingKey`
ได้ชั่วคราว แต่ต้องระบุ mapping ชัดเจนและไม่ควรใช้ชื่อเก่ากับ API payload

### Lookup response

API คืน `case` พร้อม status/timeline หลายสถานะ เช่น `SUBMITTED`, `IN_PROGRESS`,
`RESOLVED`, `REJECTED` และ `CANCELLED` ห้ามลดทุกสถานะเหลือ `submitted`

`404 TRACKING_NOT_FOUND` ต้องใช้ข้อความเดียวกันทั้งกรณีไม่มี VOC number และกรณี
Key Code ไม่ตรง เพื่อไม่เปิดเผยข้อมูลว่าเลขใดมีอยู่จริง

## Write-safety checklist

- [ ] `prepare_case` ไม่เรียก HTTP
- [ ] prepare เก็บ draft เฉพาะใน memory และสร้าง pending action
- [ ] ต้องมีการยืนยันจากผู้ใช้ผ่าน confirm endpoint ก่อน submit
- [ ] submit action เป็น internal-only และไม่อยู่ใน LLM catalogue
- [ ] ใช้ Idempotency-Key เดิมตลอด prepare/confirm/submit
- [ ] key เดิม + payload เดิมต้อง replay ผลเดิม
- [ ] key เดิม + payload ต่างกันต้อง map เป็น conflict
- [ ] reject แล้วต้องไม่ยิง POST
- [ ] reset ล้างเฉพาะ draft; ไม่เรียก API เพื่อลบเคสที่ส่งแล้ว
- [ ] ไม่สังเคราะห์ taxonomy, location code, consent หรือ timestamp

## เมื่อ API เปลี่ยน ต้องแก้ไฟล์ใด

### เปลี่ยน field/type/requiredness ของ request หรือ response
1. แก้ `app/contracts.py` ก่อน — เป็น typed source of truth ของ Agent
2. แก้ `app/tools/voc_tool.py` สำหรับ payload mapping และ error mapping
3. แก้ `app/plugins/voc/intake.py` สำหรับ slot/prompt/validation
4. ตรวจ `app/plugins/voc/plugin.yaml` ให้ contract names และ actions ครบ
5. เพิ่มหรือแก้ tests ใน `app/tools/tests/test_voc_tool.py` และ intake tests
6. รัน `python3 -m pytest -q`

### เปลี่ยน endpoint/method/header
- แก้ `app/tools/voc_tool.py`
- แก้ config ใน `app/core/config.py` และ `.env.example` หากมีค่าใหม่
- เพิ่ม HTTP transport test ที่ตรวจ method/path/header แบบ exact

### เพิ่มหรือลบ operation/action
- แก้ `ToolAction`, `TOOL_ACTIONS`, `PREPARE_TO_SUBMIT`, input/output models ใน
  `app/contracts.py`
- แก้ `plugin.yaml` ให้ประกาศ action ครบ มิฉะนั้น loader จะ fail closed
- ตรวจ MainAgent และ LLM catalogue ว่า submit ยังเป็น internal-only

### เปลี่ยนเฉพาะข้อความ UX
- แก้ `app/plugins/voc/intake.py` หรือ message formatter ในโฟลเดอร์ plugin
- ไม่ควรแก้ API contract หาก schema ไม่เปลี่ยน
- ห้ามย้ายข้อความเฉพาะ plugin ไปใส่ `app/agent/main_agent.py` — MainAgent ถือ policy กลางเท่านั้น

## Verification checklist

- [ ] อ่านและเทียบ `spec/voc.openapi.yaml` เวอร์ชันล่าสุด
- [ ] ตรวจ route/validation ใน `internal/voc/`
- [ ] ตรวจ catalog ครบ 6 journeys และ taxonomy relationships
- [ ] ทดสอบ catalog ผ่าน local API ด้วย API key
- [ ] ทดสอบ prepare ไม่มี outbound request
- [ ] ทดสอบ confirm ยิง POST หนึ่งครั้ง
- [ ] ทดสอบ confirm ซ้ำไม่สร้างเคสซ้ำ
- [ ] ทดสอบ reject ไม่ยิง POST
- [ ] ทดสอบ lookup สำเร็จและ 404 แบบ generic
- [ ] ตรวจไม่มี PII/Key Code ใน trace/log
- [ ] รัน full test suite
- [ ] ยืนยันว่า response ยังคง `simulation: true`

## Current implementation note

ระบบ Agent เดิมมี legacy VOC fields (`category`, `subject`, `contactName`,
`contactPhone`, `location`) ซึ่งไม่เพียงพอสำหรับ Demo API ใหม่ การ map ค่าเหล่านี้
ด้วย default taxonomy/location/consent ถือว่าไม่ปลอดภัย ต้องเปลี่ยน intake ให้ถาม
ข้อมูลที่ API บังคับ หรือหยุดแบบ fail-closed จนกว่าจะได้ข้อมูลครบ
