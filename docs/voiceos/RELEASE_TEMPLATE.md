# Release / Feature Contract Template

ใช้สำหรับ release หรือ feature ที่กำลังจะเริ่มทำ ไม่ต้องเขียนสเปกละเอียดทั้งปีล่วงหน้า ไม่คัดลอก schema ที่มี source of truth แล้ว ให้ลิงก์ไป CONTRACTS.md/implementation schema/tests

## Identity

- Release ID / feature ID:
- Status: Proposed / Ready / In progress / Blocked / Accepted / Released
- Product owner / engineering owner / reviewer: TBD จนเจ้าของยืนยัน
- Milestone / issue:
- Base branch + commit:
- Target window: indicative, not a delivery guarantee
- Related PRD requirements:

## Outcome

ผู้ใช้คนไหนทำอะไรสำเร็จ และทำไมผลนี้สำคัญ เขียนเป็น end-to-end user journey หนึ่งเส้นทางที่สาธิตได้

## Scope / Non-goals

ระบุสิ่งที่ต้องเปลี่ยนและสิ่งที่ห้ามเปลี่ยน โดยเฉพาะ dormant plugins, write behavior และ production integrations ที่ยังไม่ได้รับอนุญาต

## Current state and gap

| Capability | Evidence / file / test | Confirmed working / documented only / missing / unknown | Remaining work |
| --- | --- | --- | --- |
| Example | Actual source reference | Unknown until exercised | Smallest next check |

## Functional behavior

ระบุ normal path, ambiguous input, validation, cancellation/rejection, timeout, disconnect และ human handoff ที่เกี่ยวข้อง

## Technical design

- Reuse existing modules first; proposed changed/added files and ownership
- Public API/schema changes: link to exact canonical contract; no duplicate definition
- Data/state model and state transitions
- Migration / compatibility / feature flag / rollback
- Dependency/protocol evidence from official documentation and actual approved environment
- Alternatives and tradeoff only where a real decision is needed

## Permissions and data

Principal identity, authorization checks, classification, logging redaction, retention, service credentials, publish/approval authority และผลเมื่อ unauthorized ระบุให้ชัดว่า mock หรือ real integration

## Acceptance criteria

ใช้ Given / When / Then พร้อมหลักฐานว่าผ่าน ไม่ใช้เพียงคำว่า works, enterprise-ready หรือ secure

| ID | Scenario | Expected behavior | Verification / evidence |
| --- | --- | --- | --- |
| AC-01 | Happy path | Observable outcome | Test/demo reference |
| AC-02 | Unauthorized or invalid input | Deny / safe response, no side effect | Negative test |
| AC-03 | Dependency failure | Correct fallback / no invented success | Failure injection |

Metrics ต้องมี numerator/denominator, sample size, window, environment และ threshold ที่ตกลงก่อนอ่านผล latency ใช้ p50/p95 พร้อม start/end markers ไม่ใช้ average อย่างเดียว

## Tests and evaluation

Risk-driven tests สำหรับ deterministic boundaries; representative evaluation สำหรับ model output ไม่บังคับ full TDD หรือ 100% coverage รายงานคำสั่งที่รัน ผลจริง และส่วนที่ยังไม่ได้ตรวจ ห้ามใช้ mock tests เป็นหลักฐานว่า live PEA integration ผ่าน

## Release / rollback

Pin approved commit, prompt/model/config/knowledge versions, record migrations, rehearse rollback และระบุ residual risk ไม่ rollback application โดยปล่อย database/index/cache อยู่คนละ version

## Dependencies / blockers / assumptions

ระบุ owner ที่ต้องติดต่อและสิ่งที่ขาด เช่น IdP protocol, test number, API access, approved data, budget ห้ามสร้าง credentials, deadlines หรือ approvals ขึ้นเอง

## Stop condition

จบเมื่อ deliverables ที่ตกลงครบและหลักฐานตรวจผ่าน หรือรายงาน blocker พร้อมงานที่ทำได้ ห้ามทำ feature ถัดไป, refactor นอกเรื่อง, publish release, merge หรือ deploy โดยไม่มีขอบเขตคำสั่งรองรับ
