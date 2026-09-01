"""การตรวจสอบลายเซ็น webhook ของ LINE Messaging API

LINE ส่ง header ``X-Line-Signature`` เป็น base64 ของ HMAC-SHA256 ที่คำนวณ
จาก channel secret กับ raw body ทั้งหมด การตรวจสอบนี้เป็นขอบเขตความปลอดภัย
ของ webhook: ถ้าไม่ผ่านต้องปฏิเสธทันทีโดยไม่ประมวลผลใด ๆ (fail closed)
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def verify_webhook_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """คืน True เมื่อลายเซ็นตรงกับ HMAC-SHA256 ของ body ตาม channel secret

    ใช้ ``hmac.compare_digest`` เพื่อกัน timing attack และคืน False ทันที
    เมื่อข้อมูลขาดหายแทนการ raise เพื่อให้ caller ปฏิเสธแบบ fail closed
    """
    if not channel_secret or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, signature)
