"""Single construction seam for swappable Main-Agent and Judge LLM adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.adapter import LLMAdapter
from app.llm.demo import DemoLLMAdapter
from app.llm.demo_behavior import DemoBehavior
from app.llm.gemini import GeminiLLMAdapter
from app.llm.maxplus import MaxPlusDeepSeekAdapter


SUPPORTED_LLM_PROVIDERS = frozenset({"demo", "gemini", "maxplus_openai"})


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    """Provider-neutral configuration consumed by the adapter factory."""

    provider: str
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    base_url: str | None = None


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
            **kwargs,
        )
    if provider == "maxplus_openai":
        return MaxPlusDeepSeekAdapter(
            api_key=config.api_key,
            model=_required(config.model, "MAIN_LLM_MODEL/JUDGE_LLM_MODEL"),
            base_url=_required(config.base_url, "MAIN_LLM_BASE_URL/JUDGE_LLM_BASE_URL"),
        )
    raise ValueError(f"ไม่รองรับ LLM provider: {config.provider}")


def _required(value: str | None, setting_name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"ต้องกำหนด {setting_name}")
    return value.strip()
