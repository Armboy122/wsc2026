---
rules:
  - action: get_outage_by_ca
    phrases:
      - เช็คไฟดับ
      - ตรวจสอบไฟดับ
      - ดูสถานะไฟดับ
  - action: prepare_outage_with_ca
    phrases:
      - แจ้งไฟดับพร้อมเลขผู้ใช้ไฟ
      - แจ้งเหตุไฟดับมี CA
  - action: prepare_anonymous_outage
    phrases:
      - แจ้งไฟดับ
      - ไฟฟ้าดับ
      - ไม่มีไฟใช้
      - ไฟตกทั้งบ้าน
      - ไฟดับที่บ้านเลขผู้ใช้ไฟ
---

# OMS routing aliases

ใช้เป็นคำใบ้ให้ Main Agent เลือก action เริ่มต้นของ OMS เท่านั้น
ทุก action ยังผ่าน schema validation และ flow การยืนยันเดิม
