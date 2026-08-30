"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _comma_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    """Frozen runtime settings loaded from environment."""

    app_env: str = "development"
    log_level: str = "info"
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _comma_origins("http://localhost:3000,http://127.0.0.1:3000"))
    llm_adapter_name: str = "scripted"
    knowledge_backend_name: str = "gemini_file_search"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        env = environ or os.environ
        return cls(
            app_env=env.get("APP_ENV", "development").lower(),
            log_level=env.get("LOG_LEVEL", "info").lower(),
            cors_origins=_comma_origins(env.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173")),
            llm_adapter_name=env.get("LLM_ADAPTER_NAME", "scripted").lower(),
            knowledge_backend_name=env.get("KNOWLEDGE_BACKEND_NAME", "gemini_file_search").lower(),
        )


def _load_dotenv_if_present(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    values: dict[str, str] = {}
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
    """Load settings, optionally from a .env file."""
    path = dotenv_path or Path(".env")
    env = _load_dotenv_if_present(path)
    return Settings.from_env(env)
