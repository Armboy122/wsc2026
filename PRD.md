# PEA One Agent — Product Requirements Document (MVP)

**สถานะเอกสาร:** Working product baseline  
**ประเภทผลิตภัณฑ์:** Hackathon / MVP demo  
**ภาษาหลัก:** ไทย  
**สถานะเผยแพร่:** Not ready for production

## 1. Executive Summary

PEA One Agent คือผู้ช่วยสนทนาหนึ่งจุดสำหรับงานบริการลูกค้า PEA ที่รวมการค้นหาความรู้ การดูข้อมูลบริการจำลอง การรับเรื่องร้องเรียน และการเตรียมรายการที่ต้องได้รับการยืนยันจากมนุษย์ก่อนดำเนินการ

MVP นี้ต้องพิสูจน์สามเรื่อง:

1. ผู้ใช้ถามคำถามภาษาไทยและได้รับคำตอบจากเอกสารที่ตรวจสอบย้อนกลับได้
2. Main Agent เลือกและประสาน tool ที่ถูกต้องโดยไม่สร้างข้อมูลปฏิบัติการขึ้นเอง
3. รายการที่แก้ไขข้อมูลต้องผ่าน `prepare → human confirm → submit` พร้อม idempotency และ trace

ผลิตภัณฑ์นี้เป็นเดโม ไม่ใช่ระบบบริการลูกค้า PEA สำหรับ production โดย OMS, Sabuy และ VOC ใช้ backend จำลอง และต้องแสดงสถานะ **SIMULATED** อย่างชัดเจน

### One-line pitch

> ผู้ช่วย PEA ภาษาไทยตัวเดียวที่ตอบจากเอกสารจริง ประสานบริการหลายระบบ และให้มนุษย์ควบคุมทุกการเขียนข้อมูล

## 2. Problem

ข้อมูลและ workflow บริการลูกค้ากระจายอยู่หลายแหล่ง ผู้ใช้ต้องรู้ว่าจะถามที่ไหนหรือใช้ระบบใด ขณะที่คำตอบจาก LLM ทั่วไปมีความเสี่ยงจากการเดาข้อมูล การอ้างอิงที่ตรวจสอบไม่ได้ และการดำเนินการแทนผู้ใช้โดยไม่มีการยืนยันที่ชัดเจน

MVP จึงต้องลดความซับซ้อนหน้าบ้านโดยคงความปลอดภัยหลังบ้าน:

- สนทนาด้วยภาษาธรรมชาติผ่านจุดเดียว
- ตอบความรู้จากหลักฐานที่เลือกจริง
- แยกข้อเท็จจริงจริงออกจากข้อมูลจำลอง
- แสดงสิ่งที่ระบบกำลังจะทำก่อนขอคำยืนยัน
- มี trace ที่ตรวจสอบได้โดยไม่เปิดเผย chain-of-thought หรือข้อมูลลับ

## 3. Target Users

### 3.1 ผู้ใช้ไฟฟ้า

ต้องการคำตอบหรือเริ่ม workflow บริการโดยไม่ต้องรู้โครงสร้างระบบภายใน

### 3.2 เจ้าหน้าที่สาธิต/กรรมการ

ต้องการเห็น critical path แบบ end-to-end หลักฐานอ้างอิง การเรียก tool สถานะจำลอง และ human confirmation ที่ตรวจสอบได้

### 3.3 ทีมพัฒนาและผู้ดูแลข้อมูล

ต้องการ contract ที่แน่นอน test ที่ทำซ้ำได้ และขอบเขตชัดเจนระหว่างเอกสารจริงกับระบบจำลอง

## 4. Product Principles

1. **Evidence before fluency** — คำตอบที่ลื่นไหลห้ามมีอำนาจเหนือหลักฐาน
2. **One agent, explicit tools** — ใช้ Main Agent หนึ่งตัวและ tool ระดับบนสุดที่ประกาศไว้เท่านั้น
3. **Human-controlled writes** — แชตเตรียมรายการได้ แต่ยืนยันแทนมนุษย์ไม่ได้
4. **Fail closed** — เมื่อหลักฐาน ข้อมูล หรือ validation ไม่พอ ให้ถามเพิ่มหรือแจ้งข้อจำกัด
5. **Simulation must be obvious** — ห้ามทำให้ผู้ใช้เข้าใจว่าข้อมูลจำลองมาจากระบบ PEA จริง
6. **MVP first** — พิสูจน์ critical path ก่อนเพิ่ม infrastructure หรือ abstraction
7. **Auditable, not introspective** — แสดง trace ของเหตุการณ์และผลลัพธ์ ไม่แสดง reasoning ภายใน

## 5. Goals

### G1 — Trusted knowledge answers

ตอบคำถามจากข้อความฉบับเต็มของเอกสารที่เกี่ยวข้อง พร้อม citation ที่ตรวจสอบได้ว่าอยู่ในไฟล์จริง

### G2 — Correct tool orchestration

เลือก tool/action ตามเจตนาและข้อมูลที่ผู้ใช้ให้ ถ้าข้อมูลไม่ครบต้องถามเฉพาะข้อมูลที่ขาด และห้ามสร้างค่าขึ้นเอง

### G3 — Safe transaction preparation

รองรับการเตรียมรายการเขียน การยืนยันหรือปฏิเสธผ่าน endpoint เฉพาะ และป้องกันการ submit ซ้ำ

### G4 — Transparent demo experience

หน้าเว็บต้องแสดงคำตอบ citation tool result pending action trace และป้าย simulation อย่างเข้าใจง่ายบนมือถือและเดสก์ท็อป

### G5 — Repeatable evaluation

พฤติกรรม deterministic ที่สำคัญต้องตรวจด้วย automated tests/evaluation cases และแยกจากการประเมินคุณภาพภาษาของโมเดล

## 6. Non-goals

MVP นี้ไม่ครอบคลุม:

- การเชื่อม CRM, OMS, billing, payment หรือระบบ PEA production จริง
- การตัดเงินจริงหรือแก้ไขข้อมูลลูกค้าจริง
- authentication และ authorization สำหรับ production หลายผู้ใช้
- persistent production database หรือการรับประกันสถานะหลัง process restart
- การยืนยันอัตโนมัติ การยืนยันด้วยข้อความแชต หรือ background submission
- vector database, embedding, chunk retrieval, document chunking หรือ RAG สำรอง
- multi-agent topology, microservices, event bus หรือ queue
- ระบบเรียนรู้จากแชตหรือเผยแพร่คำตอบเจ้าหน้าที่โดยอัตโนมัติ
- production-scale observability, availability หรือ performance hardening

รายละเอียดงานเรียนรู้จากคำถามที่ตอบไม่ได้เป็น roadmap แยกใน `docs/plans/qa-learning-roadmap.md`

## 7. MVP Scope

Contract เป้าหมายกำหนด Main Agent หนึ่งตัวและสี่ tool:

| Capability | Tool | MVP behavior | Data status |
|---|---|---|---|
| ความรู้ PEA | `knowledge_tool` | เลือกเอกสารและตอบจากข้อความเต็มพร้อม citation | เอกสารจริงที่ต้องผ่านการอนุมัติ |
| บัญชี/การชำระเงิน | `sabuy_tool` | ดูบัญชีตัวอย่างและเตรียมการชำระเงิน | Simulated |
| เสียงลูกค้า/ร้องเรียน | `voc_tool` | แสดงหมวด เตรียมเคส ส่งหลังยืนยัน และติดตามด้วยคีย์ | Simulated |
| ไฟฟ้าขัดข้อง | `oms_tool` | ดูสถานะและเตรียมรายงานพร้อม safety message | Simulated |

> หมายเหตุสถานะ implementation: contract และเอกสารสถาปัตยกรรมระบุครบสี่ tool แต่ runtime catalogue ใน `app/agent/main_agent.py` ปัจจุบันเปิดใช้ `knowledge_tool` และ `voc_tool` ขณะที่ Sabuy/OMS ถูกคอมเมนต์ออก การนำเสนอหรือ release claim ต้องยึดพฤติกรรมที่ทดสอบได้จริง ณ เวลานั้น ไม่ยึดเอกสารเพียงอย่างเดียว

### 7.1 Voice Mode (Gemini Live) — ส่วนเพิ่มเติมของ MVP

โหมดเสียงเป็น **ช่องทางขนส่งเรียลไทม์เพิ่มเติม** บน Main Agent เดิม ไม่ใช่ตัวแทนหรือ
ขอบเขตความสามารถใหม่:

| รายการ | ค่าใน MVP |
|---|---|
| ช่องทางขนส่ง | Gemini Live API (เสียง + การถอดเสียง) ผ่าน WebSocket `/ws/live` เดียวต่อเซสชันเบราว์เซอร์ |
| ตัวแทนธุรกิจ | Main Agent ตัวเดิมเท่านั้น (`app/agent/main_agent.py`) — Voice Bridge เป็นตัวกลางบาง ๆ ไม่ใช่ตัวแทนแยก |
| ขอบเขตความสามารถ | Knowledge และ VOC เท่านั้น (ตรงกับ runtime catalogue ที่เปิดใช้) |
| เมทอดที่เรียก | `handle_chat` / `confirm_pending_action` / `reject_pending_action` เท่านั้น |
| การยืนยัน/ปฏิเสธด้วยเสียง | ผูกกับเซสชัน — โมเดลไม่รับ/ส่ง `pendingActionId` ระบบเลือก "รายการปัจจุบัน" ของเซสชันเอง และ fail closed เมื่อไม่มีรายการ |
| ความกำกวม | โมเดลต้องถามย้ำและห้ามเรียกฟังก์ชันตัดสินใจเมื่อคำตอบไม่ชัดเจน |
| สถานะโมเดล | `gemini-3.1-flash-live-preview` (Preview) — ยังไม่ใช่ GA และอาจเปลี่ยนพฤติกรรม/เสียง |
| ข้อมูล VOC | SIMULATED เช่นเดียวกับช่องทางข้อความ |

## 8. Critical User Journeys

### J1 — Ask a knowledge question

```text
ผู้ใช้ถามภาษาไทย
→ Main Agent เลือก knowledge search
→ Document Router เลือกไฟล์จาก allowlist
→ โหลดข้อความเต็มของไฟล์ที่เลือก
→ โมเดลตอบจากข้อความนั้นเท่านั้น
→ ตรวจ citation/snippet
→ แสดงคำตอบและแหล่งอ้างอิง
```

หากไม่มีหลักฐาน ต้องคืน no-evidence หรือขอคำชี้แจง ห้ามตอบจากความจำโมเดล

### J2 — Continue a knowledge conversation

คำถามต่อเนื่องต้องใช้บริบทก่อนหน้าเพื่อระบุหัวข้อเท่านั้น และเรียก knowledge search ใหม่เพื่อสร้างหลักฐานสำหรับคำตอบรอบปัจจุบัน

### J3 — Prepare and confirm a write

```text
ผู้ใช้ขอดำเนินการ
→ ตรวจข้อมูลที่จำเป็น
→ ถามข้อมูลที่ขาด
→ prepare_* และแสดงสรุป
→ ผู้ใช้กดยืนยันผ่าน confirm endpoint
→ submit_* หนึ่งครั้ง
→ แสดงผลลัพธ์และ trace
```

การยืนยันซ้ำต้องคืนผลเดิมและไม่สร้าง side effect ซ้ำ

### J4 — Reject a prepared write

ผู้ใช้ปฏิเสธผ่าน reject endpoint รายการต้องเข้าสถานะ terminal และ submit ภายหลังไม่ได้

### J5 — Submit and track a VOC case

ระบบเก็บหมวด หัวข้อ รายละเอียด ชื่อ เบอร์โทร และสถานที่ให้ครบก่อน prepare หลัง submit จึงคืน `vocId` และ `trackingKey` ซึ่งต้องใช้คู่กันเมื่อติดตาม

### J6 — Inspect and reset the demo

ผู้สาธิตเปิดดู trace ที่เรียงตามลำดับและปกปิดข้อมูลแล้ว จากนั้น reset conversation, pending actions, simulated state และ traces เพื่อเริ่มเดโมใหม่ได้

### J7 — Voice conversation with spoken confirmation/rejection

```text
ผู้ใช้กดปุ่มไมโครโฟนและพูด
→ เบราว์เซอร์ส่ง PCM16 16kHz เป็น binary ผ่าน /ws/live (same-origin WebSocket)
→ Gemini Live ถอดเสียง → เรียก pea_agent_chat → Voice Bridge ส่งต่อ Main Agent
→ Main Agent ตอบ/เตรียมรายการ → bridge เก็บเฉพาะ pendingActionId ปัจจุบันของเซสชัน
→ ผู้ช่วยเสียงสรุปและถามยืนยัน/ปฏิเสธอย่างชัดเจน
→ ผู้ใช้พูด "ยืนยัน" → pea_confirm_pending_action (ไม่รับ id จากโมเดล)
→ submit_* หนึ่งครั้งผ่าน Main Agent → ล้างสถานะสิ้นสุดของเซสชัน
→ หากคำตอบกำกวม ให้ถามย้ำ ห้ามเรียกฟังก์ชันตัดสินใจ
```

## 9. Functional Requirements

### FR-1 Conversation

- รับข้อความที่ไม่ว่างผ่าน `POST /api/v1/chat`
- รักษา `conversationId` สำหรับบทสนทนาต่อเนื่อง
- ส่งคืน `traceId`, message, citations, tool results และ pending action ตาม contract
- ถ้าไม่มี tool ที่ตรง ให้แจ้งว่าไม่รองรับโดยไม่เลือก tool แบบคาดเดา

### FR-2 Knowledge grounding

- Router เห็นเฉพาะ query และ catalog ระดับเอกสาร
- เลือกเฉพาะ `sourceId` ใน allowlist และไม่เกิน `maxResults`
- ส่งข้อความเต็มของไฟล์ที่เลือกให้โมเดลโดยไม่ตัดท้ายอย่างเงียบ ๆ
- citation ต้องอ้างไฟล์ที่เลือกและ snippet ต้องพบในข้อความจริง
- เมื่อหลักฐานไม่พอ ให้ fail closed

### FR-3 Tool safety

- Tool/action/input/output ต้องผ่าน typed validation
- runtime ต้องปฏิเสธ tool ที่ไม่รู้จัก action ที่ไม่ตรง tool และ submit action จากแชต
- ข้อเท็จจริงด้านบัญชี เคส การชำระเงิน และไฟดับต้องมาจาก typed tool result เท่านั้น

### FR-4 Pending actions

- Chat เรียกได้เฉพาะ read action และ `prepare_*`
- เฉพาะ confirm endpoint เท่านั้นที่นำไปสู่ `submit_*`
- Confirm และ reject ต้อง idempotent ตาม terminal state
- `idempotencyKey` ต้องป้องกัน duplicate submission

### FR-5 Trace and redaction

- บันทึก event ตามลำดับด้วย sequence ที่เพิ่มขึ้น
- ปกปิด payload ที่ละเอียดอ่อนก่อนจัดเก็บหรือแสดง
- ไม่เก็บหรือแสดง chain-of-thought, hidden prompt หรือ credential

### FR-6 Demo UI

- ใช้ API v1 จาก same origin
- รองรับสถานะ loading, validation, network error, 404, 409, 422 และ 5xx
- แสดง citations, pending action, confirm/reject, trace และ simulation labels
- รองรับ keyboard, focus, screen-reader announcements, reduced motion และ touch target ที่เหมาะสม

### FR-7 Configuration

- Main, Knowledge และ Judge เลือก provider/model แยกกันผ่าน environment
- Credential ต้องไม่ปรากฏใน repository, health response, logs หรือ object representation
- ห้ามอ้างว่า provider ทำงานจริงจนกว่าจะยืนยันด้วย real request

## 10. Product Safety Requirements

1. **Human confirmation:** ไม่มี write ใดเกิดจาก chat message เพียงอย่างเดียว
2. **Idempotency:** confirm ซ้ำไม่สร้างรายการซ้ำ
3. **Simulation disclosure:** ทุก operational result ต้องมีและแสดง `simulation: true`
4. **Knowledge provenance:** ทุก factual knowledge answer ต้องย้อนกลับไปยังเอกสารที่เลือกได้
5. **No secret exposure:** health, trace, log และ UI ห้ามเปิดเผย credential หรือ sensitive payload
6. **No prompt disclosure:** ปฏิเสธคำขอ system prompt, chain-of-thought และ reasoning ภายใน
7. **Electrical safety:** OMS output ต้องมี safety message และแสดงก่อนคำอธิบายอื่น
8. **No false escalation:** ห้ามอ้างว่าสร้าง ticket หรือส่งต่อสำเร็จจนกว่าระบบปลายทางจริงตอบรับ

## 11. UX Requirements

- ภาษาไทยเป็นค่าเริ่มต้นและใช้ถ้อยคำธรรมชาติ
- แยกคำตอบ หลักฐาน ข้อมูลจำลอง และ action ที่รอยืนยันให้เห็นชัด
- ผู้ใช้ต้องเข้าใจสิ่งที่จะเกิดขึ้นก่อนกดยืนยัน
- Error message ต้องบอกข้อจำกัดหรือสิ่งที่ต้องแก้โดยไม่เปิดเผยรายละเอียดภายใน
- Critical path ต้องใช้งานได้บน viewport มือถือ
- UI สำหรับเดโมควรเรียบง่ายและไม่พึ่ง build pipeline โดยไม่จำเป็น

## 12. Success Metrics

เกณฑ์ต่อไปนี้ใช้เป็น product acceptance ไม่ใช่ production SLA:

| Metric | MVP target |
|---|---|
| Contract compliance | ชุดทดสอบ route/schema ที่เกี่ยวข้องผ่านทั้งหมด |
| Citation validity | citation ที่คืนต้องอ้างไฟล์ที่เลือกและ snippet ตรวจพบได้ทั้งหมด |
| Unsupported/no-evidence safety | ไม่สร้างคำตอบหรือ tool call ทดแทนเมื่อไม่มีหลักฐาน/ความสามารถ |
| Write safety | ทุก write path ผ่าน prepare/confirm/submit และ duplicate confirm ไม่ submit ซ้ำ |
| Trace safety | event เรียงลำดับและไม่พบข้อมูลลับ/chain-of-thought ใน trace |
| Simulation clarity | operational result และ UI ระบุ SIMULATED ชัดเจน |
| Critical journey completion | เส้นทางเดโมที่เปิดใช้งานจริงทำงาน end-to-end |
| Evaluation quality | evaluator ที่กำหนดสำหรับ capability ที่ release ผ่านเกณฑ์ที่ทีมอนุมัติ |

ตัวเลขจำนวนเอกสารและจำนวน test เปลี่ยนได้ตาม repository จึงควรดึงจากผลรันล่าสุดสำหรับสไลด์ ไม่ควรคัดลอกตัวเลขเก่าจากเอกสารโดยไม่ตรวจซ้ำ

## 13. Demo Story for Slides

### Slide 1 — Problem

บริการและความรู้กระจายหลายระบบ ขณะที่ AI ที่ไม่มีหลักฐานอาจตอบผิดหรือดำเนินการเกินสิทธิ์

### Slide 2 — Solution

Main Agent หนึ่งตัวเชื่อม knowledge และ operational tools ผ่านบทสนทนาภาษาไทย พร้อม human confirmation

### Slide 3 — Trusted Knowledge

Document Router เลือกเอกสารที่เกี่ยวข้อง ส่งข้อความเต็มเข้า long context และตรวจ citation กับไฟล์จริง

### Slide 4 — Safe Actions

แชตทำได้เพียง prepare ผู้ใช้ต้องยืนยันผ่าน endpoint เฉพาะ และระบบป้องกัน duplicate submit

### Slide 5 — Transparent Demo

UI แสดง source, tool, pending action, simulation status และ redacted trace โดยไม่เปิดเผย reasoning

### Slide 6 — Validation and Next Step

แสดงผล test/evaluation ล่าสุดที่รันจริง สิ่งที่ยังจำลอง และ gate ก่อน production

## 14. Acceptance Criteria

MVP ถือว่าพร้อมสำหรับการสาธิตเมื่อ:

- แอปเริ่มทำงานและหน้าเว็บเรียก API v1 ได้
- Knowledge journey ที่เลือกสำหรับเดโมตอบจากเอกสารจริงพร้อม citation ที่ผ่าน validation
- Capability ที่ประกาศว่าเปิดใช้ในเดโมผ่านเส้นทาง end-to-end จริง
- Prepare/confirm/reject แสดง state transition และ idempotency ได้
- Trace แสดง event ตามลำดับและปกปิดข้อมูลสำคัญ
- UI แสดง simulation status อย่างต่อเนื่อง
- Automated checks ที่เกี่ยวข้องผ่าน
- ข้อจำกัดและ capability ที่ยังไม่เปิดใช้ถูกสื่อสารตรงตามจริง

MVP ยังไม่พร้อม production จนกว่า:

- เจ้าของข้อมูลอนุมัติ source documents และความเป็นปัจจุบัน
- live evaluation ครบชุดที่กำหนดผ่านเกณฑ์
- real integrations ผ่าน security/privacy review
- authentication, authorization, persistence, monitoring และ operational controls ถูกออกแบบและตรวจสอบ
- ผู้ใช้อนุมัติการ deploy อย่างชัดเจน

## 15. Current Status and Known Gaps

สถานะต้องตรวจจาก code และผลรันล่าสุดก่อนนำเสนอ เนื่องจากเอกสารเดิมบางส่วนมีตัวเลขหรือ capability claim ต่างกัน

Known gaps ณ baseline นี้:

- Runtime tool catalogue เปิด Knowledge และ VOC แต่ยังไม่เปิด Sabuy/OMS แม้ contract เป้าหมายระบุครบสี่ tool
- Operational integrations ทั้งหมดยังเป็น simulated backends
- Knowledge live verification ที่บันทึกไว้เป็นเพียงบางกรณี ไม่ใช่ full live evaluation
- จำนวน DOCX และจำนวน tests ที่ระบุใน `README.md` กับ `docs/integration_report.md` ไม่ตรงกันและอาจล้าสมัย
- ข้อมูลใน process สูญหายเมื่อ restart
- ยังไม่มี authentication/authorization สำหรับ production
- Workflow ส่งคำถามที่ตอบไม่ได้ให้เจ้าหน้าที่เป็นข้อความแจ้งเท่านั้น ยังไม่มี ticket integration จริง
- โหมดเสียงใช้ `gemini-3.1-flash-live-preview` (Preview) — ตรวจสอบสดด้วย key จริงแล้วว่า `/ws/live` เชื่อมต่อและ SDK รับ transcription/PCM audio ได้ แต่ยังไม่มีการทดสอบไมโครโฟน/ลำโพงจริงแบบอัตโนมัติ ต้องซ้อมสดด้วยมือก่อนนำเสนอ
- โหมดเสียงเปิดใช้เฉพาะ Knowledge และ VOC และต้องใช้เบราว์เซอร์ที่รองรับ AudioWorklet/getUserMedia (แนะนำ Chrome/Edge ล่าสุด)

ก่อนทำสไลด์ release/demo ให้รัน test/evaluator และอัปเดตหลักฐานสถานะในเอกสารที่เกี่ยวข้อง

## 16. Roadmap

### Phase 0 — Current MVP

- Knowledge grounded by full-document evidence
- Simulated operational workflows
- Human confirmation and audit trace
- Single-page Thai demo UI

### Phase 1 — Demo completeness

- ตัดสินใจว่าจะเปิด Sabuy/OMS ใน runtime demo หรือปรับ scope/contract ให้ตรงกับ capability ที่นำเสนอ
- ทำ live evaluation ครบชุดที่ประกาศ
- ยืนยันและจัด version ของ knowledge sources
- ทำ demo script และ evidence snapshot ที่สร้างซ้ำได้

### Phase 2 — Controlled learning loop

- persistent redacted conversation log
- unanswered queue
- staff review and approval
- versioned Approved Q&A lifecycle

### Phase 3 — Production discovery

- identity, authorization, consent และ privacy requirements
- real backend contracts and sandbox environments
- reliability, monitoring, incident response และ data retention
- security review ก่อน real write integration

แต่ละ phase ต้องเริ่มเมื่อ requirement และ owner ชัดเจนเท่านั้น ห้ามสร้าง production infrastructure ล่วงหน้าเพื่อรองรับสมมติฐาน

## 17. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated knowledge | Full-document grounding, citation validation, no-evidence fallback |
| Wrong tool/action | Fixed catalogue, typed schemas, allowlist, fail-closed validation |
| Accidental or duplicate write | Prepare/confirm/submit state machine and idempotency |
| Demo mistaken for production | Persistent SIMULATED labels and explicit release status |
| Sensitive data leakage | Redaction, secret-safe configuration, bounded trace fields |
| Stale or unapproved documents | Data-owner approval and version/inventory gate |
| Documentation drift | Verify against code/tests and record current evidence before claims |
| Overengineering delays MVP | Vertical slices, risk-driven tests, smallest safe change |

## 18. Source-of-Truth Hierarchy

ใช้ลำดับนี้เมื่อเอกสารขัดแย้งกัน:

1. Direct user-approved product decision
2. `PRD.md` — product goals, scope, user journeys, acceptance
3. `CONTRACTS.md` และ `app/contracts.py` — public/tool contracts; ต้องสอดคล้องกัน
4. `ARCHITECTURE.md` — technical topology, boundaries, and design decisions
5. Executable code and automated tests — current implementation evidence
6. `docs/integration_report.md` — dated verification evidence
7. `README.md` และ component README — setup and operational guidance
8. Optional plans/research — non-binding future work

หาก product intent กับ current implementation ไม่ตรงกัน ให้รายงาน gap และขอ/บันทึกการตัดสินใจ ห้ามแก้เอกสารหรือโค้ดให้ดูสอดคล้องโดยซ่อนความแตกต่าง

## 19. Reference Map

- Product requirements and presentation baseline: `PRD.md`
- Coding-agent working rules: `AGENTS.md`
- Technical architecture: `ARCHITECTURE.md`
- Frozen API/tool contracts: `CONTRACTS.md`
- Executable schemas: `app/contracts.py`
- Setup and current headline status: `README.md`
- Verification evidence: `docs/integration_report.md`
- Optional QA learning roadmap: `docs/plans/qa-learning-roadmap.md`
- Web demo behavior: `web/README.md`
