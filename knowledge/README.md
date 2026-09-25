# คลังความรู้ PEA

> Runtime: Gemini Live (ผ่าน ADK) เลือก `sourceId` จาก catalog แล้วเรียกเครื่องมือ
> `get_knowledge_documents` ซึ่งคืน **Markdown ฉบับเต็ม** ของเอกสารที่เลือก ฝั่ง Knowledge
> เป็น deterministic ไม่เรียก LLM ไม่ค้นหาจากคำถาม และไม่แบ่ง chunk

## นโยบายแหล่งข้อมูล

- แหล่งข้อมูล runtime มีเฉพาะ Markdown (`.md`, UTF-8) ที่ผ่านการอนุมัติใต้ `knowledge/source/`
- corpus ปัจจุบัน: 45 ไฟล์ (เอกสารบริการ/ประกาศ 34 ไฟล์ `PEA_*.md` + Approved Q&A 11 ไฟล์ใต้ `qa/`)
- `README.md` ทุกไฟล์ใน `knowledge/source/`, metadata และไฟล์ซ่อนไม่ใช่เอกสารความรู้
- ตั้งชื่อไฟล์สั้น ชัด สื่อหัวข้อ เพราะโมเดลเห็นเพียง `sourceId`, `title`, heading และ alias ใน catalog
  (ใช้ `PEA_` สำหรับเอกสารบริการ และ `qa_` สำหรับ Q&A หนึ่งหัวข้อต่อไฟล์)
- โมเดลต้องตอบจากเอกสารที่เครื่องมือคืนเท่านั้น หากไม่พบให้บอกข้อจำกัด
- `sourceId` คือพาธสัมพัทธ์; ห้ามเปิดเผย absolute path

## โครงสร้าง

```text
knowledge/
  README.md          นโยบายนี้
  aliases/           คำพ้องที่ผู้ดูแลกำหนด (หนึ่ง intent ต่อไฟล์) — ไม่ใช่หลักฐาน
    README.md        รูปแบบกฎคำพ้อง
  source/            เอกสาร authoritative
    PEA_*.md
    qa/qa_*.md       Approved Q&A
    README.md, qa/README.md   นโยบายเท่านั้น ไม่เข้า catalog
```

ไม่มี manifest, index, embedding cache หรือ state บนคลาวด์ — `knowledge/source/` คือแหล่งความจริงเดียว

## การทำงาน (`app/knowledge/`)

1. **Catalog** — ตอนเริ่มระบบสแกนไฟล์ที่อนุมัติ สร้าง entry: `sourceId`, `title`, `headings`
   (สูงสุด 12) และ `aliases` จาก `knowledge/aliases/` ที่อ้างถึงไฟล์นั้น catalog ไม่มีเนื้อหาเอกสาร
2. **Aliases** — ไฟล์ Markdown พร้อม front matter; ทุก `sourceId` ในกฎต้องมีอยู่จริง และ `id`/alias
   ต้องไม่ซ้ำ มิฉะนั้นเริ่มระบบไม่สำเร็จ alias ใช้เพียงช่วยโมเดลเลือกเอกสาร เซิร์ฟเวอร์ไม่จับคู่คำถามกับ alias
3. **เลือกเอกสาร** — `get_knowledge_documents(source_ids)` รับ 1–5 `sourceId` จาก catalog เท่านั้น
4. **โหลดทั้งไฟล์** — อ่านข้อความตามต้นฉบับทั้งหมด (heading, list, URL, ตัวเลข) รวมกันไม่เกิน
   120,000 ตัวอักษร เกินแล้วคืน error code `invalid_input` ไม่ตัดทอน
5. **Provenance** — แต่ละเอกสารคืน `sourceId`, `title`, `uri` (`knowledge://source/<sourceId>`)

สัญญาเต็มของเครื่องมืออยู่ใน [CONTRACTS.md](../CONTRACTS.md)

## การตั้งค่า

| ตัวแปร | ความหมาย |
| --- | --- |
| `KNOWLEDGE_SOURCE_ROOT` | root ของ corpus; ค่าเริ่มต้น `<repo>/knowledge/source` (alias อ่านจากโฟลเดอร์ `aliases/` ที่อยู่ข้าง root นี้) |

แก้/เพิ่มเอกสารหรือ alias แล้วต้อง restart server

## เอกสารอ้างอิงอื่น

`docs/research/electricity-tariff-sep-2569.md` เป็นบันทึกค้นคว้าอัตราค่าไฟ เก็บไว้เป็นข้อมูลความรู้
แต่อยู่นอก `KNOWLEDGE_SOURCE_ROOT` จึงไม่อยู่ใน catalog runtime
