"""ช่องทางขนส่ง LINE Messaging API บน Main Agent ตัวเดิม

โมดูลนี้เป็นสะพานบาง ๆ ระหว่าง webhook ของ LINE กับ Main Agent โดยไม่มี
นโยบายธุรกิจใด ๆ อยู่ที่นี่ ยึดข้อกำหนดเดียวกับ voice bridge:

- เรียก Main Agent ได้เฉพาะ ``handle_chat`` / ``confirm_pending_action`` /
  ``reject_pending_action``
- ไม่รับ pending action id จากผู้ใช้ ใช้เฉพาะ id ที่ผูกกับ LINE user ปัจจุบัน
- การยืนยัน/ปฏิเสธทำผ่านปุ่ม postback เท่านั้น ไม่ใช่การตีความข้อความแชต
"""
