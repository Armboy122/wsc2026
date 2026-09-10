from __future__ import annotations

import hashlib
import importlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from .contracts import DomainError, Principal
from .providers import ExtractiveProvider, GeminiProvider
from .registry import Registry
from .service import KnowledgeService
from .sessions import Sessions


@dataclass
class Settings:
    knowledge_root: Path
    database: Path
    state_key: str
    tokens: dict[str, dict]
    provider: str = "extractive"
    api_key: str = ""
    model: str = ""
    plugin_factory: str = "voice_assistant.plugins.knowledge:KnowledgePlugin"
    plugin_id: str = "knowledge.search"

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv()
        return cls(knowledge_root=Path(os.getenv("KNOWLEDGE_ROOT", "../../knowledge")),
            database=Path(os.getenv("DATABASE_PATH", "data/sessions.sqlite")),
            state_key=os.environ["STATE_KEY"], tokens=json.loads(os.environ["API_TOKENS_JSON"]),
            provider=os.getenv("ANSWER_PROVIDER", "extractive"), api_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("GEMINI_MODEL", ""), plugin_factory=os.getenv("KNOWLEDGE_PLUGIN_FACTORY", cls.plugin_factory),
            plugin_id=os.getenv("KNOWLEDGE_PLUGIN_ID", "knowledge.search"))


def authenticate(settings: Settings, value: str | None) -> Principal:
    if not value or len(value) > 512:
        raise DomainError("unauthorized", "ต้องใช้ API token", 401)
    digest = hashlib.sha256(value.encode()).digest()
    for token, principal in settings.tokens.items():
        if len(token) < 24:
            raise RuntimeError("API token ต้องยาวอย่างน้อย 24 ตัวอักษร")
        if secrets.compare_digest(digest, hashlib.sha256(token.encode()).digest()):
            return Principal.model_validate(principal)
    raise DomainError("unauthorized", "API token ไม่ถูกต้อง", 401)


def build(settings: Settings):
    module, attr = settings.plugin_factory.split(":", 1)
    factory = getattr(importlib.import_module(module), attr)
    plugin = factory(settings.knowledge_root)
    registry = Registry([plugin])
    if settings.provider == "gemini":
        provider = GeminiProvider(settings.api_key, settings.model)
    elif settings.provider == "extractive":
        provider = ExtractiveProvider()
    else:
        raise ValueError("ANSWER_PROVIDER ต้องเป็น extractive หรือ gemini")
    return KnowledgeService(registry, Sessions(settings.database, settings.state_key), provider, settings.plugin_id)
