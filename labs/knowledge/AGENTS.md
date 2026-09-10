# เป้าหมาย
ทำเฉพาะ Knowledge ใน docs/PRD.md และรายงานผลจริงทุกครั้ง
- ไม่แก้หรือย้าย wsc2026 ทั้งก้อน
- Core/เสียงต้องไม่ import ปลั๊กอินรายตัว; bootstrap โหลดจาก config
- Schema ธุรกิจอยู่ในปลั๊กอินและใช้สร้าง catalogue กับตรวจ input/output จากต้นทางเดียวกัน
- พัก OMS/VOC/งานเขียน/tracking/notifications/เสียง จนผู้ใช้สั่งใหม่
- ห้ามสร้าง mock integration เพื่ออ้างว่าเชื่อมระบบจริงได้
- ทดสอบตามความเสี่ยง ไม่บังคับ full TDD และไม่เพิ่ม coverage เพียงเพื่อเพิ่มตัวเลข
- ชุดทดสอบใช้ fake transports เท่านั้น ห้ามยิง provider แบบเสียเงินโดยอัตโนมัติ
- ห้ามอ้างว่า live integration ผ่านจาก mocked tests
- ห้ามเพิ่ม P1/P2 เองหลัง P0 จบ; รายงาน dependency ที่ยังขาด
