# Content Brief — สไลด์แข่ง "Agentic AI for Customer Service" (หัวข้อที่ 3, PEA)

เอกสารนี้คือ**เนื้อหาดิบทั้งหมด**สำหรับทำสไลด์เอง ไม่ใช่ตัวสไลด์ — นำเสนอ 10 นาที ~35-40 สไลด์ (สไลด์สั้น เปลี่ยนเร็ว)
แต่ละสไลด์มี **(1) Headline/copy ที่ใช้ได้เลย (2) เนื้อหา/ตัวเลขอ้างอิง (3) คอมเมนต์ภาพประกอบละเอียด**

**แหล่งข้อมูลที่ใช้ทั้งหมด (ทุกตัวเลข/ทุก quote ในเอกสารนี้ตรวจสอบย้อนกลับไปยังแหล่งนี้ได้):**
- โจทย์แข่ง: "หัวข้อที่ 3 Agentic AI for customer service" (Google Doc)
- `ARCHITECTURE.md`, `AGENTS.md`, `PRD.md`, `CONTRACTS.md`, `pyproject.toml` ในโปรเจกต์นี้
- โค้ดจริง: `app/plugins/loader.py`, `app/plugins/manifest.py`, `app/plugins/oms/plugin.yaml`, `app/plugins/voc/plugin.yaml`, `scripts/add-plugin`
- รายงานผลดำเนินงาน 1129 PEA Contact Center พ.ค. 2568 (`~/Downloads/1129.pdf`) — **ใช้เฉพาะสถิติรวม ไม่มี PII ลูกค้าปนอยู่เลย**
- Gemini Developer API pricing (ai.google.dev) — ราคาทางการ ณ วันที่ค้น
- ผลรัน `pytest -q` จริงในเครื่อง (275 tests, breakdown ตาม Appendix D)
- Artifact ที่ทำไปแล้ว 2 ชิ้น (ใช้เป็นภาพประกอบ/ตัดต่อได้ทันที):
  - Flow diagram: `https://claude.ai/code/artifact/47d58cfc-700b-45d2-8c70-894e59ca5c34`
  - Cost comparison chart: `https://claude.ai/code/artifact/d26ad006-e48b-49ec-aed3-b927ca9bbc84`

**เกณฑ์ให้คะแนน (ใช้ตรวจว่าแต่ละสไลด์ตอบข้อไหน — โค้ดตัวอักษร A/B/C กำกับไว้ท้ายทุก section หัวข้อ):**

| # | เกณฑ์ | คะแนน | โค้ด |
|---|---|---|---|
| 1 | ความเข้าใจปัญหา + ความสามารถแก้ปัญหา (วิเคราะห์ปัญหา, ออกแบบ Agentic AI, Flow, แผนงาน, ทดลองกับหน่วยงาน ≥2 แห่ง) | 16 | **A** |
| 2 | ความคิดสร้างสรรค์ | 10 | **B** |
| 3 | ผลประโยชน์เชิงบวก (ผลต่อองค์กร, ผลต่อลูกค้า, ความคุ้มค่า/ROI) | 24 | **C** |

---

# SECTION 0 — เปิดเรื่อง (สไลด์ 1-2)

## สไลด์ 1 — Title

**Headline:** PEA One Agent
**Sub:** จาก "ตอบคำถาม" สู่ "ทำงานแทนลูกค้า" — Agentic AI สำหรับศูนย์บริการข้อมูลผู้ใช้ไฟฟ้า
**เนื้อหาย่อย:** ชื่อทีม, หัวข้อที่ 3, วันที่นำเสนอ

**ภาพประกอบ:** โลโก้ PEA ทางการ (ต้องไปโหลดของจริงจากเว็บ กฟภ. — ห้ามสร้างเอง/วาดเอง) วางมุมบนซ้ายหรือกลางบน พื้นหลังไล่เฉดม่วง `#6B3FA0` อ่อนลงไปขาว ไม่ต้องมีกราฟิกซับซ้อน

## สไลด์ 2 — Agenda

**Headline:** สิ่งที่จะพูดวันนี้
**เนื้อหา:** 6 หัวข้อใหญ่ (ใช้เป็น section marker ตลอดเด็ค): (1) ปัญหา+ต้นเหตุ (2) แนวคิด Agentic AI (3) สถาปัตยกรรม+เทคโนโลยี (4) ช่องทางและปลั๊กอิน (5) ตัวอย่างการทำงานจริง (6) ผลลัพธ์+แผนต่อไป

**ภาพประกอบ:** ไม่ต้องมีรูป ใช้เลข 1-6 เรียงเป็น timeline แนวนอนบางๆ พอ — จะใช้ marker เดียวกันนี้ซ้ำเป็น "คุณอยู่ตรงไหน" มุมบนของทุกสไลด์ถัดไปได้ (progress indicator)

---

# SECTION 1 — ปัญหาและต้นเหตุ (สไลด์ 3-7) — ตอบเกณฑ์ A

## สไลด์ 3 — Problem Statement (จากโจทย์แข่งโดยตรง)

**Headline:** งานบริการลูกค้าที่ซับซ้อนขึ้น แต่ทรัพยากรคงที่

**เนื้อหา (3 bullet ตรงจากโจทย์แข่ง คำต่อคำเกือบทั้งหมด):**
- คำถาม/ความต้องการหลากหลาย: สอบถามข้อมูล, แจ้งปัญหา, ขอรับบริการ, ติดตามสถานะ — บางกระบวนการต้องใช้ข้อมูลจากหลายระบบ + ประสานหลายหน่วยงาน
- ผลคือ: ใช้เวลานาน, ลูกค้าต้องติดต่อหลายช่องทาง, มีความคลาดเคลื่อนจากการส่งต่อข้อมูล
- ปริมาณ+ความซับซ้อนของคำขอเพิ่มขึ้น แต่บุคลากรมีจำกัด → บริการแบบ manual ตอบสนองไม่ทัน

**ภาพประกอบ:** ไม่ต้องมีรูป ใช้ typography ใหญ่ล้วน (เกณฑ์ A ให้คะแนน "ความชัดเจนในการระบุปัญหา")

## สไลด์ 4 — Root Cause 1: SLA ที่พลาดเป้าจริง

**Headline:** ปัญหาไม่ใช่แค่ทฤษฎี — นี่คือตัวเลขจริงของเดือน พ.ค. 2568

| ตัวชี้วัด | เป้าหมาย | ผลจริง | สถานะ |
|---|---|---|---|
| % Abandon Call (ลูกค้าทิ้งสาย) | < 5% | **10.29%** | ❌ ไม่ผ่าน |
| Average Speed of Answer | < 10 วิ | **46 วิ** | ❌ ไม่ผ่าน |
| % สายที่รอ ≤10 วิ | > 85% | **57.40%** | ❌ ไม่ผ่าน |

**Insight ที่ต้องพูด:** ตัวชี้วัด "คุณภาพการตอบ" (Talk Time) ผ่านทุกหมวด แต่ตัวชี้วัด **"การเข้าถึง"** (รอคิว/ทิ้งสาย) ไม่ผ่านทั้งหมด → คอขวดคือ **ความจุ (capacity)** ไม่ใช่ **ทักษะ agent**

**ภาพประกอบ:** กราฟแท่งหรือ gauge 3 ตัว (เป้าหมาย vs ผลจริง) ใช้สีแดง/ส้มเตือนทั้ง 3 ตัวเพราะไม่ผ่านหมด — สไตล์เดียวกับ metric card ใน cost artifact

## สไลด์ 5 — Root Cause 2: ปริมาณงานกับจำนวนคน

**Headline:** ปริมาณงานโตเร็วกว่ากำลังคน

**เนื้อหา:**
- สายเข้าทั้งหมด พ.ค. 68: **244,737 สาย** (ตอบรับได้ 219,564 = 89.71%)
- จำนวน Agent: **135 คน** (เพิ่มจาก 80 คนช่วง ม.ค.-มี.ค. — เพิ่มคนแล้วแต่ SLA ยังไม่ผ่าน)
- Non-Voice เพิ่มอีก 30,290 ครั้ง/เดือน (Chat 14,848 / Social 12,879 / E-mail 2,542 / Leave Voice 21)
- เทียบปีก่อน: Call Offer ลดลง 22.07% (314,042→244,737) **แต่** Abandon Call แย่ลง (6.32%→10.29%) — แปลว่าแม้ปริมาณลดก็ยังรับมือไม่ไหว เพราะช่วงพายุฤดูร้อนทำให้สายกระจุกตัวช่วงพีค

**ภาพประกอบ:** กราฟเส้น/แท่งสองแกนแยก (ไม่ใช้ dual-axis เดียว) — กราฟ 1: จำนวน Agent เพิ่มขึ้นตามเดือน (80→80→80→125→135) กราฟ 2: %Abandon Call ตามเดือน (2.98%→7.38%→11.21%→8.79%→10.29%) วางคู่กันแบบ small multiples ให้เห็นว่าเพิ่มคนแล้วยังไม่พอ

## สไลด์ 6 — Root Cause 3: ทำไม manual ถึงตันที่ตรงนี้

**Headline:** เพิ่มคนได้ไม่จำกัด แต่พีคของสายมีจำกัดเวลา

**เนื้อหา:** ช่วงเวลาที่สายเข้าเยอะสุดคือ **06.00-23.00 น.** (17 ชม./วัน) — การเพิ่ม headcount แก้ปัญหาความจุที่พีคได้ แต่มีต้นทุนเชิงเส้น (linear cost) ตามจำนวนคน ขณะที่ agentic voice agent ตอบพร้อมกันได้หลายสายโดยไม่มี "คิว" ในความหมายเดิม — เป็นการแก้ปัญหาเชิงโครงสร้างไม่ใช่แค่เพิ่มทรัพยากร

**ภาพประกอบ:** กราฟ heat/area chart ตามชั่วโมงของวัน (จาก 1129.pdf มีข้อมูล "Trend Call and % Abandon of May 2025" อยู่แล้ว) ไฮไลต์ช่วง 06:00-23:00 ด้วยกรอบเส้นประสีอำพัน

## สไลด์ 7 — สรุปปัญหา (transition slide)

**Headline:** สรุป: ปัญหาคือ capacity ไม่ใช่คุณภาพ → คำตอบคือ Agentic AI ไม่ใช่แค่ "เพิ่มคน" หรือ "chatbot ตอบคำถามพื้นฐาน"

**ภาพประกอบ:** ไม่ต้องมี ใช้เป็นสไลด์เปลี่ยนหัวข้อ (section divider) พื้นหลังม่วงเข้ม ตัวหนังสือขาว

---

# SECTION 2 — แนวคิด Agentic AI (สไลด์ 8-11) — ตอบเกณฑ์ A + B

## สไลด์ 8 — Chatbot vs Agentic AI (เติมตารางว่างในโจทย์แข่งให้เต็ม)

**Headline:** จาก "ตอบคำถาม" สู่ "ทำงานแทนลูกค้า"

| มิติ | AI Chatbot | Agentic AI (PEA One Agent) |
|---|---|---|
| ขอบเขต | ตอบคำถามอย่างเดียว | วิเคราะห์ความต้องการ → วางแผน → เรียกเครื่องมือจริง |
| แหล่งข้อมูล | มักตอบจากสิ่งที่ฝึกมา/เอกสารเดียว | ดึงข้อมูลสด + เรียกใช้ระบบจริงหลายระบบ (OMS/VOC) |
| งานข้ามระบบ | ทำไม่ได้ ต้องส่งต่อคน | ประสานเองในลูปเดียว (bounded agent loop) |
| ความเสี่ยง | มักตอบมั่ว (hallucinate) เมื่อไม่รู้ | ตอบแบบ grounded + citation, fail-closed เมื่อไม่มีหลักฐาน |
| การเขียนข้อมูล | ปกติทำไม่ได้ หรือทำแบบเสี่ยง | **มนุษย์ต้องยืนยันก่อนเสมอ** (prepare → confirm → submit) |
| ช่องทาง | มักผูกกับช่องทางเดียว | Web / Voice / LINE ใช้สมองเดียวกัน |
| การขยายระบบ | ต้องเขียนโค้ดใหม่ทั้งชิ้น | เพิ่มระบบใหม่ผ่าน plugin manifest (ดูสไลด์ Section 4) |

**ภาพประกอบ:** ตารางเปรียบเทียบ 2 คอลัมน์ ไฮไลต์แถว "การเขียนข้อมูล" และ "การขยายระบบ" ด้วยกรอบสีเน้น (2 จุดขายหลักที่ทีมอื่นมักไม่มี)

## สไลด์ 9 — หลักการออกแบบ (design principles) — โชว์วุฒิภาวะทางวิศวกรรม

**Headline:** ลำดับความสำคัญที่ยึดตลอดโปรเจกต์

**เนื้อหา (ตรงจาก `AGENTS.md` — เป็นของจริงที่ทีมเขียนกำกับตัวเองไว้ ไม่ใช่คำโฆษณา):**
```
Correctness and safety
> Working MVP
> Simplicity
> Maintainability
> Test coverage
> Architectural purity
> Hypothetical scalability
```
พูดสั้นๆ: "เราไม่สร้างของที่ over-engineer เกินความจำเป็น แต่ไม่มีวันแลก **ความถูกต้องและความปลอดภัย** กับความเร็ว" — ตรงนี้ตอบเกณฑ์ B (ความคิดสร้างสรรค์) ในแง่ที่ทีมมี**หลักคิดที่ชัดเจนเป็นลายลักษณ์อักษร** ไม่ใช่ทำไปเรื่อยๆ

**ภาพประกอบ:** ลำดับขั้นบันได (staircase) 7 ขั้น จากสูงไปต่ำ ขั้นบนสุด (Correctness & safety) ใหญ่/เด่นสุด ไล่เล็กลง

## สไลด์ 10 — Solution Overview

**Headline:** PEA One Agent — สมองเดียว ทุกช่องทาง ทุกระบบ

**เนื้อหา:**
- 3 ช่องทางเข้า: Web Chat, Voice (Gemini Live), LINE
- 3 เครื่องมือหลัก: Knowledge (ตอบคำถามจากเอกสารทางการ), OMS (แจ้ง/ติดตามไฟฟ้าขัดข้อง), VOC (รับเรื่องร้องเรียน/บริการ)
- Orchestrator ตัวเดียว ไม่ใช่ sub-agent แยกทีละงาน

**ภาพประกอบ:** ใช้ flow diagram เดิม (crop ครึ่งบน: ช่องทาง → Main Agent loop → ToolRegistry)

## สไลด์ 11 — เป้าหมายเชิงผลลัพธ์ (ทวนจากโจทย์)

**Headline:** เป้าหมาย: เร็วขึ้น ผิดพลาดน้อยลง รองรับได้มากขึ้น

**เนื้อหา (ยกจากโจทย์แข่งเกือบคำต่อคำ เพื่อ "ตอบโจทย์" ให้กรรมการเห็นชัด):** ลดระยะเวลา/ขั้นตอนบริการ, ลดภาระงาน+ข้อผิดพลาดของเจ้าหน้าที่, เพิ่มความสามารถรองรับลูกค้าจำนวนมาก, ลดต้นทุนดำเนินงาน, เพิ่มประสิทธิภาพทรัพยากร

**ภาพประกอบ:** ไม่ต้องมี ใช้ bullet list ธรรมดา (transition ไปสู่ section เทคนิค)

---

# SECTION 3 — สถาปัตยกรรมและเทคโนโลยี (สไลด์ 12-21) — ตอบเกณฑ์ A (แผนงาน/ทรัพยากร/เครื่องมือ) + B

## สไลด์ 12 — Technology Stack

**Headline:** เทคโนโลยีที่ใช้ทั้งหมด

**เนื้อหา (จาก `pyproject.toml` จริง — ไม่ปัดตัวเลข):**

| ชั้น | เทคโนโลยี |
|---|---|
| Backend framework | FastAPI (`>=0.115`) + Uvicorn (ASGI server) |
| Data validation | Pydantic v2 (`>=2.8`) — schema ทุกจุดของระบบ ไม่มี "dict ลอยๆ" |
| HTTP client | httpx (`>=0.27`) — เรียก OMS/VOC REST + Gemini API |
| Plugin config | PyYAML (`>=6.0`) — อ่าน `plugin.yaml` ตอน startup |
| Main/Knowledge LLM | Google Gemini API (REST, httpx โดยตรง — ไม่ใช้ SDK หนัก) |
| Voice LLM | `google-genai` SDK (`>=1.0`) — เฉพาะโหมดเสียงที่ต้องใช้ WebSocket จริง |
| Realtime transport | WebSocket (`/ws/live`) — เสียงดิบ PCM16 |
| Messaging channel | LINE Messaging API (webhook + HMAC signature) |
| Testing | pytest + pytest-asyncio (`>=8.0` / `>=0.24`) |
| Package/dependency | `uv` (Python packaging, lockfile `uv.lock`) |
| Frontend | Vanilla JS + Web Audio API (AudioWorklet) — ไม่ใช้ framework หนัก เพราะเป็นหน้าสาธิต |

**เหตุผลที่เลือกแบบนี้ (พูดถ้ามีเวลา):** Pydantic v2 ทำให้ schema ของ HTTP/LLM tool call/plugin manifest **เป็นแหล่งความจริงเดียวกัน** (single source of truth) — ป้องกัน manifest กับโค้ดจริง drift กัน (ดูสไลด์ plugin validation)

**ภาพประกอบ:** ตารางเรียบๆ 2 คอลัมน์ อาจใส่ logo เล็กๆ ของแต่ละเทคโนโลยี (FastAPI/Pydantic/Gemini/LINE) ข้างชื่อถ้าหาไฟล์ logo ทางการได้ ไม่บังคับ

## สไลด์ 13 — System Topology (ภาพรวมทั้งระบบ)

**Headline:** ภาพรวมระบบทั้งหมด

**เนื้อหา:** ผังจาก `ARCHITECTURE.md` (ข้อความจริงในไฟล์):
```
Browser / judge client
    → FastAPI routes (/api/v1/*, /health)
    → Main Agent ←→ LLMAdapter (Gemini)
         → ToolRegistry (Knowledge built-in + ปลั๊กอินที่ลงทะเบียน)
              → oms_tool → httpx → External OMS REST
              → voc_tool → SimulatedVocBackend
              → knowledge_tool → Document Router → Gemini Long Context
    → TraceStore + PendingActionStore (in-process, resettable)

Browser voice UI → WebSocket /ws/live → GeminiLiveSession → VoiceBridge → Main Agent
LINE Messaging API → POST /webhook/line → LineBridge → Main Agent
```

**ภาพประกอบ:** นี่คือภาพที่เหมาะทำเป็น diagram ใหม่แบบ layered (บนลงล่าง): Layer 1 = ช่องทาง (3 กล่อง) / Layer 2 = Bridge (Voice Bridge, Line Bridge, HTTP route) / Layer 3 = Main Agent + LLMAdapter / Layer 4 = ToolRegistry + 3 tools / Layer 5 = TraceStore+PendingActionStore — ใช้สไตล์กล่องขอบบางเดียวกับ flow diagram เดิม แยกเป็นคนละภาพเพราะอันนี้เน้น "ชั้นของระบบ" ไม่ใช่ "ลำดับการทำงาน"

## สไลด์ 14 — Main Agent: หัวใจของระบบ

**Headline:** Orchestrator เดียว ควบคุมทุกอย่าง

**เนื้อหา (จาก `ARCHITECTURE.md` โมดูล Main Agent):**
- Interface: `handle_chat`, `confirm_pending_action`, `reject_pending_action`, `get_trace`, `reset_demo` — **5 เมทอดเท่านั้น**
- Agent loop แบบ bounded: **ไม่เกิน 12 agent steps / 12 tool calls ต่อข้อความ** และหยุดทันทีเมื่อพบ Knowledge call ซ้ำ (กัน loop ไม่รู้จบ)
- เรียกเฉพาะ tool ใน active catalogue จาก `ToolRegistry.llm_catalogue` — **ไม่ hardcode รายชื่อ tool ในตัว Main Agent** (นี่คือกลไกที่ทำให้เพิ่ม plugin ใหม่ได้โดยไม่แก้ Main Agent เลย)
- ผลลัพธ์จาก tool ถือเป็น**ข้อเท็จจริงที่มีอำนาจเหนือข้อความจากโมเดล** (ป้องกันโมเดลมั่วทับผลจริง)
- **ห้ามมี sub-agent หรือ agent แยกตาม tool** — เป็นกฎที่ตรึงไว้ระดับสถาปัตยกรรม

**ภาพประกอบ:** ไม่จำเป็นต้องมีรูปใหม่ ใช้ code snippet สั้นๆ ของ 5 เมทอดเป็น "interface card" (กล่องเดียว มี method signature 5 บรรทัด) จะดูน่าเชื่อถือกว่าคำอธิบายลอยๆ

## สไลด์ 15 — LLMAdapter: สลับ provider ได้โดยไม่แก้โค้ด

**Headline:** Provider-neutral interface

**เนื้อหา:**
```python
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```
- `LLMRequest` = messages + catalogue ของ tool (typed) + correlation id
- `LLMResponse` = text + รายการ `ToolCall`
- Provider ปัจจุบัน: `gemini` (production) + `demo` (internal stub สำหรับ Judge/testing, deterministic ไม่ต้องเรียก API จริง)
- Adapter ต้อง**ไม่มีนโยบายธุรกิจของ PEA, ไม่มีข้อมูลลับใน trace, ไม่เข้าถึงระบบหลังบ้านโดยตรง**

**ภาพประกอบ:** Code card เดียว (protocol 2 บรรทัด) + กล่องเล็ก 2 กล่องข้างๆ แสดง provider ที่มีจริงตอนนี้ (gemini / demo) ด้วยลูกศรชี้เข้า interface เดียวกัน — สื่อว่า "เพิ่ม provider ใหม่ (เช่น local LLM ในอนาคต) แค่ implement interface นี้"

## สไลด์ 16 — Tool Interface และ ToolRegistry

**Headline:** ทุกเครื่องมือพูดภาษาเดียวกัน

**เนื้อหา:**
```python
class Tool(Protocol):
    name: ToolName
    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult: ...
```
- ToolRegistry ถูกกำหนดตายตัวตอน startup ให้มีเฉพาะ **4 ชื่อ tool ที่รู้จัก** (Knowledge, OMS, VOC, Sabuy) — ปฏิเสธชื่อไม่รู้จักและกรณี action/name ไม่ตรงกันก่อนเรียก backend เสมอ (fail-closed)

**ภาพประกอบ:** Code card เดียวกับสไลด์ก่อน (สไตล์เดียวกัน ให้ดูเป็นชุด "3 interface หลักของระบบ": LLMAdapter / Tool / — จะพูดกับ Plugin manifest ในสไลด์ Section 4 ต่อ)

## สไลด์ 17 — HTTP API Contract: ภาพรวม 7 endpoints

**Headline:** สัญญา API ที่ตรึงไว้ (frozen contract)

**เนื้อหา (จาก `CONTRACTS.md` v1):**

| Method | Path | หน้าที่ |
|---|---|---|
| POST | `/api/v1/chat` | ส่งข้อความ ได้คำตอบ/pendingAction/citation |
| POST | `/api/v1/actions/{id}/confirm` | ยืนยันรายการที่รออยู่ → ส่ง submit จริง |
| POST | `/api/v1/actions/{id}/reject` | ปฏิเสธรายการที่รออยู่ |
| GET | `/api/v1/traces/{id}` | ดู trace event ทั้งหมดของ conversation |
| POST | `/api/v1/reset` | ล้างสถานะ demo ทั้งหมด |
| GET | `/health` | สถานะระบบ (ไม่เผย credential/URL/PII) |
| WS | `/ws/live` | ช่องเสียง (Gemini Live) |
| POST | `/webhook/line` | ช่องทาง LINE |

**กฎร่วมทุก endpoint:** field เป็น `camelCase`, ทุก write operation ต้องมี `idempotencyKey`, error มีชนิดชัดเจนและปลอดภัยสำหรับผู้ใช้เสมอ

**ภาพประกอบ:** ตาราง 8 แถวเรียบๆ ไอคอนเล็กๆ แยก REST (7 อัน) vs WebSocket (1 อัน) vs Webhook (1 อัน) ด้วยสีต่างกันเบาๆ

## สไลด์ 18 — HTTP API Contract: ตัวอย่าง request/response จริง

**Headline:** ตัวอย่างสัญญา `POST /api/v1/chat`

**เนื้อหา (JSON จริงจาก CONTRACTS.md, ย่อ):**
```json
// Request
{ "conversationId": "uuid?", "message": "string (max 4000 chars)",
  "selectedPromptId": "string?", "selectedValue": "string?" }

// Response
{ "conversationId": "uuid", "traceId": "uuid", "message": "string",
  "citations": [], "pendingAction": null, "toolResults": [], "choicePrompt": null }
```
`choicePrompt` ไม่เป็น null เมื่อ flow ต้องการให้ผู้ใช้เลือกจากตัวเลือก (มาจาก catalog ของ backend เท่านั้น ไม่ใช่ค่าที่โมเดลสร้างเอง — กัน prompt injection ผ่านตัวเลือกปลอม)

**ภาพประกอบ:** Two-column code diff-style card: request ซ้าย, response ขวา ใช้ font mono เดียวกับ diagram อื่นๆ (IBM Plex Mono) พื้นหลังกล่อง code สีเข้มนิดหน่อยให้ดูเป็น code block จริง

## สไลด์ 19 — Write-Safety State Machine (ระดับโค้ด ไม่ใช่แค่ prompt)

**Headline:** บังคับด้วยโค้ด backend ไม่ใช่แค่สั่งใน prompt

**เนื้อหา:**
```
prepare_* → pending_confirmation → [confirm endpoint | reject endpoint] → submit_* → submitted | rejected | failed
```
กฎที่ตรึงไว้ (จาก CONTRACTS.md):
- แชตเรียกได้เฉพาะ read action กับ `prepare_*` เท่านั้น — **ไม่มีทางให้โมเดลเรียก submit ได้เองแม้จะพยายาม**
- ยืนยันซ้ำ → คืนผลเดิม ไม่ยิงซ้ำ (idempotent)
- ยืนยันรายการที่ถูกปฏิเสธไปแล้ว → HTTP 409 ปฏิเสธเสมอ
- Manifest ของปลั๊กอินเองก็บังคับกฎนี้: `submit action ต้องเป็น internal เท่านั้น` (validate ตอน startup ถ้าใครประกาศผิดจะ startup ไม่ขึ้นเลย — ดูสไลด์ 27)

**ทำไมสำคัญ:** นี่คือคำตอบตรงๆ ต่อประโยคในโจทย์แข่ง — "มีมนุษย์เข้ามากำกับดูแลในกรณีที่ต้องใช้ดุลยพินิจหรือมีความเสี่ยง" — และเป็น**การบังคับด้วยสถาปัตยกรรม ไม่ใช่การขอร้องในพรอมต์**ซึ่ง bypass ได้ง่ายกว่ามาก

**ภาพประกอบ:** ใช้ crop แถบ "HUMAN-IN-THE-LOOP" จาก flow diagram เดิม + เพิ่มข้อความ "409 Conflict" กำกับที่จุดยืนยันซ้ำ/ปฏิเสธซ้ำ ให้เห็นว่ามีการป้องกันระดับ HTTP status code จริง

## สไลด์ 20 — Knowledge Grounding: ป้องกัน Hallucination

**Headline:** ตอบจากเอกสารจริง ไม่ใช่เดา

**เนื้อหา (จาก `app/backends/full_document_knowledge.py` + ARCHITECTURE.md):**
- **ไม่ใช้ vector search / embedding / RAG แบบ chunk** — เป็นการตัดสินใจทางสถาปัตยกรรมที่ตั้งใจ
- ขั้นที่ 1 — **Document Routing:** โมเดลเห็นแค่ catalog (รหัสไฟล์ + ชื่อไฟล์ + หัวข้อ) เลือกไฟล์ที่เกี่ยวข้อง (ยังไม่เห็นเนื้อหา)
- ขั้นที่ 2 — **Full-file Long Context:** อ่านเอกสารที่เลือก**เต็มไฟล์**ทุกไฟล์ ส่งเข้า Gemini Long Context พร้อมคำถาม
- Citation ทุกอันต้องอ้างอิงข้อความที่ตรวจสอบย้อนกลับไปยังไฟล์จริงได้ (snippet ต้องพบใน source file จริง ไม่ใช่โมเดลแต่งขึ้น)
- ไม่มีไฟล์ที่ตรง/กำกวม → คืน **no-evidence** ให้ Main Agent ถามกลับหรือบอกว่าไม่มีข้อมูล — **ห้ามเดา**
- มี **alias rule** (Markdown ที่ผู้ดูแลกำหนด) ให้ query ที่พบบ่อยข้ามขั้น routing ไปตรงไฟล์ได้เลย เร็วขึ้นและกันโมเดลเลือกผิด

**ทำไมต่างจากทีมอื่น:** ทีมส่วนใหญ่ทำ RAG มาตรฐาน (chunk + embedding) ซึ่งเสี่ยง citation หลุดบริบทเมื่อ chunk ตัดกลางประโยค การเลือกส่ง**เอกสารเต็มไฟล์**แลกด้วย token cost ที่สูงขึ้น เพื่อแลกกับความแม่นยำที่สูงกว่า (เหมาะกับเอกสารทางการที่ต้องแม่นยำ 100% เช่น อัตราค่าไฟฟ้า)

**ภาพประกอบ:** Diagram 4 กล่องแนวนอน: "คำถาม" → "Document Router (เห็นแค่ catalog)" → "อ่านเอกสารเต็มไฟล์ที่เลือก" → "ตอบพร้อม citation ตรวจสอบได้" ใต้กล่องที่ 2 ใส่กิ่งแยก "ไม่พบไฟล์ที่ตรง → no-evidence → ไม่ตอบมั่ว"

## สไลด์ 21 — Trace & Observability

**Headline:** ทุก step ตรวจสอบย้อนกลับได้

**เนื้อหา:**
- ทุก conversation มี `traceId` เรียงตามลำดับเวลาด้วย `sequence`
- ข้อมูลอ่อนไหวถูก **redact ก่อนบันทึก** เสมอ (ไม่ใช่ redact ตอนแสดงผล — ป้องกันข้อมูลรั่วตั้งแต่ชั้น storage)
- `GET /api/v1/traces/{id}` ให้กรรมการ/ผู้ตรวจสอบดูย้อนหลังได้ว่า agent ตัดสินใจอะไรตอนไหน
- `__repr__`/`__str__` ของ config object ก็ปกปิด secret เสมอ (มี field list ชัดเจนว่าอันไหนห้ามโชว์: `gemini_api_key`, `oms_api_key`, `voc_api_key`, `line_channel_secret`, `line_channel_access_token`)

**ภาพประกอบ:** ไม่จำเป็นต้องมีรูป ใช้ mock JSON ของ trace event เดียว (สั้นๆ 4-5 บรรทัด) เป็น proof-of-concept

---

# SECTION 4 — Multi-Channel Interfaces + Plugin System (สไลด์ 22-33) — ตอบเกณฑ์ A + B หนักสุด

## สไลด์ 22 — 3 ช่องทาง สมองเดียว

**Headline:** Web / Voice / LINE — ผูกกับ Main Agent ผ่าน interface เดียวกัน

**เนื้อหา:**
- ทุกช่องทางเรียก Main Agent ได้แค่ผ่าน `MainAgentGateway` protocol: **`handle_chat` / `confirm_pending_action` / `reject_pending_action` เท่านั้น**
- Bridge ของแต่ละช่องทาง (VoiceBridge, LineBridge) **ไม่แตะ ToolRegistry หรือ backend ธุรกิจใดๆ โดยตรง** — แปลว่าเพิ่มช่องทางใหม่ (เช่น WhatsApp, Facebook Messenger ในอนาคต) ไม่ต้องแก้ business logic เลย แค่เขียน bridge ใหม่

**ภาพประกอบ:** Diagram 3 กล่องช่องทางด้านบน ลูกศรชี้ลงมาที่กล่อง "MainAgentGateway (3 เมทอด)" กล่องเดียว แล้วลูกศรเดียวชี้ต่อไป Main Agent — สื่อภาพ "funnel" ที่ทุกช่องทางบีบเข้าจุดเดียว

## สไลด์ 23 — Web Chat Interface

**Headline:** Web Chat — choicePrompt แบบมีโครงสร้าง

**เนื้อหา:**
- ทุกตัวเลือกใน `choicePrompt` มาจาก **catalog ของ backend เท่านั้น** ไม่ใช่ text ที่โมเดลแต่งขึ้น (กัน prompt injection / ตัวเลือกหลอก)
- ปุ่มยืนยัน/ยกเลิกเรียก endpoint จริง ไม่ใช่ตีความข้อความแชต

**ภาพประกอบ:** Mockup หน้าจอแชตง่ายๆ (กล่องข้อความ + ปุ่มตัวเลือก 2-3 ปุ่ม + ปุ่มยืนยัน/ยกเลิกสีเขียว/แดง) ไม่ต้องสวยมาก แค่ให้เห็น pattern

## สไลด์ 24 — Voice Interface: Gemini Live

**Headline:** โหมดเสียงแบบเรียลไทม์

**เนื้อหา:**
- `WS /ws/live` — หนึ่ง WebSocket = หนึ่ง Gemini session + VoiceBridge + audio queue + conversationId
- ไมโครโฟน: **PCM16 16kHz mono** (binary frame) → เสียงตอบ: **PCM16 24kHz mono** เล่นแบบ gap-free, flush ทันทีเมื่อผู้ใช้พูดแทรก (`audio.interrupted`)
- โมเดลเห็นฟังก์ชันแค่ 3 ตัว: `pea_agent_chat`, `pea_confirm_pending_action`, `pea_reject_pending_action`
- **ไม่มีฟังก์ชันไหนรับ `pendingActionId` เลย** — การยืนยัน/ปฏิเสธผูกกับ "รายการปัจจุบันของ session" ที่ bridge เลือกให้เอง (กันโมเดลส่ง id ผิด/ปลอม)
- `voiceGuidance`: คำแนะนำวิธีพูดตามช่องทาง — **มีจอ**พูดสั้นว่ามีตัวเลือกให้กด, **ไม่มีจอ** (สายโทรศัพท์) ต้องอ่านตัวเลือกครบทุกข้อ

**ภาพประกอบ:** Waveform icon ง่ายๆ + ตาราง PCM16 16kHz→24kHz (in/out) ถ้าอยากได้ diagram: กล่อง "ไมค์ 16kHz" → "Gemini Live session" → "ลำโพง 24kHz" พร้อม branch "audio.interrupted → flush queue"

## สไลด์ 25 — Voice Interface: Event Protocol

**Headline:** Event ที่ WebSocket ส่งกลับมา

| `type` | ความหมาย |
|---|---|
| `session.ready` | เชื่อมต่อพร้อมแล้ว |
| `transcript.user` / `transcript.assistant` | ถอดเสียงเป็นข้อความ |
| `agent.response` | ผลลัพธ์จาก Main Agent (chat/confirm/reject) |
| `audio.interrupted` | ผู้ใช้พูดแทรก — ล้างคิวเสียง |
| `turn.complete` | จบรอบการตอบ |
| `error` | error code: `no_pending_action`, `invalid_input`, `action_conflict`, `unknown_function`, `unavailable` |

**ภาพประกอบ:** ตารางเรียบๆ พร้อมไอคอนเล็กข้าง type แต่ละแบบ (วงกลมเขียว=ready, คลื่นเสียง=transcript, ลูกศรวน=response, มือหยุด=interrupted, checkmark=complete, สามเหลี่ยมเตือน=error)

## สไลด์ 26 — LINE Interface

**Headline:** LINE — ปุ่ม postback เท่านั้น ไม่ตีความแชต

**เนื้อหา:**
- เปิดเฉพาะเมื่อตั้ง `LINE_CHANNEL_SECRET` + `LINE_CHANNEL_ACCESS_TOKEN` ครบ
- ทุก request ต้องมี `X-Line-Signature` (HMAC-SHA256 ของ raw body) — ไม่ผ่านตอบ **403 ทันที** (fail-closed ก่อนประมวลผลอะไรเลย)
- ตอบ 200 ทันทีแล้วประมวลผล background (เพราะ agent loop อาจนานกว่า timeout ของ LINE) + แสดง loading indicator ก่อน
- **ยืนยัน/ปฏิเสธทำผ่านปุ่ม postback เท่านั้น** — ตีความข้อความแชตเป็นคำยืนยันเป็น **non-goal ที่ประกาศไว้ชัดเจน**
- ข้อความยาวเกิน ~1,900 ตัวอักษร ตัดเป็นหลายข้อความ (สูงสุด 5 ข้อความ/ครั้ง) + ป้าย "simulation" เมื่อผลลัพธ์เป็นข้อมูลจำลอง

**ภาพประกอบ:** Mockup แชต LINE จริง (กล่องข้อความเขียว-ขาวสไตล์ LINE) + ปุ่ม "ยืนยัน"/"ยกเลิก" ด้านล่าง

## สไลด์ 27 — เปรียบเทียบ 3 ช่องทาง (สรุปตาราง)

| ความสามารถ | Web Chat | Voice | LINE |
|---|---|---|---|
| choicePrompt แบบปุ่ม | ✅ | ❌ (ใช้ voiceGuidance แทน) | ✅ (Quick Reply) |
| ยืนยัน/ปฏิเสธ | ปุ่ม/endpoint | ฟังก์ชันเสียง (ไม่มี id) | ปุ่ม postback เท่านั้น |
| อ่านตัวเลือกให้ครบ | ไม่จำเป็น (เห็นบนจอ) | ✅ บังคับ (ไม่มีจอ) | ไม่จำเป็น |
| Realtime | HTTP request/response | WebSocket duplex | Webhook + push |

**ภาพประกอบ:** ตาราง checklist เรียบๆ ใช้ ✅/❌ ไอคอนเดียวกันทั้งเด็ค

## สไลด์ 28 — ทำไมต้องมีระบบปลั๊กอิน (transition slide)

**Headline:** ระบบไฟฟ้าไม่ได้มีแค่ OMS/VOC — วันหน้าอาจต้องต่อ Sabuy, ระบบมิเตอร์อัจฉริยะ, หรือระบบอื่นที่ยังไม่รู้จักวันนี้

**เนื้อหา:** จุดตายของ agent framework ส่วนใหญ่คือ "เพิ่มความสามารถใหม่ = แก้โค้ดแกนกลาง" — PEA One Agent แก้ปัญหานี้ด้วยสถาปัตยกรรมปลั๊กอินที่ Main Agent **ไม่รู้จักชื่อ tool ล่วงหน้าเลย** อ่านจาก registry ที่ประกอบตอน startup เท่านั้น

**ภาพประกอบ:** ไม่ต้องมี ใช้เป็น section divider (พื้นหลังเข้ม)

## สไลด์ 29 — Plugin Manifest: ตัวอย่างจริง

**Headline:** `plugin.yaml` — ประกาศเครื่องมือใหม่แบบ declarative

**เนื้อหา (ใช้ `app/plugins/oms/plugin.yaml` จริงเป็นตัวอย่าง ย่อ):**
```yaml
apiVersion: pea.one/v1
kind: Plugin
metadata:
  id: oms_tool
  name: OMS Outage
  enabled: true
  description: ตรวจ/แจ้งเหตุไฟฟ้าขัดข้อง...
runtime:
  factory: app.plugins.oms.factory:create_plugin
configuration:
  baseUrlEnv: OMS_BASE_URL
  timeoutEnv: OMS_TIMEOUT_SECONDS
  apiKeyEnv: OMS_API_KEY
operations:
  - action: get_outage_by_ca
    exposure: llm
    mode: read
  - action: prepare_anonymous_outage
    exposure: llm
    mode: prepare
    submitAction: submit_anonymous_outage
  - action: submit_anonymous_outage
    exposure: internal   # ← LLM เรียกไม่ได้ บังคับด้วย schema
    mode: submit
```
**จุดสำคัญ:** ไฟล์นี้**ไม่เก็บ secret เลย** (เก็บแค่ชื่อ environment variable) และ operation ที่เป็น `submit` **ต้องเป็น `internal` เท่านั้น** — ประกาศผิดจะ validate fail ตั้งแต่ startup

**ภาพประกอบ:** Code card เต็มจอ (YAML syntax highlighting ถ้าทำได้) — ไม่ต้องมี diagram เพิ่ม โค้ดจริงน่าเชื่อถือกว่า mockup

## สไลด์ 30 — Plugin Loader: Fail-Closed Validation Pipeline

**Headline:** Manifest ผิด = ระบบไม่ start ไม่ใช่ error ตอนรันจริง

**เนื้อหา (จาก `app/plugins/loader.py` และ `manifest.py` จริง — ลำดับการตรวจสอบตอน startup):**
1. อ่าน `plugin.yaml` ทุกไฟล์ใต้ `app/plugins/*/` — ตัวที่ `enabled` ไม่ใช่ `true` ชัดเจน**ข้าม**ไปเลย (โครงที่เขียนไม่เสร็จอยู่ร่วม repo ได้โดยไม่พัง)
2. Validate schema ด้วย Pydantic (`PluginManifest.model_validate`)
3. **เทียบ manifest กับ `app/contracts.py` (Pydantic จริง) ทุก action** — ชื่อ input/output contract ต้องตรงเป๊ะ ไม่ตรง = raise error ทันที (กัน manifest เขียนไว้ผิดจากโค้ดจริงแบบเงียบๆ)
4. เช็ค action ที่ประกาศครบตามสัญญา ไม่มากไม่น้อย (`missing` / `unknown` action = error)
5. เช็ค `submit` action ต้องเป็น `internal` exposure เท่านั้น (บังคับ human-in-the-loop ที่ระดับ schema)
6. Import factory — **ต้องอยู่ใต้ `app.plugins.` เท่านั้น** (`TRUSTED_FACTORY_ROOT`) กัน path จากภายนอกที่ไม่น่าเชื่อถือ
7. เรียก factory จริง ตรวจว่า tool ที่คืนมามี `execute`/`reset` และชื่อ (`.name`) ตรงกับ manifest

**ทำไมสำคัญ (เกณฑ์ B):** เป็นตัวอย่างของ "**defense in depth**" ที่ทีมส่วนใหญ่ในงานแข่งไม่ได้ลงลึกขนาดนี้ — plugin ที่เขียนผิดจะ**ถูกจับตั้งแต่ก่อน deploy** ไม่ใช่ไปพังตอนลูกค้าใช้งานจริง

**ภาพประกอบ:** Flowchart แนวตั้ง 7 ขั้น แต่ละขั้นมีลูกศรแยกไป "❌ Startup fails" ด้านข้างถ้าขั้นนั้นไม่ผ่าน (fail-closed pattern ให้เห็นชัดว่าทุกขั้นมีทางออกที่ปลอดภัย)

## สไลด์ 31 — วิธีต่อระบบใหม่เข้ากับ Agent (ตอบ "การต่อ plugin อื่นๆ" ตรงๆ)

**Headline:** เพิ่มระบบใหม่ใน 6 ขั้น โดยไม่แตะ Main Agent เลย

**เนื้อหา (ขั้นตอนจริงที่ทีม developer ทำได้วันนี้ ผ่าน CLI scaffolding tool `./scripts/add-plugin`):**
```
$ ./scripts/add-plugin sabuy_v2 --preview   # ดูผลลัพธ์ก่อนโดยไม่เขียนไฟล์จริง
```
1. ประกาศ action/contract ใหม่ใน `app/contracts.py` (ถ้ายังไม่มี)
2. รัน `./scripts/add-plugin <ชื่อ>` — **generate `plugin.yaml` + `factory.py` อัตโนมัติ** ให้ตรงกับ contract เป๊ะ (ไม่มีโอกาส manifest หลุดจาก schema ตั้งแต่ต้น)
3. เขียน class เครื่องมือจริงให้ทำ HTTP call/error mapping
4. เติม description ที่เป็น `TODO` ให้สื่อความหมายกับ LLM
5. เติม configuration (base URL/API key) ใน `app/core/config.py`
6. ตั้ง `enabled: true` แล้ว restart server — **loader หาเจอเอง ไม่ต้องแก้ Main Agent, ToolRegistry, หรือโค้ดแกนกลางไฟล์ไหนเลย**

**นี่คือคำตอบของ "ความสามารถในการขยายระบบ"** ที่กรรมการมักถามในงานลักษณะนี้ — ระบบพร้อมต่อ "ระบบมิเตอร์อัจฉริยะ", "Sabuy", หรือระบบใหม่ที่ กฟภ. มีในอนาคต โดยไม่ต้องเขียนใหม่ทั้งชิ้น

**ภาพประกอบ:** Terminal/CLI mockup จริง (พื้นหลังดำ ตัวหนังสือเขียว/ขาวแบบ terminal) โชว์คำสั่ง `./scripts/add-plugin` กับ output สั้นๆ ที่มันพิมพ์ (บอกว่าเขียนไฟล์อะไรบ้าง + ขั้นตอนถัดไป) — เป็นภาพที่ทรงพลังมากเพราะเป็น "ของจริงที่รันได้" ไม่ใช่ mockup โฆษณา

## สไลด์ 32 — ปลั๊กอินที่มีอยู่วันนี้

**Headline:** ระบบพิสูจน์แล้วว่ารองรับได้หลายปลั๊กอินพร้อมกัน

| ปลั๊กอิน | สถานะ | operations | หมายเหตุ |
|---|---|---|---|
| `oms_tool` | ✅ enabled | 5 (2 read/prepare-submit pairs) | เชื่อม OMS REST จริงผ่าน httpx |
| `voc_tool` | ✅ enabled | 4 (list/prepare/submit/get) | เชื่อม SimulatedVocBackend |
| `sabuy_tool` | ⏸ dormant (เขียนโค้ด+เทสไว้แล้ว แค่ยังไม่ enable) | — | พิสูจน์ว่าเพิ่ม/ปิดปลั๊กอินทำได้โดยไม่กระทบของเดิม |

**ภาพประกอบ:** 3 การ์ดแนวตั้ง สีเขียว (enabled) × 2 + สีเทา (dormant) × 1 — แต่ละการ์ดมีจำนวน operations เป็นตัวเลขใหญ่

## สไลด์ 33 — ตัวอย่างเพิ่มความสามารถ VOC (before/after)

**Headline:** ตัวอย่างจริง: `list_categories` → `prepare_case` → `submit_case` → `get_case`

**เนื้อหา:** เดินตาม 4 operation ของ `voc_tool` ทีละอัน อธิบายว่าอันไหน `read` (ดึง catalog / ติดตามเคส) อันไหน `prepare` (ร่างไว้ก่อน) อันไหน `submit` (`internal` เท่านั้น ต้องผ่าน confirm endpoint)

**ภาพประกอบ:** Sequence diagram แนวนอน 4 กล่อง (เหมือนสไลด์ 19 แต่เจาะจง VOC) — ใช้เพื่อ "สอน" กรรมการว่า pattern นี้ใช้ซ้ำได้กับทุกปลั๊กอิน ไม่ใช่ hardcode เฉพาะ OMS

---

# SECTION 5 — ตัวอย่างการทำงานจริง (สไลด์ 34-36) — ตอบเกณฑ์ A (อธิบายขั้นตอน)

## สไลด์ 34 — Case Study: "แจ้งเหตุไฟฟ้าดับ" ผ่าน Web Chat

**Headline:** เดินตามข้อความจริง ทีละขั้น

**เนื้อหา (narrative ทีละบรรทัด — ใช้พูดสดคู่ demo หรือ screenshot):**
1. ลูกค้าพิมพ์: "ไฟดับที่บ้าน เลขที่ผู้ใช้ไฟ XXXXXXXXXXXX"
2. Main Agent: Analyze → Plan → เรียก `oms_tool.get_outage_by_ca`
3. OMS ตอบกลับ (ผลจริง/simulation) → Main Agent สรุปให้ลูกค้า
4. ถ้ายังไม่มีรายงาน → เรียก `prepare_outage_with_ca` → ได้ `pendingAction`
5. ระบบถามยืนยัน (choicePrompt: "ยืนยันแจ้งเหตุนี้ใช่ไหม")
6. ลูกค้ากดยืนยัน → `confirm` endpoint → `submit_outage_with_ca` → สำเร็จ
7. Trace event ถูกบันทึกทุกขั้นตอน ตรวจสอบย้อนหลังได้

**ภาพประกอบ:** Timeline แนวตั้ง 7 จุด พร้อม screenshot ของหน้าจอจริง (ถ้ามีเดโมรันอยู่ — แนะนำให้สกรีนช็อตจากเดโมจริงตอนซ้อม ไม่ใช่ mockup) หรือถ้าไม่มีเวลา ใช้กล่องข้อความจำลองแทน

## สไลด์ 35 — Case Study เดียวกัน แต่ผ่าน Voice

**Headline:** ต่างช่องทาง ตรรกะเดียวกัน

**เนื้อหา:** ย้ำว่า business logic (ขั้น 2-7 ข้างบน) **ไม่เปลี่ยนเลย** — สิ่งที่ต่างคือ `voiceGuidance` (พูดสั้นถ้ามีจอ / อ่านตัวเลือกครบถ้าไม่มีจอ) และการยืนยันเป็นการพูด "ใช่" แทนการกดปุ่ม

**ภาพประกอบ:** ใช้ diagram/timeline เดิมจากสไลด์ 34 แต่ไฮไลต์เฉพาะจุดที่ต่าง (สีต่างออกมา) — สื่อว่า "แก้จุดเดียว ใช้ได้ทุกช่องทาง"

## สไลด์ 36 — Fail-Closed Example: เมื่อไม่มีหลักฐาน

**Headline:** เมื่อไม่รู้ ระบบบอกว่าไม่รู้

**เนื้อหา:** ตัวอย่างคำถามที่เอกสารไม่ครอบคลุม → Document Router หาไฟล์ที่ตรงไม่เจอ → คืน no-evidence → Main Agent ตอบ "ไม่มีข้อมูลเรื่องนี้ กรุณาติดต่อ [ช่องทางที่เหมาะสม]" **แทนที่จะเดาคำตอบ**

**ภาพประกอบ:** กล่องข้อความแชต 2 ฝั่ง (ลูกค้าถาม / agent ตอบแบบ fail-closed) ไม่ต้องมี diagram ซับซ้อน

---

# SECTION 6 — ทดสอบ, ผลลัพธ์, แผนต่อไป (สไลด์ 37-42) — ตอบเกณฑ์ A (ทดสอบ) + C (ผลประโยชน์)

## สไลด์ 37 — Testing Strategy

**Headline:** 275 automated tests ผ่านทั้งหมด ใน 1.48 วินาที

**เนื้อหา (breakdown จริงจากการรัน `pytest --collect-only`):**

| หมวด | จำนวนเทส |
|---|---|
| Agent orchestration (main loop) | 45 |
| VOC plugin (intake/flow/prefill/tool/backend) | 48 |
| Knowledge grounding | 30 |
| LLM factory/config/prompting/demo | 34 |
| Voice/Live bridge | 27 |
| Contracts + API routes | 23 |
| OMS (tool+backend) | 16 |
| Sabuy (dormant, พร้อมเปิดใช้) | 14 |
| Plugin loader validation | 13 |
| Evaluation/MVP harness | 17 |
| LINE signature | 4 |
| Gemini adapter (mocked) | 3 |
| **รวม** | **275** |

**สำคัญ:** ทุกเทส**ไม่เรียก network จริงเลยแม้แต่ครั้งเดียว** (mock ทั้งหมดผ่าน `httpx.MockTransport`/`monkeypatch`) — เร็ว รันซ้ำได้ไม่จำกัด ไม่มีค่าใช้จ่าย API ตอนพัฒนา

**ภาพประกอบ:** กราฟแท่งแนวนอน (horizontal bar) 12 หมวด เรียงจากมากไปน้อย + stat tile ใหญ่ "275 / 1.48s / 0 real API calls" ด้านบน

## สไลด์ 38 — Pilot Plan (ตอบช่องโหว่ "ทดลองกับหน่วยงาน ≥2 แห่ง" ตรงไปตรงมา — ⚠️ อ่านคำเตือนด้านล่าง)

**Headline:** แผนทดลองใช้จริง 2 หน่วยงานนำร่อง

**⚠️ พูดตรงๆ ในสไลด์นี้ (สำคัญมาก อย่าข้าม):** ระบบยัง**ไม่ได้ทดลองกับหน่วยงานจริง** ณ วันนำเสนอ — OMS/VOC/Sabuy ทั้งหมดยังเป็น simulation **อย่าแกล้งบอกว่าทดลองแล้วถ้ายังไม่ได้ทำ** เดี๋ยวกรรมการถามรายละเอียดจะตอบไม่ได้ ให้นำเสนอเป็น "แผนที่พร้อมทำทันที" แทน

**เนื้อหา (โครงร่างที่แนะนำ — ต้องคุยกับทีม/อาจารย์ที่ปรึกษาก่อนใส่ชื่อหน่วยงานจริง):**
1. **หน่วยงานนำร่อง 1 — 1129 PEA Contact Center:** เริ่มจาก flow "แจ้งเหตุไฟฟ้าขัดข้อง" ผ่าน Voice เพราะมี baseline อยู่แล้ว (รายงาน พ.ค. 68) วัดผลเทียบ Abandon Call/Speed of Answer ก่อน-หลัง
2. **หน่วยงานนำร่อง 2 — กฟฟ. สาขาที่มีปริมาณ VOC/ขอใช้ไฟสูง:** ทดลอง Web Chat/LINE สำหรับ VOC intake เทียบเวลาปิดเรื่อง (case closure time)
3. Timeline: 2 สัปดาห์ shadow mode (agent เตรียมคำตอบ ให้คนตรวจก่อนส่งจริง) → 4 สัปดาห์ pilot จำกัดปริมาณ → ประเมินผล → ขยาย

**ภาพประกอบ:** Timeline แนวนอน 4 ช่วง (Gantt bar สั้นๆ): Shadow mode → Limited pilot → Evaluate → Scale

## สไลด์ 39 — Impact: ต้นทุนต่อสาย

**Headline:** ผลลัพธ์เชิงตัวเลขที่จับต้องได้

**ใช้ cost comparison artifact ที่ทำไว้แล้วทั้งหน้า** (`https://claude.ai/code/artifact/d26ad006-e48b-49ec-aed3-b927ca9bbc84`)

**ตัวเลขสรุปที่ต้องพูดปากเปล่าคู่ภาพ:**
- ต้นทุนต่อสาย: 9.2 บาท (ปัจจุบัน, labor-only) → 3.0 บาท (Gemini Voice Agent) = **ถูกกว่า ~67%**
- ประหยัดโดยประมาณ **~16.4 ล้านบาท/ปี** (ที่ปริมาณสายเท่าเดือน พ.ค. 68)
- **ต้องพูดสมมติฐานออกเสียงด้วย** (ดู Appendix A) — กรรมการเชื่อถือมากกว่าถ้าเห็นว่าทีมรู้ข้อจำกัดของตัวเลขตัวเอง

**ภาพประกอบ:** ใช้ artifact เดิมทั้งหน้า ไม่ต้องทำใหม่

## สไลด์ 40 — Impact: ผลเชิงคุณภาพ

**Headline:** ไม่ใช่แค่ถูกกว่า — ดีกว่าในมิติอื่นด้วย

**เนื้อหา:**
- ลด Abandon Call: ตอบพร้อมกันหลายสาย ไม่ต้องรอคิว agent ว่าง (แก้ตรงจุดคอขวดจากสไลด์ 4-6)
- บริการ 24/7 ไม่ขึ้นกับกะเวลาทำงานของ agent มนุษย์
- ความสม่ำเสมอของคำตอบ (ตอบจากเอกสารทางการเดียวกันทุกครั้ง)
- Audit trail ครบ (trace ทุก step) → ตรวจสอบย้อนหลังง่ายกว่าบันทึกเสียงแบบเดิม

**ภาพประกอบ:** ไอคอนเรียบง่าย 4 อัน (นาฬิกา 24 ชม. / คนหลายคนพร้อมกัน / เอกสารตรวจสอบได้ / ใบเสร็จ trace) เรียงแถวเดียว ไม่ต้องเป็น illustration ซับซ้อน

## สไลด์ 41 — ความคิดสร้างสรรค์ / จุดต่างจากทีมอื่น (เกณฑ์ B)

**Headline:** สิ่งที่ทีมอื่นมักไม่ทำ แต่เราทำ

1. **ไม่ใช้ RAG/vector search แบบทั่วไป** — เอกสารเต็มไฟล์แทน chunk ลด hallucination
2. **Orchestrator เดียว ไม่ fragment เป็น sub-agent หลายตัว** — audit trail ตรวจง่าย ลด failure mode
3. **Write-safety บังคับด้วยโค้ด/schema ไม่ใช่ prompt** — bypass ไม่ได้
4. **Plugin scaffolding CLI** (`./scripts/add-plugin`) — ต่อระบบใหม่โดยไม่แก้ core เลย พิสูจน์ได้จริงในสไลด์ 31
5. **สมองเดียวรองรับ 3 ช่องทาง** พร้อม UX เฉพาะช่องทาง (เช่น สายโทรศัพท์อ่านตัวเลือกครบ)

**ภาพประกอบ:** ไม่จำเป็นต้องมีภาพ ถ้าอยากได้: 5 การ์ดไอคอน (ไม่ใช้เลข 01-05 เพราะไม่ใช่ sequence — ใช้ไอคอนแทน: เอกสาร/สมอง/กุญแจล็อก/terminal/ช่องทางสามช่อง)

## สไลด์ 42 — Roadmap

**Headline:** จากนี้ไปคืออะไร

- **ระยะสั้น:** pilot 2 หน่วยงาน (สไลด์ 38), เก็บผลจริงมาแทนตัวเลขประมาณการ
- **ระยะกลาง:** ขยายช่องทาง Voice ไปที่สาย 1129 จริง, เปิดใช้ `sabuy_tool` ที่เตรียมโค้ดไว้แล้ว
- **ระยะยาว:** ลงทุน hardware/local LLM เอง แทนจ่ายตาม token ให้ผู้ให้บริการภายนอก — ลดต้นทุนต่อสายอีกเมื่อ scale สูงขึ้น (ต้องนับ capex แยกจาก opex ที่โชว์ในสไลด์ 39)

**ภาพประกอบ:** เส้น timeline 3 จุด (สั้น/กลาง/ยาว) แนวนอน ธีมเดียวกับสไลด์ 38

## สไลด์ 43 — Closing

**Headline:** PEA One Agent — พร้อมทดลองจริง

**เนื้อหา:** สรุป 3 ตัวเลขหลัก (275 tests ผ่าน / ถูกกว่า ~67% ต่อสาย / มนุษย์ยืนยันทุกจุดเสี่ยง) + ขอบคุณ/ติดต่อทีม

**ภาพประกอบ:** ธีมเดียวกับสไลด์ปก (title) เพื่อปิดจบให้ดูเป็นชุดเดียวกัน

---

# Appendix A — ตัวเลขอ้างอิงทั้งหมด (ห้ามพิมพ์ผิดจากนี้)

### จาก 1129 PEA Contact Center (พ.ค. 2568, ที่มา: `1129.pdf`)
```
Call Offer (สายเข้าทั้งหมด)      : 244,737 สาย
Call Answer (ตอบรับได้)          : 219,564 สาย (89.71%)
Abandon Call (พลาด/ทิ้งสาย)      : 25,173 สาย (10.29%)   เป้าหมาย <5%   → ไม่ผ่าน
Average Speed of Answer          : 46 วินาที               เป้าหมาย <10s  → ไม่ผ่าน
% Calls Waiting within 10 Sec.   : 57.40%                  เป้าหมาย >85%  → ไม่ผ่าน
จำนวน Agent (พ.ค. 68)            : 135 คน (ม.ค.-มี.ค. = 80, เม.ย. = 125)
เทียบ พ.ค. 67 → พ.ค. 68          : Call Offer 314,042 → 244,737 (ลดลง 22.07%)
                                    Abandon Call 6.32% → 10.29% (แย่ลง)

Average Talk Time & Wrap Time (ผ่านเป้าหมายทุกหมวด):
  แจ้งเหตุไฟฟ้าดับ   : 3:34 (เป้าหมาย <5:00)
  สอบถามข้อมูล       : 2:24 (เป้าหมาย <3:00)
  รับคำร้องขอใช้ไฟ    : 4:29 (เป้าหมาย <10:00)
  แจ้งเบาะแส         : 4:14 (เป้าหมาย <5:00)
  ร้องเรียน           : 3:31 (เป้าหมาย <5:00)
  เฉลี่ย 5 หมวด       : 3:38 (218.4 วินาที) → ใช้เป็น AHT ในการคำนวณต้นทุน

Non-Voice (พ.ค. 68): Chat 14,848 / E-mail 2,542 / Social 12,879 / Leave Voice 21 = รวม 30,290
รวมทุกช่องทางสะสม ม.ค.-พ.ค. 68 (Voice): 903,919 สาย
```

### การคำนวณต้นทุน (ประมาณการ — ระบุสมมติฐานเสมอเวลาพูด)
```
ต้นทุนปัจจุบัน (labor-only proxy):
  135 agents × 15,000 บาท/เดือน = 2,025,000 บาท/เดือน
  ÷ 219,564 สาย/เดือน = 9.2 บาท/สาย
  × 12 เดือน = 24,300,000 บาท/ปี

ราคา Gemini Live API (ทางการ, gemini-3.1-flash-live-preview):
  Audio input  : $0.005 / นาที
  Audio output : $0.018 / นาที
  รวม full-duplex (สมมติฐานอนุรักษ์นิยม) : $0.023 / นาที
  แปลงบาท (~36 บาท/USD) : 0.828 บาท/นาที

ต้นทุน Gemini ต่อสาย:
  0.828 บาท/นาที × 3.64 นาที (AHT เฉลี่ย) = 3.01 บาท/สาย
  × 219,564 สาย/เดือน = 660,868 บาท/เดือน (~661,000)
  × 12 เดือน = 7,930,000 บาท/ปี (~7.9 ล้าน)

ผลต่าง:
  ต่อสาย: 9.2 → 3.0 บาท (ถูกกว่า 67.4%, ~3.06 เท่า)
  ต่อเดือน: 2,025,000 - 660,868 = 1,364,132 บาท
  ต่อปี: ~16,369,584 บาท (~16.4 ล้านบาท)
```

**สมมติฐานที่ต้องพูดคู่กับทุกตัวเลข:**
1. 15,000 บาท/เดือน/คน คือ labor cost เปล่าๆ **ไม่ใช่มูลค่าสัญญา outsource จริงกับทรูทัช** → ส่วนต่างจริงน่าจะมากกว่านี้
2. คิด Gemini แบบ full-duplex เต็มความยาวสาย (worst-case) → ของจริงน่าจะถูกกว่านี้
3. ไม่ได้แปลว่าแทนที่ agent 100% — เหมาะกับเคสประจำ/ตอบซ้ำ ไม่ใช่เคสร้องเรียน/ซับซ้อน
4. ยังไม่รวม capex ของระบบ/การพัฒนา และยังไม่รวมการลงทุน hardware เอง (ถูกกว่านี้อีกในระยะยาว)

### ระบบ/โค้ด
```
Automated tests: 275 ผ่านทั้งหมด, รันจบใน 1.48 วินาที, ไม่มีการเรียก API จริงเลยแม้แต่ครั้งเดียว
Providers ที่ใช้จริง: Gemini (production) + demo (internal stub สำหรับ Judge/testing)
Bounded agent loop: ≤12 steps / ข้อความ
Channels: Web Chat, Voice (Gemini Live), LINE Messaging API
Tools: Knowledge (built-in, read-only), OMS (plugin, 5 operations), VOC (plugin, 4 operations)
Sabuy: โค้ด+เทสมีแล้ว แต่ enabled: false (dormant, ไม่ได้ลงทะเบียนใน runtime)
HTTP endpoints: 7 (chat, confirm, reject, traces, reset, health) + 1 WebSocket + 1 webhook
```

---

# Appendix B — สรุปรายการภาพประกอบทั้งหมด (checklist งานทำจริง)

| กลุ่มสไลด์ | ต้องการภาพ? | ใช้ของเดิมได้ไหม | ถ้าต้องทำใหม่ ทำแบบไหน |
|---|---|---|---|
| 1 Title / 43 Closing | โลโก้ PEA ทางการ | ต้องหาเพิ่ม | โหลดจากเว็บทางการ กฟภ. |
| 4-6 Root cause | กราฟ/gauge SLA + small multiples agent/abandon + heat chart รายชั่วโมง | ทำใหม่ (มีข้อมูลครบใน Appendix A) | metric card style เดียวกับ cost artifact |
| 10 Solution overview | Flow diagram (crop ครึ่งบน) | ✅ ใช้ของเดิม | — |
| 13 System topology | Layered diagram 5 ชั้น | ทำใหม่ | กล่องขอบบาง+ลูกศร สไตล์เดียวกับ flow diagram |
| 14-16 Interfaces (Agent/LLM/Tool) | Code card | ทำใหม่ (ง่าย แค่ code block) | mono font, ไม่ต้อง diagram |
| 17-18 HTTP API | ตาราง + code request/response | ทำใหม่ | ตารางเรียบ + two-column code card |
| 19 Write-safety | Crop แถบ gate จาก flow diagram | ✅ ใช้ของเดิม (crop) + เพิ่มข้อความ 409 | — |
| 20 Knowledge grounding | Diagram 4 กล่อง | บางส่วนยืมจาก flow diagram ได้ | ตัดมาแค่แถว Knowledge แล้วขยาย |
| 24-25 Voice interface | Waveform icon + event table | ทำใหม่ (เรียบง่าย) | ไอคอนเล็ก + ตาราง |
| 26 LINE interface | Mockup แชต LINE | ทำใหม่ | สไตล์ LINE จริง (เขียว-ขาว) |
| 30 Plugin loader | Flowchart 7 ขั้น | ทำใหม่ | fail-closed branch สีแดงข้างแต่ละขั้น |
| 31 Add-plugin CLI | Terminal mockup | ทำใหม่ (สำคัญมาก — ภาพนี้ทรงพลังสุดในเด็ค) | พื้นดำ ตัวหนังสือเขียว/ขาว, โชว์ output จริงถ้ารันได้ |
| 32 Plugins ที่มีอยู่ | 3 การ์ดสถานะ | ทำใหม่ (ง่าย) | เขียว×2 + เทา×1 |
| 34-36 Case study | Timeline/screenshot จริงจากเดโม | ทำใหม่ — **แนะนำสกรีนช็อตจากเดโมจริงตอนซ้อม** | ถ้าไม่มีเวลา ใช้กล่องข้อความจำลอง |
| 37 Testing | กราฟแท่งแนวนอน 12 หมวด | ทำใหม่ (มีตัวเลขครบใน Appendix A) | horizontal bar + stat tile |
| 38, 42 Timeline (pilot/roadmap) | Gantt bar สั้นๆ | ทำใหม่ (ใช้ template เดียวกันทั้งคู่) | 3-4 ช่วง แนวนอน |
| 39 Cost impact | Cost comparison เต็มหน้า | ✅ ใช้ของเดิม | — |
| 40 Qualitative impact | ไอคอน 4 อัน | ไม่จำเป็นต้องมี | เรียบง่ายถ้าต้องการ |
| 41 Creativity | ไอคอน 5 อัน (ไม่บังคับ) | ไม่จำเป็นต้องมี | — |

**สรุป:** ภาพที่**คุ้มค่าทำมากที่สุด**และไม่มีในระบบเดิมเลยคือ **สไลด์ 31 (terminal mockup ของ `add-plugin`)** — เป็นหลักฐานที่จับต้องได้ว่าระบบขยายได้จริง ไม่ใช่แค่คำโฆษณา แนะนำให้อัดวิดีโอสั้นๆ (10-15 วิ) รันคำสั่งจริงแทนภาพนิ่งด้วยซ้ำถ้ามีเวลา

---

# Appendix C — โทนภาพรวม (ให้ทุกสไลด์ดูเป็นชุดเดียวกัน)

- **สี:** ม่วง `#6B3FA0` (accent หลัก, Agentic AI/สิ่งใหม่) + อำพัน `#B8631E` (สถานะเตือน/ของเดิม/manual) + เขียว `#276B47` (success/saving) + แดง `#A6373A` (fail/rejected) — ผ่านการเช็ค accessibility (colorblind-safe) แล้วจาก 2 artifact ที่ทำไปแล้ว ใช้ต่อได้ทั้งเด็ค
- **ฟอนต์:** Kanit (หัวข้อ) + IBM Plex Sans Thai (เนื้อหา) + IBM Plex Mono (ตัวเลข/โค้ด) — Google Fonts ฟรีทั้งหมด
- **พื้นหลัง:** ขาวล้วน ไม่มี gradient เน้นคลีน
- **กฎการใช้ภาพ:** ทุกไดอะแกรมใช้กล่องขอบบาง + ลูกศร ไม่ใช้เงา/3D/ไอคอน stock ทั่วไป — ให้ดูเป็นเอกสารทางเทคนิคที่น่าเชื่อถือ ไม่ใช่สไลด์การตลาด
- **จังหวะนำเสนอ 10 นาที / ~43 สไลด์:** เฉลี่ย ~14 วินาที/สไลด์ — สไลด์ code card/ตาราง/ตัวเลข **พูดสั้นมาก** (แค่ชี้ประเด็นเดียว) ส่วนสไลด์ที่ยกระดับ (Root cause, Write-safety gate, Add-plugin CLI, Cost impact) **ใช้เวลานานกว่า** ~30-40 วิ ได้ เพราะเป็นจุดที่กรรมการจำ

---

# Appendix D — Test Breakdown ดิบ (สำหรับอ้างอิงถ้าโดนถามลึก)

```
45  tests/test_agent_orchestration.py
23  app/live/tests/test_bridge.py
19  knowledge/tests/test_full_document_knowledge.py
14  tests/test_contracts.py
13  app/plugins/tests/test_voc_intake.py
13  app/plugins/tests/test_loader.py
12  tests/test_mvp_evaluation.py
11  knowledge/tests/test_knowledge_tool.py
11  app/plugins/tests/test_voc_flow.py
 9  app/llm/tests/test_demo_plugin_planning.py
 9  app/core/tests/test_config.py
 9  app/backends/tests/test_simulated_voc.py
 9  app/api/tests/test_routes.py
 8  app/tools/tests/test_oms_tool.py
 8  app/plugins/tests/test_voc_prefill.py
 8  app/backends/tests/test_simulated_sabuy.py
 8  app/backends/tests/test_simulated_oms.py
 7  app/tools/tests/test_voc_tool.py
 6  app/tools/tests/test_sabuy_tool.py
 6  app/llm/tests/test_prompting.py
 6  app/core/tests/test_startup.py
 4  tests/test_line_signature.py
 4  app/core/tests/test_llm_factory.py
 3  tests/test_live_session.py
 3  tests/test_evaluator_datasets.py
 3  app/backends/tests/test_gemini_llm_adapter.py
 2  tests/test_qa_chat_flow.py
 1  tests/test_live_frontend_audio.py
 1  tests/test_frontend_linkify.py
---
275 total, 1.48s runtime, 0 real network calls
```

---

# Appendix E — เนื้อหาเพิ่มเติมจากการอ่านเอกสารรอบสอง (PRD / CONTRACTS เต็ม / VOC intake / docs/research / README)

> รอบนี้อ่านเพิ่ม: `PRD.md` (ทั้งไฟล์), `CONTRACTS.md` บรรทัด 231-391 (โมเดลโดเมนที่ตรึงไว้ + schema ของทุก tool),
> `app/plugins/voc/intake.py`, `app/plugins/voc/flow.py`, `app/plugins/voc/prefill.py`,
> `docs/research/*.md` (5 ไฟล์), `README.md` (ทั้งไฟล์)
> ทุกตัวเลข/ข้อความในภาคผนวกนี้ระบุไฟล์ต้นทางกำกับไว้ทุกจุด — **ห้ามเพิ่มตัวเลขที่ไม่มีไฟล์รองรับ**
> สไลด์ในภาคผนวกนี้ต่อเลขจากเด็คเดิม (จบที่สไลด์ 43) — เลือกหยิบไปแทรกตาม section ที่เหมาะสม
> ไม่จำเป็นต้องใส่ครบทุกอันในเวลา 10 นาที (ดู "ลำดับความสำคัญ" ท้ายภาคผนวก)

---

## สไลด์ 44 — VOC Prefill: ไม่ถามซ้ำสิ่งที่ลูกค้าบอกไปแล้ว (เกณฑ์ B)

**Headline:** ลูกค้าเล่ามาแล้ว ระบบไม่ถามซ้ำ — แต่ก็ไม่ยอมให้โมเดล "เดา" แทนลูกค้า

**เนื้อหา (จาก `app/plugins/voc/prefill.py` ทั้งไฟล์):**
- ปัญหาที่แก้: แบบฟอร์ม VOC ต้องการรหัส taxonomy ครบชุด ถ้าถามทีละข้อทั้งหมดจะ "รู้สึกเหมือนกรอกฟอร์ม" ทั้งที่ผู้ใช้มักเล่าอาการมาครบตั้งแต่ประโยคแรก
- วิธีทำ: `VocPrefiller` เดินคำถามในลำดับปกติ (สูงสุด **6 ขั้น**, `max_steps=6`) แล้วให้โมเดล**เลือกจากตัวเลือกที่ catalog สร้างมาแล้วเท่านั้น** ไม่ใช่ให้โมเดลกรอกค่าเอง
- **ด่านตรวจ 2 ชั้น:** (1) ค่าที่โมเดลตอบต้องอยู่ใน `{option.value}` ของคำถามรอบนั้น ไม่อยู่ = ทิ้งทันที (log `voc_prefill_out_of_catalog`) (2) ค่าที่ผ่านชั้นแรกยังต้องผ่าน `flow.apply()` ซึ่งเป็น validator เดียวกับที่ใช้ตอนผู้ใช้ตอบเอง
- โมเดลตอบ `NONE` เมื่อไม่มั่นใจ → หยุดเติมทันที แล้วถามผู้ใช้ตามปกติ
- provider ล่ม/ตอบไม่ได้ → คืน `None` (log `voc_prefill_llm_unavailable`) **การแจ้งเรื่องไม่ล้ม** แค่กลับไปถามตามปกติ
- **กฎความปลอดภัยที่ตรึงไว้เป็นค่าคงที่ในโค้ด:** `_NEVER_PREFILL = {STEP_CONSENT, STEP_CA_NUMBER}` — **ความยินยอม (consent) และหมายเลขผู้ใช้ไฟ (CA) ห้ามให้โมเดลเติมให้เด็ดขาด** ต้องมาจากการกระทำของผู้ใช้เท่านั้น
- ตัวเดียวกันนี้ยังใช้ตอนโหมดเสียง: เมื่อผู้ใช้พูดตอบแล้วจับคู่ตัวเลือกแบบตรงตัวไม่ได้ `VocGuidedFlow.advance` จะเรียก `prefiller.choose()` ช่วยตีความ (จาก `app/plugins/voc/flow.py`)

**ประโยคที่ใช้พูดบนเวที:** "worst case ของฟีเจอร์นี้คือ *ถามเพิ่มอีกหนึ่งคำถาม* ไม่ใช่ *สร้างรหัสผิดขึ้นมา*"

**ภาพประกอบ:** Diagram 2 เลน — เลนบน "ไม่มี prefill": กล่องคำถาม 6 กล่องเรียงยาว | เลนล่าง "มี prefill": กล่องคำถาม 2 กล่อง + กล่องเทา 4 กล่องที่มีเครื่องหมาย ✓ (เติมจากประโยคแรก) และ **มีกล่องแดง 2 กล่องคาไว้เสมอ** ป้ายว่า "consent / CA — ห้ามเติมอัตโนมัติ" ใช้สีม่วง `#6B3FA0` กับส่วนที่เติมได้ และสีแดง `#A6373A` กับ 2 กล่องที่ห้ามเติม

## สไลด์ 45 — VOC Guided Intake: บทสนทนาที่ขับด้วย catalog ไม่ใช่ prompt (เกณฑ์ A + B)

**Headline:** เพิ่มประเภทเรื่องใหม่ใน catalog = บทสนทนาเปลี่ยนเอง โดยไม่แก้โค้ดสักบรรทัด

**เนื้อหา (จาก `app/plugins/voc/intake.py`):**
- ที่มาของปัญหา (เขียนไว้ใน docstring ของไฟล์): gateway VOC รับเรื่องได้ก็ต่อเมื่อมีรหัส taxonomy ครบ (journey / request type / topic / issue / sub-issue / frequency / severity / จังหวัด-อำเภอ-ตำบล-สำนักงาน กฟภ.) — **โมเดลสร้างรหัสพวกนี้เองไม่ได้** ถ้าปล่อยให้โมเดลนำบทสนทนาจะได้ค่าที่เดาขึ้นมา หรือวนถามไม่จบ
- คำถามถัดไป **คำนวณจาก flag ของ journey ที่ catalog ประกาศเอง**: `requiresSubIssue`, `requiresFrequency`, `requiresSeverity`, `requiresIncidentLocation`, `reporterMode`, `supportsCaNumber`
- **ข้ามคำถามที่ไม่มีทางเลือกให้อัตโนมัติ** — ถ้าขั้นไหนมีตัวเลือกเดียว ระบบเติมให้แล้วเดินต่อทันที (ไม่ถามคำถามที่มีคำตอบเดียว)
- **ย้อนไปแก้คำตอบต้นทาง = ล้างคำตอบปลายทางอัตโนมัติ** (ตาราง `_DEPENDENTS`) เช่น เปลี่ยน journey → ล้าง request type/topic/issue/sub-issue/frequency/severity ทิ้ง เพื่อไม่ให้รหัสชุดสุดท้ายขัดกันเอง
- ทุกคำตอบผ่าน `apply()` ที่ตรวจกับตัวเลือกจริงเสมอ — **กันค่าปลอมที่ client ยิงมาเอง** และคุมความยาวรายฟิลด์ (หัวข้อ 140 / รายละเอียด 2,000 / ชื่อ 100 / เบอร์ 32 / สถานที่ 500 / CA 32 อักขระ)
- consent เป็น **ประตูบังคับ**: `build_external_payload()` โยน error ทันทีถ้ายังไม่ได้ `accept` และบันทึกลง payload ครบ (`noticeVersion`, `acceptedAt`, `channel: CHAT`) — ตรงกับ PDPA notice ที่ตรวจพบบนเว็บ VOC จริง (ดู `docs/research/voc-external-spec-research.md`)

**ภาพประกอบ:** Flowchart แนวตั้งแบบมีสาขา: กล่อง "catalog (journeys + flags)" อยู่ซ้าย มีลูกศรชี้เข้าทุกขั้นของคำถามที่อยู่ตรงกลาง สื่อว่า *catalog เป็นคนกำหนดลำดับ ไม่ใช่โค้ด* + ป้ายกำกับข้างลูกศร "เพิ่ม journey ใหม่ → คำถามเปลี่ยนเอง"

## สไลด์ 46 — บทสนทนาที่ "ไม่มีทางตัน" และใช้ได้กับสายโทรศัพท์ (เกณฑ์ A + B)

**Headline:** ออกแบบเผื่อกรณีที่ผู้ใช้ตอบไม่ตรงแบบ — เพราะของจริงเป็นแบบนั้น

**เนื้อหา (จาก `app/plugins/voc/flow.py` และ `intake.py`):**

| สถานการณ์จริง | สิ่งที่ระบบทำ (บังคับด้วยโค้ด) |
|---|---|
| ผู้ใช้พูดตัวเลขแทนการกดปุ่ม ("ข้อ 2") | `_match_option` รองรับการตอบด้วยลำดับข้อ — จำเป็นสำหรับสายโทรศัพท์ที่ไม่มีปุ่ม |
| ตอบขั้นเดิมไม่ผ่าน 3 ครั้ง | `_MAX_STEP_RETRIES = 3` แล้ว**ข้ามให้อัตโนมัติเฉพาะขั้นที่ข้ามได้** (เช่น CA) ไม่ปล่อยให้วนตัน |
| ตอบว่า "ไม่มี / ไม่ทราบ / จำไม่ได้ / ข้าม" | จับเป็นการข้ามขั้นตอน ไม่ใช่คำตอบผิด |
| กดปุ่มของคำถามเก่า (ค้างบนจอ) | ตรวจ `selectedPromptId` ไม่ตรงกับคำถามปัจจุบัน → ถามคำถามปัจจุบันซ้ำ ไม่รับค่าผิดขั้น |
| ที่อยู่อยู่นอก catalog ตัวอย่าง | เก็บ `locationText` ไว้เสมอ + ใส่รหัสพื้นที่เป็น `UNSPECIFIED` แล้วให้ VOC ปลายทาง map เอง — **ไม่ปฏิเสธผู้ใช้เพราะ catalog ตัวอย่างไม่ครบ** |
| พูดว่า "ยกเลิก / ไม่เอาแล้ว" | ปิด session ทันที ตอบยืนยันการยกเลิก |
| ไม่ยินยอม PDPA | ยกเลิกทันที + บอกตรงๆ ว่า "ระบบจะไม่เก็บข้อมูลและไม่ส่งเรื่องต่อ" |
| catalog ของ VOC ล่ม | ไม่เปิด session ค้างไว้เลย ตอบว่าบริการยังไม่พร้อม (fail-closed) |
| ถามว่า "มีหัวข้อร้องเรียนอะไรบ้าง" | `_INQUIRY_PATTERNS` กันไม่ให้เข้าใจผิดว่าเป็นการ**เปิดเรื่องใหม่** — คำถามขอข้อมูลต้องได้คำตอบ ไม่ใช่โดนลากเข้าแบบฟอร์ม |

**ทำไมสำคัญ:** นี่คือ "ความสามารถในการแก้ปัญหา" ที่เกณฑ์ A ให้คะแนน — ทีมส่วนใหญ่สาธิตเฉพาะเส้นทางที่ทุกอย่างถูกต้อง (happy path) แต่ระบบบริการลูกค้าจริงชนะหรือแพ้ที่ **เส้นทางที่ผู้ใช้ตอบไม่ตรงแบบ**

**ภาพประกอบ:** ตารางข้างบนใช้เป็นสไลด์ได้เลย (2 คอลัมน์) — ถ้ามีเวลา ทำเป็นการ์ด 4 ใบเลือกเฉพาะแถวที่แรงที่สุด (ตอบเป็นตัวเลข / ข้ามอัตโนมัติหลัง 3 ครั้ง / นอก catalog ไม่ปฏิเสธ / ไม่ยินยอมแล้วไม่เก็บข้อมูล)

## สไลด์ 47 — โมเดลโดเมนที่ตรึงไว้ 5 ชนิด (เกณฑ์ A)

**Headline:** ทุกสิ่งที่วิ่งในระบบมี schema ตายตัว ไม่มี "ก้อน dict ลอยๆ"

**เนื้อหา (จาก `CONTRACTS.md` หัวข้อ "โมเดลโดเมนที่ตรึงไว้"):**

| โมเดล | จุดที่น่าสนใจที่สุดเวลาพูด |
|---|---|
| `Citation` | `uri` เป็น logical URI (`knowledge://source/...`) **ไม่เปิดเผย absolute path ของเซิร์ฟเวอร์**, snippet ≤1,000 อักขระ และต้องตรวจสอบได้ว่าอยู่ในไฟล์จริง |
| `ToolCall` | tool ปฏิเสธการเรียกที่ `name` ไม่ได้เป็นเจ้าของ `action` นั้น |
| `ToolResult` | `simulation` เป็น `false` **ได้เฉพาะผลลัพธ์ Knowledge เท่านั้น** — ผลปฏิบัติการทุกตัวถูกบังคับให้ประกาศว่าเป็นข้อมูลจำลอง |
| `PendingAction` | `preparedInput` เปิดเผยเฉพาะฟิลด์ที่ผู้ใช้กรอกเอง, `idempotencyKey` ถูกปกปิดเป็น `[redacted]` **เสมอ** เพราะข้อความของผู้ใช้กำหนดค่านี้ได้ (กันผู้ใช้ยัดข้อมูลลง trace) |
| `TraceEvent` | `sequence` เพิ่มขึ้นอย่างเคร่งครัด + `kind` มี **10 ชนิด** (`chat_received`, `llm_requested`, `llm_responded`, `tool_called`, `tool_result`, `action_prepared`, `action_confirmed`, `action_rejected`, `action_submitted`, `error`) และ `data` จำกัดไม่เกิน 20 key |

**Error taxonomy:** `ToolError.code` มี **6 ค่าเท่านั้น** (`invalid_input`, `not_found`, `unavailable`, `conflict`, `confirmation_required`, `internal`) และ `message` ต้อง "ปลอดภัยสำหรับผู้ใช้" ยาวไม่เกิน 500 อักขระ — แปลว่า error ที่ผู้ใช้เห็นไม่มีทางหลุด stack trace หรือรายละเอียดภายในออกไป

**ภาพประกอบ:** ตาราง 5 แถวข้างบน + แถบล่างเป็น 6 ชิปสี (error code) เรียงแนวนอน — ใช้สีเทาทั้งหมด ยกเว้น `confirmation_required` ที่ใช้สีม่วง `#6B3FA0` เพื่อชี้ว่า human-in-the-loop เป็น error code ระดับสัญญา ไม่ใช่แค่ข้อความ

## สไลด์ 48 — "สิ่งที่เราตั้งใจไม่ทำ" (เกณฑ์ A — ใช้ตอบตอนถาม-ตอบ)

**Headline:** ขอบเขตที่ประกาศไว้ตั้งแต่ต้น ไม่ใช่ข้อแก้ตัวหลังบ้าน

**เนื้อหา (ยกตรงจาก `PRD.md` §6 Non-goals — เขียนไว้ก่อนเริ่มพัฒนา):**
- ไม่เชื่อม CRM / billing / payment / ระบบ กฟภ. production จริง และไม่ตัดเงินหรือแก้ข้อมูลลูกค้าจริง
- ไม่มี authentication/authorization สำหรับ production หลายผู้ใช้ และไม่มี persistent database (ข้อมูลหายเมื่อ restart)
- **ไม่มี vector database / embedding / chunk retrieval / RAG สำรอง** (การตัดสินใจเชิงสถาปัตยกรรม ไม่ใช่ข้อจำกัดด้านเวลา)
- **ไม่มี multi-agent topology, microservices, event bus หรือ queue**
- ไม่มีการยืนยันอัตโนมัติ ไม่มีการยืนยันผ่านข้อความแชต ไม่มี background submission
- ไม่มีระบบเรียนรู้จากแชตหรือเผยแพร่คำตอบเจ้าหน้าที่อัตโนมัติ (แยกเป็น roadmap ที่ `docs/plans/qa-learning-roadmap.md`)

**คู่กับหลักการที่ประกาศไว้ (`PRD.md` §4 Product Principles) — 7 ข้อ:** Evidence before fluency / One agent, explicit tools / Human-controlled writes / Fail closed / Simulation must be obvious / MVP first / **Auditable, not introspective** (แสดง trace ของเหตุการณ์ ไม่แสดง reasoning ภายใน)

**วิธีใช้สไลด์นี้:** อย่าพูดยาว — โชว์แล้วพูดประโยคเดียวว่า "ทุกอย่างที่เราไม่ได้ทำ เราเขียนไว้ว่าจะไม่ทำตั้งแต่วันแรก พร้อมเหตุผล" แล้วเก็บไว้เป็นสไลด์สำรองตอบคำถามกรรมการ ("ทำไมไม่ใช้ RAG", "ทำไมไม่ทำ multi-agent", "ทำไมยังไม่ต่อ production")

**ภาพประกอบ:** 2 คอลัมน์ ซ้าย = "หลักการ 7 ข้อ" (ตัวเล็ก) ขวา = "Non-goals" (ตัวเล็ก) ไม่ต้องมีไอคอน — สไลด์นี้เน้นความหนาแน่นของข้อมูลเพราะเป็นสไลด์สำรองสำหรับ Q&A

## สไลด์ 49 — เกณฑ์รับงานและประตูก่อนขึ้น production (เกณฑ์ A + C)

**Headline:** เรารู้ว่าอะไรคือ "พร้อมสาธิต" และอะไรคือ "พร้อม production" — และเราอยู่ตรงไหน

**เนื้อหา (จาก `PRD.md` §14 Acceptance Criteria):**

**พร้อมสาธิต (ผ่านแล้ว):** แอปเริ่มทำงาน + หน้าเว็บเรียก API v1 ได้ / Knowledge ตอบพร้อม citation ที่ผ่าน validation / capability ที่ประกาศทำงาน end-to-end จริง / prepare-confirm-reject แสดง state transition + idempotency ได้ / trace เรียงลำดับและปกปิดข้อมูล / UI แสดงสถานะ simulation ตลอด / automated checks ผ่าน / **สื่อสารข้อจำกัดตรงตามจริง**

**ยังไม่พร้อม production จนกว่า (5 ประตู):** เจ้าของข้อมูลอนุมัติเอกสารต้นทาง → live evaluation ครบชุดผ่านเกณฑ์ → real integration ผ่าน security/privacy review → มี authentication/authorization/persistence/monitoring → ผู้ใช้อนุมัติการ deploy อย่างชัดเจน

**ลำดับความจริงเมื่อเอกสารขัดกัน (`PRD.md` §18):** user decision > `PRD.md` > `CONTRACTS.md`+`app/contracts.py` > `ARCHITECTURE.md` > โค้ด/เทสที่รันได้ > integration report > README > แผนงานในอนาคต — และมีกฎกำกับว่า **"ห้ามแก้เอกสารหรือโค้ดให้ดูสอดคล้องกันโดยซ่อนความแตกต่าง"**

**ทำไมกรรมการจะชอบ:** เป็นหลักฐานว่าทีมแยก "เดโมที่ใช้ได้" ออกจาก "ระบบที่ปลอดภัยพอจะให้ประชาชนใช้" ได้ชัดเจน — และไม่ขายเกินจริง

**ภาพประกอบ:** เกจ/แถบความคืบหน้าแนวนอน 2 แถบซ้อน: แถบบน "พร้อมสาธิต" เต็มสีเขียว `#276B47` / แถบล่าง "พร้อม production" มีหมุด 5 จุด ยังไม่ติ๊กสักจุด ใช้สีเทา — ตรงไปตรงมาแต่ทรงพลังเพราะกล้ายอมรับ

## สไลด์ 50 — ทางเลือกที่เราศึกษาแล้วเลือกไม่ใช้ (เกณฑ์ A: ความเหมาะสมของกระบวนงาน + เกณฑ์ B)

**Headline:** ก่อนตัดสินใจ เราอ่าน framework ระดับโลกมาแล้ว 5 ตัว

**เนื้อหา (จาก `docs/research/enterprise_agent_orchestration_patterns.md` — บันทึกวิจัยจากเอกสารทางการของผู้พัฒนาเท่านั้น):**

| Framework ที่ศึกษา | สิ่งที่หยิบมาใช้ | สิ่งที่เลือกไม่ใช้ และเพราะอะไร |
|---|---|---|
| **OpenAI Agents SDK** | แยก conversation history / workflow state / domain facts ออกจากกัน และให้ tool คืน typed result ไม่เป็นเจ้าของบทสนทนา | ไม่ผูก SDK — MVP ไม่ต้องการ session backend หลายชนิด |
| **LangGraph** | แนวคิด human-in-the-loop ที่ side effect ก่อนจุดหยุดต้อง idempotent → กลายเป็นกฎ `idempotencyKey` ของเรา | ไม่ใช้ checkpointer/graph runtime — MVP ยังไม่มี branching/retry/compensation จริง |
| **Google ADK** | `SequentialAgent` = ลำดับที่มีผลกระทบต้องคุมด้วยโค้ด ไม่ใช่ให้โมเดลคุม → กลายเป็น guided intake ของ VOC | ไม่นำ ADK เข้ามาเป็น dependency |
| **Microsoft Semantic Kernel / Process Framework** | เมื่อ flow มี SLA/retry/approval ค่อยย้ายไป explicit process — ไม่ใช่ก่อนหน้านั้น | เอกสาร/ตำแหน่ง API ยังย้ายบ่อยในรุ่นใหม่ ไม่เหมาะเป็น dependency ของงานที่ต้องแม่นยำ |
| **Rasa Forms** | pattern `required_slots` + ถามช่องที่ยังไม่ครบตามลำดับ | ไม่นำ Rasa มาใช้ — "Pydantic models + reducer ใน Python ให้ผลเทียบเท่าและเล็กกว่า" (คำในเอกสารวิจัย) |

**ประโยคสรุปที่ใช้พูด:** "เราไม่ได้เลือกเขียนเองเพราะไม่รู้จักของที่มีอยู่ — เราอ่านมาแล้วและเลือกสิ่งที่เล็กที่สุดที่ตอบโจทย์ได้จริง"

**ภาพประกอบ:** ตาราง 3 คอลัมน์ข้างบน หรือถ้าอยากให้เร็วกว่า: โลโก้/ชื่อ 5 framework เรียงแถวเดียว แต่ละอันมีป้ายเล็กใต้ชื่อว่า "หยิบแนวคิด X มา / ไม่นำ dependency มา"

## สไลด์ 51 — เราตรวจคำตอบกับแหล่งทางการจริงก่อนใส่คลังความรู้ (เกณฑ์ A + C)

**Headline:** คลังความรู้ผ่านการ fact-check ทีละหัวข้อ กับเว็บ กฟภ. และ กกพ. เท่านั้น

**เนื้อหา (จาก `docs/research/pea_qa_fact_check.md` — ตรวจ 31 ส.ค. 2569):**
- ตรวจ Q&A **11 หัวข้อ** โดยใช้เฉพาะเว็บไซต์/ระบบทางการของ กฟภ. และสำนักงาน กกพ. — **ไม่ใช้เว็บข่าว เว็บตอบคำถาม หรือแหล่งข้อมูลรอง**
- ผลลัพธ์: **ตรง 5 หัวข้อ / ตรงบางส่วน 2 / ไม่พบหลักฐาน 4**
- หัวข้อที่ "ไม่พบหลักฐาน" (เช่น การเปลี่ยนที่อยู่จัดส่งใบแจ้งค่าไฟ, การจ่ายบิลเกินกำหนดที่ Counter Service) → ระบุให้ระบบ **fail closed: บอกตรงๆ ว่าไม่พบขั้นตอนสาธารณะทางการ แล้วเสนอช่องทางติดต่อแทน** ห้ามอนุมานจากแนวปฏิบัติทั่วไป
- ตัวอย่างความละเอียดที่ทำจริง: ค่าบริการรายเดือนบ้านอยู่อาศัยยืนยันได้ว่า ประเภท 1.1.1 (ไม่เกิน 150 หน่วย) = **8.19 บาท/เดือน** และ 1.1.2 (เกิน 150 หน่วย) = **24.62 บาท/เดือน** (ยังไม่รวม VAT/Ft) พร้อมกฎว่า **ห้ามตอบเลขเดียวโดยไม่ถามประเภทอัตรา/แรงดันก่อน**
- ค่า Ft ต้องแยก "นิยาม / วิธีคำนวณ / อัตราของงวด" ออกจากกันเสมอ และห้ามใช้ตัวเลขข้ามงวด

**ทำไมสำคัญ:** สไลด์ 20 (Knowledge grounding) พูดถึง *กลไก* ป้องกัน hallucination — สไลด์นี้แสดง *กระบวนการทำงานของคน* ที่มาก่อนกลไก คือการตรวจเอกสารต้นทางทีละหัวข้อและกล้าติดสถานะ "ไม่พบหลักฐาน" กับงานของตัวเอง

**ภาพประกอบ:** Donut/stacked bar เดียว แบ่ง 3 ส่วน (5 / 2 / 4) สีเขียว `#276B47` = ตรง, อำพัน `#B8631E` = ตรงบางส่วน, เทา = ไม่พบหลักฐาน + ข้อความข้างๆ ว่า "4 หัวข้อที่ไม่พบหลักฐาน = 4 หัวข้อที่ระบบจะไม่ตอบเอง"

## สไลด์ 52 — แผนสาธิตสด: กรรมการจะเห็นอะไร ภายในกี่นาที (เกณฑ์ A)

**Headline:** ทุกอย่างในเด็คนี้รันได้จริงบนเครื่องเดียว ใน 5 นาที

**เนื้อหา (จาก `README.md` — Quick Start และหัวข้อ "รันและตรวจสอบคุณภาพ"):**
```bash
uv sync --extra dev --extra voice     # ติดตั้ง (มี --extra voice สำหรับโหมดเสียง)
cp .env.example .env                  # ใส่ GEMINI_API_KEY
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
open http://127.0.0.1:8000
```
สิ่งที่กรรมการเห็นได้ทันที (ไม่ต้องเตรียมข้อมูลเพิ่ม — เอกสารความรู้อยู่ในโค้ดแล้ว อ่านสดจากดิสก์ ไม่มีขั้นตอนอัปโหลด/สร้างดัชนี):
1. ถามคำถามภาษาไทย เช่น *"ต้องการขอใช้ไฟฟ้าต้องมีเอกสารอะไรบ้าง"* → ได้คำตอบพร้อม citation
2. กดปุ่มไมโครโฟน 🎙 → คุยด้วยเสียงกับ agent ตัวเดียวกัน
3. `GET /health` → ต้องเห็น `"knowledge_backend": "ready"`
4. เปิด trace ดูเหตุการณ์ย้อนหลังทั้งหมด แล้วกด reset เริ่มเดโมใหม่ได้
5. อีก terminal: `uv run pytest -q` (ชุดเทสทั้งหมด) และ `./scripts/evaluate http://127.0.0.1:8000` (ตัวประเมิน 70 เคส)

**ข้อควรระวังตอนซ้อม (จาก `README.md` และ `PRD.md` §15 — ต้องอ่านก่อนวันงาน):**
- โหมดเสียงต้องกด **"อนุญาต (Allow)"** ไมโครโฟน และต้องเปิดผ่าน `http://127.0.0.1:8000` หรือ https เท่านั้น (สิทธิ์ไมโครโฟนไม่ทำงานบน http ที่ไม่ใช่ localhost) — ใช้ Chrome/Edge ล่าสุด เพราะต้องรองรับ AudioWorklet
- **ใช้หูฟัง** ลดเสียงสะท้อน; การพูดแทรกจะตัดเสียงที่เหลือทันที
- WebSocket ใหม่ = Gemini session ใหม่และบทสนทนาใหม่เสมอ → ถ้าเน็ตหลุดกลางเดโม ต้องเริ่มเรื่องใหม่ ไม่ต่อของเดิม
- **ยังไม่มีเทสอัตโนมัติสำหรับไมโครโฟน/ลำโพงจริงใน CI — ต้องซ้อมสดด้วยมือก่อนนำเสนอ** (ระบุไว้เองใน `PRD.md` §15)
- `gemini-3.1-flash-live-preview` เป็น **Preview** พฤติกรรม/เสียงอาจเปลี่ยนโดยไม่แจ้งล่วงหน้า → **แนะนำอัดวิดีโอสำรองไว้ล่วงหน้า**

**ภาพประกอบ:** Terminal mockup (ธีมเดียวกับสไลด์ 31) โชว์ 4 บรรทัดคำสั่ง + ภาพหน้าจอเดโมจริงเล็กๆ มุมขวาล่าง — ถ้าจะสาธิตสดจริง ให้ใช้สไลด์นี้เป็น "สไลด์ค้างจอ" ระหว่างสลับไปหน้าเว็บ

---

## บันทึกอ้างอิง (ไม่ต้องทำเป็นสไลด์ — ใช้ตอบคำถามหรือเป็นข้อมูลสำรอง)

### E1. ⚠️ ความไม่ตรงกันของเอกสารที่ต้องเช็กก่อนขึ้นสไลด์ (สำคัญที่สุดในภาคผนวกนี้)

ทีมต้องรู้ก่อนโดนถาม เพราะ `PRD.md` §17 เขียน "Documentation drift" ไว้เป็นความเสี่ยงของตัวเองอยู่แล้ว:

| ประเด็น | เอกสารว่าอย่างไร | โค้ดจริงว่าอย่างไร | ควรพูดว่าอย่างไร |
|---|---|---|---|
| สถานะ `voc_tool` | `PRD.md` §7 และ `CONTRACTS.md` (ตาราง `ToolCall`, `PendingAction`, หัวข้อ "สิ่งที่ไม่ใช่เป้าหมาย") ระบุว่า **VOC ไม่ลงทะเบียนใน runtime catalogue** | `app/plugins/voc/plugin.yaml` ตั้ง `enabled: true` และ `README.md` อธิบาย VOC เป็นความสามารถที่ใช้ได้ | **ยึดโค้ด** (VOC เปิดใช้งานจริง) แต่ถ้าโดนถามให้ตอบตรงว่า PRD/CONTRACTS บางส่วนเขียนไว้ตอน VOC ยัง dormant และยังตามอัปเดตไม่ทัน |
| จำนวนไฟล์ความรู้ | `README.md` ระบุ **44 ไฟล์** (บริการ 33 + Q&A 11) | นับสดวันที่ตรวจ: `knowledge/source/*.md` = **34** ไฟล์ + `knowledge/source/qa/*.md` = **12** ไฟล์ = **46** ไฟล์ | นับสดอีกครั้งก่อนขึ้นสไลด์ — `PRD.md` §15 ระบุเองว่าตัวเลขนี้ "ไม่ตรงกันและอาจล้าสมัย" |
| จำนวนเอกสารในเอกสารต้นทุน | `docs/research/gemini_token_cost.md` คิดจาก **38 เอกสาร** และเรียกว่า "DOCX" | ปัจจุบันคลังเป็นไฟล์ **Markdown** ไม่ใช่ DOCX | ถ้าอ้างตัวเลข token ต้องบอกว่าเป็นค่า ณ วันที่วิจัย (2 ก.ย. 2026) ไม่ใช่ค่าปัจจุบัน |
| enum หมวด VOC | ตาราง `voc_tool.prepare_case` ใน `CONTRACTS.md` ยังเขียน `billing/service/safety/other` | โค้ดจริงใช้ 6 ค่า: `power_quality`, `service`, `compliment`, `tip_off`, `operations`, `stakeholder_feedback` (ตาราง `_CATEGORY_BY_JOURNEY` ใน `flow.py`) ซึ่งตรงกับ 6 การ์ดบนหน้าแรก `voc.pea.co.th` จริง | ใช้ 6 ค่าจากโค้ด — `docs/research/voc-external-spec-research.md` ระบุความไม่ตรงนี้ไว้แล้วเช่นกัน |

### E2. ตัวเลขต้นทุนอีกชุดหนึ่งที่มีหลักฐานแน่นกว่า (สำรองไว้ถ้ากรรมการถามลึกเรื่อง ROI)

`docs/research/gemini_token_cost.md` (อัปเดต 2 ก.ย. 2026, อัตราแลกเปลี่ยนที่ใช้ **US$1 = ฿33** ต่างจาก Appendix A ที่ใช้ ~36) คำนวณด้วยวิธีที่ **นับ token จาก payload จริงด้วย Gemini `countTokens`** ไม่ใช่ประมาณจากจำนวนตัวอักษร:

```text
โมเดลที่ใช้จริง: Main Agent + Knowledge = gemini-3.5-flash-lite | Voice = gemini-3.1-flash-live-preview
Token ที่วัดได้: system instruction + tool catalogue = 3,053 tokens
                Document Router catalog (38 เอกสาร)   = 3,461 tokens
                เอกสารทั้งคลัง 38 ไฟล์                 = 34,915 tokens
ต้นทุนต่อ 1 turn: OMS ~฿0.086 | Knowledge ~฿0.197 | Knowledge worst case ~฿0.401
ต้นทุนต่อ session (≤5 turns): LINE/Text แนะนำตั้งงบ ฿2 | Voice+Chat แนะนำ ฿5
เทียบ manual (แบบจำลอง man-hour): AHT 5 นาที × ฿130/man-hour = ฿2.38 ล้าน/เดือน = ฿10.83/สาย
เทียบ AI (219,564 answered calls/เดือน, ทุกสายเต็มเพดาน 5 turns): ฿0.25-0.86 ล้าน/เดือน
`confirm → submit` ไม่เรียก LLM เพิ่ม เพราะเป็น typed tool call ภายใน
`pytest` = ฿0 (mock ทั้งหมด) | `./scripts/evaluate` 70 เคส ≈ ฿12
```

**ข้อสรุปเชิงธุรกิจที่เอกสารวิจัยเขียนไว้เอง และควรพูดตาม (อย่าตัดออก):** "ยังห้ามสรุปว่า AI ถูกกว่าสัญญา 1129 จริง จนกว่าจะได้มูลค่าสัญญา, AHT, FTE, SLA และ scope จริง" + ต้นทุนจริงต้องบวก integration, telephony/platform, monitoring, human escalation, QA, security/PDPA และ knowledge governance
**ถ้าเลือกใช้ชุดนี้แทน Appendix A ต้องเปลี่ยนทั้งเด็คให้สอดคล้องกัน — อย่าผสมสองชุด** (ต่างกันที่อัตราแลกเปลี่ยน ฿33 vs ฿36 และฐานเทียบ ฿10.83/สาย vs ฿9.2/สาย)

### E3. VOC intake ที่ทำอยู่ อ้างอิงจากการสำรวจเว็บ VOC จริง

`docs/research/voc-external-spec-research.md` (ตรวจ 1 ก.ย. 2569, **ใช้ `GET` อย่างเดียว ไม่ล็อกอิน ไม่ส่งคำร้อง ไม่แตะ write endpoint ใดๆ**) — ใช้เป็นคำตอบเมื่อถูกถามว่า "รู้ได้อย่างไรว่า schema ตรงกับของจริง":
- หน้าแรก `voc.pea.co.th` มี **6 ตัวเลือก** ตรงกับ 6 ค่าใน enum ของเรา (แจ้งปัญหาคุณภาพไฟฟ้า / แจ้งปัญหาด้านบริการ / ชื่นชม / แจ้งเบาะแส / แจ้งปัญหาการดำเนินงาน / ชื่นชม-เสนอแนะ-ข้อคิดเห็น)
- แบบฟอร์มจริงเก็บมากกว่าที่ contract ภายในเรามี: ชื่อแยกคำนำหน้า/ชื่อ/สกุล, CA, เลขบัตร, อีเมล, ที่อยู่แบบโครงสร้าง, สำนักงาน กฟภ., hierarchy 4 ชั้น, ความถี่, ความรุนแรง 1-5, ไฟล์แนบ, PDPA และ reCAPTCHA → **นี่คือเหตุผลที่ต้องมี `externalPayload` และ guided intake ที่ถามทีละขั้น** ไม่ใช่ให้โมเดลกรอกเอง
- เว็บจริงมี `POST /api/request/submit` ตรงหลัง validation + PDPA + reCAPTCHA + modal ยืนยัน — **ไม่พบ external "prepare" endpoint** → เอกสารวิจัยสรุปเองว่า `prepare_case → confirm → submit_case` ของเราเป็น **safety state machine ภายในที่ควรรักษาไว้ แต่ห้ามอ้างว่า mirror API ของ กฟภ.** (ประโยคนี้สำคัญมาก อย่าพูดเกิน)
- ข้อสังเกตด้านความปลอดภัยที่บันทึกไว้: หน้าเว็บ public ที่ตรวจ **ไม่พบ** header `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` — เป็นเพียง header observation **ไม่ใช่ข้อสรุปว่า exploit ได้** และ**ไม่ควรพูดบนเวที** เว้นแต่ถูกถามตรงๆ เรื่องความปลอดภัยของระบบปลายทาง

### E4. `sabuy_tool` ที่ dormant อยู่ ไม่ใช่โค้ดเปล่า — มี catalog ที่ verify แล้ว

`docs/research/sabuy_service_route_catalog.md` (ตรวจ 31 ส.ค. 2026, `GET` อย่างเดียว): ตรวจ URL ทางการจริงทีละหน้า และออกแบบสัญญาไว้แล้วเป็น **ToolAction เดียว `get_official_link`** ที่รับได้เฉพาะ `serviceKey` จาก allowlist **14 รายการ** (ไม่รับ URL อิสระจากโมเดล) คืน `officialUrl` + `requiresAuth`/`requiresOtp` เท่านั้น — **ห้ามกรอกฟอร์ม กด submit ยืนยัน OTP หรือชำระเงินแทนผู้ใช้**
มีกฎแยกความกำกวมเขียนไว้ด้วย: ถ้าผู้ใช้พูดแค่ "ติดตามสถานะ" โดยไม่ระบุว่าเป็นคำร้องบริการหรือเรื่องร้องเรียน → **ต้องถามกลับก่อน ห้ามเดาแล้วเปิดลิงก์**
ใช้ตอบคำถาม "ปลั๊กอินตัวถัดไปจะใช้เวลานานแค่ไหน" ได้ตรงๆ ว่า catalog + สัญญาพร้อมแล้ว เหลือแค่เขียน adapter กับตั้ง `enabled: true`

### E5. รายละเอียด Knowledge ที่เพิ่มจาก CONTRACTS (ถ้าถูกถามลึกในสไลด์ 20)

จาก `CONTRACTS.md` §1 `knowledge_tool` — กฎที่บังคับใช้ 8 ข้อ ที่น่าหยิบมาพูดเพิ่ม:
- `maxResults` = **จำนวนไฟล์ฉบับเต็มสูงสุดที่เลือกได้ (1-5, ค่าเริ่มต้น 3)** ไม่ใช่จำนวน chunk
- ต้องเลือก **ชุดไฟล์ที่เล็กที่สุดที่ครอบคลุมคำถาม** ห้ามส่งทั้งคลังเมื่อเกี่ยวข้องแค่บางไฟล์ (นี่คือคำตอบเวลาถูกถามว่า "ส่งเอกสารเต็มไฟล์แล้ว token ไม่บานหรือ")
- **ถ้าชุดไฟล์ที่เลือกเกิน context budget ห้ามตัดข้อความท้ายไฟล์แบบเงียบๆ** ต้องถามชี้แจงหรือคืน typed failure แทน
- `answerContext` ต้องเป็นคำตอบที่ครบและตรงคำถาม **ไม่ใช่หัวเอกสาร รายการลิงก์ หรือ citation snippet ดิบ**

### E6. รายละเอียดสัญญาที่เพิ่มจาก CONTRACTS (สำรองสำหรับสไลด์ Section 3)

- **`GeoPoint`** = `{lat, lon, gisType: "POINT"|"AREA"|null}` — พิกัดโดยประมาณจาก GIS ของ OMS ที่ gateway จริงเพิ่มเข้ามาภายหลัง; ถ้า OMS คืน `safetyMessage` มา **Main Agent ต้องแสดงข้อความความปลอดภัยนั้นก่อนข้อความอื่นเสมอ** (ตรงกับ `PRD.md` §10 ข้อ 7 "Electrical safety")
- `submit_outage_with_ca` คืน `level: METER` แบบตายตัวและตอบ 201 พร้อม `eventId`
- **การจับคู่ model-to-action ถูกเขียนไว้เป็นตารางในสัญญา 13 บรรทัด** (`knowledge_tool.search → KnowledgeSearchInput/Output` ฯลฯ) — runtime ตรวจ input ด้วยโมเดล `*Input` ก่อนเรียก tool และตรวจ output ด้วย `*Output` ก่อนสร้าง `ToolResult` **สองชั้น**
- `PRD.md` §10 ข้อ 8 "No false escalation": **ห้ามอ้างว่าสร้าง ticket หรือส่งต่อสำเร็จ จนกว่าระบบปลายทางจริงจะตอบรับ** — ประโยคนี้ใช้ปิดคำถาม "แล้วถ้าระบบหลังบ้านล่มล่ะ" ได้ดีมาก

### E7. ลำดับความสำคัญ ถ้าเวลาไม่พอ (10 นาทีใส่ไม่หมดแน่นอน)

เด็คตอนนี้จะกลายเป็น ~52 สไลด์ ซึ่งเกินจังหวะ 10 นาที — แนะนำ:
1. **ใส่แน่นอน (คุ้มค่าที่สุดต่อคะแนน):** สไลด์ 44 (VOC prefill — เกณฑ์ B) และ 45 (catalog-driven intake — เกณฑ์ A+B) เพราะเป็นของที่ทีมอื่นแทบไม่มี และเป็นหลักฐานว่า "agentic" จริง ไม่ใช่ chatbot
2. **ใส่ถ้ามีที่ว่าง:** สไลด์ 51 (fact-check — เสริมความน่าเชื่อถือของคลังความรู้) และ 52 (แผนสาธิตสด — ถ้าจะสาธิตจริงต้องมี)
3. **เก็บเป็นสไลด์สำรองท้ายเด็คสำหรับ Q&A (ไม่พูดในรอบนำเสนอ):** สไลด์ 46, 47, 48, 49, 50 — โดยเฉพาะ **48 (non-goals)** และ **50 (framework ที่ศึกษาแล้วไม่ใช้)** ซึ่งเป็นสองสไลด์ที่ช่วยได้มากที่สุดตอนโดนถามว่า "ทำไมไม่ทำ X"
