# PEA electricity-tariff evidence gate — Sep–Dec 2569 (2026)

This is a research/evidence note, not a runtime rate table. The downloaded primary-source files remain in `/tmp/pea-tariff-2569/`; provenance and page-completeness details are in `provenance-page-completeness.md` there. Live retrieval and byte/hash checks were performed on **2026-09-07**.

## Evidence status

**Verified from the official PEA PDFs**

- The residential schedule is Type 1 (ประเภทที่ 1 บ้านอยู่อาศัย), page 3.
- Normal-rate 1.1.2 has the three blocks `0–200 @ 3.0000`, `201–400 @ 4.1584`, and `401+ @ 4.3583`, with a 24.62 baht/month service charge. The surprising `3.0000` is printed in the rendered page and in the PDF text layer; it is not an inferred or rounded value.
- The base schedule starts with the September 2569 electricity month, and PEA says the base rates exclude VAT. Ft is 0.1623 baht/unit for the September–December 2569 billing months and also excludes VAT.

**Not verified and therefore not asserted**

- A usage total alone does not establish the customer's PEA customer type, meter rating, account history, or whether the customer elected TOU. A household purpose, one-meter arrangement, and the applicable account facts are still required.
- No official invoice-rounding rule was found in the inspected PEA PDFs. A two-decimal result below is an explicitly labeled estimate policy, not a PEA invoice rule; no error bound is claimed.
- The evidence does not support a state-welfare credit, a credit “on top,” or any other benefit amount. Those claims have been removed.
- The PEA PDFs do not establish a 7% VAT rate for every month in Sep–Dec 2569. The Revenue Department evidence has an important expiry boundary: September is inside the dated legal period; October–December are outside it unless a later extension is independently verified.

## Exact PEA evidence

### Residential schedule and category rules (PEA tariff PDF, printed page 3)

The following is the relevant text-layer output / visual transcription, retained in full in `/tmp/pea-tariff-2569/tariff-pdfkit-full-text.txt`:

```text
ประเภทที่ 1 บ้านอยู่อาศัย
สำหรับการใช้ไฟฟ้ากับบ้านที่อยู่อาศัย วัด สำนักสงฆ์ สถานประกอบศาสนกิจของทุกศาสนา และการใช้ไฟฟ้าเพื่ออยู่อาศัยอย่างต่อเนื่องที่ยังไม่มี
ทะเบียนบ้านถาวร ตลอดจนบริเวณที่เกี่ยวข้อง โดยต่อผ่านเครื่องวัดไฟฟ้าเครื่องเดียว
1.1 อัตราปกติ ค่าพลังงานไฟฟ้า (บาท/หน่วย) ค่าบริการ (บาท/เดือน)
1.1.1 ใช้พลังงานไฟฟ้าไม่เกิน 150 หน่วยต่อเดือน 8.19
15 หน่วยแรก (หน่วยที่ 0 – 15) 2.3488
10 หน่วยต่อไป (หน่วยที่ 16 – 25) 2.9882
175 หน่วยต่อไป (หน่วยที่ 26 – 200) 3.0000
200 หน่วยต่อไป (หน่วยที่ 201 – 400) 4.1584
เกิน 400 หน่วยขึ้นไป (หน่วยที่ 401 เป็นต้นไป) 4.3583
1.1.2 ใช้พลังงานไฟฟ้าเกิน 150 หน่วยต่อเดือน 24.62
200 หน่วยแรก (หน่วยที่ 0 – 200) 3.0000
200 หน่วยต่อไป (หน่วยที่ 201 – 400) 4.1584
เกิน 400 หน่วยขึ้นไป (หน่วยที่ 401 เป็นต้นไป) 4.3583
1.2 อัตราตามช่วงเวลาของการใช้ (Time of Use Rate : TOU) ค่าพลังงานไฟฟ้า (บาท/หน่วย) ค่าบริการ (บาท/เดือน)
Peak Off Peak
1.2.1 แรงดัน 22 – 33 กิโลโวลท์ 5.1135 2.6037 312.24
1.2.2 แรงดันต่ำกว่า 22 กิโลโวลท์ 5.7982 2.6369 24.62
หมายเหตุ 1. ผู้ใช้ไฟฟ้าที่ติดตั้งเครื่องวัดไฟฟ้าไม่เกิน 5 แอมป์ 220 โวลท์ 1 เฟส 2 สาย จะจัดเข้าประเภทที่ 1.1.1 แต่หากใช้ไฟฟ้าเกิน 150 หน่วยติดต่อกัน
3 เดือน ในเดือนถัดไปจะจัดเข้าประเภทที่ 1.1.2 และเมื่อใดมีการใช้ไฟฟ้าไม่เกิน 150 หน่วย ติดต่อกัน 3 เดือน ในเดือนถัดไปจะจัดเข้าประเภทที่ 1.1.1
2. ผู้ใช้ไฟฟ้าที่ติดตั้งเครื่องวัดไฟฟ้าเกิน 5 แอมป์ 220 โวลท์ 1 เฟส 2 สาย จะจัดเข้าประเภทที่ 1.1.2
```

The schedule's text says the 1.1.2 block is for use over 150 units/month, and the notes separately specify meter and three-consecutive-month transitions. It does **not** say that 966 units by itself proves every account fact. The unsupported statement that 966 units is “physically impossible on a 5 A meter” has been removed.

TOU is not selected by a total-unit number alone. The same page identifies it as an optional rate and requires the applicable meter/choice facts; a TOU calculation additionally needs the Peak/Off-Peak split. No TOU bill is calculated here.

### Bill composition and effective date (PEA tariff PDF, printed pages 6, 8, and 12)

Exact text from the inspected pages:

> `ค่าไฟฟ้าที่เรียกเก็บในแต่ละเดือน ประกอบด้วย ค่าไฟฟ้าตามอัตราข้างต้น ค่าไฟฟ้า ตามสูตรการปรับอัตราค่าไฟฟ้าโดยอัตโนมัติ (Ft) และภาษีมูลค่าเพิ่ม`
>
> `อัตราค่าไฟฟ้าข้างต้น ยังไม่รวมภาษีมูลค่าเพิ่ม`
>
> `อัตราค่าไฟฟ้าข้างต้น เริ่มใช้ตั้งแต่ ค่าไฟฟ้าประจำเดือน กันยายน 2569 เป็นต้นไป`

These are the PEA document's statements. They establish composition and exclusion of VAT, not the applicable VAT percentage or a rounding algorithm.

### Ft (PEA Ft PDF, pages 1–2)

Exact text from page 1:

> `ประจำเดือนกันยายน – ธันวาคม 2569`
>
> `ตามมติคณะกรรมการกำกับกิจการพลังงาน เมื่อวันที่ 22 กรกฎาคม 2569`
>
> `ค่า Ft หน่วยละ 0.1623 บาท หรือ 16.23 สตางค์ (ยังไม่รวมภาษีมูลค่าเพิ่ม)`

Page 2 states that the ERC-approved Ft collected on bills for September–December 2569 is 16.23 satang/unit, excluding VAT. The complete available text-layer extraction is preserved in `/tmp/pea-tariff-2569/ft-pdfkit-full-text.txt`.

## VAT evidence and date boundary

The Revenue Department's official English VAT page, `https://www.rd.go.th/english/6043.html`, says under “4.1 General Rate”: **“Currently, the rate is 7 percent.”** The page is dated “Last updated: 23.11.2020,” so it is useful primary context but not a date-specific Sep–Dec 2569 extension.

The Revenue Department hosts the official Royal Gazette copy of Royal Decree (No. 799), `https://www.rd.go.th/fileadmin/user_upload/kormor/newlaw/dc799.pdf`. Its rendered page 2 states exactly:

> `มาตรา ๔ ให้ลดอัตราภาษีมูลค่าเพิ่มตามมาตรา ๘๐ แห่งประมวลรัษฎากร และคงจัดเก็บในอัตราร้อยละหกจุดสาม สำหรับการขายสินค้า การให้บริการ หรือการนำเข้าทุกกรณี ซึ่งความรับผิดในการเสียภาษีมูลค่าเพิ่มเกิดขึ้นตั้งแต่วันที่ ๑ ตุลาคม พ.ศ. ๒๕๖๘ ถึงวันที่ ๓๐ กันยายน พ.ศ. ๒๕๖๙`

The exact legal text is retained with provenance in `/tmp/pea-tariff-2569/provenance-page-completeness.md` and the complete source PDF is `/tmp/pea-tariff-2569/rd-dc799.pdf`. Accordingly:

- **September 2569:** the dated legal period reaches through 30 September 2569. For September only, the decree establishes national VAT at 6.3%; with the 0.7% local tax component, the customer-facing combined rate is 7%. PEA's calculator corroborates the combined 7% formula. October–December remain unresolved.
- **October–December 2569:** the cited decree no longer covers VAT liabilities after 30 September 2569. No later official extension was verified in this evidence set. Do not project 7% (or any other rate) into those months without a later Revenue Department / Royal Gazette source.

## Conditional 966-unit arithmetic example

This is **not a verified eligibility result**. It is a conditional example: assume (a) the account is confirmed as PEA Type 1 normal rate 1.1.2, (b) the month is within the PEA tariff/Ft periods above, (c) 966 metered units are billed under the block schedule, and (d) for the **September-only illustrative total**, a 7% VAT calculation assumption is approved.

The pre-VAT arithmetic is independently derived as follows:

| Component | Computation | Baht |
| --- | --- | ---: |
| First 200 units | 200 × 3.0000 | 600.0000 |
| Units 201–400 | 200 × 4.1584 | 831.6800 |
| Units 401–966 | 566 × 4.3583 | 2,466.7978 |
| Service charge | 24.62 | 24.6200 |
| Ft | 966 × 0.1623 | 156.7818 |
| **Subtotal before VAT** | sum | **4,079.8796** |

For a September illustration only, `4,079.8796 × 1.07 = 4,365.471172`, displayed as **4,365.47 baht under an explicit two-decimal estimate policy**. That display policy is not an official invoice-rounding rule. No whole-baht result and no “≤1 baht” error claim is made. October–December totals are blocked pending a time-valid VAT source and the account's confirmed category/meter facts.

## Primary-source retrieval and integrity record

1. **PEA tariff page:** `https://www.pea.co.th/our-services/tariff` (official listing identifies the 2569 schedule as effective from the September 2569 electricity month).
2. **PEA tariff PDF:** `https://www.pea.co.th/sites/default/files/users/user34/attachments/Electricity_Tariff_SEP_2026_3.pdf`; PDF 1.4, 12 pages, 2,002,117 bytes; SHA-256 `f903f76b37b836ad35e896784f568cc2f13dea599e82c3a4ed5a548af7f20d0b`.
3. **PEA Ft listing:** `https://www.pea.co.th/our-services/tariff/ft`.
4. **PEA Ft PDF:** `https://www.pea.co.th/sites/default/files/ft/2026/Ft%20surcharge%20SEP-DEC%202026_Final.pdf`; PDF 1.4, 2 pages, 167,445 bytes; SHA-256 `3b77cd50cdabae135fd1446c7ffe7b0a7ef9e2d47fa1ff2924544d21c0940e63`.
5. **Revenue Department VAT page:** `https://www.rd.go.th/english/6043.html` (official general-rate context; last updated 23.11.2020).
6. **Revenue Department-hosted Royal Gazette Decree 799:** `https://www.rd.go.th/fileadmin/user_upload/kormor/newlaw/dc799.pdf`; 3 pages; SHA-256 `796b9aff527081720587dcf5b378833eb09bac731c3cc941fea382ce18302ba3`.

A fresh HTTPS download of each PEA PDF on 2026-09-07 returned HTTP 200 and was byte-identical to the local copy. The tariff response reported `content-length: 2002117`, `last-modified: Sat, 22 Aug 2026 11:24:46 GMT`, and ETag `"1e8cc5-659a1001d9011"`; the Ft response reported `content-length: 167445`, `last-modified: Thu, 13 Aug 2026 04:08:38 GMT`, and ETag `"28e15-658e5dbcf1b85"`.

## Exact blockers before runtime use

1. Confirm the customer's PEA purpose/type, one-meter arrangement, meter amperage/voltage, account history, and normal-vs-TOU selection. Do not infer 1.1.2 solely from 966 units.
2. Confirm a time-valid VAT source for October–December 2569. The cited binding Revenue Department/Royal Gazette period ends 30 September 2569, and its exact wording is 6.3, while the general RD web page says 7% without a 2569 date bound.
3. Obtain the official PEA invoice-rounding rule, or keep any two-decimal result explicitly as an estimate policy rather than an invoice claim.
