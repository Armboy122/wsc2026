# Plugin routing aliases

ปลั๊กอินที่เปิดใช้งานสามารถมี `aliases.md` ได้หนึ่งไฟล์ในไดเรกทอรีของตัวเอง
เช่น `app/plugins/oms/aliases.md` ไฟล์นี้ช่วย Main Agent จับคู่คำพูดผู้ใช้กับ
**action เริ่มต้น** ของปลั๊กอิน โดย loader จะรวมกฎที่ตรวจสอบแล้วเข้าไปใน
คำอธิบาย tool ที่ LLM เห็นตอนเริ่มระบบ

```md
---
rules:
  - action: action_name_exposed_to_llm
    phrases:
      - คำที่ผู้ใช้อาจพิมพ์
      - อีกคำหนึ่ง
---

# คำอธิบายสำหรับผู้ดูแล
```

กฎ:

- `action` ต้องเป็น action ที่ manifest เปิด `exposure: llm` เท่านั้น
- ห้ามอ้าง action `submit_*` หรือ action internal
- phrase ห้ามว่างหรือซ้ำภายในไฟล์เดียวกัน
- ไฟล์ผิดรูปแบบทำให้ plugin loader ปฏิเสธการเริ่มระบบแบบ fail closed
- alias เป็นเพียงคำใบ้การ route; input ยังผ่าน typed schema และ write flow
  ยังต้องเป็น `prepare → explicit confirm endpoint → submit`
- plugin สามารถเรียก API หลายครั้งภายใน implementation ของตนเองได้ตามปกติ

หลังเพิ่มหรือแก้ `aliases.md` ให้ restart process เพื่อสร้าง LLM catalogue ใหม่
