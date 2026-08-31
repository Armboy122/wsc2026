# รูปแบบการประสานงาน AI Agent ระดับองค์กร (บันทึกวิจัยสำหรับ MVP)

อัปเดต: 2025-02-14  
ขอบเขต: เอกสารทางการและ source repository ของผู้พัฒนาเท่านั้น

## สรุปสำหรับทีม

- **Tool ควรเป็น capability/domain operation ไม่ใช่เจ้าของบทสนทนา**: รับ input ที่ตรวจสอบชนิดแล้ว ทำงานโดเมน และคืนผลลัพธ์ที่มี schema; agent/orchestrator เป็นผู้ตัดสินใจว่าจะเรียกอะไรและพูดกับผู้ใช้แบบใด OpenAI ระบุว่า function tool ผ่าน runtime จะได้ argument validation, context, guardrails, timeout, failure handling และ tracing แต่การห่อฟังก์ชันไม่ได้ทำให้ฟังก์ชันเป็นเจ้าของ UX ([OpenAI Tools](https://openai.github.io/openai-agents-python/tools/), [OpenAI repo](https://github.com/openai/openai-agents-python))
- **State ต้องแยก conversation history, workflow state และ domain facts**: OpenAI Sessions เก็บ items อัตโนมัติข้าม `Runner.run`; LangGraph แยก checkpoint ระดับ thread จาก Store ระยะยาวข้าม thread; Google ADK ใช้ `session.state` แบบ key/value ที่ต้อง serialize ได้ และ event เป็นหลักฐานของการเปลี่ยน state ([OpenAI Sessions](https://openai.github.io/openai-agents-python/sessions/), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [ADK state](https://google.github.io/adk-docs/sessions/state/))
- **ให้ LLM เลือก intent/ค่าได้ แต่ให้โค้ดคุม invariant และลำดับที่มีผลกระทบ**: ADK `SequentialAgent` รันตามลำดับแบบ deterministic โดยไม่ให้โมเดลคุม flow; LangGraph interrupt ทำให้หยุดและ resume จาก checkpoint เดิม และเตือนว่า node อาจรันส่วนก่อน interrupt ซ้ำ จึงต้อง idempotent ([ADK SequentialAgent](https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts))
- **Structured output เป็น protocol ระหว่าง backend กับ channel**: ส่ง envelope ที่มี `type`, `schemaVersion`, `data`, `simulation`, `citations`, `actions` แล้วให้ Web/LINE render ตามชนิด; อย่าให้แต่ละ tool สร้างข้อความ/ปุ่มเฉพาะช่องทาง การบังคับ schema ด้วย Pydantic/annotations และการคืน dictionary/Pydantic จาก OpenAI tools เป็น precedent ที่ตรงกับแนวทางนี้ ([OpenAI Tools](https://openai.github.io/openai-agents-python/tools/))

## สิ่งที่แต่ละ framework บอกเรา

### OpenAI Agents SDK
`Session` เป็น abstraction สำหรับประวัติการสนทนา: ก่อน run จะโหลด history และหลัง run จะบันทึก user/assistant/tool items; มี backend เช่น SQLite, SQLAlchemy, Redis และ custom session protocol. ส่วน `RunContextWrapper` เหมาะกับ mutable application state ที่ส่งให้ tools/guardrails/handoffs แต่ควรจัดเก็บ state สำคัญใน persistence ของแอป ไม่ใช่พึ่ง prompt history อย่างเดียว. Function tools ใช้ type annotations/Pydantic สร้าง schema และมี runtime checks ([Sessions](https://openai.github.io/openai-agents-python/sessions/), [Context](https://openai.github.io/openai-agents-python/context/), [Tools](https://openai.github.io/openai-agents-python/tools/)).

**นัยต่อการออกแบบ**: แยก `ConversationState` (ข้อความ/turn), `WorkflowState` (ขั้นตอนและช่องที่ขาด), และ `DomainResult` (ผลจากระบบ) แม้จะ serialize ลง store เดียวกันได้; อย่าปล่อยให้ tool แก้ข้อความตอบหรือเปลี่ยนสถานะ write โดยตรง.

### LangGraph
Checkpointer บันทึก snapshot ของ graph state ต่อ thread เพื่อ conversation continuity, fault recovery และ HITL; Store ใช้ข้อมูลระยะยาวข้าม thread. `interrupt()` ส่ง payload ที่ JSON-serializable ให้ client, รอได้ไม่จำกัด และ resume ด้วย `Command(resume=...)` พร้อม `thread_id` เดิม. การ resume เริ่ม node ใหม่ตั้งแต่ต้น ดังนั้น side effect ก่อน interrupt ต้อง idempotent หรือย้ายไปหลัง approval ([Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)).

**นัยต่อการออกแบบ**: pending action ควรเป็น durable state ที่มี state machine และ approval payload; ไม่ใช้คำว่า “ยืนยัน” ในแชตเป็น authorization.

### Google ADK
`session.state` เป็น key/value ที่ serializable; prefix ช่วยกำหนด scope (`temp:`, session, `user:`, `app:`) และการแก้ state ควรผ่าน managed context/event เพราะการแก้ตรงบน Session อาจไม่ถูก persist. `SequentialAgent` บังคับลำดับที่กำหนดในโค้ดและแชร์ invocation/session state; control flow ไม่ได้ถูกตัดสินโดย AI ([State](https://google.github.io/adk-docs/sessions/state/), [Sequential workflow](https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/), [ADK Python repo](https://github.com/google/adk-python)).

**นัยต่อการออกแบบ**: VOC slot-filling ควรเป็น deterministic reducer: รับข้อความ → extract candidate → validate → บันทึกเฉพาะค่าที่ผ่าน validation → ถาม `next_missing_slot`; ไม่ให้ prompt เดา field ที่หาย.

### Microsoft Semantic Kernel / Agent Framework
Microsoft วาง agent orchestration และ Process Framework เป็นชั้น workflow แยกจากความสามารถของ agent: process ใช้ steps/events เพื่อทำ stateful business process และรองรับการเดินแบบเป็นลำดับ/ขนาน/branching/HITL. ชื่อและตำแหน่งเอกสารมีการย้ายในรุ่นใหม่ จึงควรยึด source ปัจจุบันก่อนนำ dependency มาใช้ ([Semantic Kernel docs](https://learn.microsoft.com/en-us/semantic-kernel/), [Semantic Kernel repo](https://github.com/microsoft/semantic-kernel), [Agent Framework overview](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/)).

**นัยต่อการออกแบบ**: เมื่อ flow มี SLA, retry, approval, compensation หรือหลาย event ให้ย้ายจาก “agent loop ที่เดาเอง” ไปสู่ explicit process/state machine; อย่าเพิ่ม framework ใน MVP จนกว่าจะมี requirement จริง.

### Rasa (รูปแบบ form/slot ที่เป็นประโยชน์)
Rasa Forms กำหนด `required_slots` และถามช่องที่ยังไม่ครบตามลำดับ; custom validation เปลี่ยน required slots แบบ dynamic ได้ ([Rasa Forms](https://rasa.com/docs/rasa/forms), [Form validation](https://rasa.com/docs/rasa/advanced/fn-validation-action)). นี่เป็น pattern ที่เหมาะกับ VOC แต่ไม่จำเป็นต้องนำ Rasa มาใช้: ใช้ Pydantic models + reducer/state ใน Python ให้ผลเทียบเท่าและเล็กกว่า.

## ข้อเสนอเฉพาะ repository นี้

จาก `PRD.md`, `ARCHITECTURE.md`, `CONTRACTS.md` และโค้ดที่ตรวจสอบ:

- ขอบเขตที่ถูกต้องอยู่แล้ว: Main Agent เป็น orchestrator, tool/backend แยกกัน, `ToolCall`/`ToolResult` typed และตรวจว่า action อยู่ใต้ tool, result operational บังคับ `simulation=true`, trace redaction, และ write flow `prepare → confirm endpoint → submit`.
- `MainAgent` เก็บ conversation messages ใน `ConversationStore`, knowledge context แยกต่างหาก และ `_direct_response_contexts` เพื่อเดิน clarification chain; เป็น state แบบ in-process ที่ยอมรับได้สำหรับ demo แต่ไม่ใช่ persistence หลัง restart.
- VOC backend เก็บ draft/case ใน memory และใช้ idempotency key ตอน submit; `VocTool` ทำหน้าที่ domain adapter ได้เหมาะสม. จุดเสี่ยงคือ planner/LLM ยังเป็นผู้อนุมานลำดับ slot จากข้อความและ direct response หลายชนิด ขณะที่ contract ต้องการ “ถามทีละขั้น” และ “ห้ามสร้างค่า”.
- ห้ามให้ผลลัพธ์ tool กลับมาเป็นข้อความที่ channel ต้องตีความเอง: ผลลัพธ์ VOC ควรเป็นข้อมูล `categories`, `pendingAction`, `case`, `error` แล้ว adapter ของ Web/LINE แปลงเป็น card/list/button หรือข้อความ fallback ตาม capability.

## คำแนะนำแบบ phased สำหรับ MVP

### Phase 0 — คงของเดิมและแก้ VOC bug (ทันที)

1. ให้ tool คืน **domain result เท่านั้น**; ห้าม tool สร้างคำถาม, ปุ่ม, LINE markup หรือเลือกช่องทาง.
2. เพิ่ม `WorkflowState` ต่อ conversation แบบ explicit (ยัง in-process ได้): `active_flow`, `slots: VocDraft`, `missing_slot`, `version`, `pending_action_id`.
3. ให้ code-level validator เป็น authority: รับเฉพาะ field ที่ผู้ใช้ระบุ, ไม่ overwrite ด้วยค่าเดา, ตรวจ enum/length/phone/location และคำนวณ missing slot deterministic.
4. หลังทุก tool result ให้ผ่าน reducer เดียวที่ตรวจ `action + schema + state transition`; reject unknown action และผลลัพธ์ที่ไม่ตรง contract.
5. ป้องกันการเรียกซ้ำจากข้อความเดียว: หนึ่ง turn มีได้ไม่เกินหนึ่ง prepare; submit มีได้เฉพาะ confirm endpoint และใช้ idempotency key เดิม.

### Phase 1 — Channel-neutral rendering

กำหนด internal presentation envelope (ไม่จำเป็นต้องเปลี่ยน public v1 ทันที):

```json
{
  "type": "slot_request|tool_result|pending_confirmation|error|knowledge_answer",
  "schemaVersion": 1,
  "text": "...",
  "data": {},
  "fields": [{"name":"contactPhone","label":"เบอร์โทร","required":true}],
  "choices": [{"id":"service","label":"แจ้งปัญหาด้านบริการ"}],
  "actions": [{"id":"confirm","kind":"confirm","target":"pendingAction"}],
  "simulation": true,
  "citations": []
}
```

Web render เป็น form/card; LINE ใช้ quick replies/postback เมื่อรองรับ และ fallback เป็น numbered text. `id` ของ choice/action ต้อง map กลับ server-side enum/endpoint ไม่รับ label หรือคำสั่ง arbitrary จาก client. เก็บ `simulation`, citation และ redaction policy ใน envelope เดียวกัน.

### Phase 2 — Durable state เมื่อเริ่ม production concern

เพิ่ม database-backed conversation/workflow/pending-action store พร้อม optimistic concurrency และ unique idempotency constraint; เก็บ event/trace แยกจาก user-visible message. แนวคิดเลือกได้ตามบริบท: OpenAI Session backend, LangGraph checkpointer/store หรือ schema ของเราเอง—อย่าเลือก framework เพียงเพราะมี memory. ต้องรองรับ resume หลัง process restart, expiry, audit และ PII retention ก่อนเชื่อมระบบจริง.

### Phase 3 — ห่อ deterministic workflow เมื่อ complexity พิสูจน์แล้ว

คง Main Agent เป็น intent/slot extraction และคำอธิบาย แต่ให้ state machine/process คุม `collect → validate → prepare → await_confirm → submit → terminal`. ใช้ graph/process framework ก็ต่อเมื่อมีหลาย step, branching, retry/compensation, concurrent work หรือ HITL หลายจุด; สำหรับ MVP ปัจจุบัน explicit Python reducer เพียงพอและสอดคล้องกับสถาปัตยกรรมที่ประกาศไว้.

## Checklist ป้องกันไม่ให้ tool อื่นทำ VOC bug ซ้ำ

- [ ] ทุก tool มี schema input/output แยก action และ `extra="forbid"`.
- [ ] Tool ไม่มีสิทธิ์สร้าง conversational prompt หรือแก้ `ConversationState` โดยตรง.
- [ ] Orchestrator เป็นจุดเดียวที่เลือก next step; state reducer เป็นจุดเดียวที่คำนวณ missing slot.
- [ ] ผลลัพธ์ success ที่ไม่มีข้อมูล, simulation ผิดค่า, citation ผิด tool และ action/tool mismatch ถูก reject.
- [ ] ทุก write ต้อง `prepare_*` ก่อน, confirmation เป็น endpoint แยก, submit ไม่อยู่ใน tool catalogue ที่โมเดลเลือกได้.
- [ ] ทุก side effect มี idempotency key; retry/duplicate confirm คืน terminal result เดิม.
- [ ] ทดสอบ property/contract เดียวกันกับทุก tool: malformed input, unknown action, duplicate call, stale pending action, reset และ malformed output.
- [ ] Trace บันทึก state transition/tool call/result แบบ redacted; ไม่เก็บ hidden prompt หรือ chain-of-thought.
- [ ] ทดสอบ channel adapters แยกจาก domain tool ด้วย fixture เดียวกัน เพื่อยืนยันว่า Web และ LINE แสดงข้อมูล authoritative เหมือนกัน.

## แหล่งอ้างอิงหลัก

- [OpenAI Agents SDK — Tools](https://openai.github.io/openai-agents-python/tools/) และ [Sessions](https://openai.github.io/openai-agents-python/sessions/)
- [OpenAI Agents SDK source](https://github.com/openai/openai-agents-python)
- [LangGraph — Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) และ [Interrupts/HITL](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Google ADK — State](https://google.github.io/adk-docs/sessions/state/) และ [Sequential agents](https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/)
- [Google ADK Python source](https://github.com/google/adk-python)
- [Microsoft Semantic Kernel docs](https://learn.microsoft.com/en-us/semantic-kernel/) และ [source](https://github.com/microsoft/semantic-kernel)
- [Rasa Forms](https://rasa.com/docs/rasa/forms) และ [FormValidationAction](https://rasa.com/docs/rasa/advanced/fn-validation-action)
