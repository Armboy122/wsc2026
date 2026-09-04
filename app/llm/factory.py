"""Single construction seam for swappable Main-Agent and Judge LLM adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.adapter import LLMAdapter
from app.llm.demo import DemoLLMAdapter
from app.llm.demo_behavior import DemoBehavior
from app.llm.gemini import GeminiLLMAdapter
from app.llm.openai_compatible import OpenAICompatibleLLMAdapter


SUPPORTED_LLM_PROVIDERS = frozenset({"demo", "gemini", "local", "openai-compatible"})


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    """Provider-neutral configuration consumed by the adapter factory."""

    provider: str
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    base_url: str | None = None
    thinking: bool = False
    effort: str = "low"


def create_llm_adapter(
    config: LLMProviderConfig,
    *,
    demo_behaviors: tuple[DemoBehavior, ...] = (),
) -> LLMAdapter:
    """Create one adapter; only the offline demo consumes plugin behaviors."""
    provider = config.provider.strip().lower()
    if provider == "demo":
        return DemoLLMAdapter(demo_behaviors)
    if provider == "gemini":
        kwargs = {"base_url": config.base_url} if config.base_url else {}
        return GeminiLLMAdapter(
            api_key=config.api_key,
            model=_required(config.model, "*_LLM_MODEL"),
            thinking=config.thinking,
            effort=_effort(config.effort),
            **kwargs,
        )
    if provider in {"local", "openai-compatible"}:
        return OpenAICompatibleLLMAdapter(
            api_key=config.api_key,
            base_url=_required(config.base_url, "*_LLM_BASE_URL"),
            model=_required(config.model, "*_LLM_MODEL"),
            thinking=config.thinking,
            effort=_effort(config.effort),
        )
    raise ValueError(f"ไม่รองรับ LLM provider: {config.provider}")


def _required(value: str | None, setting_name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"ต้องกำหนด {setting_name}")
    return value.strip()


def _effort(value: str) -> str:
    effort = value.strip().lower()
    if effort not in {"low", "medium", "high"}:
        raise ValueError("LLM effort ต้องเป็น low, medium หรือ high")
    return effort
