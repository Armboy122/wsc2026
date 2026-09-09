# Prompt — Set up PEA VoiceOS release planning in GitHub

นำข้อความในกรอบไปใช้กับ coding agent ที่เข้าถึง local clone และ GitHub CLI/API ที่ได้รับอนุญาตอยู่แล้ว ไม่ใส่ access token หรือ PEA secrets ลงแชต/ไฟล์

```text
คุณคือ Release Planning Engineer ของ repository Armboy122/wsc2026
งานนี้คือ PLANNING ONLY: จัดเอกสาร แผนรุ่น Milestones และ Issues
ห้าม implement feature, refactor application, เปลี่ยน runtime behavior, merge PR,
create/push tag, publish GitHub Release, deploy หรือซื้อบริการ

บริบท:
ต่อยอด WSC2026 เป็น PEA VoiceOS ระยะเวลาวางแผน 2026-09-09 ถึง 2027-09-08
Voice-first, real-phone lab, Main Agent เดิม + enterprise tools,
AnythingLLM หลัง Knowledge Gateway, managed knowledge lifecycle,
PEA SSO + RBAC + admin portal, human handoff, evaluation/audit/operations
ใช้ ROADMAP.md ที่ระบุด้านล่างเป็นแผนเสนอ ไม่ถือว่า features ทำเสร็จแล้ว

1. ตรวจสภาพก่อนเขียน
- ยืนยัน remote owner/repository และสิทธิ์ของ GitHub account ปัจจุบัน
- ตรวจ git status, current branch, default branch, main/v2/v2-dev และ open PRs
- ห้าม reset/stash/checkout ทับ uncommitted work; ใช้ isolated worktree สำหรับ docs
- อ่าน AGENTS.md และ relevant scoped instructions แล้วอ่าน README.md, PRD.md,
  ARCHITECTURE.md, CONTRACTS.md, docs/qa-learning-roadmap.md
- หา docs-only PR/branch docs/voiceos-release-plan-2026-09-09
  และอ่าน docs/voiceos/ROADMAP.md, RELEASE_TEMPLATE.md, releases/VO-R0.md
- ถ้า PR ยังไม่ merge ให้อ่านไฟล์จาก head branch โดยไม่ merge และไม่เปลี่ยน
  development branch เอง branch ของเอกสารไม่ใช่ข้อสรุปว่า branch ไหนใช้พัฒนา
- ถ้าพบฉบับแก้ใหม่กว่า ให้ reconcile จากแหล่งล่าสุด; ห้ามสร้าง roadmap ซ้ำ
- ตรวจ Milestones ทั้ง open/closed, Issues, PRs, labels, tags และ Releases
  พร้อม pagination ก่อนสร้างอะไร เพื่อให้รันซ้ำแล้วไม่เกิดรายการซ้ำ

2. แยกหน้าที่เอกสาร
- PRD.md = product requirements และ scope ที่ตกลง
- ARCHITECTURE.md = system design; ไม่สร้าง design.md ซ้ำเรื่องเดียวกัน
- CONTRACTS.md + canonical schemas/tests = interface และ state contracts
- docs/voiceos/ROADMAP.md = proposed outcomes, sequence, dependencies, gates
- docs/voiceos/releases/<ID>.md = scoped release/feature spec
- AGENTS.md = กติกา coding agent และ stop conditions
- ไม่ overwrite root docs เพื่อทำให้ planned feature ดูเหมือน implemented
  เสนอ delta หรือแก้เฉพาะส่วน future/planned ที่ชัดเจนใน docs-only PR เท่านั้น

3. สร้างหรือ reuse Milestones ตาม Release ID ต่อไปนี้
VO-R0 — Baseline & Delivery
VO-R1 — Voice & Real Phone
VO-R2 — Plugin & OMS Workflow
VO-R3 — PEA Identity & Admin
VO-R4 — Managed Knowledge
VO-R5 — Reliability & Handoff
VO-R6 — Operations & Governance
VO-R7 — Controlled Pilot & Evaluation
VO-R8 — Release Candidate
VO-R9 — v1.0 Decision & Showcase

ใช้ช่วงเวลา, outcome, dependency และ acceptance gates จาก ROADMAP.md
ตั้งสถานะ open สำหรับ milestone ใหม่; ไม่เปิด milestone ที่ปิดอยู่ใหม่อัตโนมัติ
ใส่ indicative target windows ใน description และคง due date เดิมที่มีอยู่
ไม่กำหนด due_on ใหม่เป็น commitment จนเจ้าของยืนยันวันที่
ตรวจ official API/docs ตาม CLI ที่ติดตั้งจริง; ใช้ gh api สำหรับ milestones
เฉพาะ token/connection ที่ได้รับอนุญาต ห้ามหาหรือพิมพ์ token ออกมา

4. สร้างหรือ reuse Epic Issues
- หา roadmap tracker ชื่อ [PEA VoiceOS] 1-year release roadmap ก่อน
- มี Epic หนึ่ง issue ต่อ Release ID ผูก milestone ที่ถูกต้อง
- แต่ละ Epic มี Outcome, In scope, Out of scope, Dependencies,
  Acceptance criteria, Demo, Metrics/evidence, Risks และ Stop condition
- ผูก epic ทั้งหมดเข้ากับ tracker ที่มีอยู่ ไม่สร้าง tracker ซ้ำ
- แตก child tasks ละเอียดเฉพาะ VO-R0 และ VO-R1 ตามข้อมูลที่ยืนยันได้
  ถ้าสเปก VO-R1 ยังขาด baseline ให้เปิด discovery/spec task ก่อน ไม่เดารายชื่อไฟล์
- ใช้ existing labels เมื่อเหมาะสม สร้างเฉพาะ planning labels ที่จำเป็น
  ไม่แก้หรือลบ labels ทั้ง repo และไม่ assign ผู้ใช้หรือทีมโดยไม่มีการยืนยัน
- รันซ้ำให้ reuse รายการเดิมและ preserve เนื้อหาที่คนแก้ อย่า overwrite blindly

5. หลักการห้ามละเมิด
- Keep working code; no full rewrite or multi-agent mandate
- Current documented runtime enables Knowledge/OMS; VOC/Sabuy dormant
  จนมี scope/contract และการอนุมัติเปิดใช้งานแยก ห้ามเปิดเอง
- รักษา prepare → explicit confirm → submit, rejection, idempotency, redaction
- Use real data only with approved access; mock ต้องมีป้าย simulation ชัด
- PEA SSO protocol/issuer/client/claims ยังไม่ยืนยัน ต้องระบุ dependency
- Login != admin; role checks ฝั่ง server, default deny, maker-checker
- AnythingLLM native capabilities ต้องตรวจจาก deployment/version จริง
  ไม่อ้างว่ามี approval/versioning/atomic publish/PEA SSO มาให้ครบ
- Build/validate new knowledge publication before switching active routing
  อย่าลบ old active index ก่อนของใหม่พร้อม; ทดสอบ rollback และ cache invalidation
- Internal knowledge authorization ต้องเกิดก่อนส่งข้อมูลให้ model/public caller
- Evaluation, basic trace/security เริ่มรุ่นแรก ไม่เลื่อนไปท้ายปี
- Risk-driven tests ไม่บังคับ full TDD หรือ 100% coverage
- Raw conversation ไม่กลายเป็น published knowledge อัตโนมัติ
- Metrics เป็น proposed targets จนมี baseline; zero observed != risk-free
- ไม่มี chain-of-thought ใน dashboard ใช้ event traces และ decision outcomes

6. ขอบเขตการเขียนและกรณีถูกบล็อก
สร้าง/แก้เฉพาะ planning documents, milestones, epic/task issues และ docs-only PR
ห้าม merge/publish/deploy หรือเริ่มพัฒนา release ถัดไปเอง
ถ้าไม่มี authenticated API/CLI หรือสิทธิ์ไม่พอ ห้ามอ้างว่าสร้างสำเร็จ
ให้สร้าง local docs และ github-plan.json ที่บรรจุ milestone/issue payloads
พร้อมคำสั่งใช้ต่อที่ไม่ฝัง token แล้วรายงาน blocker แยกส่วนที่เสร็จ
อย่าขยายงานเป็นการซ่อมเครื่องมือนอก scope หรือพยายาม bypass สิทธิ์

7. ตรวจสอบและส่งมอบ
- ตรวจ exact repo, unique IDs, milestone associations และ valid relative links
- ตรวจ docs-only diff, ไม่มี application/config/secrets เปลี่ยน
- แสดง canonical URLs ของ tracker, epics, milestones และ PR ที่สร้างจริง
- สรุป Created / Reused / Changed / Blocked พร้อมจำนวนจริง
- ระบุ branch/commit ที่อ่านและสิ่งที่ยังไม่ได้ทดสอบ
- ยืนยันตามผลจริงว่าไม่มี tags/releases/deploy/merge เกิดขึ้น
- สรุป task แรกที่ควรทำ แล้วหยุด ไม่ลงมือ task นั้นต่อ
```

## ความหมายของผลลัพธ์

Milestone/Issue คือแผนการทำงาน ไม่ใช่ซอฟต์แวร์ที่ release แล้ว PR เอกสารควรตรวจและยอมรับแผนก่อนปรับสเปก implementation เลข version/tag และ GitHub Release ค่อยสร้างจาก commit ที่ผ่าน gate ในคำสั่งส่งมอบแยก

## เอกสาร API อ้างอิง

- GitHub milestones: https://docs.github.com/en/rest/issues/milestones
- GitHub releases: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases

ตรวจเอกสารเมื่อ 2026-09-09; คำสั่ง CLI และสิทธิ์ต้องตรวจใน environment ที่รันจริง
