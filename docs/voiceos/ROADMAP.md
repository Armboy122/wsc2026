# PEA VoiceOS — Release Roadmap

สถานะ: **Proposed / ยังไม่ใช่หลักฐานว่า implementation เสร็จ**  
วันที่จัดทำ: 2026-09-09  
กรอบเวลาเสนอ: 2026-09-09 ถึง 2027-09-08 (ไม่ใช่วันแข่งขันที่ได้รับการยืนยัน)  
เป้าหมาย: ต่อยอด `Armboy122/wsc2026` เป็น Enterprise Voice Agent โดยใช้ของเดิมเป็นฐาน ไม่รื้อระบบทั้งหมด

## 1. ขอบเขตและเอกสารหลัก

เอกสารนี้รวมข้อเสนอ Voice, enterprise tools, AnythingLLM knowledge และ PEA SSO ให้เป็น roadmap ชุดเดียว โดยใช้รหัส `VO-R0` ถึง `VO-R9` เพื่อไม่สับสนกับ milestone หรือเฟสเดิม ไม่ได้เปลี่ยนชื่อหรือลบแผนเดิม

**แผนอนาคตนี้ไม่แทนที่ข้อกำหนด runtime ปัจจุบัน** การเปลี่ยน behavior ต้องมี implementation PR ที่อัปเดตเอกสารหลักและ tests ที่เกี่ยวข้อง ไม่ถือว่าการ merge เอกสารนี้อนุญาตให้เชื่อม production หรือเปิด tool ที่ปิดอยู่

| เอกสาร | หน้าที่ / แหล่งอ้างอิงหลัก |
| --- | --- |
| [PRD.md](../../PRD.md) | ผู้ใช้ ปัญหา เป้าหมาย ขอบเขต และ acceptance criteria ของผลิตภัณฑ์ที่ตกลงแล้ว |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | โครงสร้างและขอบเขตความรับผิดชอบของระบบ ไม่จำเป็นต้องสร้าง design.md ที่บอกเรื่องเดียวกันอีกฉบับ |
| [CONTRACTS.md](../../CONTRACTS.md) | Public API, schema, state transitions และกติกาข้ามโมดูล; implementation ต้องตรงกับโค้ดและ tests |
| [AGENTS.md](../../AGENTS.md) | กติกาทำงานของ coding agents, scope และ risk-driven validation |
| ROADMAP.md ฉบับนี้ | ลำดับการส่งมอบ Dependencies, outcomes และ release gates ที่เสนอ |
| [RELEASE_TEMPLATE.md](RELEASE_TEMPLATE.md) | Spec และ release contract ต่อรุ่น; เขียนรายละเอียดลึกเฉพาะรุ่นที่ใกล้ทำ |
| [releases/VO-R0.md](releases/VO-R0.md) | งานตั้งต้นสำหรับประเมิน baseline และเตรียมงานรุ่นแรก |
| [GITHUB_SETUP_PROMPT.md](GITHUB_SETUP_PROMPT.md) | Prompt สำหรับสร้าง Milestones และ Issues โดยไม่ publish software ที่ยังไม่พร้อม |

ไม่สร้าง spec.md ขนาดใหญ่ซ้ำ PRD/Architecture/Contracts ทั้งระบบ ใช้ spec ต่อ release หรือ feature และเพิ่ม design note เฉพาะการตัดสินใจที่ซับซ้อน ลิงก์ไป contract แทนการคัดลอก schema หลายแห่ง

## 2. Baseline ที่ตรวจอ่านแล้ว

ตรวจจาก `main` commit `2c8932d688b8ec70d38327ae5ad12f71d141ef85` เมื่อจัดทำแผนนี้:

- PRD ระบุผลิตภัณฑ์ปัจจุบันเป็น MVP/demo และยังไม่พร้อม production
- PRD มี Voice Mode / Gemini Live บน Main Agent เดิมแล้ว จึงต้องวัดและปรับปรุงของเดิมก่อนเสนอสร้างใหม่
- Runtime catalogue ตาม PRD เปิด Knowledge และ OMS; VOC/Sabuy ระบุเป็น dormant ห้ามนับเป็น capability ที่เปิดใช้งานแล้ว
- `AGENTS.md` กำหนดความปลอดภัยของ write, idempotency, citation และ redaction รวมทั้งไม่บังคับ full TDD
- [QA learning roadmap เดิม](../qa-learning-roadmap.md) มีแนวคิด review/approval ก่อนเผยแพร่ Q&A ให้ต่อยอด ไม่สร้างเส้นทางเผยแพร่คู่ขนาน
- พบ branch `main`, `v2` และ `v2-dev` แต่ยังไม่ได้ตรวจเปรียบเทียบ implementation ทั้งสาม branch; `main` เป็นฐานของเอกสารเสนอเท่านั้น ไม่ใช่การเลือก development branch แทนเจ้าของงาน

การตรวจข้างต้นเป็น document review ไม่ใช่ runtime audit หรือผลทดสอบ live integration ยังไม่มีการรัน test, benchmark, โทรจริง, PEA SSO หรือ AnythingLLM ในงานจัดทำแผนนี้

## 3. Product outcome ที่ต้องพิสูจน์

ลูกค้าโทรเข้าเบอร์ทดสอบจริง สนทนาภาษาไทย พูดแทรกได้ ถามต่อเนื่องได้ และได้รับคำตอบจากเอกสารที่อนุมัติหรือข้อมูลจากระบบที่ได้รับสิทธิ์เท่านั้น หากระบบทำไม่ได้ต้องแจ้งข้อจำกัดหรือส่งต่อเจ้าหน้าที่โดยไม่อ้างว่าสำเร็จก่อนระบบปลายทางตอบรับ

พนักงานเข้า Control Center ด้วย PEA SSO ตามโปรโตคอลที่องค์กรยืนยัน และทำงานได้ตาม role ไม่ใช่ทุกคนที่ login ได้จะเป็น admin ผู้จัดการความรู้เพิ่มหรือแก้เอกสาร ส่งตรวจ อนุมัติ เผยแพร่ และย้อนเวอร์ชันได้ พร้อม audit

ไม่ทำ autonomous write, multi-agent จำนวนมาก, CRM/GIS/notification ทุกระบบ หรือเปลี่ยน stack ทั้งระบบเพียงเพื่อให้ดู enterprise งานนอก release ให้ลง backlog แล้วหยุด

## 4. Release schedule ที่เสนอ

ช่วงเวลาเป็น planning windows ไม่ใช่คำรับประกันส่งมอบ และไม่ใช่หลักฐานการผ่าน gate ทุก gate ต้องมีผลวัดจริง รุ่นถัดไปเริ่ม discovery ได้ แต่ห้ามข้าม security gate เพื่อปล่อยให้ผู้ใช้จริงใช้

| Release ID | ช่วงเป้าหมาย | Outcome / Release gate หลัก | Dependency |
| --- | --- | --- | --- |
| VO-R0 — Baseline & Delivery | ก.ย. 2026 | ยืนยัน branch/สิ่งที่ใช้ได้จริง, ชุดทดสอบ critical path, metric definitions, backlog และเจ้าของ dependency | ไม่มี |
| VO-R1 — Voice & Real Phone | ต.ค. 2026 | โทรเบอร์ lab จริง คุยต่อเนื่อง 5 นาที พูดแทรกได้ ปิดสายแล้ว cleanup; วัด latency จริง | VO-R0 |
| VO-R2 — Plugin & OMS Workflow | พ.ย. 2026 | Voice → OMS adapter → grounded result; plugin contract ที่เพิ่ม test plugin ได้โดยไม่เพิ่ม vendor branch ใน core; write ไม่ข้าม confirmation | VO-R1 และ approved API contract |
| VO-R3 — PEA Identity & Admin | ธ.ค. 2026 | PEA SSO ใน environment ที่อนุมัติ, server-side role mapping, revoke session/access, deny unauthorized admin actions, audit | ติดต่อ IdP owner ตั้งแต่ VO-R0 |
| VO-R4 — Managed Knowledge | ม.ค.–ก.พ. 2027 | เพิ่ม/อัปเดตเอกสาร, version, maker-checker, permission-scoped retrieval, citation, safe publish และ rollback ผ่าน Knowledge Gateway | VO-R2, VO-R3 ก่อนเปิดข้อมูลภายใน |
| VO-R5 — Reliability & Handoff | มี.ค. 2027 | ทดสอบ timeout/failure, durable state ที่จำเป็น, duplicate-write protection และโอนสายพร้อมบริบทที่ได้รับอนุญาตจริง | VO-R1–VO-R4, contact-center owner |
| VO-R6 — Operations & Governance | เม.ย. 2027 | Control Center เห็น trace, cost, error, knowledge/prompt/model versions; backup/restore และ runbook ผ่านการซ้อม | tracing/audit ขั้นพื้นฐานมีตั้งแต่รุ่นแรก |
| VO-R7 — Controlled Pilot & Evaluation | พ.ค.–มิ.ย. 2027 | ทดลองในกลุ่มจำกัดที่ได้รับอนุมัติ วัด task success/latency/safety/cost และ regression จากข้อมูลที่ใช้ได้อย่างเหมาะสม | security/privacy/operations approval และ VO-R5–VO-R6 |
| VO-R8 — Release Candidate | ก.ค. 2027 | Freeze scope, load/failure/recovery rehearsal, security review, user acceptance และ known limitations ครบ | pilot evidence จาก VO-R7 |
| VO-R9 — v1.0 Decision & Showcase | ส.ค.–8 ก.ย. 2027 | สาธิตด้วยสถานการณ์จริงและ failure cases พร้อมหลักฐาน; อนุมัติ v1.0 เฉพาะเมื่อผ่าน gates | VO-R8 และ sign-off ที่จำเป็น |

ไม่สร้าง Git tags หรือ GitHub Releases จากตารางนี้ล่วงหน้า เลขเวอร์ชันซอฟต์แวร์ให้กำหนดหลังตรวจ tags, package version และนโยบาย versioning จริง ชื่อ milestone ใช้ Release ID ก่อนเพื่อไม่ชนของเดิม หากครบกรอบเวลาแต่ production gates ยังไม่ผ่าน ให้แสดงสถานะ RC/pilot อย่างตรงไปตรงมา ไม่เรียก production-ready

Multi-agent เป็น optional backlog หลังมีผลวัดว่าช่วยคุณภาพหรือค่าใช้จ่ายเหนือ single-agent baseline และไม่ทำ latency/security แย่ลง ไม่ใช่ release บังคับก่อน v1.0

## 5. กติกาที่ต้องมีตั้งแต่รุ่นแรก

- Voice เป็นเส้นทางหลักของ demo และ evaluation ไม่ใช่ UI เสริมที่ตรวจทีหลัง
- เริ่ม representative evaluation, trace ID, redaction และ error visibility ตั้งแต่ VO-R0/VO-R1; รุ่นท้ายเป็นการยกระดับ ไม่ใช่เริ่มทำครั้งแรก
- โทร lab ด้วย synthetic/public data เท่านั้นจน identity, privacy, retention และ environment approvals ครบ ห้ามเปิด production admin/API แบบไร้ auth ระหว่างรอ SSO
- ค่าไฟ สถานะไฟดับ ETA และข้อมูลลูกค้าห้ามสร้างขึ้นเอง ถ้า source ไม่มี ETA ให้บอกว่าไม่มีข้อมูลนั้น
- รักษา `prepare → explicit confirmation → submit`, rejection terminality และ idempotency ตาม contract ปัจจุบัน การยืนยันด้วยเสียงต้องผ่าน session binding/validation ที่มีการออกแบบและทดสอบ ไม่ใช่ให้โมเดลเดาว่าผู้ใช้ตกลง
- Main Agent ใช้ typed adapter contract; OMS/VOC หรือ provider-specific intake/schema ต้องอยู่ในขอบเขตของ adapter/plugin ที่เหมาะสม
- การบันทึกเสียง/บทสนทนาใช้เฉพาะข้อมูลจำเป็นตามนโยบายที่อนุมัติ ไม่ใช้ raw calls เป็น knowledge อัตโนมัติ
- Tests เน้น permissions, public contract, write state, data leakage, citations และ regressions ไม่กำหนด 100% coverage หรือ full TDD เป็น gate แบบไร้เหตุผล

## 6. VO-R3: PEA SSO และ Authorization

ให้ PEA Identity Provider ยืนยันตัวตน และให้ VoiceOS ตัดสินสิทธิ์ฝั่ง server โดย default deny

Role เริ่มต้นที่เสนอ: EMPLOYEE, KNOWLEDGE_EDITOR, KNOWLEDGE_APPROVER, SYSTEM_ADMIN, AUDITOR แต่ชื่อ group/claim และการแมปจริงต้องได้รับการยืนยันจาก PEA ไม่ invent issuer URL, client ID, tenant, claims หรือ production endpoint

แยก service identity ของ VoiceOS → Knowledge Engine/OMS ออกจาก employee session API key ของบริการหลังบ้านต้องไม่ลง browser หรือ public chat ใช้ allowlist ของสิทธิ์/workspace ฝั่ง server ไม่เชื่อ scope ที่ LLM หรือ client เลือกเอง

งาน discovery เริ่มใน VO-R0: โปรโตคอล OIDC หรือ SAML ที่รองรับจริง, test tenant/application, redirect/logout requirements, group claims, lifecycle ของพนักงานและนโยบาย session MFA เป็นไปตาม IdP/policy ที่ตกลง ไม่อ้างว่ารองรับแล้ว

Acceptance: พนักงานธรรมดาเรียก admin endpoint ไม่ได้; editor อนุมัติผลงานตนเองไม่ได้; unauthorized/expired/revoked sessions ถูกปฏิเสธ; action สำคัญมี audit; การทดสอบ mock IdP ต้องติดป้าย mock ไม่เท่ากับทดสอบ PEA SSO จริง

## 7. VO-R4: AnythingLLM และ Knowledge Lifecycle

AnythingLLM เป็น implementation candidate สำหรับ Knowledge Engine หลัง Knowledge Gateway ไม่ใช่เจ้าของ identity หรือ business authorization ของ VoiceOS และไม่ใช่ Main Voice Agent ตัวใหม่

AnythingLLM มี Developer API แต่ workflow version/approval/rollback, โปรโตคอล SSO ของ PEA, retrieval-only API และ document-level permission ที่ต้องการต้องตรวจจาก deployment/version ที่เลือกจริง **ห้ามถือว่าคุณสมบัติทั้งหมดมีมาให้โดยไม่ต้องพัฒนาเพิ่ม** ให้ทำ capability matrix และ integration spike ก่อนออกแบบ adapter ถ้า API ส่งคำตอบที่ผ่าน LLM มาแล้ว ให้วัด extra model hop/latency/cost เทียบกับ retrieval-only และคง source evidence ที่ตรวจได้

Proposed gateway output: evidence snippets, document ID, immutable version, source reference, effective period และ publication identifier โดย public client ไม่มีสิทธิ์เลือก internal workspace ตามใจ

Lifecycle ที่ต้องพิสูจน์:

```text
Upload new version → Parse/validate → Review → Approve
→ Prepare NEW index/publication snapshot → Test citations/permissions
→ Publish approved snapshot through gateway → Invalidate affected caches
→ Archive/remove OLD retrieval snapshot when safe
```

**อย่าลบ active embeddings เดิมก่อน index ใหม่พร้อม** เพื่อไม่ให้เกิดช่วงข้อมูลหายหรือใช้เอกสารไม่ครบ ต้องมี application-level publication manifest/routing boundary หรือ equivalent ที่พิสูจน์ได้ว่า publication สอดคล้องกัน ไม่สมมติว่า engine รองรับ atomic swap โดยตรง

เก็บ original source และประวัติ version แยกจาก retrieval index การ archive ไม่เท่ากับลบประวัติ audit ส่วน deletion ต้องเป็นไปตาม retention policy ที่ตกลง ทดสอบ rollback ทั้ง source/index/cache และคำตอบที่ตามมา

Retrieval ปกติเลือกเฉพาะ approved, published, authorized และ effective version; เอกสารที่อัปโหลดล่าสุดไม่จำเป็นต้องมีผลใช้บังคับล่าสุด กรณีเอกสารขัดแย้งกันให้ใช้ policy ที่ตกลงหรือส่งตรวจ ไม่ให้ LLM เดา เอกสารในอนาคต/หมดอายุ/ร่างต้องไม่รั่วเข้าสู่คำตอบทั่วไป

เริ่ม parser กับชนิดเอกสารที่ใช้จริงและทดสอบได้ แล้วขยาย PDF/DOCX/MD/XLSX ตาม capability matrix อย่าอ้างว่าทุก format พร้อมเพียงเพราะอยู่ใน infographic ใช้เอกสารสาธารณะหรือ synthetic ใน spike; self-host engine ไม่ได้แปลว่าข้อมูลไม่ออกองค์กรหากยังใช้ external LLM/embedding provider ต้องตรวจ data flow จริง

Reuse flow จาก [QA learning roadmap](../qa-learning-roadmap.md) สำหรับคำถามที่ส่งให้เจ้าหน้าที่ตอบ โดยต้อง review/approve ก่อน publish และไม่อ้างว่าส่งต่อสำเร็จจนปลายทางรับจริง

## 8. การวัดผลและ Release Gates

ตัวเลขต่อไปนี้เป็น **provisional targets สำหรับตกลงหลังเก็บ baseline** ไม่ใช่ benchmark ของระบบที่ทำแล้ว:

| Metric | ต้องระบุวิธีวัด | เป้าหมายตั้งต้นที่เสนอ |
| --- | --- | --- |
| Voice latency | end-of-user-speech ถึง first audible response; รายงาน p50/p95 แยก tool/no-tool, เครือข่าย, concurrency และเวลาทั้ง workflow; filler ไม่นับว่าแก้งานเสร็จ | p95 ของ no-tool turn ไม่เกิน 2.5 วินาทีใน lab ที่ตกลง |
| Barge-in | successful interruptions / attempted interruptions; ระบุ maximum stop latency และ false interruption | อย่างน้อย 95% ในชุดทดสอบที่ระบุ |
| Task success | งานสำเร็จอย่างถูกต้อง / eligible tasks; แยกสาเหตุ handoff/abandonment ไม่ซ่อนด้วยการตัด denominator | อย่างน้อย 90% ใน pilot scope ที่ตกลง |
| Critical safety | unauthorized actions, data leakage, invented operational facts และ duplicate writes ในชุดทดสอบ | พบ 1 เคสที่ยืนยันได้เป็น release blocker จนแก้และ regression ผ่าน |
| Knowledge freshness | approved effective version ถูกใช้และ citation ย้อนกลับได้; test draft/expired/rollback/caches | ผ่าน deterministic acceptance cases ทุกข้อ |
| Cost | model + voice + telephony + infrastructure ต่อ completed task และ per-call distribution | กำหนด budget กับเจ้าของระบบหลัง baseline |

ทุกผลต้องแนบ sample size, scenario set/version, environment, date/window, model/prompt/knowledge version และข้อจำกัด **zero observed incidents ไม่ใช่การรับประกันว่าจะไม่มี incident ในอนาคต** Availability เช่น 99.9% เป็น SLO ที่ต้องตกลงพร้อม measurement window ไม่ใช่คำกล่าวอ้างจาก demo

Release readiness ต้องมี owner ที่รับผิดชอบจริง, scoped tests/evals, known limitations, deployment/rollback procedure ที่ทดสอบได้ และ approvals ที่เหมาะกับ environment งานไม่ครบให้ระบุ blocked/deferred ไม่ย้ายเส้นชัยด้วยการอ้างว่า code เสร็จแล้ว

## 9. วิธีบริหารบน GitHub

```text
PRD (why/what) → Roadmap (sequence)
→ Milestone per release → Epic/Issues (scoped work)
→ Release/feature spec → PR + tests/evals
→ Acceptance/sign-off → Tag + GitHub Release when ready
```

Milestones ใช้ติดตามงานอนาคต; GitHub Releases ใช้ประกาศซอฟต์แวร์ที่ผูกกับ Git tag ไม่ใช้การ publish รุ่นเปล่าแทน roadmap การสร้างแผน/issue ไม่ได้แปลว่า release เสร็จ

ตอนนี้แตกงานละเอียด VO-R0 และ VO-R1 เท่านั้น รุ่นไกลมี outcomes/dependencies/gates แล้วปรับด้วยข้อมูลจริงรายเดือน ทุก issue ต้องระบุ scope, non-goals, acceptance evidence, dependencies, file ownership และ stop condition โดยห้าม coding agent ขยายไปงานถัดไปเอง

## 10. หลักฐานอ้างอิง

- Repository baseline: PRD.md, AGENTS.md และ docs/qa-learning-roadmap.md ที่ commit ที่ระบุในหัวข้อ 2; เป็นหลักฐานของสิ่งที่เอกสารกล่าว ไม่ใช่ผล runtime test
- GitHub — About milestones: https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/about-milestones
- GitHub — About releases: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- AnythingLLM — API Access & Keys: https://docs.anythingllm.com/features/api

ตรวจเอกสารภายนอกเมื่อ 2026-09-09 และต้องตรวจ deployment/version/API จริงอีกครั้งก่อน implementation
