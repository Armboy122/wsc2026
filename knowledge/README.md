# คลังความรู้ PEA

> สถานะ: runtime ใช้ **Document Routing + Full-file Long Context** โดย public contract
> ของ `knowledge_tool.search` ยังคงเดิม

`knowledge_tool` ต้องเลือกเฉพาะเอกสารที่เกี่ยวข้องกับคำถาม แล้วส่ง **ข้อความฉบับเต็ม**
ของเอกสารที่เลือกให้ Gemini Long Context เพื่อสร้างคำตอบที่ครบและตรงคำถาม ระบบนี้ไม่ใช่
การแบ่งข้อความเป็นส่วนย่อย และห้ามโหลดทั้ง corpus ทุกครั้งโดยไม่มีความจำเป็น

## นโยบายแหล่งข้อมูลที่เชื่อถือได้

- แหล่งข้อมูล runtime มีได้เฉพาะเอกสารที่ผ่านการอนุมัติภายใต้ `knowledge/source/`
- corpus ปัจจุบันประกอบด้วย DOCX ที่ผู้ใช้อนุมัติ 38 ไฟล์ รวม Approved Q&A แบบ DOCX 11 ไฟล์ใต้ `knowledge/source/qa/`
- Q&A ควรแยกหนึ่งหัวข้อต่อหนึ่งไฟล์ โดยใช้คำถามหลักเป็นย่อหน้าแรก เพื่อให้ Router จับคู่คำถามที่มีความหมายใกล้เคียงได้จาก catalog
- `knowledge/source/README.md`, `knowledge/source/qa/README.md`, metadata และไฟล์ซ่อนทุกชนิดไม่ใช่เอกสารความรู้
- LLM ต้องตอบจากข้อความในไฟล์ที่เลือกเท่านั้น ห้ามใช้ความจำของโมเดลเติมข้อเท็จจริง PEA
- หากไม่มีไฟล์หรือหลักฐานที่ตรงคำถาม ต้องคืน no-evidence และไม่มี citation
- ชื่อไฟล์และพาธสัมพัทธ์เป็น identifier ที่ตรวจสอบย้อนหลังได้ ห้ามเปิดเผย absolute path

## โครงสร้าง

```text
knowledge/
  README.md            สเปก Knowledge และนโยบาย corpus
  source/              เอกสาร authoritative ที่ Document Router เลือกได้
    *.docx              แหล่งข้อมูลฉบับเต็ม
    qa/                 Approved Q&A; หนึ่งหัวข้อต่อหนึ่ง DOCX
      *.docx            คำถาม คำตอบ และแหล่งอ้างอิงที่อนุมัติแล้ว
      README.md         รูปแบบและนโยบาย Q&A; ห้ามนำเข้า context
    README.md           นโยบายเท่านั้น; ห้ามนำเข้า context
  tests/               เทสต์ Document Router, full-file loading และ fail-closed
```

> ไม่มีไฟล์ manifest, ดัชนี, embedding cache หรือ state ฝั่งคลาวด์ใด ๆ ในคลังนี้
> `knowledge/source/` คือแหล่งความจริงเพียงแหล่งเดียว

## ขั้นตอนทำงานที่บังคับใช้

### 1. สร้าง catalog ระดับเอกสาร

เมื่อเริ่มระบบ backend ต้องค้นพบไฟล์ที่อนุมัติและสร้าง catalog โดยมีข้อมูลขั้นต่ำ:

- `sourceId`: พาธสัมพัทธ์ เช่น `source/PEA_01_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.docx`
- `title`: ชื่อไฟล์หรือหัวข้อแรกของเอกสาร
- `topics`: หัวข้อบริการระดับเอกสารที่ดึงจากชื่อและ heading โดยไม่สร้างข้อเท็จจริงใหม่

Catalog ห้ามมี chunk, embedding หรือข้อความสรุปที่โมเดลแต่งขึ้น

### 2. เลือกไฟล์ที่เกี่ยวข้อง

Document Router รับเฉพาะคำถามและ catalog ระดับเอกสาร แล้วคืน `sourceId` จาก allowlist
ไม่เกิน `maxResults` รายการ โดยต้องเลือกชุดไฟล์ที่เล็กที่สุดซึ่งครอบคลุมคำถาม

- คำถามหนึ่งบริการ: เลือกไฟล์หลักที่ตรงที่สุด และไฟล์ภาพรวมเฉพาะเมื่อจำเป็น
- คำถามหลายบริการ: เลือกหลายไฟล์ฉบับเต็มได้
- คำถามกำกวม: คืน no-evidence เพื่อให้ Main Agent ถามให้ชัดเจน
- รหัสไฟล์ที่ไม่อยู่ใน catalog ต้องถูกปฏิเสธ ห้ามอ่านพาธจากข้อความที่โมเดลสร้าง

### 3. โหลดข้อความทั้งไฟล์

หลังตรวจ allowlist แล้ว backend ต้องแปลง DOCX ที่เลือกเป็นข้อความตามลำดับการอ่าน โดยรวม:

- paragraph และ heading ทุกส่วน
- numbered/bulleted list
- ข้อความใน table cell
- URL และตัวเลขตามต้นฉบับ

ห้ามตัดเฉพาะส่วนต้น ห้ามเลือกเฉพาะย่อหน้าที่คล้ายคำถาม และห้ามแบ่งเป็น chunk เพื่อส่งเข้า
LLM ข้อความที่แปลงแล้วอาจ cache ใน memory ตาม hash ของไฟล์ได้ แต่ cache ไม่ใช่ search index

### 4. ส่งเข้า Gemini Long Context

Prompt สำหรับตอบประกอบด้วย:

1. คำสั่งให้ใช้เฉพาะเอกสารที่แนบมาและห้ามเดา
2. คำถามของผู้ใช้
3. ข้อความฉบับเต็มของแต่ละไฟล์ พร้อมขอบเขต `[SOURCE: <sourceId>] ... [/SOURCE]`
4. รูปแบบผลลัพธ์แบบมีโครงสร้าง: คำตอบตรงคำถามและหลักฐานแยกตาม `sourceId`

`answerContext` ต้องเป็นคำตอบที่อ่านได้และตรงคำถาม ไม่ใช่การคัดหัวเอกสาร รายการลิงก์ หรือ
citation snippet มาต่อกัน

### 5. ตรวจ citation

citation ทุกตัวต้องผ่านกฎต่อไปนี้:

- `sourceId` ต้องเป็นไฟล์ที่ Document Router เลือกจริง
- `title` ต้องเป็นชื่อเอกสารจริง
- `uri` ใช้ logical URI เช่น `knowledge://source/<encoded-relative-path>`
- `snippet` ต้องเป็นข้อความหลักฐานจากไฟล์ฉบับเต็มนั้นและตรวจสอบ substring ได้
- หากคำตอบหรือ snippet อ้างถึงไฟล์อื่น ให้ปฏิเสธผลลัพธ์และ fail closed

## Context budget

- ห้ามส่งทั้ง 38 ไฟล์ทุกคำถาม
- ห้ามตัดท้ายไฟล์ที่เลือกเพื่อให้พอดี context window
- หากหลายไฟล์ที่จำเป็นรวมกันเกิน context budget ให้ขอให้ผู้ใช้จำกัดหัวข้อ หรือคืน typed failure
- สามารถใช้ in-memory extraction cache หรือ provider context cache ต่อชุดไฟล์ได้ แต่ต้องไม่เปลี่ยน
  เนื้อหา การเลือกไฟล์ หรือกฎการอ้างอิง

## การกำหนดค่าเป้าหมาย

| ตัวแปร | ความหมาย |
|---|---|
| `KNOWLEDGE_PROVIDER` | `gemini` (ค่าเริ่มต้น) หรือ `maxplus_openai` |
| `GEMINI_API_KEY` | คีย์ Google AI Studio เมื่อเลือก `gemini`; ห้ามบันทึกใน repository หรือ trace |
| `GEMINI_LONG_CONTEXT_MODEL` | โมเดล Google สำหรับ Document Router และ full-file answer; ค่าเริ่มต้นคือ `gemini-3.5-flash` |
| `MAXPLUS_API_KEY` | inference key รูปแบบ `ccsk-…` เมื่อเลือก `maxplus_openai`; ห้ามใช้ management token `ccmk-…` |
| `MAXPLUS_BASE_URL` | OpenAI-compatible base URL ที่ตรงกับ pool ของ key เช่น `https://api.maxplus-ai.cc/v1` |
| `MAXPLUS_MODEL` | model id ที่ pool นั้นเปิดให้ key ใช้งาน เช่น `gpt-5.4-mini` |
| `KNOWLEDGE_SOURCE_ROOT` | root ของ corpus; ค่าเริ่มต้นคือ `<repo>/knowledge/source` |

runtime อ่านเอกสารจาก `KNOWLEDGE_SOURCE_ROOT` โดยไม่ต้องใช้ชื่อ store หรือขั้นตอนอัปโหลดเอกสาร
ใด ๆ `knowledge_tool` ต้องส่งเฉพาะเอกสารที่ Document Router เลือก พร้อมข้อความฉบับเต็มของ
แต่ละ DOCX ให้ provider ที่กำหนด ทั้งสอง provider ใช้กฎ citation และ fail-closed ชุดเดียวกัน

## เกณฑ์ยอมรับ

- คำถาม “ต้องการขอใช้ไฟฟ้าต้องมีเอกสารอะไรบ้าง” เลือกไฟล์ขอใช้ไฟฟ้าที่เกี่ยวข้อง
  และคำตอบต้องใช้หัวข้อเอกสารจากส่วนใดก็ได้ของไฟล์ ไม่ใช่เฉพาะ 1,000 อักขระแรก
- เทสต์ยืนยันว่า fact ที่อยู่ท้าย DOCX ยังปรากฏในคำตอบได้
- เทสต์ยืนยันว่าไฟล์ที่ไม่เกี่ยวข้องไม่ถูกส่งเข้า Long Context
- เทสต์ยืนยันว่าคำถามหลายหัวข้อโหลดหลายไฟล์ฉบับเต็ม
- เทสต์ยืนยันว่า router ไม่สามารถเลือกพาธนอก allowlist
- เทสต์ยืนยันว่า no-match, context overflow, parse error และ citation mismatch ทำงานแบบ fail closed
- ไม่มี dependency หรือคำขอ runtime ไปยัง vector DB, embedding หรือ chunk retrieval
