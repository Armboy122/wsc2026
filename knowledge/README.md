# คลังความรู้ PEA

> Runtime: Gemini Live (ผ่าน ADK) เรียกเครื่องมือ `search_knowledge` ด้วยคำถามภาษาไทย
> แล้วได้รับ approved Q&A ก่อน และตามด้วย chunk ของเอกสารที่เกี่ยวข้องพร้อมแหล่งอ้างอิง
> ฝั่ง Knowledge เป็น deterministic ไม่เรียก generative model และไม่สร้างคำตอบเอง

## นโยบายแหล่งข้อมูล

- แหล่งข้อมูล runtime มีเฉพาะ Markdown (`.md`, UTF-8) ที่ผ่านการอนุมัติใต้ `knowledge/source/`
- corpus ปัจจุบัน: 45 ไฟล์ (เอกสารบริการ/ประกาศ 34 ไฟล์ `PEA_*.md` + Approved Q&A 11 ไฟล์ใต้ `qa/`)
- `README.md` ทุกไฟล์ใน `knowledge/source/`, metadata และไฟล์ซ่อนไม่ใช่เอกสารความรู้
- ตั้งชื่อไฟล์สั้น ชัด สื่อหัวข้อ เพราะ index ใช้ `sourceId`, `title` และ heading ในการค้นหา
  (ใช้ `PEA_` สำหรับเอกสารบริการ และ `qa_` สำหรับ Q&A หนึ่งหัวข้อต่อไฟล์)
- โมเดลต้องตอบจากเนื้อหาที่เครื่องมือคืนเท่านั้น หากไม่พบให้ถามกลับหรือแนะนำศูนย์บริการ 1129
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
    README.md, qa/README.md   นโยบายเท่านั้น ไม่เข้า index
```

index เป็น derived artefact: cache อยู่ใต้ `KNOWLEDGE_INDEX_DIR` (ค่าเริ่มต้น `.cache/knowledge-index`,
gitignored) และสร้างใหม่ได้เสมอ — `knowledge/source/` ยังคงเป็นแหล่งความจริงเดียว

## การทำงาน (`app/knowledge/`)

1. **Catalog** — ตอนสร้าง index สแกนไฟล์ที่อนุมัติ (ข้าม README และไฟล์ซ่อน) เพื่อทำหน้าที่เป็น
   allowlist ของ `sourceId`/`title`/`path`; ไม่มีเนื้อหาเอกสารถูกฝังใน instruction
2. **Aliases** — ไฟล์ Markdown พร้อม front matter; ทุก `sourceId` ในกฎต้องมีอยู่จริง และ `id`/alias
   ต้องไม่ซ้ำ มิฉะนั้นสร้าง index ไม่สำเร็จ alias ใช้ขยายคำค้นของ index (deterministic ไม่ใช้ LLM)
3. **Chunk + Index** — chunk แบบ heading-aware, แยก Q&A ใต้ `qa/` เป็น lane ของตัวเอง,
   ใช้ BM25 (PyThaiNLP) + dense cosine หลอมด้วย RRF
4. **ค้นหา** — `search_knowledge(query)` รับคำถาม 1–500 ตัวอักษร แล้วคืน approved Q&A ก่อนเสมอ
   ตามด้วย chunk พร้อม `sourceId`, `title`, `uri` (`knowledge://source/<sourceId>`) และ heading
5. **Provenance** — ทุกผลลัพธ์อ้างอิงกลับไปยังไฟล์ที่อนุมัติได้; เอกสารไม่ถูกแก้ไข ตัดทอน หรือเปลี่ยนชื่อ

สัญญาเต็มของเครื่องมืออยู่ใน [CONTRACTS.md](../CONTRACTS.md)

## การตั้งค่า

| ตัวแปร | ความหมาย |
| --- | --- |
| `KNOWLEDGE_SOURCE_ROOT` | root ของ corpus; ค่าเริ่มต้น `<repo>/knowledge/source` (alias อ่านจากโฟลเดอร์ `aliases/` ที่อยู่ข้าง root นี้) |
| `KNOWLEDGE_INDEX_DIR` | cache ของ derived index (ค่าเริ่มต้น `.cache/knowledge-index`, gitignored) |
| `KNOWLEDGE_EMBEDDER` | `bge-m3` (ค่าเริ่มต้น, self-host) หรือ `fake` สำหรับเทสต์ออฟไลน์ |

เพิ่ม/แก้/ลบเอกสารหรือ alias แล้วระบบ rebuild index ให้อัตโนมัติ ไม่ต้อง restart

## เอกสารอ้างอิงอื่น

`docs/research/electricity-tariff-sep-2569.md` เป็นบันทึกค้นคว้าอัตราค่าไฟ เก็บไว้เป็นข้อมูลความรู้
แต่อยู่นอก `KNOWLEDGE_SOURCE_ROOT` จึงไม่อยู่ใน index runtime
