"""การตั้งค่าแอปพลิเคชัน"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _comma_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# ชื่อฟิลด์ที่ห้ามแสดงผ่าน repr/str/logging โดยเด็ดขาด
_SECRET_FIELD_NAMES: frozenset[str] = frozenset({"gemini_api_key"})


@dataclass(frozen=True)
class Settings:
    """การตั้งค่า runtime แบบคงที่ซึ่งโหลดจาก environment"""

    app_env: str = "development"
    log_level: str = "info"
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _comma_origins(
            "http://localhost:3000,http://127.0.0.1:3000"
        )
    )
    llm_adapter_name: str = "demo"
    knowledge_backend_name: str = "full_document"
    gemini_api_key: str | None = None
    knowledge_source_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "knowledge"
        / "source"
    )
    gemini_long_context_model: str = "gemini-3.6-flash"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        env = environ or os.environ

        def _get(key: str) -> str | None:
            value = env.get(key)
            return value if value is not None and value.strip() != "" else None

        return cls(
            app_env=env.get("APP_ENV", "development").lower(),
            log_level=env.get("LOG_LEVEL", "info").lower(),
            cors_origins=_comma_origins(
                env.get(
                    "CORS_ORIGINS",
                    "http://localhost:3000,http://localhost:5173,"
                    "http://127.0.0.1:3000,http://127.0.0.1:5173",
                )
            ),
            llm_adapter_name=env.get("LLM_ADAPTER_NAME", "demo").lower(),
            knowledge_backend_name=env.get(
                "KNOWLEDGE_BACKEND_NAME", "full_document"
            ).lower(),
            gemini_api_key=_get("GEMINI_API_KEY"),
            knowledge_source_root=Path(
                env.get(
                    "KNOWLEDGE_SOURCE_ROOT",
                    str(Path(__file__).resolve().parents[2] / "knowledge" / "source"),
                )
            ),
            gemini_long_context_model=env.get(
                "GEMINI_LONG_CONTEXT_MODEL", "gemini-3.6-flash"
            ),
        )

    def __repr__(self) -> str:
        # แทนที่ __repr__ ของ dataclass โดยตั้งใจ เพื่อไม่ให้ข้อมูลลับถูกเปิดเผย
        fields = []
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name in _SECRET_FIELD_NAMES:
                value = "[REDACTED]" if value is not None else None
            fields.append(f"{name}={value!r}")
        return f"{self.__class__.__qualname__}({', '.join(fields)})"

    def __str__(self) -> str:
        return self.__repr__()


def _load_dotenv_if_present(path: Path) -> dict[str, str]:
    """แยกวิเคราะห์ไฟล์ dotenv โดยข้ามคอมเมนต์และบรรทัดว่าง"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_settings(dotenv_path: Path | None = None) -> Settings:
    """โหลดการตั้งค่าจาก .env แล้วรวมกับ environment จริงของ process

    ตัวแปร environment จริงมีลำดับความสำคัญเหนือค่าจาก .env เพื่อให้การตั้งค่า
    ที่ใช้ระหว่าง deploy/runtime มีผลเหนือกว่าค่าตัวอย่างที่ commit ไว้เสมอ
    """
    path = dotenv_path or Path(".env")
    dotenv = _load_dotenv_if_present(path)
    # รวมค่าโดยให้ environment จริงของ process มีผลเหนือกว่ารายการใน .env
    merged = {**dotenv, **os.environ}
    return Settings.from_env(merged)
