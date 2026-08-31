# PEA SABUY Service route catalog (read-only research)

> ตรวจสอบเมื่อ 2026-08-31 ด้วย `GET` เท่านั้นจากโดเมน/ระบบทางการของ PEA ไม่ได้ล็อกอิน ส่งแบบฟอร์ม หรือทำธุรกรรม และไม่ใช้ secondary source หรือเดา URL จาก slug

## ขอบเขตและหลักฐานต้นทาง

- หน้าแรก [PEA SABUY Service](https://sabuyservice.pea.co.th/) ตอบ `200` โดยไม่ redirect; ไม่มี `<title>` ใน HTML ที่ server ส่ง แต่มี metadata `description="PEA Sabuy Service สบายทุกเรื่องไฟฟ้า"` และ keywords ที่ระบุ `จ่ายบิลไฟฟ้าออนไลน์`, `สมัครใช้ไฟฟ้าออนไลน์`, `ติดตั้งมิเตอร์ใหม่`.
- API ทางการ [FrontEnd/GetAllCategory](https://sabuyservice.pea.co.th/api/v1.0/FrontEnd/GetAllCategory) ตอบ `200 application/json` และคืน 14 หมวดบริการ ส่วน [MasterMenu/GetAll?search=&status=1&category=](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) ตอบ `200 application/json` และคืน 59 menu records พร้อม `id`, `name`, `content_type`, `url`, `open_mode` และหมวด จึงใช้ API นี้เป็นหลักฐานชื่อบริการกับ URL โดยไม่อนุมานจาก path.
- JavaScript ที่หน้าเว็บทางการโหลดเรียก `FrontEnd/GetAllCategory`, `MasterMenu/GetAll` และ `FrontEnd/GetDetailMenuByID`; สำหรับรายการ `richtext` หน้าเว็บสร้าง safe information route `/service/{menu_id}` ก่อนส่งผู้ใช้ต่อไปยังแบบฟอร์ม. Detail API ที่ใช้ยืนยันตัวอย่างคือ [GetDetailMenuByID (S318)](https://sabuyservice.pea.co.th/api/v1.0/FrontEnd/GetDetailMenuByID?id=51c61340-4150-4a18-140c-08dcb7573509) และ [GetDetailMenuByID (S320)](https://sabuyservice.pea.co.th/api/v1.0/FrontEnd/GetDetailMenuByID?id=7ed81067-e6f6-4f49-13ff-08dcb7573509).

## Route verification inventory

### Verified — เปิดได้และหน้าที่มีหลักฐานทางการ

| URL | HTTP/result/title | หลักฐานยืนยันหน้าที่ |
|---|---|---|
| [https://sabuyservice.pea.co.th/](https://sabuyservice.pea.co.th/) | `200`, no redirect, ไม่มี emitted `<title>` | meta description `PEA Sabuy Service สบายทุกเรื่องไฟฟ้า`; keywords ระบุการจ่ายบิล สมัครใช้ไฟ และติดตั้งมิเตอร์ใหม่ |
| [https://sabuyservice.pea.co.th/status](https://sabuyservice.pea.co.th/status) | `200`, no redirect, ไม่มี emitted `<title>` | official client text `ติดตามสถานะ`; [tracking API](https://sabuyservice.pea.co.th/api/v1.0/MasterTrackingStatus/GetAll?search=&status=1&order=) ตอบ `200` และคืน 3 ปลายทาง: `สถานะขอใช้ไฟฟ้า`, `การดำเนินงานขยายเขตระบบไฟฟ้า`, `สถานะธุรกิจเกี่ยวเนี่อง` |
| [https://eservice.pea.co.th/cos/checkstatus/](https://eservice.pea.co.th/cos/checkstatus/) | `200`, no redirect; title `CheckStatus - การไฟฟ้าส่วนภูมิภาค` | ข้อความ `ตรวจสอบสถานะการขอใช้ไฟฟ้า`, `หมายเลขคำร้อง`, `ค้นหา`; URL นี้มาจาก [tracking API](https://sabuyservice.pea.co.th/api/v1.0/MasterTrackingStatus/GetAll?search=&status=1&order=) |
| [https://eservice.pea.co.th/Expansion/CheckStatus](https://eservice.pea.co.th/Expansion/CheckStatus) | `200`, no redirect; title `ตรวจสอบติดตามสถานะงานก่อสร้างขยายเขต - การไฟฟ้าส่วนภูมิภาค` | heading เดียวกับ title พร้อม `เลขประจำตัวประชาชน/นิติบุคคล`, `หมายเลขคำร้อง`, `ค้นหา`; URL มาจาก [tracking API](https://sabuyservice.pea.co.th/api/v1.0/MasterTrackingStatus/GetAll?search=&status=1&order=) |
| [https://eservice.pea.co.th/cos/individual/](https://eservice.pea.co.th/cos/individual/) | `200`, no redirect; title `ขอใช้ไฟฟ้าใหม่ประเภทบุคคลธรรมดา - การไฟฟ้าส่วนภูมิภาค` | `คำร้องขอใช้ไฟฟ้า (เอกสารที่ต้องเตรียม+อัตราค่าธรรมเนียม)`, `ข้อมูลมิเตอร์`, `ประเภทมิเตอร์`; [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) ตั้งชื่อ `บริการขอใช้ไฟฟ้าใหม่ (บ้านอยู่อาศัย)` |
| [https://eservice.pea.co.th/cos/Corporate/](https://eservice.pea.co.th/cos/Corporate/) | `200`, no redirect; title `ขอใช้ไฟฟ้าใหม่ประเภทนิติบุคคล - การไฟฟ้าส่วนภูมิภาค` | มีคำร้อง/ข้อมูลมิเตอร์เช่นเดียวกันและช่อง `เลขทะเบียนนิติบุคคล`; [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) ตั้งชื่อ `บริการขอใช้ไฟฟ้าใหม่ (ลูกค้าธุรกิจ)` |
| [https://eservice.pea.co.th/ebill/](https://eservice.pea.co.th/ebill/) | `200`, no redirect; title `PEA E-Docs Register` | `ยืนยันตัวตน`, `หมายเลขผู้ใช้ไฟฟ้า (CA)`, `บิลค่าไฟฟ้าประจำเดือน`, `จำนวนเงินค่าไฟฟ้า`; [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) ระบุ `PEA e-Bill` สำหรับบ้านและธุรกิจ |
| [https://installment.pea.co.th/](https://installment.pea.co.th/) | `200`, no redirect; title `ลงทะเบียนขอผ่อนชำระค่าไฟฟ้า - การไฟฟ้าส่วนภูมิภาค` | มี `ลงทะเบียนขอผ่อนชำระค่าไฟฟ้า`, `ยืนยันแผนผ่อนชำระค่าไฟฟ้า`, `ติดตามผลการขอผ่อนชำระค่าไฟฟ้า`; [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) map บ้านและธุรกิจมาที่ URL นี้ |
| [https://sabuyservice.pea.co.th/e-tax](https://sabuyservice.pea.co.th/e-tax) | `200`, no redirect, ไม่มี emitted `<title>` | official client text `ขอรับใบกำกับภาษีอิเล็กทรอนิกส์ (e-Tax) สำหรับธุรกิจเกี่ยวเนื่อง`, `หมายเลขคำร้อง`, `ค้นหา e-Tax` |
| [https://sabuyservice.pea.co.th/service/51c61340-4150-4a18-140c-08dcb7573509](https://sabuyservice.pea.co.th/service/51c61340-4150-4a18-140c-08dcb7573509) | `200`, no redirect, ไม่มี emitted `<title>` | [detail API](https://sabuyservice.pea.co.th/api/v1.0/FrontEnd/GetDetailMenuByID?id=51c61340-4150-4a18-140c-08dcb7573509) ตอบ `200` ชื่อ `ขอซื้อมิเตอร์/อุปกรณ์ไฟฟ้า` และอธิบายการจำหน่ายหม้อแปลง/มิเตอร์; API ระบุปลายทางแบบฟอร์ม [S318](https://sabuyservice.pea.co.th/y-form2/serviceForm/S318) |
| [https://sabuyservice.pea.co.th/service/7ed81067-e6f6-4f49-13ff-08dcb7573509](https://sabuyservice.pea.co.th/service/7ed81067-e6f6-4f49-13ff-08dcb7573509) | `200`, no redirect, ไม่มี emitted `<title>` | [detail API](https://sabuyservice.pea.co.th/api/v1.0/FrontEnd/GetDetailMenuByID?id=7ed81067-e6f6-4f49-13ff-08dcb7573509) ตอบ `200` ชื่อ `ขอติดตั้งมิเตอร์เปรียบเทียบ กรณีผิดปกติ` และอธิบายการตรวจความเที่ยงตรง; API ระบุปลายทางแบบฟอร์ม [S320](https://sabuyservice.pea.co.th/y-form2/serviceForm/S320) |
| [https://complaint.pea.co.th/](https://complaint.pea.co.th/) | `200`, no redirect; title `การไฟฟ้าส่วนภูมิภาค` | ข้อความ `ระบบรับฟังเสียงของลูกค้า (PEA-VOC System)`, `ติดตามเสียง`, `ติดตามปัญหาคุณภาพไฟฟ้า`; [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) map `แนะนำ/ร้องเรียน` มาที่นี่ |
| [https://sabuyservice.pea.co.th/privacy-policy](https://sabuyservice.pea.co.th/privacy-policy) | `200`, no redirect, ไม่มี emitted `<title>` | official client labels `ตั้งค่าความเป็นส่วนตัว`, `นโยบายคุกกี้` |

### Redirect และ auth-required

| URL | Classification | ผลที่ตรวจพบ |
|---|---|---|
| [https://eservice.pea.co.th/](https://eservice.pea.co.th/) | **redirect + auth-required** | `302 Location: /Account/Login?ReturnUrl=%2f` → `200` ที่ login URL; final title `เข้าสู่ระบบรับชำระค่าไฟฟ้าทางอินเตอร์เน็ต - การไฟฟ้าส่วนภูมิภาค`, heading `เข้าสู่ระบบ e-Service`. [master menu](https://sabuyservice.pea.co.th/api/v1.0/MasterMenu/GetAll?search=&status=1&category=) ระบุ URL นี้เป็น `บริการรับชำระค่าไฟฟ้า` ทั้งบ้านและธุรกิจ |
| [https://sabuyservice.pea.co.th/status/login](https://sabuyservice.pea.co.th/status/login) | **auth/OTP-required for actual lookup** | public landing ตอบ `200`; official client text ระบุ `ติดตามสถานะด้วย Digital ID`, `เข้าสู่ระบบด้วย Digital ID`, `ติดตามสถานะผ่านระบบ e-Service` และช่อง OTP/เลขประจำตัวหรือเลขผู้เสียภาษี/หมายเลขคำร้อง/โทรศัพท์. URL มาจาก [tracking API](https://sabuyservice.pea.co.th/api/v1.0/MasterTrackingStatus/GetAll?search=&status=1&order=) ในชื่อ `สถานะธุรกิจเกี่ยวเนี่อง` |

### 404 — ทดสอบแล้ว ห้าม route ไป

| URL | Result |
|---|---|
| [https://sabuyservice.pea.co.th/tracking](https://sabuyservice.pea.co.th/tracking) | `404`, no redirect; Next error `404: This page could not be found.` |
| [https://sabuyservice.pea.co.th/eservice](https://sabuyservice.pea.co.th/eservice) | `404`, no redirect |
| [https://sabuyservice.pea.co.th/service](https://sabuyservice.pea.co.th/service) | `404`, no redirect; ต้องมี verified menu ID หลัง `/service/` |
| [https://sabuyservice.pea.co.th/ebill](https://sabuyservice.pea.co.th/ebill) | `404`, no redirect; e-Bill ที่ catalog ทางการให้คือ [https://eservice.pea.co.th/ebill/](https://eservice.pea.co.th/ebill/) |

### Uncertain

ไม่มีในชุด URL ที่แนะนำด้านล่าง ทุก URL ถูกเปิดตรวจจริงและมี first-party evidence. อย่างไรก็ดี หน้า Next.js หลายหน้าของ SABUY ไม่มี server-rendered `<title>`/body; การยืนยันหน้าที่ของหน้าเหล่านั้นจึงอ้างเฉพาะข้อความใน official client bundle และ/หรือ same-origin official API ไม่อ้างชื่อ path.

## Recommended intent → official-link catalog for `sabuy_tool`

> ชุดด้านล่างเป็น **core catalog ที่ตรวจหน้าปลายทางแล้ว** สำหรับ flow ที่ตกลงกัน ไม่ใช่การอ้างว่าครอบคลุมทั้ง 59 เมนูใน official API. หากต้องการให้ Tool รองรับทุกบริการ ต้องทำ verification และเพิ่มคำอธิบาย/guard ของเมนูที่เหลือก่อน ห้าม fallback ไป URL ที่ยังไม่ได้ตรวจ.

หลักการ: ใช้ ToolAction เดียว เช่น `get_official_link`; ให้ LLM เลือก `serviceKey` จาก catalog ด้านล่าง แล้ว tool คืน `official_url`, `classification`, และคำเตือนเรื่อง login/OTP เท่านั้น; **ห้าม**กรอกข้อมูล กด submit ยืนยัน OTP หรือชำระเงินแทนผู้ใช้. Tool ต้องเลือก URL จาก allowlist เท่านั้นและไม่รับ URL อิสระจากโมเดล.

| `serviceKey` (LLM เลือก) | LLM description | Positive intents (TH / EN) | Official URL | Exclusions / routing guard |
|---|---|---|---|---|
| `open_sabuy_service_home` | เปิด landing รวมบริการ PEA SABUY Service เมื่อผู้ใช้ถามภาพรวมหรือยังไม่ระบุบริการ | `บริการออนไลน์ PEA มีอะไรบ้าง`, `หน้า SABUY Service` / `PEA online services`, `open SABUY Service` | [SABUY home](https://sabuyservice.pea.co.th/) | ไม่ใช้แทน route เฉพาะเมื่อ intent ชัด; ไม่ทำธุรกรรม |
| `open_electricity_bill_payment` | ส่งลิงก์ e-Service ทางการสำหรับรับชำระค่าไฟ; แจ้งว่าระบบ redirect ไป login | `จ่ายค่าไฟ`, `ชำระบิลไฟ`, `จ่ายค่าไฟออนไลน์` / `pay electricity bill`, `pay my PEA bill` | [PEA e-Service](https://eservice.pea.co.th/) | **ไม่ใช่** e-Bill registration, ประวัติบิล, ผ่อนชำระ หรือการเตรียม/submit payment ใน agent; auth-required |
| `open_sabuy_status_hub` | เปิดศูนย์รวมติดตามสถานะงานบริการ SABUY เมื่อผู้ใช้ระบุชัดว่าเป็นคำร้อง/งานบริการของ SABUY | `ติดตามสถานะบริการ SABUY`, `เช็กคำร้อง PEA`, `งานบริการ SABUY ไปถึงไหน` / `track SABUY request`, `check PEA service status` | [SABUY status hub](https://sabuyservice.pea.co.th/status) | **ห้าม route VOC** เมื่อมี `ร้องเรียน`, `ติดตามเสียง`, `เคส VOC`, `ปัญหาคุณภาพไฟฟ้า`, `complaint`, `VOC case`; ให้ Main Agent ส่งต่อไป `voc_tool` |
| `track_new_electricity_request` | เปิดหน้าตรวจสถานะคำขอใช้ไฟฟ้าใหม่ด้วยหมายเลขคำร้อง | `ตามสถานะขอไฟใหม่`, `เช็กคำร้องติดตั้งมิเตอร์ใหม่` / `track new electricity application`, `check new meter request` | [new-service status](https://eservice.pea.co.th/cos/checkstatus/) | ไม่ใช้กับคำร้องเรียน/VOC และไม่ใช้กับงานขยายเขต |
| `track_distribution_expansion` | เปิดหน้าติดตามสถานะงานก่อสร้างขยายเขตระบบไฟฟ้า | `ตามงานขยายเขตไฟฟ้า`, `สถานะก่อสร้างขยายเขต` / `track grid extension`, `distribution expansion status` | [expansion status](https://eservice.pea.co.th/Expansion/CheckStatus) | ไม่ใช้กับขอไฟใหม่ทั่วไปหรือ VOC case |
| `track_related_business_service` | เปิดหน้า tracking ธุรกิจเกี่ยวเนื่อง; แจ้งว่าต้อง Digital ID/e-Service/OTP เพื่อค้นจริง | `ติดตามสถานะธุรกิจเกี่ยวเนื่อง`, `ตามคำร้องบริการ S3xx` / `track related-business service`, `check S3xx request` | [related-business tracking](https://sabuyservice.pea.co.th/status/login) | ไม่ใช้กับ VOC/complaint; ไม่ขอหรือกรอก OTP ให้ผู้ใช้ |
| `request_new_electricity_residential` | ส่งลิงก์คำร้องขอใช้ไฟใหม่/ข้อมูลมิเตอร์สำหรับบุคคลธรรมดาหรือบ้านอยู่อาศัย | `ขอใช้ไฟใหม่ที่บ้าน`, `ติดตั้งมิเตอร์ใหม่ บุคคลธรรมดา` / `apply for new residential electricity`, `new home meter` | [residential new service](https://eservice.pea.co.th/cos/individual/) | ไม่ใช้กับซื้ออุปกรณ์/มิเตอร์แยก, มิเตอร์เปรียบเทียบ หรือบริษัท |
| `request_new_electricity_corporate` | ส่งลิงก์คำร้องขอใช้ไฟใหม่สำหรับนิติบุคคล/ธุรกิจ | `ขอไฟใหม่บริษัท`, `ติดตั้งมิเตอร์โรงงาน` / `apply for corporate electricity`, `new business meter` | [corporate new service](https://eservice.pea.co.th/cos/Corporate/) | ไม่ใช้กับบ้าน/บุคคลธรรมดา, ซื้ออุปกรณ์ หรือมิเตอร์เปรียบเทียบ |
| `register_pea_ebill` | เปิดหน้าลงทะเบียนเอกสารค่าไฟอิเล็กทรอนิกส์ | `สมัคร e-Bill`, `รับใบแจ้งค่าไฟออนไลน์` / `register PEA e-Bill`, `electronic electricity bill` | [PEA e-Bill](https://eservice.pea.co.th/ebill/) | **ไม่ใช่การชำระค่าไฟ**; ไม่ route คำว่า `จ่าย/pay` มาที่นี่หากไม่มี intent เอกสาร/ใบแจ้งหนี้ |
| `open_installment_registration` | เปิดระบบลงทะเบียน/ยืนยัน/ติดตามการผ่อนชำระค่าไฟ | `ขอผ่อนค่าไฟ`, `ลงทะเบียนผ่อนชำระ` / `electricity bill installment`, `request payment plan` | [PEA installment](https://installment.pea.co.th/) | ไม่ใช่ payment ปกติและไม่รับเงื่อนไขแทนผู้ใช้ |
| `open_related_business_etax` | เปิดหน้าค้นหา/ขอรับ e-Tax สำหรับธุรกิจเกี่ยวเนื่อง | `ขอ e-Tax ธุรกิจเกี่ยวเนื่อง`, `ค้นหาใบกำกับภาษีคำร้อง` / `related-business e-Tax`, `find electronic tax invoice` | [SABUY e-Tax](https://sabuyservice.pea.co.th/e-tax) | ไม่ใช่ e-Bill ทั่วไปหรือหน้าจ่ายค่าไฟ |
| `open_meter_purchase_info` | เปิดหน้า **ข้อมูลบริการ** ขอซื้อมิเตอร์/อุปกรณ์ไฟฟ้า; agent ไม่เปิด/ส่งแบบฟอร์มเอง | `ซื้อมิเตอร์จาก PEA`, `ขอซื้ออุปกรณ์ไฟฟ้า` / `buy a PEA meter`, `purchase electrical equipment` | [meter/equipment information](https://sabuyservice.pea.co.th/service/51c61340-4150-4a18-140c-08dcb7573509) | ไม่ใช่ขอใช้ไฟใหม่/ติดตั้งมิเตอร์ใหม่ และไม่ใช่ตรวจมิเตอร์ผิดปกติ |
| `open_abnormal_meter_comparison_info` | เปิดหน้า **ข้อมูลบริการ** ติดตั้งมิเตอร์เปรียบเทียบเพื่อตรวจความเที่ยงตรงกรณีผิดปกติ | `มิเตอร์ผิดปกติ ขอเทียบมิเตอร์`, `ตรวจความเที่ยงตรงมิเตอร์` / `abnormal meter comparison`, `check meter accuracy` | [comparison-meter information](https://sabuyservice.pea.co.th/service/7ed81067-e6f6-4f49-13ff-08dcb7573509) | ไม่ใช่ขอไฟใหม่, ซื้อมิเตอร์ หรือ complaint/VOC |
| `open_sabuy_privacy_policy` | เปิดนโยบายความเป็นส่วนตัว/คุกกี้ของ SABUY Service | `นโยบายความเป็นส่วนตัว SABUY`, `ตั้งค่าคุกกี้` / `SABUY privacy policy`, `cookie policy` | [privacy policy](https://sabuyservice.pea.co.th/privacy-policy) | ไม่ใช้กับคำถามสถานะหรือบริการไฟฟ้า |

## Disambiguation rule: SABUY tracking vs VOC case tracking

1. ส่งต่อไป `voc_tool` ก่อน หากมีสัญญาณ complaint/case เช่น `ร้องเรียน`, `แนะนำ`, `เสียงลูกค้า`, `ติดตามเสียง`, `VOC`, `เคสร้องเรียน`, `ปัญหาคุณภาพไฟฟ้า`, `complaint`, `customer voice`, `power-quality complaint` — หลักฐานคือหน้า [PEA-VOC](https://complaint.pea.co.th/) ใช้คำเหล่านี้โดยตรง และลิงก์นี้ไม่อยู่ใน action catalog ของ `sabuy_tool`.
2. Route ไป SABUY tracking เฉพาะคำร้อง/งานบริการ: `คำร้องขอใช้ไฟ`, `ขยายเขต`, `ธุรกิจเกี่ยวเนื่อง`, `หมายเลขคำร้อง`, `service request`, `new connection`, `expansion`, `S3xx` — สามกลุ่มนี้ตรงกับ [official tracking API](https://sabuyservice.pea.co.th/api/v1.0/MasterTrackingStatus/GetAll?search=&status=1&order=).
3. ถ้ามีเพียง `ติดตามสถานะ/track status` โดยไม่มี object ให้ Main Agent ถามกลับว่าเป็น **คำร้องงานบริการ SABUY** หรือ **เรื่องร้องเรียน/VOC**; ห้ามเดาหรือเปิดลิงก์ใดทันที.

## Proposed minimal contract and orchestration plan

### Tool contract

- มี ToolAction เดียว: `get_official_link`.
- Input ขั้นต่ำ: `{ "serviceKey": <enum> }` โดย enum มาจาก catalog ด้านบน; ไม่รับ `url` จาก LLM.
- Output ขั้นต่ำ: `{ "serviceKey", "title", "officialUrl", "purpose", "requiresAuth", "requiresOtp" }`.
- Tool เป็น read-only navigation resolver: ไม่มี account lookup, `prepare_payment`, `submit_payment`, form submission หรือ status lookup ภายใน agent.
- หาก `serviceKey` ไม่อยู่ใน allowlist ให้คืน typed `invalid_input` และไม่สร้าง/fallback URL เอง.

### Main Agent orchestration

1. **จ่ายค่าไฟ** → เรียก SABUY `get_official_link` ด้วย `serviceKey=open_electricity_bill_payment`; คำตอบต้องแจ้งว่าลิงก์พาไปหน้า login e-Service.
2. **ขอใช้ไฟฟ้าใหม่/ติดตั้งมิเตอร์ใหม่** → เรียก `knowledge_tool.search` เพื่ออธิบายขั้นตอน/เอกสารจากหลักฐาน และเรียก SABUY `get_official_link` ด้วย `serviceKey=request_new_electricity_residential` หรือ `request_new_electricity_corporate` เพื่อคืนลิงก์ในรอบเดียวกัน. หากไม่ทราบว่าเป็นบุคคลธรรมดาหรือนิติบุคคล ให้ถามก่อนเลือก URL.
3. **ติดตามงาน SABUY ที่ระบุประเภท** → เลือก status hub หรือ status route เฉพาะตาม catalog.
4. **ติดตาม VOC/ร้องเรียน** → ไม่เรียก `sabuy_tool`; ส่งต่อ `voc_tool`.
5. **พูดเพียง “ติดตามสถานะ”** → ถาม clarification ก่อนและยังไม่เรียก tool.

## Implementation notes (non-transactional contract)

- Catalog ควรเก็บ URL แบบคงที่จาก API/route ที่ verify แล้ว ไม่สร้าง URL จากชื่อ action หรือ slug.
- ผลลัพธ์ควรระบุ `requires_auth=true` สำหรับ payment และ `requires_auth_or_otp=true` สำหรับ related-business tracking.
- ลิงก์ `/service/{id}` ใช้เป็น information landing สำหรับ richtext service; อย่าเรียก API submit หรือเปิด POST flow. ปลายทาง `y-form2/serviceForm/*` บันทึกไว้เป็น evidence ใน detail API เท่านั้น ไม่จำเป็นต้องคืนเป็น default link.
- Route ที่อยู่ในรายการ 404 ต้อง fail closed: ไม่ fallback ไป URL ที่เดาจาก slug.
