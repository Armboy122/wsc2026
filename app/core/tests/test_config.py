"""ทดสอบการโหลดการกำหนดค่าของแพลตฟอร์ม"""

from pathlib import Path

import pytest

from app.core.config import Settings, load_settings


def test_default_settings() -> None:
    settings = Settings.from_env({})
    assert settings.app_env == "development"
    assert settings.log_level == "info"
    assert "http://localhost:3000" in settings.cors_origins
    assert settings.llm_adapter_name == "demo"
    assert settings.knowledge_backend_name == "full_document"
    assert settings.gemini_api_key is None
    assert settings.knowledge_provider == "gemini"
    assert settings.maxplus_api_key is None
    assert settings.maxplus_base_url == "https://api.maxplus-ai.cc/v1"
    assert settings.maxplus_model == "deepseek-v4-flash-0731"
    assert settings.knowledge_source_root == (
        Path(__file__).resolve().parents[3] / "knowledge" / "source"
    )
    assert settings.gemini_long_context_model == "gemini-3.5-flash"


def test_env_override() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "CORS_ORIGINS": "https://demo.example.com",
            "LLM_ADAPTER_NAME": "judge",
            "KNOWLEDGE_BACKEND_NAME": "other",
            "GEMINI_API_KEY": "sk-test",
            "KNOWLEDGE_PROVIDER": "maxplus_openai",
            "MAXPLUS_API_KEY": "ccsk-test",
            "MAXPLUS_BASE_URL": "https://api.maxplus-ai.cc/gpt-lite/v1/",
            "MAXPLUS_MODEL": "gpt-5.4-mini-fast",
            "KNOWLEDGE_SOURCE_ROOT": "/srv/pea-knowledge",
            "GEMINI_LONG_CONTEXT_MODEL": "gemini-3.6-pro",
        }
    )
    assert settings.app_env == "production"
    assert settings.log_level == "warning"
    assert settings.cors_origins == ("https://demo.example.com",)
    assert settings.llm_adapter_name == "judge"
    assert settings.knowledge_backend_name == "other"
    assert settings.gemini_api_key == "sk-test"
    assert settings.knowledge_provider == "maxplus_openai"
    assert settings.maxplus_api_key == "ccsk-test"
    assert settings.maxplus_base_url == "https://api.maxplus-ai.cc/gpt-lite/v1"
    assert settings.maxplus_model == "gpt-5.4-mini-fast"
    assert settings.knowledge_source_root == Path("/srv/pea-knowledge")
    assert settings.gemini_long_context_model == "gemini-3.6-pro"


def test_empty_api_key_is_normalized_to_none() -> None:
    settings = Settings.from_env({"GEMINI_API_KEY": "", "MAXPLUS_API_KEY": "  "})
    assert settings.gemini_api_key is None
    assert settings.maxplus_api_key is None


def test_load_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=test\nLOG_LEVEL=debug\nCORS_ORIGINS=http://test.local\n"
        "GEMINI_API_KEY=dotenv-key\nKNOWLEDGE_SOURCE_ROOT=/dotenv/knowledge\n"
        "GEMINI_LONG_CONTEXT_MODEL=gemini-3.6-pro\n"
    )
    settings = load_settings(env_file)
    assert settings.app_env == "test"
    assert settings.log_level == "debug"
    assert settings.cors_origins == ("http://test.local",)
    assert settings.llm_adapter_name == "demo"
    assert settings.gemini_api_key == "dotenv-key"
    assert settings.knowledge_source_root == Path("/dotenv/knowledge")
    assert settings.gemini_long_context_model == "gemini-3.6-pro"


def test_real_environment_precedes_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=from-dotenv\n"
        "LOG_LEVEL=debug\n"
        "LLM_ADAPTER_NAME=scripted\n"
        "GEMINI_API_KEY=dotenv-key\n"
    )
    monkeypatch.setenv("APP_ENV", "from-env")
    monkeypatch.setenv("GEMINI_API_KEY", "real-key")

    settings = load_settings(env_file)
    assert settings.app_env == "from-env"
    assert settings.log_level == "debug"  # ไม่ถูกแทนค่า จึงใช้ค่าจาก dotenv
    assert settings.llm_adapter_name == "scripted"  # ใช้ค่าจาก dotenv
    assert settings.gemini_api_key == "real-key"


def test_settings_repr_does_not_expose_secrets() -> None:
    settings = Settings.from_env(
        {
            "GEMINI_API_KEY": "super-secret",
            "MAXPLUS_API_KEY": "ccsk-also-secret",
            "KNOWLEDGE_SOURCE_ROOT": "/private/knowledge",
            "GEMINI_LONG_CONTEXT_MODEL": "gemini-3.6-pro",
        }
    )
    text = repr(settings)
    assert "super-secret" not in text
    assert "ccsk-also-secret" not in text
    assert "/private/knowledge" in text
    assert "gemini-3.6-pro" in text
    assert "[REDACTED]" in text


def test_settings_str_matches_repr() -> None:
    settings = Settings.from_env({"GEMINI_API_KEY": "another-secret"})
    assert str(settings) == repr(settings)
