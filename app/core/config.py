"""การตั้งค่าแอปพลิเคชัน"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


def _comma_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# ชื่อฟิลด์ที่ห้ามแสดงผ่าน repr/str/logging โดยเด็ดขาด
_SECRET_FIELD_NAMES: frozenset[str] = frozenset({
    "gemini_api_key",
    "oms_api_key",
    "voc_api_key",
    "line_channel_secret",
    "line_channel_access_token",
})
_ALLOWED_EFFORTS = frozenset({"low", "medium", "high"})


@dataclass(frozen=True, slots=True)
class LLMRuntimeSettings:
    """การตั้งค่า provider-neutral สำหรับ LLM หนึ่งบทบาท"""

    provider: str = "demo"
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    thinking: bool = False
    effort: str = "low"


@dataclass(frozen=True)
class Settings:
    """การตั้งค่า runtime แบบคงที่ซึ่งโหลดจาก settings + environment"""

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
    knowledge_source_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "knowledge"
        / "source"
    )
    gemini_long_context_model: str = "gemini-3.5-flash-lite"
    live_model: str = "gemini-3.1-flash-live-preview"
    live_voice: str = "Puck"
    oms_base_url: str = "http://127.0.0.1:8080/api/v1/oms"
    oms_timeout_seconds: float = 5.0
    oms_api_key: str | None = field(default=None, repr=False)
    voc_base_url: str = "http://127.0.0.1:8080/api/v1/voc"
    voc_timeout_seconds: float = 5.0
    voc_api_key: str | None = field(default=None, repr=False)
    voc_consent_notice_version: str = "VOC-PDPA-DEMO-1.0"
    line_channel_secret: str | None = field(default=None, repr=False)
    line_channel_access_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        llm_settings: Mapping[str, Any] | None = None,
    ) -> Settings:
        env = environ or os.environ
        llm_settings = llm_settings or {}
        profiles = _mapping(llm_settings.get("providers"))
        roles = _mapping(llm_settings.get("roles"))

        def _get(key: str) -> str | None:
            value = env.get(key)
            return value if value is not None and value.strip() != "" else None

        gemini_api_key = _get("GEMINI_API_KEY")
        gemini_long_context_model = env.get(
            "GEMINI_LONG_CONTEXT_MODEL", "gemini-3.5-flash-lite"
        )
        live_model = env.get("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        live_voice = env.get("GEMINI_LIVE_VOICE", "Puck")
        oms_base_url = (_get("OMS_BASE_URL") or "http://127.0.0.1:8080/api/v1/oms").rstrip("/")
        oms_api_key = _get("OMS_API_KEY")
        voc_base_url = (_get("VOC_BASE_URL") or "http://127.0.0.1:8080/api/v1/voc").rstrip("/")
        voc_api_key = _get("VOC_API_KEY")
        voc_consent_notice_version = _get("VOC_CONSENT_NOTICE_VERSION") or "VOC-PDPA-DEMO-1.0"
        try:
            voc_timeout_seconds = float(env.get("VOC_TIMEOUT_SECONDS", "5"))
            if voc_timeout_seconds <= 0:
                raise ValueError
        except (TypeError, ValueError):
            voc_timeout_seconds = 5.0
        try:
            oms_timeout_seconds = float(env.get("OMS_TIMEOUT_SECONDS", "5"))
            if oms_timeout_seconds <= 0:
                raise ValueError
        except (TypeError, ValueError):
            oms_timeout_seconds = 5.0

        def _llm_settings(
            prefix: str,
            role_name: str,
            *,
            default_provider: str = "demo",
            legacy_provider_key: str | None = None,
            gemini_model: str = "gemini-3.5-flash-lite",
        ) -> LLMRuntimeSettings:
            role = _mapping(roles.get(role_name))
            profile_name = (
                _get(f"{prefix}_LLM_PROVIDER")
                or (_get(legacy_provider_key) if legacy_provider_key else None)
                or _string(role.get("provider"))
                or default_provider
            ).lower()
            profile = _mapping(profiles.get(profile_name))
            provider = (_string(profile.get("api")) or profile_name).lower()
            if provider == "gemini":
                fallback_model, fallback_key, fallback_base_url = gemini_model, gemini_api_key, None
            elif provider == "demo":
                fallback_model, fallback_key, fallback_base_url = None, None, None
            else:
                fallback_model, fallback_key, fallback_base_url = None, None, None
            key_env = _string(role.get("api_key_env")) or _string(profile.get("api_key_env"))
            configured_key = _get(key_env) if key_env else fallback_key
            effort = (_get(f"{prefix}_LLM_EFFORT") or _string(role.get("effort")) or "low").lower()
            if effort not in _ALLOWED_EFFORTS:
                raise ValueError(f"{prefix}_LLM_EFFORT ต้องเป็น low, medium หรือ high")
            thinking = _bool(
                _get(f"{prefix}_LLM_THINKING"),
                _bool(role.get("thinking"), False),
                f"{prefix}_LLM_THINKING",
            )
            return LLMRuntimeSettings(
                provider=provider,
                model=(
                    _get(f"{prefix}_LLM_MODEL")
                    or _string(role.get("model"))
                    or fallback_model
                ),
                api_key=_get(f"{prefix}_LLM_API_KEY") or configured_key,
                base_url=(
                    (_get(f"{prefix}_LLM_BASE_URL") or _string(role.get("base_url"))
                     or _string(profile.get("base_url")) or fallback_base_url or "").rstrip("/")
                    or None
                ),
                thinking=thinking,
                effort=effort,
            )

        main_llm = _llm_settings("MAIN", "main", legacy_provider_key="LLM_ADAPTER_NAME")
        knowledge_llm = _llm_settings(
            "KNOWLEDGE",
            "knowledge",
            default_provider="gemini",
            legacy_provider_key="KNOWLEDGE_PROVIDER",
            gemini_model=gemini_long_context_model,
        )
        judge_llm = _llm_settings("JUDGE", "judge")

        line_channel_secret = _get("LINE_CHANNEL_SECRET")
        line_channel_access_token = _get("LINE_CHANNEL_ACCESS_TOKEN")

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
            knowledge_backend_name=env.get("KNOWLEDGE_BACKEND_NAME", "full_document").lower(),
            knowledge_provider=knowledge_llm.provider,
            gemini_api_key=gemini_api_key,
            knowledge_source_root=Path(env.get(
                "KNOWLEDGE_SOURCE_ROOT",
                str(Path(__file__).resolve().parents[2] / "knowledge" / "source"),
            )),
            gemini_long_context_model=gemini_long_context_model,
            live_model=live_model,
            live_voice=live_voice,
            oms_base_url=oms_base_url,
            oms_timeout_seconds=oms_timeout_seconds,
            oms_api_key=oms_api_key,
            voc_base_url=voc_base_url,
            voc_timeout_seconds=voc_timeout_seconds,
            voc_api_key=voc_api_key,
            voc_consent_notice_version=voc_consent_notice_version,
            line_channel_secret=line_channel_secret,
            line_channel_access_token=line_channel_access_token,
        )

    @property
    def llm_adapter_name(self) -> str:
        """ชื่อเดิมที่คงไว้เพื่อให้ deployment และ caller เก่ายังทำงานได้"""
        return self.main_llm.provider

    def __repr__(self) -> str:
        fields = []
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name in _SECRET_FIELD_NAMES:
                value = "[REDACTED]" if value is not None else None
            fields.append(f"{name}={value!r}")
        return f"{self.__class__.__qualname__}({', '.join(fields)})"

    def __str__(self) -> str:
        return self.__repr__()


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return value


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _bool(value: object, default: bool, name: str = "thinking") -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{name} ต้องเป็น true หรือ false")


def _load_dotenv_if_present(path: Path) -> dict[str, str]:
    """แยกวิเคราะห์ไฟล์ dotenv โดยข้ามคอมเมนต์และบรรทัดว่าง"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _load_llm_settings(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise RuntimeError(f"อ่าน LLM settings ไม่สำเร็จ: {path}") from error
    if not isinstance(loaded, Mapping):
        raise RuntimeError(f"LLM settings ต้องเป็น YAML object: {path}")
    return loaded


def load_settings(
    dotenv_path: Path | None = None,
    llm_settings_path: Path | None = None,
) -> Settings:
    """โหลด LLM settings ที่ไม่ลับ แล้วรวม dotenv กับ environment (env ชนะเสมอ)."""
    path = dotenv_path or Path(".env")
    dotenv = _load_dotenv_if_present(path)
    merged = {**dotenv, **os.environ}
    config_path = llm_settings_path or Path(
        merged.get("LLM_SETTINGS_PATH", str(Path(__file__).resolve().parents[2] / "llm-settings.yaml"))
    )
    return Settings.from_env(merged, _load_llm_settings(config_path))
