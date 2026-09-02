# ต้นทุน Gemini และเทียบ Man-hour 1129 PEA Contact Center

> เอกสารสรุปฉบับเดียวสำหรับทำสไลด์  
> อัปเดต: 2 กันยายน 2026  
> ขอบเขต: PEA One Agent ตาม `tests/` และ `evaluation/datasets/` + สถิติ aggregate จากรายงาน 1129 เดือนพฤษภาคม 2568

---

## 1. Executive summary

| หัวข้อ | ตัวเลขสำหรับสไลด์ |
|---|---:|
| Gemini text: Knowledge 1 turn | **~฿0.20** |
| Gemini text: OMS/adversarial 1 turn | **~฿0.09** |
| Gemini Live: Voice อย่างเดียว 1 turn | **฿0.15–0.38** |
| Voice + Chat: session ไม่เกิน 5 turns, OMS | **฿1.16–2.33** |
| Voice + Chat: session ไม่เกิน 5 turns, Knowledge | **฿1.72–3.91** |
| Text/LINE: session ไม่เกิน 5 turns, Knowledge | **~฿0.99** โดยทั่วไป; เพดาน ~฿2.01 |
| Evaluator 70 เคส | **~฿12** |
| 1129 voice (219,564 answered calls/เดือน), หาก AI รับทุกสายและทุกสายเต็ม 5 turns | **~฿0.25–0.86 ล้าน/เดือน** |
| 1129 manual outsourced base case (แบบจำลอง, ไม่ใช่มูลค่าสัญญาจริง) | **~฿2.38 ล้าน/เดือน** |

> **สรุป:** สำหรับ workload ใน test ค่า Gemini ต่อ session ไม่สูง; ต้นทุนจะขยายตามจำนวนสาย Voice และเวลาพูดตอบเป็นหลัก

---

## 2. ราคา Gemini ที่ใช้คำนวณ

### โมเดลในระบบ

| บทบาท | โมเดล |
|---|---|
| Main Agent / planner | `gemini-3.5-flash-lite` |
| Knowledge router + answer | `gemini-3.5-flash-lite` |
| Voice Mode | `gemini-3.1-flash-live-preview` |

### ราคา Paid Standard tier

| โมเดล / modality | Input | Output |
|---|---:|---:|
| Gemini 3.5 Flash-Lite (text) | $0.30 / 1M tokens | $2.50 / 1M tokens |
| Gemini 3.1 Flash Live (text) | $0.75 / 1M tokens | $4.50 / 1M tokens |
| Gemini 3.1 Flash Live (audio) | $3.00 / 1M tokens (~$0.005/นาที) | $12.00 / 1M tokens (~$0.018/นาที) |

อัตราแปลงเพื่อคำนวณเอกสารนี้: **US$1 = ฿33**

แหล่งอ้างอิง: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

---

## 3. Token ที่นับจาก payload จริง

นับด้วย Gemini `countTokens` จาก payload ของระบบ ไม่ใช่การประเมินจากจำนวนตัวอักษร

| ส่วนประกอบ | Token |
|---|---:|
| Main system instruction + tool catalogue | **3,053** |
| Document Router catalog metadata 38 เอกสาร | **3,461** |
| ข้อความ DOCX ต่อไฟล์: min / p50 / p90 / max | 236 / **924** / 1,656 / 2,048 |
| เอกสารทั้งคลัง 38 ไฟล์ | 34,915 |

ข้อสรุป: full-document architecture ของ MVP ยังมีขนาดเล็กในเชิง token; ไม่ใช่ตัวที่ทำให้ต้นทุนพุ่งโดยลำพัง

---

## 4. ต้นทุน Gemini ต่อ 1 turn

**นิยาม:** 1 turn = ผู้ใช้ส่งข้อความหรือพูด 1 ครั้ง และระบบตอบ 1 ครั้ง

| สถานการณ์ | Input tokens | Output tokens | USD | บาท |
|---|---:|---:|---:|---:|
| OMS / adversarial: planner 2 steps | 6,676 | 240 | $0.00260 | **฿0.086** |
| Knowledge: router + answer, เลือก 3 เอกสาร | 13,399 | 780 | $0.00597 | **฿0.197** |
| Multi-tool: Knowledge + OMS | 17,412 | 900 | $0.00747 | **฿0.247** |
| Knowledge worst case: ค้น 2 รอบ + เอกสาร p90 | 28,527 | 1,440 | $0.01216 | **฿0.401** |

`confirm → submit` ไม่เรียก LLM เพิ่ม เพราะเป็น typed tool call ภายใน

### Voice Live ต่อ 1 turn

| รูปแบบเสียง | สมมติฐาน | USD | บาท |
|---|---|---:|---:|
| Turn สั้น | ผู้ใช้พูด 10 วินาที / AI ตอบ 12 วินาที | $0.00443 | **฿0.146** |
| Turn ยาว | ผู้ใช้พูด 30 วินาที / AI ตอบ 30 วินาที | $0.01150 | **฿0.380** |

---

## 5. งบต่อ 1 session (ไม่เกิน 5 turns)

ใช้ 3 turns เป็น baseline สำหรับ MVP และกำหนด **5 turns เป็นเพดาน**

- 1–2 turns: ถามข้อมูลหรือเช็กสถานะแล้วจบ
- 3 turns: แจ้งเหตุแบบไม่มี CA (เปิดเรื่อง → ให้รายละเอียด → เตรียมรายการ)
- 4–5 turns: ต้องถามข้อมูลเพิ่มหรือมีคำถามต่อเนื่อง

| Session ≤5 turns | วิธีคิด | ต้นทุนรวม |
|---|---|---:|
| Text/LINE: OMS เป็นหลัก | ฿0.086 × 5 | **~฿0.43** |
| Text/LINE: Knowledge โดยทั่วไป | ฿0.197 × 5 | **~฿0.99** |
| Text/LINE: Knowledge worst case | ฿0.401 × 5 | **~฿2.01** |
| Voice + Chat: OMS | (฿0.146–0.380 + ฿0.086) × 5 | **฿1.16–2.33** |
| Voice + Chat: Knowledge | (฿0.146–0.380 + ฿0.197–0.401) × 5 | **฿1.72–3.91** |

### คำแนะนำสำหรับสไลด์

| ช่องทาง | งบแนะนำต่อ session ≤5 turns |
|---|---:|
| LINE / Text | **฿2** |
| Voice + Chat | **฿5** |

LINE Messaging API, ระบบโทรศัพท์ และ contact-center platform เป็นค่าแยก ไม่รวมในค่า Gemini

---

## 6. ค่า evaluator และ unit tests

Evaluator ใช้ 70 เคส: Knowledge 40, OMS 10, Multi-tool 10, Adversarial 10

| รายการ | ค่าใช้จ่าย Gemini |
|---|---:|
| `./scripts/evaluate` ทั้งชุด | **~$0.37 / ~฿12** |
| `.venv/bin/python -m pytest -q` | **฿0** |

`pytest` ใช้ fake/mocked provider, mock OMS transport และ fake Live session จึงไม่ยิง Google API จริง

---

## 7. เทียบกับ volume ของ 1129 PEA Contact Center

รายงาน 1129 เดือนพฤษภาคม 2568 ระบุสถิติ aggregate:

| ช่องทาง | ปริมาณต่อเดือน | ใช้ทำอะไรในการคำนวณ |
|---|---:|---|
| Voice: Call Offer | 244,737 สาย | ปริมาณสายรวม รวมสายที่ไม่รับ |
| Voice: Call Answer | **219,564 สาย** | ฐานการคำนวณ AI session ที่สนทนาเกิดขึ้น |
| Voice: Abandon | 25,173 สาย | ไม่คิดเป็น AI session ที่สนทนาจบ |
| Non-Voice รวม | 30,290 ครั้ง | รวม Chat, Email, Social, Leave Voice |
| Chat | **14,848 ครั้ง** | ตัวเทียบที่ใกล้ที่สุดกับ text-chat session |

> รายงานไม่บอก AHT, จำนวน turns, average call duration, จำนวน FTE หรือมูลค่าสัญญา จึงไม่อาจใช้เป็นใบเสนอราคาหรือ forecast ที่ยืนยันได้

### หาก AI Voice รับทุก answered call และทุก session เต็มเพดาน 5 turns

| Scenario | ต้นทุนต่อ session | 219,564 sessions / เดือน |
|---|---:|---:|
| OMS เป็นหลัก | ฿1.16–2.33 | **฿254,694–511,584** |
| Knowledge เป็นหลัก | ฿1.72–3.91 | **฿377,650–858,495** |

นี่คือ **เพดาน cost ตาม assumption** ไม่ใช่ค่าเฉลี่ยจริง: ในความเป็นจริงหลายสายอาจจบ 1–3 turns และบาง intent อยู่นอก scope ของ MVP

---

## 8. Man-hour และราคา manual contact center

### สูตร

```text
Man-hours/เดือน = จำนวนสายที่รับสำเร็จ × AHT (นาที) ÷ 60
FTE = Man-hours ÷ 173 productive hours/FTE/เดือน
```

สำหรับ 219,564 answered calls/เดือน:

| AHT สมมติ | Man-hours / เดือน | FTE โดยประมาณ |
|---:|---:|---:|
| 3 นาที/สาย | 10,978 | 63.5 |
| 5 นาที/สาย | 18,297 | 105.8 |
| 7 นาที/สาย | 25,616 | 148.1 |

### Base case ที่ใช้เทียบ

สมมติเงินเดือนเจ้าหน้าที่ **฿15,000/เดือน**:

```text
฿15,000 ÷ 173 productive hours ≈ ฿87/man-hour
เลือก ฿100/man-hour เพื่อเผื่อสวัสดิการและภาระนายจ้าง
เลือก ฿130/man-hour เป็น Fully Outsource all-in ขั้นต่ำ
```

| รายการ Base case: AHT 5 นาที/สาย | ราคา |
|---|---:|
| Man-hours | 18,297 ชั่วโมง/เดือน |
| Agent direct: ฿100/man-hour | ฿1,829,700 / เดือน |
| **Fully Outsource: ฿130/man-hour** | **฿2,378,610 / เดือน** |
| Fully Outsource ต่อ answered call | **฿10.83 / สาย** |
| Fully Outsource ต่อปี | **฿28.54 ล้าน** |
| Fully Outsource ต่อ 60 เดือน | **฿142.72 ล้าน** |

> นี่เป็น **แบบจำลอง man-hour ไม่ใช่มูลค่าสัญญา 1129 จริง** เพราะเอกสารต้นทางไม่มีราคากลาง/ราคาชนะ/AHT/FTE

---

## 9. ตารางเปรียบเทียบสำหรับสไลด์

| รายการ | AI Voice + Chat | Manual Fully Outsource (Base case) |
|---|---:|---:|
| ขอบเขต volume | 219,564 answered calls/เดือน | 219,564 answered calls/เดือน |
| สมมติฐาน | ≤5 turns/session | AHT 5 นาที/สาย, ฿130/man-hour |
| ต้นทุน / เดือน | **฿0.25–0.86 ล้าน** | **฿2.38 ล้าน** |
| ต้นทุน / ปี | **฿3.06–10.30 ล้าน** | **฿28.54 ล้าน** |
| ต้นทุน / contact | ฿1.16–3.91 | ฿10.83 |

### ข้อสรุปเชิงธุรกิจ

- เฉพาะค่า Gemini inference มีโอกาสต่ำกว่าแบบจำลอง manual outsourcing
- แต่ **ยังห้ามสรุปว่า AI ถูกกว่าสัญญา 1129 จริง** จนกว่าจะได้มูลค่าสัญญา, AHT, FTE, SLA และ scope จริง
- MVP ปัจจุบันรองรับ Knowledge และ OMS เท่านั้น จึงยังไม่ครอบคลุมทุก use case ของ 1129 เช่นปัญหา PEA Smart Plus, การชำระเงิน, OTP หรือการประสานงานเฉพาะทาง
- ต้นทุนจริงต้องบวก integration, platform/telephony, monitoring, human escalation, QA, security/PDPA และ knowledge governance

---

## 10. วิธีวัดค่าใช้จ่ายจริงก่อน production

1. บันทึก `usageMetadata` ทุก Gemini call: input, output, thought และ cached tokens
2. เก็บ average turns/session และความยาวเสียงเข้า/ออกจาก Gemini Live
3. แยก intent จริง: OMS, Knowledge, FAQ, escalation, unsupported
4. เทียบกับ AHT, FTE, SLA และต้นทุนสัญญา 1129 ที่ยืนยันได้

### แหล่งข้อมูล

- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Understand and count tokens](https://ai.google.dev/gemini-api/docs/tokens)
- [Counting tokens API](https://ai.google.dev/api/tokens)
- โค้ดที่ตรวจ: `app/llm/gemini.py`, `app/backends/full_document_knowledge.py`, `app/live/gemini_live.py`, `scripts/evaluate`
