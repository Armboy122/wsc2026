# PEA One Agent — สถาปัตยกรรมสำหรับเดโม

## สรุปการตัดสินใจ

สร้างโพรเซส FastAPI หนึ่งโพรเซสที่มี **Main Agent** เพียงหนึ่งตัว และโมดูลเครื่องมือระดับบนสุดที่เรียกใช้ได้สองโมดูลเท่านั้น:

1. `knowledge_tool`
2. `oms_tool`

Sabuy และ VOC คงเฉพาะ implementation/contracts/isolated tests แบบ dormant และไม่ลงทะเบียนใน runtime catalogue

นี่คือการออกแบบโมดูลที่มีขนาดเล็กแต่มีความลึกโดยตั้งใจ: ตัวจัดการ HTTP ทำหน้าที่เพียงตรวจสอบและแปลงคำขอ; Main Agent รับผิดชอบการประสานงาน นโยบาย และคำตอบสำหรับผู้ใช้ ส่วนโมดูลเครื่องมือรับผิดชอบความหมายของข้อมูลที่เกี่ยวข้องและรายละเอียดของระบบหลังบ้านจำลอง งานนี้ไม่ครอบคลุม LangGraph, LangChain, คิว, ไมโครเซอร์วิส, ฐานข้อมูลเวกเตอร์ที่สร้างเอง หรือการผสานระบบ PEA จริง

## โทโพโลยีของเดโม

```text
Browser / judge client
        |
        v
FastAPI routes (/api/v1/*, /health)
        |
        +-- Request/response contract validation (Pydantic)
        |
        v
Main Agent  <---->  LLMAdapter (judge-provided LLM implementation)
    |  |
    |  +--------> oms_tool ------> httpx → External OMS REST (gateway จริงเป็น source of truth)
    +-----------> knowledge_tool -> Document Router -> Full selected DOCX text -> Gemini Long Context

Sabuy/VOC implementation + contracts + isolated tests: dormant, not registered
        |
        v
TraceStore + PendingActionStore (in-process, resettable demo state)

Browser voice UI (AudioWorklet capture -> PCM16 16kHz, PCM16 24kHz playback)
        |
        v
WebSocket /ws/live  -->  GeminiLiveSession (Gemini Live API, one per socket)
                              |
                              v
                         VoiceBridge (session-bound: conversationId + current pendingActionId)
                              |
                              v
                         Main Agent (sole business agent; handle_chat / confirm / reject only)
```

## โมดูลและจุดเชื่อมต่อขณะทำงาน

### โมดูล HTTP

**ส่วนเชื่อมต่อ:** route ที่จัดทำเอกสารไว้ใน `CONTRACTS.md` โมดูลนี้ตรวจสอบ input เรียก operation ของ Main Agent หนึ่งรายการ และส่งคืนโมเดลตาม frozen contract โดยไม่มี business policy และไม่เรียก tool โดยตรง

### โมดูล Main Agent

**ส่วนเชื่อมต่อ:** `handle_chat`, `confirm_pending_action`, `reject_pending_action`, `get_trace` และ `reset_demo`

โมดูลนี้เป็นตัวประสานงานที่ขับเคลื่อนด้วยโมเดลเพียงตัวเดียว โดยทำหน้าที่ดังนี้:

- รับข้อความผู้ใช้และแยก conversation history, workflow state และผลลัพธ์จาก tool ออกจากกัน;
- ใช้ agent loop แบบ bounded โดยค่าเริ่มต้นไม่เกิน 12 agent steps/12 tool calls ต่อหนึ่งข้อความ และหยุดทันทีเมื่อพบ Knowledge call ซ้ำ;
- เรียกเฉพาะ tool ระดับบนสุดที่เปิดใช้งานใน runtime catalogue ซึ่งปัจจุบันคือ Knowledge และ OMS; Sabuy/VOC ไม่ลงทะเบียน;
- ถือว่าผลลัพธ์จาก tool เป็นข้อเท็จจริงที่มีอำนาจเหนือข้อความจากโมเดล และไม่รวม no-evidence เข้ากับคำตอบที่มี citation แล้ว;
- บังคับ OMS flow แบบมี CA ให้ GET ก่อน prepare เสมอ และใช้ anonymous prepare เมื่อไม่มี CA;
- สร้าง pending action หลังจากได้รับผลลัพธ์ `prepare_*` ที่สำเร็จ;
- ส่งคำขอเขียนหลังจากมีการเรียก confirm route อย่างชัดเจนเท่านั้น;
- สร้าง trace event ตามลำดับ;
- สร้างคำตอบแชตสุดท้าย

โมดูลนี้ต้องไม่เปิดเผย sub-agent, agent แยกตาม tool หรือ tool ที่ไม่ได้ประกาศไว้ tool อาจมีโค้ด helper ภายในได้ แต่จะไม่มีการลงทะเบียน tool ระดับบนสุดเพิ่มเติมกับ LLM

### โมดูล Voice (Gemini Live)

**ส่วนเชื่อมต่อ:** `app/live/bridge.py` (`VoiceBridge`), `app/live/gemini_live.py` (`GeminiLiveSession`) และ `app/api/live.py` (`/ws/live`)

โหมดเสียงเป็นช่องทางขนส่งเรียลไทม์เพิ่มเติมบน Main Agent เดิม โดยมีหลักการดังนี้:

- **หนึ่ง WebSocket เป็นเจ้าของชุดสถานะหนึ่งชุด** ได้แก่ Gemini session, `VoiceBridge`, audio queue และ `conversationId` ของเซสชัน (สร้างใหม่ทุก socket)
- **Voice Bridge เรียก Main Agent ได้เพียงสามเมทอด** คือ `handle_chat`, `confirm_pending_action`, `reject_pending_action` ผ่านโปรโตคอล `MainAgentGateway` และไม่แตะ ToolRegistry หรือ backend ธุรกิจใด ๆ
- ไมโครโฟนของเบราว์เซอร์ถูก downsample เป็น **PCM16 16kHz** ส่งเป็น binary ผ่าน WebSocket; เสียงตอบกลับเป็น **PCM16 24kHz** เล่นแบบ gap-free scheduling และ flush ทันทีเมื่อมี `audio.interrupted` (ผู้พูดแทรก)
- **ฟังก์ชันที่โมเดลเรียกได้มีสามตัวเท่านั้น**: `pea_agent_chat`, `pea_confirm_pending_action`, `pea_reject_pending_action` — ไม่มีฟังก์ชันใดรับ/ส่ง `pendingActionId`; การยืนยัน/ปฏิเสธผูกกับรายการปัจจุบันของเซสชัน และ fail closed เมื่อไม่มีรายการ (`no_pending_action`)
- **โมเดลเป็นเพียงส่วนติดต่อเสียง**: system instruction บังคับให้ส่งต่อทุกคำขอ PEA ไปยัง Main Agent, ห้ามสร้างข้อเท็จจริง/สถานะเรื่องขึ้นเอง, ห้ามตัดสินใจเมื่อคำตอบกำกวม (ถามย้ำก่อน), และห้ามขอ/รับ/ส่ง pending action id
- สถานะการเขียนยังเป็นไปตามกลไก `prepare → human confirm → submit` เดิม — เสียงเป็นเพียงวิธีบอก "ยืนยัน/ปฏิเสธ" เท่านั้น

### จุดเชื่อมต่อ `LLMAdapter`

Main Agent ขึ้นต่อส่วนเชื่อมต่อที่ไม่ผูกกับผู้ให้บริการรายใด ไม่ใช่ SDK ของกรรมการ:

```python
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

`LLMRequest` ประกอบด้วย messages, แค็ตตาล็อก tool สองรายการที่ลงทะเบียนแบบ typed และกำหนดตายตัว และ correlation id ส่วน `LLMResponse` ประกอบด้วย text และค่า `ToolCall` ตั้งแต่ศูนย์รายการขึ้นไป อะแดปเตอร์สำหรับกรรมการจะแปลงโครงสร้าง SDK ของตนเป็น contract ภายในเหล่านี้ โดย `ScriptedLLMAdapter` เพียงพอสำหรับเดโม/การทดสอบที่กำหนดผลได้แน่นอน

อะแดปเตอร์ต้องไม่มีนโยบายของ PEA, ข้อมูลลับในผลลัพธ์ trace หรือการเข้าถึงระบบหลังบ้านโดยตรง

### จุดเชื่อมต่อของโมดูล Tool

แต่ละ tool มีส่วนเชื่อมต่อแบบจำกัดขอบเขตหนึ่งรายการ:

```python
class Tool(Protocol):
    name: ToolName
    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult: ...
```

Tool Registry ถูกกำหนดตายตัวเมื่อเริ่มระบบให้มีเฉพาะชื่อ tool ที่ต้องการทั้งสี่ชื่อ โดยจะปฏิเสธชื่อที่ไม่รู้จักและกรณี action/name ไม่ตรงกันก่อนเรียก backend

### อะแดปเตอร์ระบบหลังบ้าน

- `FullDocumentKnowledgeBackend` ใช้ **Document Routing + Full-file Long Context** โดยไม่ใช้ Gemini File Search, vector search, embedding หรือ chunk retrieval
- ขั้นเลือกเอกสารส่งเฉพาะคำถามและ catalog ระดับเอกสาร (รหัสไฟล์ ชื่อไฟล์ และหัวข้อ) ให้โมเดลเลือกไฟล์ที่เกี่ยวข้องไม่เกิน `maxResults` รายการ รหัสไฟล์ที่โมเดลส่งคืนต้องอยู่ใน allowlist ของ catalog เท่านั้น
- หลังเลือกแล้ว backend ต้องอ่านและแปลง **ข้อความฉบับเต็มของทุกไฟล์ที่เลือก** จาก `knowledge/source/` และส่งข้อความทั้งหมดพร้อมคำถามให้ Gemini Long Context ห้ามตัดเฉพาะบาง chunk หรือเติมไฟล์ที่ไม่เกี่ยวข้อง
- หากคำถามเกี่ยวข้องหลายหัวข้อให้เลือกหลายไฟล์ฉบับเต็ม หากกำกวมหรือไม่มีไฟล์ที่ตรงต้องคืน no-evidence เพื่อให้ Main Agent ถามกลับหรือแจ้งว่าไม่มีข้อมูล ห้ามเดาคำตอบ
- คำตอบต้องอ้างอิงเฉพาะไฟล์ที่ถูกเลือก และ citation ต้องใช้รหัสไฟล์/ชื่อไฟล์จริงพร้อมข้อความหลักฐานที่ตรวจสอบได้ว่าอยู่ในไฟล์นั้น
- backend อาจ cache ข้อความฉบับเต็มที่แปลงแล้วใน memory ได้ แต่ห้ามใช้ cache เป็นดัชนีค้น chunk หากไฟล์ที่เลือกทั้งหมดเกิน context budget ต้องลดชุดผ่านการถามให้ชัดเจนหรือ fail closed ห้ามตัดท้ายไฟล์โดยเงียบ
- `SimulatedVocBackend` ใช้ข้อมูล fixture ใน memory แบบ deterministic; OMS เป็น connector ภายนอกผ่าน httpx โดยถือ endpoint จริงของ gateway เป็น source of truth คำตอบของระบบเหล่านี้มี `simulation: true` และจะไม่มีการกล่าวอ้างว่า action ได้ส่งถึง PEA แล้ว

สำหรับเดโม 2 วัน store จะอยู่ภายใน process และ reset ได้ การสูญเสียสถานะหลัง restart เป็นสิ่งที่ยอมรับได้และมีการระบุไว้ใน UI/สคริปต์เดโม

## กลไกสถานะสำหรับความปลอดภัยในการเขียน

การดำเนินการทั้งหมดที่แก้ไขข้อมูลต้องเป็นไปตามเงื่อนไขคงที่นี้:

```text
prepare_* -> pending_confirmation -> confirm endpoint -> submit_* -> submitted | failed
                              \-> reject endpoint -> rejected
```

กฎ:

1. request แชตเรียกได้เฉพาะ read action และ action `prepare_*`
2. `prepare_*` ตรวจสอบ payload ที่ร้องขอและส่งคืน `PendingAction`; โดยไม่ก่อให้เกิด simulated side effect
3. เฉพาะ `POST /api/v1/actions/{pending_action_id}/confirm` เท่านั้นที่เปลี่ยน pending action ไปสู่การ submission ได้
4. การยืนยันต้องเป็น idempotent: การยืนยันซ้ำจะส่งคืน terminal result เดิมและต้องไม่ submit ซ้ำ
5. การปฏิเสธเป็น terminal และ idempotent; action ที่ถูกปฏิเสธแล้วจะไม่มีวันถูก submit
6. `submit_*` เป็นการเรียกจาก Main Agent ไปยัง tool ภายใน ไม่ใช่ action ที่ LLM เลือกระหว่างการแชต
7. trace บันทึก preparation, confirmation/rejection, submission และผลลัพธ์ โดยปกปิดข้อมูลใน payload

ไม่มี endpoint ใดรับคำสั่งจาก client เช่น `confirmed=true` เพื่อใช้แทน confirm route

## ลำดับความสำคัญของข้อมูลและความจริง

1. ผลลัพธ์จาก typed tool ที่สำเร็จเป็นแหล่งข้อมูลที่เชื่อถือได้สำหรับข้อเท็จจริงเชิงปฏิบัติการและผลลัพธ์ของ transaction
2. สำหรับ knowledge แหล่งข้อมูลที่เชื่อถือได้คือข้อความฉบับเต็มจากไฟล์ที่ Document Router เลือกเท่านั้น คำตอบจาก Gemini ใช้ได้เมื่ออ้างอิงไฟล์ที่เลือกและมี citation ซึ่งตรวจสอบย้อนกลับไปยังข้อความในไฟล์นั้นได้
3. LLM อธิบายข้อเท็จจริงได้ แต่ต้องไม่แต่งรายละเอียดเกี่ยวกับ account, outage, case, payment หรือ citation
4. หาก tool ล้มเหลวหรือไม่มีผลลัพธ์ คำตอบต้องระบุข้อจำกัดแทนการสร้างผลลัพธ์ขึ้นเอง

## แนวทางการจัดการข้อผิดพลาด

- request ไม่ถูกต้องหรือละเมิด contract: HTTP 422
- ไม่พบ conversation, trace หรือ pending action: HTTP 404
- การเปลี่ยนสถานะไม่ถูกต้อง (เช่น ยืนยันรายการที่ถูกปฏิเสธแล้ว): HTTP 409
- Gemini Long Context, Document Router, ตัวแปลงเอกสาร, judge LLM หรือ simulated backend ใช้งานไม่ได้: ปรับให้อยู่ในรูป typed failure มาตรฐาน และใช้ HTTP 502 เฉพาะเมื่อ route ไม่สามารถสร้างคำตอบ chat/action ที่ถูกต้องได้
- tool ที่ไม่รู้จัก, action ที่ไม่รู้จัก หรือ action ที่ไม่ได้รับอนุญาตใน flow ปัจจุบัน: ทำงานแบบ fail closed และเพิ่ม trace error event
- โหมดเสียง: ไม่มี `GEMINI_API_KEY` → `{"type":"error"}` + close 1011; ฟังก์ชันที่ไม่รู้จัก → `{"error":{"code":"unknown_function"}}`; ไม่มี pending action → `{"error":{"code":"no_pending_action"}}`; ข้อผิดพลาดอื่น → `{"error":{"code":"unavailable"}}` พร้อมข้อความปลอดภัยต่อผู้ใช้ และไม่มีการบันทึก raw audio/secret

## รายการตรวจสอบการผสานระบบ (โหมดเสียง)

- [ ] `WS /ws/live` สร้าง Gemini session, VoiceBridge, audio queue และ conversation ใหม่ทุก socket
- [ ] ไมโครโฟนเบราว์เซอร์ส่ง PCM16 16kHz binary; เสียงตอบกลับ PCM16 24kHz เล่นต่อเนื่องและ flush เมื่อ `audio.interrupted`
- [ ] ฟังก์ชันที่เปิดให้โมเดลมีสามตัวเท่านั้น; ไม่มีฟังก์ชันรับ `pendingActionId`
- [ ] การยืนยัน/ปฏิเสธด้วยเสียงผูกกับรายการปัจจุบันของเซสชัน และ fail closed เมื่อไม่มีรายการ
- [ ] โมเดลถามย้ำเมื่อคำตอบกำกวม และไม่สร้างข้อเท็จจริง/สถานะเรื่องขึ้นเอง
- [ ] ไม่มีการบันทึก raw audio หรือ secret ใน log

## ความเป็นเจ้าของไฟล์สำหรับผู้ปฏิบัติงานแบบขนาน

| ผู้รับผิดชอบ | ไฟล์/ไดเรกทอรีที่รับผิดชอบแต่เพียงผู้เดียว | สัญญาที่ขึ้นต่อกัน |
|---|---|---|
| หัวหน้าทีม/การผสานระบบ | `ARCHITECTURE.md`, `CONTRACTS.md`, `app/contracts.py`, `app/main.py`, `tests/test_contracts.py` | เป็นเจ้าของ frozen contract และการเชื่อม route; อนุมัติการเปลี่ยนแปลง contract ทั้งหมด |
| ผู้ปฏิบัติงาน A — เอเจนต์ | `app/agent/`, `app/llm/` | import เฉพาะ `app.contracts`; เรียกเฉพาะ interface `ToolRegistry` |
| ผู้ปฏิบัติงาน B — ฐานความรู้ | `app/tools/knowledge_tool.py`, `app/backends/full_document_knowledge.py`, `knowledge/` | ใช้ document-level routing และ full-file context เท่านั้น; ห้ามเพิ่ม vector DB, chunk retrieval หรือเปลี่ยน public contract |
| ผู้ปฏิบัติงาน C — งานปฏิบัติการ | `app/tools/oms_tool.py` และ external OMS connector; ไฟล์ VOC คง dormant | ใช้ action และ model ที่ตรึงไว้ใน `app.contracts` |
| ผู้ปฏิบัติงาน Voice — โหมดเสียง | `app/live/`, `app/api/live.py`, `web/gemini-live-client.js`, `web/media-handler.js`, `web/pcm-processor.js` | import เฉพาะ `app.contracts` + `app.live.models`; เรียก Main Agent ผ่าน `MainAgentGateway` เท่านั้น; ห้ามแตะ ToolRegistry/backend ธุรกิจ |
| ผู้ปฏิบัติงาน D — การตรวจสอบ/เอกสาร | `tests/`, `README.md`, `demo/` | ไม่แก้ไข production module หรือ contract |

ไฟล์ที่ใช้ร่วมกันเป็นแบบ read-only สำหรับผู้ปฏิบัติงาน เว้นแต่หัวหน้าทีมจะมอบหมายการเปลี่ยนแปลงอย่างชัดเจน ผู้ปฏิบัติงานเพิ่มไฟล์ใหม่ได้เฉพาะในไดเรกทอรีที่ตนรับผิดชอบ การเปลี่ยนแปลงใด ๆ ต่อ `app/contracts.py` หรือเอกสาร contract Markdown ที่ไดเรกทอรีรากทั้งสองไฟล์ถือเป็นการเปลี่ยนแปลงด้านการผสานระบบที่ต้องผ่านการตรวจโดยหัวหน้าทีม

## ลำดับงาน 2 วัน

**วันที่ 1:** ตรึง contract; สร้าง stub สำหรับการตรวจสอบ route และ model; พัฒนาระบบหลังบ้านจำลองที่กำหนดผลได้แน่นอน; พัฒนา Document Router และตัวแปลง DOCX แบบเต็มไฟล์; พัฒนาจุดเชื่อมต่อของ scripted/judge adapter; พิสูจน์ trace ของ prepare/confirm/reject

**วันที่ 2:** เชื่อมต่อ judge adapter; เตรียม catalog ของเอกสารที่อนุมัติ; เชื่อม Gemini Long Context ด้วยข้อความเต็มของไฟล์ที่เลือก; เพิ่ม fixture และเส้นทางความล้มเหลว; ซ้อมเส้นทางเดโมตามสคริปต์สี่เส้นทาง; รันรายการตรวจสอบการผสานระบบ

## รายการตรวจสอบการผสานระบบ

- [ ] startup ลงทะเบียน `knowledge_tool` และ `oms_tool` อย่างละหนึ่งครั้งเท่านั้น โดยใช้ typed registry และไม่โหลด OpenAPI แบบอัตโนมัติ
- [ ] `POST /api/v1/chat` ตรวจสอบ frozen request/response model และส่งคืน trace id
- [ ] Document Router เลือกเฉพาะไฟล์ที่เกี่ยวข้องจาก allowlisted catalog และไม่เกิน `maxResults`
- [ ] knowledge search ส่งข้อความฉบับเต็มของไฟล์ที่เลือกให้ Gemini Long Context โดยไม่ chunk, truncate หรือโหลดทั้ง corpus โดยไม่จำเป็น
- [ ] knowledge citations อ้างถึงชื่อไฟล์จริงและข้อความหลักฐานที่ตรวจสอบได้; ไม่มี Gemini File Search, local embedding/index/vector หรือ chunk retrieval
- [ ] ผลลัพธ์ operational จาก OMS ระบุ `simulation: true` อย่างชัดเจน
- [ ] ทุกเส้นทางการเขียนพิสูจน์ลำดับ prepare -> human confirm -> submit; การ submit โดยตรงจากแชตจะถูกปฏิเสธ
- [ ] การ confirm ซ้ำไม่สร้าง outage event/report ซ้ำ
- [ ] reject เป็น terminal และไม่ทิ้ง simulated side effect
- [ ] `GET /api/v1/traces/{trace_id}` แสดง event ตามลำดับและปกปิดข้อมูลสำหรับแต่ละเส้นทาง
- [ ] `POST /api/v1/reset` ล้างสถานะเดโม รวมถึง pending action และ trace
- [ ] `/health` รายงาน process health และความพร้อมของ adapter โดยไม่เปิดเผย credentials

## นิยามของคำว่าเสร็จสมบูรณ์

prototype พร้อมสำหรับเดโมเมื่อ public route ใน `CONTRACTS.md` ทำงานกับ frozen Pydantic model ได้; Document Router เลือกเฉพาะไฟล์ที่เกี่ยวข้องและ Main Agent ตอบจากข้อความฉบับเต็มของไฟล์เหล่านั้นพร้อม citation ที่ตรวจสอบได้; OMS connector รักษาสาม operation ใน immutable OpenAPI และคืน `simulation: true`; สามารถ prepare รอ explicit human confirmation แล้ว internal submit หนึ่งครั้งโดยมี trace ที่ปกปิดข้อมูล ระบบต้องทำงานเป็น FastAPI process หนึ่ง process มี Main Agent เพียงหนึ่งตัวและ tool ระดับบนสุดสองรายการคือ Knowledge และ OMS เท่านั้น โดย Sabuy/VOC คงแบบ dormant
