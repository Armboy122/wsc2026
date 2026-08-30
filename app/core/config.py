"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _comma_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# Field names that must never be emitted by repr/str/logging.
_SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {"gemini_api_key", "file_search_store", "file_search_model"}
)


@dataclass(frozen=True)
class Settings:
    """Frozen runtime settings loaded from environment."""

    app_env: str = "development"
    log_level: str = "info"
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _comma_origins(
            "http://localhost:3000,http://127.0.0.1:3000"
        )
    )
    llm_adapter_name: str = "demo"
    knowledge_backend_name: str = "gemini_file_search"
    gemini_api_key: str | None = None
    file_search_store: str | None = None
    file_search_model: str | None = None

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
                "KNOWLEDGE_BACKEND_NAME", "gemini_file_search"
            ).lower(),
            gemini_api_key=_get("GEMINI_API_KEY"),
            file_search_store=_get("GEMINI_FILE_SEARCH_STORE"),
            file_search_model=_get("GEMINI_FILE_SEARCH_MODEL"),
        )

    def __repr__(self) -> str:
        # Dataclass __repr__ is intentionally replaced so secrets are not exposed.
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
    """Parse a dotenv file, ignoring comments and blank lines."""
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
    """Load settings from .env merged with the real process environment.

    Real environment variables take precedence over .env values so that
    deployed/runtime configuration always wins over committed examples.
    """
    path = dotenv_path or Path(".env")
    dotenv = _load_dotenv_if_present(path)
    # Merge: real process environment overrides .env entries.
    merged = {**dotenv, **os.environ}
    return Settings.from_env(merged)
