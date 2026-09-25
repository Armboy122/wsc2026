# PEA Knowledge Voice Agent — หน้าเว็บเสียง

หน้าเว็บแบบ static ไม่ใช้เฟรมเวิร์ก ไม่มี build step เสิร์ฟโดย FastAPI ที่ `/`

| ไฟล์ | หน้าที่ |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | หน้าหลัก: ปุ่มไมโครโฟน, สถานะเสียง, transcript |
| `phone.html`, `phone.css`, `phone.js` | หน้าจำลองโทรศัพท์ 1129 ที่ใช้โหมดเสียงเดียวกัน |
| `gemini-live-client.js` | client ของ `WS /ws/live` (ส่ง/รับเสียงและ event) |
| `media-handler.js` | จับเสียงไมโครโฟนและเล่นเสียงตอบ |
| `pcm-processor.js` | AudioWorklet: downsample เป็น PCM16 16 kHz |

หน้าเว็บคุยกับเซิร์ฟเวอร์ผ่าน `WS /ws/live` เท่านั้น (สัญญาอยู่ใน [../CONTRACTS.md](../CONTRACTS.md))
ไม่มีแชตแบบพิมพ์, REST API, pending action, trace, reset หรือ geolocation

## โหมดเสียง

- **จับเสียง**: `getUserMedia` (echoCancellation/noiseSuppression/autoGainControl พร้อม fallback
  `{ audio: true }`) → AudioWorklet → PCM16 little-endian 16 kHz → ส่งเป็น binary
- **เล่นเสียง**: PCM16 24 kHz → scheduling แบบต่อเนื่องด้วย `nextStartTime`; ล้างคิวทันทีเมื่อได้
  `audio.interrupted` (ผู้ใช้พูดแทรก)
- **Transcript**: `transcript.user` / `transcript.assistant`; ข้อความชั่วคราวต่อท้าย และเมื่อ
  `final`/`replace` เป็น true จะแทนที่ด้วยข้อความสะสมทั้งหมด
- **สถานะ**: `session.ready` → กำลังฟัง, `state: thinking` → กำลังคิด (โมเดลเรียกเครื่องมือ Knowledge), `turn.complete` → จบรอบ,
  `error` → แสดงข้อความภาษาไทยที่ปลอดภัย
- **ไม่มี API key ในเบราว์เซอร์**: การเชื่อมต่อ Gemini Live ทั้งหมดเกิดบนเซิร์ฟเวอร์

## คำแนะนำและการแก้ปัญหา

- ใช้หูฟังเพื่อลดเสียงสะท้อน; ต้องอนุญาตสิทธิ์ไมโครโฟน; ใช้ localhost หรือ https;
  ใช้ Chrome/Edge ล่าสุด (AudioWorklet + `getUserMedia`)

| อาการ | วิธีแก้ |
| --- | --- |
| "โหมดเสียงยังไม่ได้ตั้งค่า" | เซิร์ฟเวอร์ไม่มี `GEMINI_API_KEY` — ตั้งใน `.env` แล้ว restart |
| เปิดโหมดเสียงไม่สำเร็จ | อนุญาตไมโครโฟน, ใช้ localhost/https, ตรวจการรองรับ AudioWorklet |
| เสียงตอบถูกตัด | การพูดแทรกจะตัดเสียงที่เหลือทันที (ตั้งใจ) |

## การเข้าถึง

ลิงก์ข้ามไปยังปุ่มไมโครโฟน, บทสนทนา `role="log"`, ประกาศสถานะผ่าน `aria-live`, วงแหวนโฟกัส
ที่มองเห็นได้ และรองรับ `prefers-reduced-motion`
