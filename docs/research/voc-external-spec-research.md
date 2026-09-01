# PEA VOC external-spec research (read-only)

> ตรวจสอบเมื่อ 1 กันยายน 2569 โดยใช้เฉพาะหน้าเว็บ, client assets, public JSON endpoints ของ `voc.pea.co.th` และ source/spec ใน repository นี้ การตรวจภายนอกใช้เฉพาะ `GET`; ไม่ล็อกอิน ไม่ค้นเคสจริง ไม่อัปโหลดไฟล์ และไม่ส่งคำร้องหรือเรียก write endpoint ใด ๆ

## ขอบเขตและวิธีอ่านผล

- **Observed fact** คือสิ่งที่เห็นโดยตรงใน first-party page/asset/JSON response หรือ source/spec ใน repository
- **Inference** คือข้อเสนอสำหรับ external OpenAPI ที่สรุปจาก observed facts แต่ยังไม่ใช่สัญญา backend ของ PEA
- **Open question** คือสิ่งที่ยืนยันไม่ได้โดยไม่ใช้ credentials, เคสจริง, การส่งคำร้อง หรือเอกสาร backend ทางการ
- Hash ของ Next.js assets อาจเปลี่ยนเมื่อ deploy ใหม่ จึงอ้างทั้งหน้าต้นทางและ asset ที่ตรวจครั้งนี้

## สรุปสำหรับการออกแบบสัญญา

1. หน้าแรกแสดง **6 ตัวเลือก** ตรงกับ enum/fixture หกค่าใน repository โดยความหมายหลักสอดคล้องกัน แต่เว็บไม่ได้เปิด public API ชื่อ `list_categories`; มันแสดง cards และใช้ VOC hierarchy API ที่ละเอียดกว่า
2. public tracking UI เป็น **ค้น/ติดตามทีละ VOC number** ไม่พบหน้าหรือ client call สำหรับ “list all cases”. `list_categories` ใน repository เป็นรายการประเภทเรื่อง ไม่ใช่รายการเคส
3. intake จริงมีข้อมูลมากกว่า `category, subject, detail, contactName, contactPhone, location, contactChannel`: ชื่อถูกแยก, มี CA/PEA No./เลขบัตร/อีเมล/ที่อยู่แบบโครงสร้าง/สำนักงาน PEA/VOC hierarchy/ความถี่/ความรุนแรง/ไฟล์แนบ/PDPA/reCAPTCHA; ขณะเดียวกันไม่พบช่อง free-text `subject` หรือ `contactChannel` ที่ตรงกับ local contract
4. เว็บมี `POST /api/request/submit` โดยตรงหลัง validation, PDPA, reCAPTCHA และ confirmation modal; ไม่พบ external “prepare” endpoint. การแยก `prepare_case → explicit confirmation → submit_case` ของ repository เป็น safety state machine ภายในที่ควรรักษาไว้ แต่ไม่ควรอ้างว่า mirror PEA API
5. tracking client เรียก `GET /api/voc-tracking/search?vocNumber=...&keyCode=...`; ปุ่มค้นหาเปิดใช้งานเมื่อมี VOC number แม้ key code ว่าง และ client ละ `keyCode` ออกจาก query เมื่อว่าง ดังนั้นห้ามระบุว่า backend บังคับใช้ key code จนกว่าจะมีหลักฐานเพิ่ม

## Observed facts — end-user flows

### หน้าแรกและ 6 ตัวเลือก

หน้า [PEA-VOC](https://voc.pea.co.th/) แสดงหกตัวเลือกดังนี้:

| # | ข้อความบนเว็บ | กลุ่ม/คำอธิบายที่เห็น | route ที่ยืนยันได้จาก page links |
|---|---|---|---|
| 1 | แจ้งปัญหาคุณภาพไฟฟ้า | ประชาชนทั่วไป; ไฟตก ไฟดับ แรงดันไม่คงที่ หรือเหตุขัดข้องอื่น | [`/report-power/`](https://voc.pea.co.th/report-power/) |
| 2 | แจ้งปัญหาด้านบริการ | ประชาชนทั่วไป; สาขา เจ้าหน้าที่ หรือแอปพลิเคชัน | [`/customer-voice/service-issue/`](https://voc.pea.co.th/customer-voice/service-issue/) |
| 3 | ชื่นชม | ประชาชนทั่วไป; ประสบการณ์ที่ดี/คำชม | [`/customer-voice/praise/`](https://voc.pea.co.th/customer-voice/praise/) จาก [homepage client asset](https://voc.pea.co.th/_next/static/chunks/18jc5808crmpv.js) |
| 4 | แจ้งเบาะแส | ประชาชนทั่วไป; ความผิดปกติ/ความเสี่ยงด้านความปลอดภัย | [`/customer-voice/tip/`](https://voc.pea.co.th/customer-voice/tip/) จาก [homepage client asset](https://voc.pea.co.th/_next/static/chunks/18jc5808crmpv.js) |
| 5 | แจ้งปัญหาการดำเนินงาน | คู่ค้า/ผู้มีส่วนได้ส่วนเสีย | [`/stakeholder-voice/issue/`](https://voc.pea.co.th/stakeholder-voice/issue/) |
| 6 | ชื่นชม เสนอแนะ ข้อคิดเห็น | คู่ค้า/ผู้มีส่วนได้ส่วนเสีย | [`/stakeholder-voice/feedback/`](https://voc.pea.co.th/stakeholder-voice/feedback/) |

public hierarchy ที่ [`GET /api/voc-hierarchy/request-types?activeOnly=true`](https://voc.pea.co.th/api/voc-hierarchy/request-types?activeOnly=true) คืน records เช่น `REQUEST_1 ร้องเรียน`, `REQUEST_2 ข้อเสนอแนะ/ข้อคิดเห็น`, `REQUEST_3 ชื่นชม`, `REQUEST_4 แจ้งเบาะแส`, `REQUEST_6 แจ้งเหตุ` และประเภท stakeholder เพิ่มเติม จึงเป็น taxonomy สำหรับ form ที่ละเอียดกว่า cards หกใบบนหน้าแรก ไม่ใช่ API ที่คืน cards หกใบแบบหนึ่งต่อหนึ่ง

### แจ้งปัญหาคุณภาพไฟฟ้า

Observed จาก [`/report-power/`](https://voc.pea.co.th/report-power/) และ client assets ของหน้านั้น:

1. ขั้นแรก “สอบถามปัญหาเบื้องต้น” เก็บความถี่, ระดับความรุนแรง 1–5 และ hierarchy ประเด็น/ประเด็นย่อย แล้วไป [`/report-power/next-step-form`](https://voc.pea.co.th/report-power/next-step-form)
2. ความถี่มาจาก public JSON [`GET /api/master-data/incident-frequencies?isActive=true`](https://voc.pea.co.th/api/master-data/incident-frequencies?isActive=true); response ที่ตรวจเป็น `{ "data": [...] }` โดย item มี `id`, `code`, `name`, `sort_order`, `is_active`, `created_at`, `updated_at`
3. ขั้นรายละเอียดเก็บข้อมูลผู้ยื่น, ที่อยู่ติดต่อ, สถานที่เกิดเหตุ/แผนที่, สำนักงาน PEA, รายละเอียดเหตุการณ์และไฟล์แนบ ก่อน PDPA/reCAPTCHA/confirmation
4. client asset ใช้ draft/session state ระหว่างสองหน้า; ยังไม่มี network write ในขั้น “ถัดไป” ที่ตรวจพบ

### intake routes อีกห้าประเภท

[`/customer-voice/service-issue/`](https://voc.pea.co.th/customer-voice/service-issue/), [`/customer-voice/praise/`](https://voc.pea.co.th/customer-voice/praise/), [`/customer-voice/tip/`](https://voc.pea.co.th/customer-voice/tip/), [`/stakeholder-voice/issue/`](https://voc.pea.co.th/stakeholder-voice/issue/) และ [`/stakeholder-voice/feedback/`](https://voc.pea.co.th/stakeholder-voice/feedback/) ใช้ form pattern ร่วมกันโดยสรุป:

1. ข้อมูลผู้แจ้งและที่อยู่ติดต่อ
2. เลือกจังหวัด → อำเภอ → ตำบล → การไฟฟ้าที่ต้องการแจ้ง และระบุพื้นที่เกิดเหตุ
3. เลือกประเภทเสียง/VOC hierarchy และกรอกรายละเอียด
4. แนบไฟล์ได้
5. ยอมรับ PDPA, ผ่าน reCAPTCHA, เปิด modal ยืนยัน แล้วจึง “ส่งคำร้อง”
6. success UI แสดง VOC Number และ Key Code และแจ้งว่าจะส่ง link/password ทาง SMS สำหรับติดตาม

requiredness ต่างตาม route: service/stakeholder issue และ praise แสดงชื่อ/โทรศัพท์และพื้นที่เป้าหมายเป็น required; หน้า tip ไม่ทำเครื่องหมายข้อมูลตัวตน/การติดต่อเป็น required แต่การ submit แบบ anonymous ยังยืนยันไม่ได้เพราะไม่ได้ส่งจริง

public [`GET /api/pea-office`](https://voc.pea.co.th/api/pea-office) คืน array ของสำนักงาน/พื้นที่ โดย record ที่ตรวจมี `id`, `name`, `region_group`, `pea_office`, `subdistrict_code`, `postal_code`. Endpoint นี้ตอบข้อมูลจำนวนมากและไม่มี pagination ที่เห็นจาก request นี้

### ติดตามคำร้อง: track one, ไม่พบ list all

หน้า [`/voc-tracking/`](https://voc.pea.co.th/voc-tracking/) แสดงเพียง:

- `หมายเลขเสียงของลูกค้า (VOC Number)`; placeholder ตัวอย่าง `I-68100011`
- `Key Code`; placeholder ตัวอย่าง 6 หลัก
- ปุ่มล้างค่าและค้นหา
- ข้อความว่า VOC number และ key code อยู่ในอีเมล/SMS ที่ผู้ใช้ได้รับ

[tracking client asset ที่ตรวจ](https://voc.pea.co.th/_next/static/chunks/0rlogzckdjrya.js) สร้าง request:

```http
GET /api/voc-tracking/search?vocNumber={vocNo}[&keyCode={keyCode}]
```

Observed client behavior เพิ่มเติม:

- submit handler ต้องมี `vocNo.trim()` เท่านั้น; ปุ่ม disabled เมื่อไม่มี VOC number หรือกำลังค้นหา
- `keyCode` ถูกส่งเฉพาะเมื่อไม่ว่าง
- success เก็บ `voc_tracking_auth_{vocNo}=true` ใน `sessionStorage` แล้ว navigate ไป `/voc-tracking/{vocNo}`
- result client มี read calls `GET /api/voc-tracking/{vocNo}` และ `GET /api/voc-tracking/{vocNo}/check-status`; client asset ยังอ้าง additional-file read/upload flow แต่ไม่ได้ทดสอบ
- ไม่พบ cases table, account login, owner identifier, “my cases”, pagination หรือ client endpoint สำหรับ list-all-cases ใน public pages/assets ที่ตรวจ

ดังนั้น **หลักฐานรองรับเฉพาะ track-one-case**. การไม่มี client call ไม่พิสูจน์ว่า backend ไม่มี admin/list endpoint; พิสูจน์เพียงว่าไม่ observable ใน public unauthenticated flow นี้

## Observed facts — fields and validation

### ฟิลด์ intake ที่ปรากฏ

| กลุ่ม | ฟิลด์/พฤติกรรมที่เห็น | validation ที่เห็นใน client |
|---|---|---|
| ผู้แจ้ง | CA/user number, PEA meter number, คำนำหน้า, ชื่อจริง, นามสกุล, เลขบัตรประชาชน, โทรศัพท์, อีเมล | CA 12 ตัวเลขเมื่อกรอก; citizen ID 13 หลักและ checksum; โทรศัพท์ 10 ตัวเลข/ขึ้นต้น `0`; email format |
| ที่อยู่ติดต่อ | บ้านเลขที่, หมู่, หมู่บ้าน/อาคาร, ถนน, ซอย, รหัสไปรษณีย์, จังหวัด, อำเภอ, ตำบล | postal code 5 ตัวเลข; cascading/auto-filled fields |
| เป้าหมาย/สถานที่เกิดเหตุ | จังหวัด, อำเภอ, ตำบล, การไฟฟ้า, ใช้ที่อยู่ติดต่อหรือระบุสถานที่เกิดเหตุ, lat/lng ใน payload mapping | dropdown dependencies; required PEA office; map/manual location |
| เนื้อหา VOC | request type, main topic, issue, sub-issue, frequency, severity, event detail, product importance/result | hierarchy dependencies; frequency required ใน service flow; severity 1–5; detail required และ UI แสดง limit 250 characters |
| ไฟล์ | JPG/JPEG/PNG/TIFF/PDF/MP4/DOC/DOCX/XLS/XLSX | client บังคับเพดานรวม 25 MB |
| consent/security | `acceptTerms`, reCAPTCHA token | ต้องยอมรับ terms และยืนยัน reCAPTCHA ก่อน submit |

ข้อสำคัญ: requiredness ต่างกันตาม flow. ตัวอย่าง stakeholder page ทำเครื่องหมายคำนำหน้า/ชื่อ/นามสกุล/โทรศัพท์/พื้นที่เป้าหมาย/สำนักงาน/รายละเอียดเป็น required ขณะที่ CA, citizen ID และ email ไม่ได้เป็น required เสมอ จึงไม่ควรรวมทุกหน้าเป็น schema เดียวโดยไม่มี discriminator

### network calls ที่ client อ้าง

read calls ที่เห็นใน first-party assets (ไม่ได้เรียก customer/case-specific endpoints ด้วยข้อมูลจริง):

```text
GET /api/voc-tracking/search?vocNumber=...&keyCode=...
GET /api/voc-tracking/{vocNo}
GET /api/voc-tracking/{vocNo}/check-status
GET /api/master-data/departments/{id}
GET /api/master-data/title-prefixes?isActive=true
GET /api/master-data/incident-frequencies?isActive=true
GET /api/voc-hierarchy/request-types?activeOnly=true
GET /api/voc-hierarchy/request-types/{id}/topics?activeOnly=...
GET /api/voc-hierarchy/topics/{id}/issues?activeOnly=...
GET /api/voc-hierarchy/issues/{id}/sub-issues?activeOnly=...
GET /api/voc-hierarchy/sub-issues/{id}/causes?activeOnly=...
GET /api/customer/{customerCode}
GET /api/customer/validate/{customerCode}
GET /api/locations/provinces
GET /api/locations/provinces/{id}/districts
GET /api/locations/districts/{id}/subdistricts
GET /api/locations/hierarchy?... | search?... | postal-code/{postal}
GET /PDPA.txt
```

write calls ที่ assets อ้างแต่ **ไม่ได้เรียก**: `POST /api/request/submit`, `POST /api/voc-tracking/{vocNo}/additional-files`, `POST /api/voc-satisfaction/submit`.

### request payload ที่ client สร้าง

[submit client asset](https://voc.pea.co.th/_next/static/chunks/2leo9scb1w0rk.js) map form state เป็น object ที่มีทั้ง nested และ flattened fields ได้แก่:

- `vocType`
- `personalInfo { prefix, firstName, lastName, citizenId, phone, email }`
- `contactAddress { houseNo, moo, village, road, soi, postal, province, district, subdistrict, ..._name }`
- `initialData`, `eventDetails`, `powerQuality`
- `incidentLocation { locationType, isContactLocationSame, incidentAddress, contactAddress }`
- `userNumber`, `meterNumber`, `requestProvince`, `requestDistrict`, `requestSubdistrict`, `requestPEA`
- flattened `incident_*`
- `topic`, `details`, `acceptTerms`
- hierarchy IDs: `requestType`, `mainTopic`, `issue`, `subIssue`
- `productImportanceInput`, `productImportanceResult`

เมื่อไม่มีไฟล์ client ส่ง `POST https://voc.pea.co.th/api/request/submit` ด้วย JSON. เมื่อมีไฟล์ client ส่ง `multipart/form-data` โดย part `data` เป็น JSON string และ part `files` ซ้ำต่อไฟล์. **ไม่ได้เรียก endpoint นี้ในการวิจัย** จึงไม่มี authoritative success/error response example หรือ server-side validation contract

## Observed facts — statuses and result data

[tracking result asset](https://voc.pea.co.th/_next/static/chunks/2rnibt3qbrui7.js) แสดง `VOC NO.`, `Case Type`, “สถานะการดำเนินงาน”, รายละเอียดประเด็น/ประเด็นย่อย, ความถี่, ความรุนแรง, รายละเอียด และตารางไฟล์แนบ. Asset map status strings ไป timeline ดังนี้:

กลุ่มหลักที่เห็นได้แก่ `SUBMITTED`, `PENDING`, `IN_PROGRESS`, `ASSIGNED`, `PROCESSING`, `FORWARDED`/`FORWARD`, `CAUSE_INVESTIGATION`, `PLANNED`, `IMPLEMENTING`, `REQUEST_ACCEPTANCE`, `CUS_ACCEPTED`/`CUS_UNACCEPTED`, `REVIEW`, `WAITING_CANCEL`, `CANCELLED`, หลายสถานะ `PRE_COMPLETED`/`WAITING_*COMPLETED*` และสถานะเปลี่ยนประเภท/หัวข้อ. completed family มี `COMPLETED`, `DONE`, `COMPLETED_FOUNDED`, `COMPLETED_UNFOUNDED`, `COMPLETED_ON_BEHALF`, `FORCE_COMPLETED`. UI รวมรายละเอียดเหล่านี้เป็น timeline ประมาณห้าตำแหน่ง

นี่เป็น **client-recognized vocabulary**, ไม่ใช่หลักฐานว่า backend จะคืนทุกค่า หรือเป็น exhaustive server enum. ไม่ได้ค้นเคสจริง จึงไม่เห็น response payload จริง

## Observed facts — privacy and security

- [VOC PDPA notice](https://voc.pea.co.th/PDPA.txt) อธิบายประเภทข้อมูล วัตถุประสงค์/ฐานกฎหมาย ผู้รับข้อมูล สิทธิ มาตรการ และการเก็บจนหมดความจำเป็น; form แสดง consent modal/checkbox, บังคับให้ scroll ถึงท้าย notice ก่อนกดยอมรับ และ link ไป [PEA PDPA](https://www.pea.co.th/pea-pdpa)
- แบบฟอร์มใช้การยืนยัน anti-bot ก่อน submit และมีความสามารถเลือกตำแหน่งจากแผนที่; รายงานนี้ไม่บันทึกค่ากำหนดหรือ key ใด ๆ จาก frontend
- หน้า public ตอบผ่าน HTTPS และมี HSTS; response ที่ตรวจใช้ `Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate`
- response หน้าเว็บที่ตรวจ **ไม่พบ** `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` หรือ `Referrer-Policy`; นี่เป็น header observation เท่านั้น ไม่ใช่ข้อสรุปว่า exploit ได้
- tracking client ใช้ `sessionStorage` flag หลัง search success แล้วอ่าน details ด้วย VOC number ใน path. ไม่ได้ทดสอบ direct API access, key-code enforcement, rate limiting, error equivalence หรือ authorization จึงต้องถือเป็น open security questions

## Comparison กับ local semantic actions และ fields

แหล่ง local authoritative: [`app/contracts.py`](../../app/contracts.py), [`app/tools/voc_tool.py`](../../app/tools/voc_tool.py), [`app/backends/simulated_voc.py`](../../app/backends/simulated_voc.py), [`app/agent/voc_intake.py`](../../app/agent/voc_intake.py), [`data/mock/voc_categories.json`](../../data/mock/voc_categories.json), และ [`CONTRACTS.md`](../../CONTRACTS.md).

| Local action | สิ่งที่ local ทำ | เทียบกับเว็บจริง |
|---|---|---|
| `list_categories` | คืน fixture 6 ค่า | สอดคล้องกับ cards หกใบในเชิง UX; ไม่พบ external endpoint ที่คืนหก cards แบบเดียวกัน และ public hierarchy มี taxonomy มากกว่าหกค่า |
| `prepare_case` | ตรวจ local schema, เก็บ draft ตาม `idempotencyKey`, ไม่มี side effect | เป็น safety abstraction ของ agent; เว็บใช้ client state/draft และไม่มี observed external prepare API |
| `submit_case` | internal-only หลัง explicit confirmation; คืน simulated `caseId`, `vocId`, `trackingKey`, status `submitted` | เว็บมี confirmation modal แล้ว POST `/api/request/submit`; response จริงไม่ได้สังเกต จึง map output ไม่ได้อย่าง authoritative |
| `get_case` | ต้องใช้ `vocId + trackingKey` และคืน status `submitted` เท่านั้น | conceptually ใกล้ `vocNumber + keyCode`; แต่ public client เปิด submit ด้วย VOC number อย่างเดียวและส่ง key code แบบ optional ขณะที่ result UI รู้จัก status มากกว่าหนึ่งค่า |

### Category mapping

| Local enum | Local label | หน้าแรก PEA VOC |
|---|---|---|
| `power_quality` | แจ้งปัญหาคุณภาพไฟฟ้า | ตรง |
| `service` | แจ้งปัญหาด้านบริการ | ตรง |
| `compliment` | ชื่นชม | ตรง |
| `tip_off` | แจ้งเบาะแส | ตรง |
| `operations` | แจ้งปัญหาการดำเนินงาน | ตรง |
| `stakeholder_feedback` | ชื่นชม เสนอแนะ ข้อคิดเห็น | ตรง |

หมายเหตุ local inconsistency: runtime enum/fixture มีหกค่าข้างต้น แต่ตารางเก่าใน [`CONTRACTS.md`](../../CONTRACTS.md#L271-L276) ยังอธิบาย category เป็น `billing|service|safety|other`. External spec ไม่ควรคัดลอก enum สี่ค่านี้

### Intake field mapping

| Current local field | ความสัมพันธ์กับเว็บ | ข้อสรุป |
|---|---|---|
| `category` | cards หกใบ + hierarchy หลายชั้น | ใช้เป็น high-level discriminator ได้ แต่ไม่พอแทน request type/topic/issue/sub-issue |
| `subject` | ไม่พบ free-text subject ที่ตรงกัน; เว็บใช้ hierarchy | local-only convenience field; อย่า map ไป `topic` แบบเงียบ ๆ |
| `detail` | ตรงกับ `details`/event detail โดยประมาณ | ใกล้ที่สุด แต่ local max 2000 ขณะที่ UI ที่ตรวจแสดง 250 characters |
| `contactName` | เว็บแยก prefix/firstName/lastName | ต้อง transform อย่าง explicit หรือเปลี่ยน schema; string เดียวสูญเสียโครงสร้าง |
| `contactPhone` | ตรงกับ phone ในเชิงความหมาย | local min 1/max 32 ไม่ตรง client rule 10 digits/ขึ้นต้น 0 |
| `location` | เว็บแยก contact address, incident address, target administrative area และ PEA office | string เดียวไม่พอสำหรับ external submit schema |
| `contactChannel` | ไม่พบ field เลือก phone/email/none บน form ที่ตรวจ | local-only; เว็บมี phone และ optional email แต่ไม่ใช่ channel enum |

ฟิลด์เว็บที่ local intake ขาด: CA, meter number, prefix/name parts, citizen ID, email, structured addresses, target PEA office, incident-location mode/coordinates, hierarchy IDs, frequency, severity, product importance, attachments, PDPA acceptance และ reCAPTCHA token

## Inferences / recommendations for a complete external OpenAPI

1. **แยก semantic facade ออกจาก PEA wire schema.** คง `prepare_case/submit_case` เป็น state machine ภายใน แต่กำหนด adapter DTO สำหรับ PEA form โดยไม่เรียก local model ว่า external payload
2. **ใช้ discriminated schemas ตาม flow** อย่างน้อย `power_quality`, `customer_voice`, `stakeholder_issue`, `stakeholder_feedback`; required fields และ step logic ไม่เหมือนกัน
3. **ห้ามออก operation `list_all_cases`** จากหลักฐานชุดนี้. ระบุเพียง track-one operation และบันทึกว่า public list capability not observed
4. **tracking input naming** ควรใช้ external `vocNumber`, `keyCode`; จะ expose semantic aliases `vocId`, `trackingKey` ก็ได้แต่ต้อง map ชัดเจน. อย่าใส่ server-side `required: [keyCode]` จนกว่าจะยืนยัน backend แม้ UX text ขอข้อมูลครบ
5. **status schema** ควรเป็น open string enum หรือ enum + unknown fallback จนมี backend spec; ห้ามลดเหลือ `submitted` หากเป้าหมายคือ external fidelity
6. **public GET catalogs** ที่ตรวจอาจใส่ใน research/reference OpenAPI ได้พร้อม exact observed response envelope แต่ไม่ควรรับรอง stability, SLA หรือ intended third-party use
7. **write operation ต้อง disabled by default** และต้องใช้ explicit human confirmation, reCAPTCHA/PDPA handling, credentials/authorization จาก PEA และ non-production verification ที่ได้รับอนุมัติก่อน ไม่มีหลักฐานรองรับ server-to-server bypass ของ browser controls
8. **ไม่ใช้ frontend configuration เป็น integration contract.** External spec ควรบันทึกเฉพาะ public routes, schemas และ capabilities ที่ตรวจได้ โดยไม่คัดลอกค่ากำหนดด้านความปลอดภัยจาก assets

## Open questions

- มี OpenAPI/Swagger หรือ integration documentation ทางการที่ PEA อนุมัติให้ third party หรือไม่? เส้นทางที่ลองแบบ read-only (`/api/docs`, `/api/openapi.json`, `/api/swagger-json`, `/api/v3/api-docs`) ไม่พบเอกสาร; `/api-json/` เป็น Next.js 404
- server-side request schema, requiredness, field formats, attachment count/aggregate limit และ error model ของ `POST /api/request/submit` คืออะไร?
- success response คืน VOC number/key code ใน payload หรือส่งเฉพาะ email/SMS? รูปแบบ/อายุ/entropy ของ key code คืออะไร?
- backend ยอมให้ค้นด้วย VOC number อย่างเดียวจริงหรือ client เพียงอนุญาตให้ส่ง request ที่จะ fail? มี rate limit, CAPTCHA, lockout และ generic errors เพื่อป้องกัน enumeration หรือไม่?
- `GET /api/voc-tracking/{vocNo}` บังคับ authorization/key-code server side อย่างไร? `sessionStorage` เป็นเพียง UX gate หรือมี server token/cookie ที่ไม่ได้เห็นจาก static asset?
- status enum ที่ server รองรับจริงและ transition graph คืออะไร? ค่า client-recognized ทั้งหมด active หรือเป็น legacy aliases?
- หน้าแจ้งเบาะแส submit แบบ anonymous ได้จริงหรือไม่ แม้ UI ไม่ทำเครื่องหมาย identity fields เป็น required?
- server เก็บข้อมูลส่วนบุคคล/ไฟล์แต่ละประเภทนานเท่าไร และใช้ deletion/revocation flow ใด?
- public catalog endpoints มี versioning, pagination, caching, authentication policy หรือ stability guarantee หรือไม่?
- high-level cards หกใบควร map ไป hierarchy IDs ใดในแต่ละ environment? IDs ใน public JSON เป็น UUID และไม่ควรถูก hard-code โดยไม่มี PEA contract

## Citation inventory

### First-party PEA web/API

- [PEA VOC home](https://voc.pea.co.th/)
- [VOC tracking](https://voc.pea.co.th/voc-tracking/)
- [Power-quality intake](https://voc.pea.co.th/report-power/)
- [Power-quality step 2](https://voc.pea.co.th/report-power/next-step-form)
- [Customer service issue intake](https://voc.pea.co.th/customer-voice/service-issue/)
- [Customer praise intake](https://voc.pea.co.th/customer-voice/praise/)
- [Customer tip intake](https://voc.pea.co.th/customer-voice/tip/)
- [Stakeholder issue intake](https://voc.pea.co.th/stakeholder-voice/issue/)
- [Stakeholder feedback intake](https://voc.pea.co.th/stakeholder-voice/feedback/)
- [Incident frequencies JSON](https://voc.pea.co.th/api/master-data/incident-frequencies?isActive=true)
- [VOC request types JSON](https://voc.pea.co.th/api/voc-hierarchy/request-types?activeOnly=true)
- [Complete hierarchy JSON](https://voc.pea.co.th/api/voc-hierarchy/complete)
- [PEA office JSON](https://voc.pea.co.th/api/pea-office)
- [Homepage client asset observed on review date](https://voc.pea.co.th/_next/static/chunks/18jc5808crmpv.js)
- [Tracking client asset observed on review date](https://voc.pea.co.th/_next/static/chunks/0rlogzckdjrya.js)
- [Common form/validation/success asset observed on review date](https://voc.pea.co.th/_next/static/chunks/11gznf_kl2s57.js)
- [Submit/payload client asset observed on review date](https://voc.pea.co.th/_next/static/chunks/2leo9scb1w0rk.js)
- [Customer form client asset observed on review date](https://voc.pea.co.th/_next/static/chunks/3rvshfj77hud6.js)
- [Tracking-result client asset observed on review date](https://voc.pea.co.th/_next/static/chunks/2rnibt3qbrui7.js)
- [VOC PDPA notice](https://voc.pea.co.th/PDPA.txt)
- [PEA personal-data policy](https://www.pea.co.th/pea-pdpa)

### Repository sources

- [`app/contracts.py`](../../app/contracts.py)
- [`app/tools/voc_tool.py`](../../app/tools/voc_tool.py)
- [`app/backends/simulated_voc.py`](../../app/backends/simulated_voc.py)
- [`app/agent/voc_intake.py`](../../app/agent/voc_intake.py)
- [`data/mock/voc_categories.json`](../../data/mock/voc_categories.json)
- [`CONTRACTS.md`](../../CONTRACTS.md)
