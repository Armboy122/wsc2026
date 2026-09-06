# A3 — ตรวจสอบการเพิ่ม REST tool จากหน้าเว็บจน AI เรียกใช้ได้

เอกสารนี้เป็นหลักฐานชุดใหม่ของ A3 และ **ไม่เขียนทับ** `docs/v2/DEMO-VERIFICATION.md` (P5)

## สรุปสถานะ

- **ผล critical path A3:** ผ่านบน test instance แยก โดยใช้หน้าเว็บจริงและ provider Gemini จริง
- **commit ฐานก่อน A3:** `e9e5627869aceb5a55dcb8467e95b320199f7a0d` (หลัง A1/A2)
- **commit แก้ blocker ของ A3:** `7d44f5d` — แก้การรักษา `submitAction` เมื่อเปิดฟอร์ม tool เดิม
- **วันที่ตรวจ:** 2026-09-06
- **test instance:** `http://127.0.0.1:8111`
- **environment:** `APP_ENV=development`, SQLite file ชั่วคราวนอก repository
- **provider mode:** Main Agent ใช้ Gemini `gemini-3.5-flash-lite`; ตรวจพบ request จริงตอบ HTTP 200 ทั้ง Gemini และ upstream REST
- **ขอบเขตความปลอดภัย:** ไม่มี credential หรือข้อมูลลูกค้าจริงใน tool definition, หลักฐาน, หรือเอกสารนี้; ไม่แตะ `data/pea.db`

## Tool ที่ใช้พิสูจน์

เลือก `cat_fact_tool` ซึ่งยังไม่อยู่ใน catalogue ตอนเริ่ม test instance

```text
slug:        cat_fact_tool
displayName: ข้อเท็จจริงเกี่ยวกับแมว
auth:        ไม่มี
action:      get_random_fact
policy:      plain_read
mode:        read
exposure:    llm
method:      GET
URL:         https://catfact.ninja/fact
input:       max_length (integer, optional)
output:      fact (string), length (integer)
```

เอกสารอ้างอิง upstream: `https://catfact.ninja/` (หน้า `Cat Facts API`, ตรวจ HTTP 200)
endpoint ใช้ `GET /fact?max_length=<integer>` และตอบ JSON แบบเรียบง่าย ไม่มี OAuth และไม่มี
ข้อมูลลูกค้า

## ผลการเดิน flow จริง

| ขั้นตอน | ผล | หลักฐานที่ตรวจได้ |
|---|---|---|
| 1. เปิด `/admin.html` และ login | **ผ่าน** | Chrome headless เปิดหน้าและกรอกรหัสผ่านผ่านฟอร์มจริง; session สำเร็จ |
| 2. สร้าง tool จากฟอร์ม | **ผ่าน** | กด `สร้าง tool ใหม่`, กรอก slug/description/action/method/URL, กด `เพิ่มฟิลด์`, กรอก `max_length` และบันทึก; ไม่ seed SQL |
| 3. ลองยิงจากฟอร์ม | **ผ่าน** | กรอก `max_length=120`; UI แสดง `HTTP สำเร็จ · 200`, request `GET .../fact?max_length=120` และ JSON response |
| 4. เปลี่ยน input ตอนลองยิง | **ผ่าน** | เปลี่ยนเป็น `max_length=60`; UI/request แสดง query `max_length=60`, upstream ตอบ JSON `length=60` ในรอบที่ตรวจ |
| 5. บันทึกและเปิดใช้ | **ผ่าน** | รายการแสดง `cat_fact_tool`, `declarative (DB)`, `เปิดใช้งาน`; registry catalogue มี tool โดยไม่ restart |
| 6. ถามผ่านหน้าแชต | **ผ่าน** | คำถาม `ช่วยหาข้อเท็จจริงเกี่ยวกับแมว โดยกำหนดความยาวสูงสุด 60 ตัวอักษร`; หน้าแชตแสดง `cat_fact_tool.get_random_fact`, `SIMULATED` และผล JSON จาก upstream |
| 7. ตรวจ trace | **ผ่าน** | trace `1caf4449-4564-463d-8c43-85bfd36257c8` มี `tool_called` sequence 4 และ `tool_result` sequence 5 พร้อม slug/action/policy; trace `d1d0daa4-441e-4dd1-b20e-6f65ec41a671` ยืนยันรอบ `max_length=120` |
| 8. ตรวจ input ถึง upstream | **ผ่าน** | HTTP access log ของ server แสดง `GET https://catfact.ninja/fact?max_length=60` และ `...max_length=120` ตอบ `200`; trace ไม่เก็บ query ตามกติกาความปลอดภัย |
| 9. ปิด tool แล้วถามเทิร์นใหม่ | **ผ่าน** | ปิดจากปุ่มในหน้า admin; คำถามใหม่ตอบว่าไม่รองรับ และ trace `5b08a446-6559-452a-b370-aa4828a9a4b0` ไม่มี `tool_called` |
| 10. เปิดกลับโดยไม่ restart | **ผ่าน** | เปิดจากปุ่มเดิม; คำถามใหม่เรียก tool ได้อีกครั้งและมี `tool_called/tool_result` ใน trace |
| 11. เปิดฟอร์มแก้และบันทึกซ้ำ | **ผ่านหลังแก้ blocker** | เปิด `oms_tool` ซึ่งมี prepare/submit และ auth เดิม; ค่า submit action, `clientContext` และแถว auth ไม่หายหลัง save |

ผล upstream ที่เห็นในรอบ AI เป็น JSON เช่น `{"fact":"Cats walk on their toes.","length":24`
และอีกรอบ `{"fact":"Cats, especially older cats, do get cancer. Many times this disease can be treated successfully.","length":96}`
ซึ่งสอดคล้องกับข้อจำกัด `max_length` ของคำถามและ access log

## Blocker ที่พบและแก้

ก่อนแก้ เมื่อเปิด `oms_tool` จากหน้า admin จริง operation แบบ `prepare` มีตัวเลือก
`submitAction` ว่าง แม้ข้อมูลเดิมมีคู่ `prepare → submit` อยู่แล้ว การกดบันทึกโดยไม่แก้ไข
จึงหยุดที่ UI ด้วยข้อความ:

```text
Operation ที่ 2 (prepare_anonymous_outage): กรุณาเลือก submitAction
```

Root cause คือ `addOperationCard()` เรียก `syncSubmitField()` ขณะ submit cards ยังไม่ถูกสร้าง
ตัวเลือกที่ไม่มีในขณะนั้นทำให้ค่าเดิมถูกทิ้งไป แม้จะมีการ sync อีกรอบหลังโหลดครบแล้วก็ตาม

แก้เฉพาะ blocker นี้ใน:

- `web/admin.js` — เก็บค่า `submitAction` เดิมไว้จนกว่าจะสร้าง operation ครบ และ sync หลังโหลดฟอร์ม
- `tests/test_admin_edit_payload.py` — regression boundary สำหรับการ sync หลังโหลดฟอร์ม

หลังแก้ เปิด `oms_tool` ใหม่แล้วพบค่า `submit_anonymous_outage` และ
`submit_outage_with_ca` ถูกเลือกถูกต้อง; save สำเร็จ และตรวจ metadata ที่ไม่ใช่ความลับว่า
`clientContext={lat:lat, lon:lon}` กับ auth header `X-API-Key`/scheme ว่างยังอยู่

## Validation commands

```text
.venv/bin/python -m pytest -q tests/test_admin_edit_payload.py tests/test_admin_tools.py tests/test_admin_try_operation.py tests/test_admin_try_status.py tests/test_admin_try_saved_auth.py
73 passed, 1 warning

node --check web/admin.js && node --check web/admin-form.js
ผ่าน

./scripts/evaluate http://127.0.0.1:8111
exit 1
```

`evaluate` **ไม่ผ่านและไม่ได้อ้างว่าเป็นผลผ่าน**: สคริปต์เดิมเรียก public API/reset โดยไม่มี
API key หรือ admin session ขณะที่ instance ปัจจุบันบังคับ auth; จึงได้ HTTP 401 สำหรับ reset/chat
และ completion `0.0` แม้ `/health` ตอบ 200 นอกจากนี้สคริปต์ยังคาด health fields แบบเก่า
(`knowledgeBackend`) ไม่ตรงกับ envelope ปัจจุบัน ปัญหานี้อยู่นอกขอบเขต A3 และไม่ได้แก้เงียบ ๆ

Full suite หลังรวมการแก้และเอกสาร: `.venv/bin/python -m pytest -q` → **746 passed, 7 warnings** (2026-09-06)

## ข้อจำกัดและการทำซ้ำ

1. การตรวจนี้ใช้ `development` เพื่อให้ปลายทางสาธารณะ HTTPS ยิงได้โดยไม่ต้องเพิ่ม production allowlist; production ต้องเพิ่มโดเมนใน allowlist ตาม policy
2. `catfact.ninja` คืนข้อความแบบสุ่ม จึงอาจได้ `fact` ต่างกันในแต่ละรอบ; หลักฐานที่คงที่คือ status, query, schema และ trace slug/action
3. Trace จงใจไม่เก็บ query string, header หรือ request body; การพิสูจน์ input ที่ไป upstream ใช้ access log ที่ไม่มี secret และผลจากปุ่มลองยิง
4. หน้าแชตปัจจุบันแสดงผล tool ทั่วไปเป็น JSON ดิบ แม้ถูกต้องตามผล upstream — เป็นจุดติดขัด UX สำหรับ A4 ควรมี presentation ของ plain-read ที่อ่านเป็นภาษามนุษย์
5. ไม่ได้เชื่อม write เข้าระบบ PEA จริง; OMS และผล operational เดิมยังเป็น simulation
6. มีการจับ screenshot ระหว่างทดสอบโดยไม่มี credential แต่เก็บเป็น artifact ชั่วคราวนอก repository ไม่เพิ่มไฟล์ binary ในงานนี้

วิธีทำซ้ำ: ใช้ DB/config ทดสอบแยก, เริ่ม server โดยไม่ใช้ `--reload`, เปิด `/admin.html`, login,
สร้าง definition ตามด้านบน, กดลองยิงด้วย `120` และ `60`, save, เปิดหน้าแชตถามสองค่า, ปิด/เปิด
จากหน้า admin แล้วตรวจ trace ของแต่ละเทิร์น

งานเดิมรวมถึง P11 และ `docs/v2/PROMPTS-PLUGIN.md` ไม่ได้ถูกแตะหรือรวมเข้าการเปลี่ยนแปลงนี้
