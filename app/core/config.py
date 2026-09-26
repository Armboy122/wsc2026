"""Application settings for the PEA Knowledge Voice Agent.

Only settings the Voice + deterministic Knowledge architecture needs: app environment and log
level, Gemini Live credentials/model/voice, and the approved Knowledge source root.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_KNOWLEDGE_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "source"
# Derived index cache. Never a source of truth; safe to delete and rebuild.
_DEFAULT_KNOWLEDGE_INDEX_DIR = Path(__file__).resolve().parents[2] / ".cache" / "knowledge-index"
# Field names whose values must never appear in repr/str/logging.
_SECRET_FIELD_NAMES: frozenset[str] = frozenset({"gemini_api_key"})
SUPPORTED_KNOWLEDGE_EMBEDDERS: frozenset[str] = frozenset({"bge-m3", "fake"})


@dataclass(frozen=True)
class Settings:
    """Static runtime settings loaded from `.env` and the process environment."""

    app_env: str = "development"
    log_level: str = "info"
    gemini_api_key: str | None = field(default=None, repr=False)
    live_model: str = "gemini-3.8-live"
    live_voice: str = "Puck"
    knowledge_source_root: Path = field(default_factory=lambda: _DEFAULT_KNOWLEDGE_SOURCE_ROOT)
    knowledge_index_dir: Path = field(default_factory=lambda: _DEFAULT_KNOWLEDGE_INDEX_DIR)
    knowledge_embedder: str = "bge-m3"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        def _get(key: str) -> str | None:
            value = env.get(key)
            return value.strip() if value is not None and value.strip() != "" else None

        return cls(
            app_env=(_get("APP_ENV") or "development").lower(),
            log_level=(_get("LOG_LEVEL") or "info").lower(),
            gemini_api_key=_get("GEMINI_API_KEY"),
            live_model=_get("GEMINI_LIVE_MODEL") or "gemini-3.8-live",
            live_voice=_get("GEMINI_LIVE_VOICE") or "Puck",
            knowledge_source_root=Path(
                _get("KNOWLEDGE_SOURCE_ROOT") or _DEFAULT_KNOWLEDGE_SOURCE_ROOT
            ),
            knowledge_index_dir=Path(
                _get("KNOWLEDGE_INDEX_DIR") or _DEFAULT_KNOWLEDGE_INDEX_DIR
            ),
            knowledge_embedder=(_get("KNOWLEDGE_EMBEDDER") or "bge-m3").lower(),
        )

    def __post_init__(self) -> None:
        if self.knowledge_embedder not in SUPPORTED_KNOWLEDGE_EMBEDDERS:
            supported = ", ".join(sorted(SUPPORTED_KNOWLEDGE_EMBEDDERS))
            raise ValueError(
                f"unsupported KNOWLEDGE_EMBEDDER {self.knowledge_embedder!r}: expected {supported}"
            )

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


def _load_dotenv_if_present(path: Path) -> dict[str, str]:
    """Parse a dotenv file, skipping comments and blank lines."""
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


def load_settings(dotenv_path: Path | None = None) -> Settings:
    """Merge `.env` with the real environment; the real environment always wins."""
    dotenv = _load_dotenv_if_present(dotenv_path or Path(".env"))
    return Settings.from_env({**dotenv, **os.environ})
