# VO-R0 — Baseline & Delivery

สถานะ: Proposed / ยังไม่รัน implementation หรือ baseline tests ใน PR เอกสารนี้  
ช่วงเป้าหมาย: กันยายน 2026  
Owner / reviewer: TBD  
อ้างอิง: [ROADMAP](../ROADMAP.md), [PRD](../../../PRD.md), [AGENTS](../../../AGENTS.md)

## Outcome

มีแผนที่ตรงกับของที่มีอยู่จริง และงานรุ่นแรกที่เริ่มได้โดยไม่เลือกผิด branch หรือเขียนทับงานอื่น ผู้พัฒนารู้ว่าอะไรเสร็จ อะไรยังเป็น mock อะไรต้องขอทีม PEA และจะวัดความสำเร็จของ voice อย่างไร

## Scope

Baseline inspection, development-branch decision, critical-path evidence, dependency inventory และ spec ของ VO-R1 เท่านั้น ไม่มีการ refactor Main Agent, เปิด VOC/Sabuy, เปลี่ยน production API หรือเชื่อม AnythingLLM/SSO จริงในงานเอกสารนี้

## Tasks ที่เสนอให้เปิดเป็น Issues

### VO-R0-T1 — Reconcile branch and baseline

ตรวจ `main`, `v2`, `v2-dev`, open PRs, tags และ relevant AGENTS files ก่อนเลือกฐานสำหรับ implementation บันทึก capability matrix แยก documented / exercised / mock / missing / unknown

Acceptance: มี commit SHA และหลักฐานของ branch comparison; ไม่ปนข้อมูลคนละ branch; ไม่มีการ merge/cherry-pick/force-push งานเดิมเพื่อให้เอกสารดูตรงกัน

### VO-R0-T2 — Reproduce critical paths

ทดสอบ text + voice multi-turn, citations, OMS read, pending write confirmation/rejection, disconnect, malformed result, unavailable dependency และ redaction ด้วย fixtures/synthetic data ที่เหมาะสม ใช้คำสั่ง validation ใน AGENTS.md หลังเตรียม environment ที่ปลอดภัย

Acceptance: บันทึกคำสั่งจริง ผลจริงและ environment; live provider checks ที่ไม่ได้รันระบุ not verified; แยก test failure ของ environment ออกจาก product defects; ไม่อ้างว่า baseline ผ่านจากการอ่าน README

### VO-R0-T3 — Define voice evaluation baseline

กำหนด markers สำหรับ end-of-user-speech, first audio, tool invocation/result และ completed task; เก็บ p50/p95 แยก tool/no-tool; เตรียม representative Thai conversation set ที่รวมพูดแทรก, ให้ข้อมูลไม่ครบ, ขอคน, API failure และข้อมูลที่ห้ามเดา

Acceptance: dataset และ metric definitions มี version; มี sample size; เป้าหมายที่ยังไม่ตกลงติดป้าย provisional; ไม่กำหนดว่าต้องครบ 1,000 cases ก่อนเริ่ม pilot

### VO-R0-T4 — External dependency register

เตรียมรายการที่ต้องขอ: PEA SSO owner/protocol/test app/claims; approved telephony lab; OMS test contract; contact-center handoff path; knowledge owner/classification; security/privacy reviewer; budget owner

Acceptance: ทุก dependency ระบุ known / pending / blocked และผู้รับผิดชอบเมื่อได้รับการยืนยัน ไม่มีรหัสผ่าน, token, internal URL หรือข้อมูลลูกค้าถูกใส่ใน public repo; แผนนี้ไม่ส่งคำขอ/อีเมลไปยังบุคคลภายนอกเอง

### VO-R0-T5 — Finalize VO-R1 contract and GitHub planning

เขียน VO-R1 spec ด้วย RELEASE_TEMPLATE.md ตาม gap ที่พบจริง ตั้ง milestone/epic และแตกงานเท่าที่พร้อมทำ โดยแต่ละ task มี acceptance, non-goals, file ownership, dependencies และ stop condition

Acceptance: มี branch strategy ที่เจ้าของงานยืนยัน; ไม่ซ้ำ PRD/ARCHITECTURE/CONTRACTS; ไม่มี GitHub Release หรือ tag ใหม่สำหรับงานที่ยังไม่ผ่าน acceptance

## VO-R1 brief เพื่อเตรียมสเปก

ใช้ voice bridge/runtime ปัจจุบันเท่าที่ทำได้ เพิ่มทางโทรเข้าเบอร์ lab จริง พร้อม streaming, barge-in, session cleanup และ safe transfer/fallback เส้นทาง demo ต้องใช้ข้อมูลสาธารณะหรือ synthetic ก่อน production approvals

เกณฑ์ขั้นต่ำที่เสนอ: โทรเข้าแล้วคุยได้ต่อเนื่อง 5 นาที, ถามต่อเนื่องโดยไม่หลุดบริบทสำคัญ, พูดแทรกแล้วหยุด output ที่เกี่ยวข้องได้, API ไม่ตอบแล้วไม่เดาข้อมูล, ปิดสายแล้วไม่เหลือ orphan session/งานเขียนที่ไม่ได้ยืนยัน และมี latency/trace evidence

Telephony provider, codec, deployment, concurrency, recording policy และ latency threshold ยังต้องตัดสินจาก compatibility test และ baseline ไม่ lock vendor หรือซื้อบริการในงาน planning

## Stop condition

จบ VO-R0 เมื่อ baseline evidence และ VO-R1 contract พร้อม review งานที่ติด external access ให้รายงาน blocker และทำเฉพาะส่วนที่ใช้ mock/synthetic ได้อย่างปลอดภัย ห้ามทำ VO-R1–VO-R9 ต่อโดยอัตโนมัติ
