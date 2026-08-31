"""การตั้งค่าแอปพลิเคชัน"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _comma_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# ชื่อฟิลด์ที่ห้ามแสดงผ่าน repr/str/logging โดยเด็ดขาด
_SECRET_FIELD_NAMES: frozenset[str] = frozenset({"gemini_api_key", "maxplus_api_key"})


@dataclass(frozen=True, slots=True)
class LLMRuntimeSettings:
    """การตั้งค่า provider-neutral สำหรับ LLM หนึ่งบทบาท"""

    provider: str = "demo"
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None


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
    main_llm: LLMRuntimeSettings = field(default_factory=LLMRuntimeSettings)
    knowledge_llm: LLMRuntimeSettings = field(
        default_factory=lambda: LLMRuntimeSettings(
            provider="gemini", model="gemini-3.5-flash-lite"
        )
    )
    judge_llm: LLMRuntimeSettings = field(default_factory=LLMRuntimeSettings)
    knowledge_backend_name: str = "full_document"
    knowledge_provider: str = "gemini"
    gemini_api_key: str | None = None
    maxplus_api_key: str | None = None
    maxplus_base_url: str = "https://api.maxplus-ai.cc/v1"
    maxplus_model: str = "deepseek-v4-flash-0731"
    knowledge_source_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "knowledge"
        / "source"
    )
    gemini_long_context_model: str = "gemini-3.5-flash-lite"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        env = environ or os.environ

        def _get(key: str) -> str | None:
            value = env.get(key)
            return value if value is not None and value.strip() != "" else None

        gemini_api_key = _get("GEMINI_API_KEY")
        maxplus_api_key = _get("MAXPLUS_API_KEY")
        maxplus_base_url = env.get(
            "MAXPLUS_BASE_URL", "https://api.maxplus-ai.cc/v1"
        ).rstrip("/")
        maxplus_model = env.get("MAXPLUS_MODEL", "deepseek-v4-flash-0731")
        gemini_long_context_model = env.get(
            "GEMINI_LONG_CONTEXT_MODEL", "gemini-3.5-flash-lite"
        )

        def _llm_settings(
            prefix: str,
            *,
            default_provider: str = "demo",
            legacy_provider_key: str | None = None,
            gemini_model: str = "gemini-3.5-flash-lite",
        ) -> LLMRuntimeSettings:
            provider = (
                _get(f"{prefix}_LLM_PROVIDER")
                or (_get(legacy_provider_key) if legacy_provider_key else None)
                or default_provider
            ).lower()
            if provider == "gemini":
                default_model = gemini_model
                default_key = gemini_api_key
                default_base_url = None
            elif provider == "maxplus_openai":
                default_model = maxplus_model
                default_key = maxplus_api_key
                default_base_url = maxplus_base_url
            else:
                default_model = None
                default_key = None
                default_base_url = None
            return LLMRuntimeSettings(
                provider=provider,
                model=_get(f"{prefix}_LLM_MODEL") or default_model,
                api_key=_get(f"{prefix}_LLM_API_KEY") or default_key,
                base_url=(
                    (_get(f"{prefix}_LLM_BASE_URL") or default_base_url or "").rstrip("/")
                    or None
                ),
            )

        main_llm = _llm_settings("MAIN", legacy_provider_key="LLM_ADAPTER_NAME")
        knowledge_llm = _llm_settings(
            "KNOWLEDGE",
            default_provider="gemini",
            legacy_provider_key="KNOWLEDGE_PROVIDER",
            gemini_model=gemini_long_context_model,
        )
        judge_llm = _llm_settings("JUDGE")

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
            main_llm=main_llm,
            knowledge_llm=knowledge_llm,
            judge_llm=judge_llm,
            knowledge_backend_name=env.get(
                "KNOWLEDGE_BACKEND_NAME", "full_document"
            ).lower(),
            knowledge_provider=knowledge_llm.provider,
            gemini_api_key=gemini_api_key,
            maxplus_api_key=maxplus_api_key,
            maxplus_base_url=maxplus_base_url,
            maxplus_model=maxplus_model,
            knowledge_source_root=Path(
                env.get(
                    "KNOWLEDGE_SOURCE_ROOT",
                    str(Path(__file__).resolve().parents[2] / "knowledge" / "source"),
                )
            ),
            gemini_long_context_model=gemini_long_context_model,
        )

    @property
    def llm_adapter_name(self) -> str:
        """ชื่อเดิมที่คงไว้เพื่อให้ deployment และ caller เก่ายังทำงานได้"""
        return self.main_llm.provider

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
