"""สร้าง secret ของ lab ใน .env ท้องถิ่น ไม่พิมพ์ค่า secret"""
import json
import os
import secrets
from pathlib import Path
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
target = root / ".env"
token = secrets.token_urlsafe(32)
values = {
    "STATE_KEY": Fernet.generate_key().decode(),
    "API_TOKENS_JSON": json.dumps({token: {"id": "lab-user", "scopes": ["knowledge:read"]}}),
    "ANSWER_PROVIDER": "extractive",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "",
    "KNOWLEDGE_ROOT": "../../knowledge",
    "DATABASE_PATH": "data/sessions.sqlite",
}
with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
    for key, value in values.items():
        f.write(f"{key}='{value}'\n")
print("สร้าง .env แล้ว ใช้โหมดค้นข้อความได้ทันที; หากใช้ Gemini ให้กรอก key/model และเปลี่ยน ANSWER_PROVIDER")
