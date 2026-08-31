# PEA One Agent — สถาปัตยกรรมสำหรับเดโม

## สรุปการตัดสินใจ

สร้างโพรเซส FastAPI หนึ่งโพรเซสที่มี **Main Agent** เพียงหนึ่งตัว และโมดูลเครื่องมือระดับบนสุดที่เรียกใช้ได้สี่โมดูลเท่านั้น:

1. `knowledge_tool`
2. `sabuy_tool`
3. `voc_tool`
4. `oms_tool`

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
    |  |  |  |
    |  |  |  +--> oms_tool ------> SimulatedOmsBackend
    |  |  +-----> voc_tool ------> SimulatedVocBackend
    |  +--------> sabuy_tool ----> SimulatedSabuyBackend
    +-----------> knowledge_tool -> Gemini File Search Hosted RAG
        |
        v
TraceStore + PendingActionStore (in-process, resettable demo state)
```

## โมดูลและจุดเชื่อมต่อขณะทำงาน

### โมดูล HTTP

**ส่วนเชื่อมต่อ:** route ที่จัดทำเอกสารไว้ใน `CONTRACTS.md` โมดูลนี้ตรวจสอบ input เรียก operation ของ Main Agent หนึ่งรายการ และส่งคืนโมเดลตาม frozen contract โดยไม่มี business policy และไม่เรียก tool โดยตรง

### โมดูล Main Agent

**ส่วนเชื่อมต่อ:** `handle_chat`, `confirm_pending_action`, `reject_pending_action`, `get_trace` และ `reset_demo`

โมดูลนี้เป็นตัวประสานงานที่ขับเคลื่อนด้วยโมเดลเพียงตัวเดียว โดยทำหน้าที่ดังนี้:

- รับข้อความผู้ใช้และสถานะการสนทนา;
- เรียกเฉพาะ tool ระดับบนสุดสี่รายการที่ลงทะเบียนไว้;
- ถือว่าผลลัพธ์จาก tool เป็นข้อเท็จจริงที่มีอำนาจเหนือข้อความจากโมเดล;
- สร้าง pending action หลังจากได้รับผลลัพธ์ `prepare_*` ที่สำเร็จ;
- ส่งคำขอเขียนหลังจากมีการเรียก confirm route อย่างชัดเจนเท่านั้น;
- สร้าง trace event ตามลำดับ;
- สร้างคำตอบแชตสุดท้าย

โมดูลนี้ต้องไม่เปิดเผย sub-agent, agent แยกตาม tool หรือ tool ที่ไม่ได้ประกาศไว้ tool อาจมีโค้ด helper ภายในได้ แต่จะไม่มีการลงทะเบียน tool ระดับบนสุดเพิ่มเติมกับ LLM

### จุดเชื่อมต่อ `LLMAdapter`

Main Agent ขึ้นต่อส่วนเชื่อมต่อที่ไม่ผูกกับผู้ให้บริการรายใด ไม่ใช่ SDK ของกรรมการ:

```python
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

`LLMRequest` ประกอบด้วย messages, แค็ตตาล็อก tool สี่รายการที่กำหนดตายตัว และ correlation id ส่วน `LLMResponse` ประกอบด้วย text และค่า `ToolCall` ตั้งแต่ศูนย์รายการขึ้นไป อะแดปเตอร์สำหรับกรรมการจะแปลงโครงสร้าง SDK ของตนเป็น contract ภายในเหล่านี้ โดย `ScriptedLLMAdapter` เพียงพอสำหรับเดโม/การทดสอบที่กำหนดผลได้แน่นอน

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

- `GeminiFileSearchKnowledgeBackend` เรียกเฉพาะ Gemini File Search Hosted RAG โดย tool จะส่งต่อ retrieval query และแปลง source metadata ที่ส่งคืนมาเป็น citations ตัวมันเองจะไม่ทำ embed, chunk, index, rank หรือ persist เอกสาร
- `SimulatedSabuyBackend`, `SimulatedVocBackend` และ `SimulatedOmsBackend` ใช้ข้อมูล fixture ใน memory แบบ deterministic คำตอบของระบบเหล่านี้มี `simulation: true` และจะไม่มีการกล่าวอ้างว่า action ได้ส่งถึง PEA แล้ว

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
2. ผลลัพธ์ retrieval จาก Gemini เป็นแหล่งข้อมูลที่เชื่อถือได้เฉพาะ knowledge ที่ส่งคืนพร้อม citations
3. LLM อธิบายข้อเท็จจริงได้ แต่ต้องไม่แต่งรายละเอียดเกี่ยวกับ account, outage, case, payment หรือ citation
4. หาก tool ล้มเหลวหรือไม่มีผลลัพธ์ คำตอบต้องระบุข้อจำกัดแทนการสร้างผลลัพธ์ขึ้นเอง

## แนวทางการจัดการข้อผิดพลาด

- request ไม่ถูกต้องหรือละเมิด contract: HTTP 422
- ไม่พบ conversation, trace หรือ pending action: HTTP 404
- การเปลี่ยนสถานะไม่ถูกต้อง (เช่น ยืนยันรายการที่ถูกปฏิเสธแล้ว): HTTP 409
- Gemini/judge LLM/simulated backend ใช้งานไม่ได้: ปรับให้อยู่ในรูป typed failure มาตรฐาน และใช้ HTTP 502 เฉพาะเมื่อ route ไม่สามารถสร้างคำตอบ chat/action ที่ถูกต้องได้
- tool ที่ไม่รู้จัก, action ที่ไม่รู้จัก หรือ action ที่ไม่ได้รับอนุญาตใน flow ปัจจุบัน: ทำงานแบบ fail closed และเพิ่ม trace error event

## ความเป็นเจ้าของไฟล์สำหรับผู้ปฏิบัติงานแบบขนาน

| ผู้รับผิดชอบ | ไฟล์/ไดเรกทอรีที่รับผิดชอบแต่เพียงผู้เดียว | สัญญาที่ขึ้นต่อกัน |
|---|---|---|
| หัวหน้าทีม/การผสานระบบ | `ARCHITECTURE.md`, `CONTRACTS.md`, `app/contracts.py`, `app/main.py`, `tests/test_contracts.py` | เป็นเจ้าของ frozen contract และการเชื่อม route; อนุมัติการเปลี่ยนแปลง contract ทั้งหมด |
| ผู้ปฏิบัติงาน A — เอเจนต์ | `app/agent/`, `app/llm/` | import เฉพาะ `app.contracts`; เรียกเฉพาะ interface `ToolRegistry` |
| ผู้ปฏิบัติงาน B — ฐานความรู้ | `app/tools/knowledge_tool.py`, `app/backends/gemini_file_search.py` | ห้ามเพิ่ม vector DB หรือเปลี่ยน public contract |
| ผู้ปฏิบัติงาน C — งานปฏิบัติการจำลอง | `app/tools/sabuy_tool.py`, `app/tools/voc_tool.py`, `app/tools/oms_tool.py`, `app/backends/simulated_*.py` | ใช้ action และ model ที่ตรึงไว้ใน `app.contracts` |
| ผู้ปฏิบัติงาน D — การตรวจสอบ/เอกสาร | `tests/`, `README.md`, `demo/` | ไม่แก้ไข production module หรือ contract |

ไฟล์ที่ใช้ร่วมกันเป็นแบบ read-only สำหรับผู้ปฏิบัติงาน เว้นแต่หัวหน้าทีมจะมอบหมายการเปลี่ยนแปลงอย่างชัดเจน ผู้ปฏิบัติงานเพิ่มไฟล์ใหม่ได้เฉพาะในไดเรกทอรีที่ตนรับผิดชอบ การเปลี่ยนแปลงใด ๆ ต่อ `app/contracts.py` หรือเอกสาร contract Markdown ที่ไดเรกทอรีรากทั้งสองไฟล์ถือเป็นการเปลี่ยนแปลงด้านการผสานระบบที่ต้องผ่านการตรวจโดยหัวหน้าทีม

## ลำดับงาน 2 วัน

**วันที่ 1:** ตรึง contract; สร้าง stub สำหรับการตรวจสอบ route และ model; พัฒนาระบบหลังบ้านจำลองที่กำหนดผลได้แน่นอน; พัฒนาอะแดปเตอร์สำหรับ Gemini hosted retrieval; พัฒนาจุดเชื่อมต่อของ scripted/judge adapter; พิสูจน์ trace ของ prepare/confirm/reject

**วันที่ 2:** เชื่อมต่อ judge adapter; จัดเตรียม corpus สำหรับ Gemini File Search; เพิ่ม fixture และเส้นทางความล้มเหลว; ซ้อมเส้นทางเดโมตามสคริปต์สี่เส้นทาง; รันรายการตรวจสอบการผสานระบบ

## รายการตรวจสอบการผสานระบบ

- [ ] startup ลงทะเบียน `knowledge_tool`, `sabuy_tool`, `voc_tool` และ `oms_tool` อย่างละหนึ่งครั้งเท่านั้น
- [ ] `POST /api/v1/chat` ตรวจสอบ frozen request/response model และส่งคืน trace id
- [ ] knowledge search ส่งคืน citations จาก Gemini File Search; ไม่มี dependency สำหรับ local embedding/index/vector
- [ ] คำตอบจาก Sabuy, VOC และ OMS ระบุ `simulation: true` อย่างชัดเจน
- [ ] ทุกเส้นทางการเขียนพิสูจน์ลำดับ prepare -> human confirm -> submit; การ submit โดยตรงจากแชตจะถูกปฏิเสธ
- [ ] การ confirm ซ้ำไม่สร้าง simulated payment, VOC case หรือ outage report ซ้ำ
- [ ] reject เป็น terminal และไม่ทิ้ง simulated side effect
- [ ] `GET /api/v1/traces/{trace_id}` แสดง event ตามลำดับและปกปิดข้อมูลสำหรับแต่ละเส้นทาง
- [ ] `POST /api/v1/reset` ล้างสถานะเดโม รวมถึง pending action และ trace
- [ ] `/health` รายงาน process health และความพร้อมของ adapter โดยไม่เปิดเผย credentials

## นิยามของคำว่าเสร็จสมบูรณ์

prototype พร้อมสำหรับเดโมเมื่อ public route ใน `CONTRACTS.md` ทำงานกับ frozen Pydantic model ได้; Main Agent สามารถอธิบายคำตอบจาก Gemini hosted-RAG ที่มี citation; สามารถอ่านข้อมูล Sabuy/VOC/OMS ที่จำลองขึ้น; และสามารถ prepare, รอการยืนยันจากมนุษย์อย่างชัดเจน แล้ว submit การเขียนจำลองหนึ่งครั้งโดยมี trace ที่ตรวจสอบย้อนหลังได้ ระบบต้องทำงานเป็น FastAPI process หนึ่ง process มี Main Agent เพียงหนึ่งตัวและ tool ระดับบนสุดสี่รายการที่ประกาศไว้เท่านั้น และระบุอย่างชัดเจนว่าข้อมูลเชิงปฏิบัติการทั้งหมดที่ไม่ใช่ knowledge เป็นข้อมูลจำลอง
