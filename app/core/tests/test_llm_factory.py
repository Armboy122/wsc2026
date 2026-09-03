"""ทดสอบ seam กลางสำหรับเลือก LLM adapter"""

import pytest

from app.llm import DemoLLMAdapter, GeminiLLMAdapter
from app.llm.factory import LLMProviderConfig, create_llm_adapter


def test_factory_creates_demo_adapter() -> None:
    adapter = create_llm_adapter(LLMProviderConfig(provider="demo"))
    assert isinstance(adapter, DemoLLMAdapter)


def test_factory_creates_gemini_adapter() -> None:
    adapter = create_llm_adapter(
        LLMProviderConfig(
            provider="gemini",
            api_key="gemini-secret",
            model="gemini-2.5-flash",
        )
    )
    assert isinstance(adapter, GeminiLLMAdapter)


def test_provider_config_repr_redacts_api_key() -> None:
    config = LLMProviderConfig(provider="gemini", api_key="super-secret")
    assert "super-secret" not in repr(config)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="ไม่รองรับ LLM provider"):
        create_llm_adapter(LLMProviderConfig(provider="unknown"))
