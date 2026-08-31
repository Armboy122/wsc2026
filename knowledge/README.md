# คลังความรู้ PEA

ไดเรกทอรีรากของคลังข้อมูลสำหรับคลัง RAG แบบโฮสต์ของ Gemini File Search ที่รองรับ
`knowledge_tool` (Worker B — ความรู้) โดยผู้ให้บริการใช้ **การแบ่งส่วนตามค่าเริ่มต้น**
ของตนเอง (สคริปต์ sync จะไม่ส่งขนาดส่วนข้อมูลหรือระยะซ้อนทับที่กำหนดเอง)

## นโยบายแหล่งข้อมูลที่เชื่อถือได้ (สำคัญต่อความปลอดภัย)

- ไฟล์ **เพียงกลุ่มเดียว** ที่จะถูกอัปโหลดไปยังคลังจัดเก็บคือไฟล์ภายใต้ `source/`
- `source/` อาจมีได้เฉพาะ **เอกสารส่งออก PEA ที่เชื่อถือได้และผ่านการอนุมัติจากหัวหน้าทีม**
  ที่เก็บซอร์สโค้ดนี้จงใจ **ไม่รวมไฟล์ดังกล่าว**: ไม่มีเอกสาร PEA ที่เป็นตัวอย่าง สาธิต หรือ
  เขียนโดยโมเดลอยู่ในโครงสร้างนี้
- ข้อเท็จจริงขององค์กร (อัตราค่าไฟฟ้า ระดับอัตรา การเรียกเก็บเงิน การชำระเงิน เหตุไฟฟ้าดับ
  และข้อมูลติดต่อ) ต้องไม่มาจากการสร้างขึ้นเองของโมเดลโดยเด็ดขาด คลังข้อมูลตัวอย่าง `docs/`
  ที่เคยรวมมา (รวมถึง `pea-electricity-rates.md`) ถูกนำออกแล้ว
  เนื่องจากมีข้อเท็จจริงขององค์กรที่ไม่มีแหล่งอ้างอิง
- `knowledge/source/README.md` เป็นเอกสารแทนชั่วคราวที่ไม่มีข้อเท็จจริง ใช้บันทึก
  นโยบายนี้ เช่นเดียวกับ `README.md` และไฟล์ข้อมูลกำกับทุกไฟล์ ไฟล์นี้จะไม่ถูกอัปโหลด
- หากไม่มีเอกสารส่งออกที่ได้รับอนุมัติใน `source/` การรัน sync จะเป็น no-op และ
  `knowledge_tool.search` จะไม่ส่งคืนข้อมูลอ้างอิงสำหรับคำถามที่ไม่มีข้อมูลครอบคลุม
  (fail-closed)

## โครงสร้าง

```text
knowledge/
  README.md            this file (never uploaded)
  source/              the only uploadable subtree (lead-approved PEA exports)
    README.md          non-factual placeholder (never uploaded)
  manifest.json        SHA256 source manifest (generated, git-ignored)
  tests/               knowledge system tests (run: python3 -m pytest knowledge/tests)
```

## การกำหนดค่า

| ตัวแปร | ความหมาย |
|---|---|
| `GEMINI_FILE_SEARCH_STORE` | ชื่อทรัพยากรของคลังจัดเก็บ File Search เช่น `fileSearchStores/pea-knowledge` (สร้างคลังจัดเก็บใน Google AI Studio หรือผ่าน API) |
| `GEMINI_API_KEY` | คีย์ API ของ Google AI Studio (ใช้ `GOOGLE_API_KEY` เป็นค่าสำรอง) |
| `GEMINI_FILE_SEARCH_MODEL` | โมเดลสำหรับการสร้างคำตอบที่อ้างอิงแหล่งข้อมูล (ค่าเริ่มต้น `gemini-2.5-flash`) |

## การ sync

เรียกใช้จากไดเรกทอรีรากของที่เก็บซอร์สโค้ด (`google-genai` SDK จำเป็นสำหรับการ
อัปโหลดจริงเท่านั้น ส่วน `--dry-run` ใช้งานได้โดยไม่ต้องมี SDK):

```bash
pip install google-genai          # once, for real uploads

python3 scripts/sync_knowledge.py --dry-run          # show the plan only
python3 scripts/sync_knowledge.py                     # upload new/changed sources under source/ only
python3 scripts/sync_knowledge.py --file source/<approved-export>.md
python3 scripts/sync_knowledge.py --force             # re-upload unchanged sources as well
python3 scripts/sync_knowledge.py --prune --yes       # also delete removed sources
python3 scripts/sync_knowledge.py --root /path/to/export-corpus   # only /path/to/export-corpus/source/** is syncable
python3 scripts/sync_knowledge.py --dry-run --prune --yes --verbose
```

พฤติกรรม:

- ไดเรกทอรีรากของคลังข้อมูลเริ่มต้นคือ `<repo>/knowledge` และ manifest เริ่มต้นคือ
  `knowledge/manifest.json` ส่วน `--root` ใช้แทนที่ไดเรกทอรีรากของคลังข้อมูล โดยโครงสร้างย่อยที่
  sync ได้คือ `<root>/source/**` และ manifest จะมีค่าเริ่มต้นเป็น
  `<root>/manifest.json` การระบุไดเรกทอรีรากที่ไม่มีไดเรกทอรี `source/` ถือเป็นข้อผิดพลาดจากการใช้งาน
  (exit 2) ไม่ใช่ silent no-op
- เฉพาะไฟล์ใต้ `source/` เท่านั้นที่ sync ได้ ส่วน `README.md` (ไม่ว่าจะใช้อักษรตัวพิมพ์แบบใดหรืออยู่ลึกระดับใด)
  manifest ไฟล์ซ่อน และไฟล์ที่ไม่มีนามสกุลเอกสารจะไม่ถูก
  อัปโหลด
- manifest แบบ SHA256 จะจับคู่พาธสัมพัทธ์จากคลังข้อมูลแต่ละรายการ (เช่น
  `source/<export>.md`) กับแฮชเนื้อหาและชื่อเอกสารระยะไกล
- เฉพาะแหล่งข้อมูลที่ **ใหม่** หรือ **เปลี่ยนแปลง** เท่านั้นที่จะถูกอัปโหลด ส่วนไฟล์ที่ไม่เปลี่ยนแปลง
  จะถูกปล่อยไว้ตามเดิม ขณะที่ `--force` จะอัปโหลดไฟล์ที่ไม่เปลี่ยนแปลงซ้ำด้วย
- `--file PATH` จำกัดการรันไว้ที่พาธสัมพัทธ์จากคลังข้อมูลแบบเจาะจงหนึ่งรายการ
  (หรือหลายรายการเมื่อใช้ซ้ำ) ภายใต้ `source/` ส่วนพาธอื่นถือเป็นข้อผิดพลาดจากการใช้งาน
- การลบข้อมูลระยะไกลจะเกิดขึ้น **เฉพาะ** เมื่อระบุทั้ง `--prune` และ `--yes`
  `--prune` ที่ไม่มี `--yes` จะแสดงคำเตือนและไม่ลบสิ่งใด รายการจาก
  manifest ก่อนหน้า (ก่อนการแก้ไข) ที่ไม่สามารถอ้างถึงไฟล์ต้นทางได้อีก
  จะกลายเป็นรายการที่อาจถูกตัดออก ทำให้เอกสารที่ไม่มีแหล่งอ้างอิงซึ่งเคยอัปโหลดไว้
  สามารถถูกนำออกจากคลังจัดเก็บด้วย `--prune --yes`
- การแบ่งส่วนใช้ค่าเริ่มต้นของผู้ให้บริการเสมอ โดยสคริปต์จะไม่ส่งการตั้งค่า
  การแบ่งส่วน

## ข้อจำกัดที่ทราบ (การสาธิต 2 วัน)

- การอัปโหลดไฟล์ที่เปลี่ยนแปลงซ้ำจะสร้างเอกสารระยะไกลใหม่ โดย manifest
  ติดตามชื่อเอกสารล่าสุด แต่ฉบับแก้ไขเก่าอาจยังคงอยู่ใน
  คลังจัดเก็บจนกว่าจะทำความสะอาดผ่านคอนโซลของผู้ให้บริการ
- การตัดข้อมูลจะลบตามชื่อเอกสารที่เก็บไว้ใน manifest ส่วนเอกสารที่อัปโหลด
  นอกสคริปต์นี้จะไม่ถูกติดตามและจะไม่ถูกลบ
