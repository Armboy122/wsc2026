"""Tests for platform configuration loading."""

from pathlib import Path

from app.core.config import Settings, load_settings


def test_default_settings() -> None:
    settings = Settings.from_env({})
    assert settings.app_env == "development"
    assert settings.log_level == "info"
    assert "http://localhost:3000" in settings.cors_origins
    assert settings.llm_adapter_name == "scripted"
    assert settings.knowledge_backend_name == "gemini_file_search"


def test_env_override() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "CORS_ORIGINS": "https://demo.example.com",
            "LLM_ADAPTER_NAME": "judge",
            "KNOWLEDGE_BACKEND_NAME": "other",
        }
    )
    assert settings.app_env == "production"
    assert settings.log_level == "warning"
    assert settings.cors_origins == ("https://demo.example.com",)
    assert settings.llm_adapter_name == "judge"
    assert settings.knowledge_backend_name == "other"


def test_load_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=test\nLOG_LEVEL=debug\nCORS_ORIGINS=http://test.local\n")
    settings = load_settings(env_file)
    assert settings.app_env == "test"
    assert settings.log_level == "debug"
    assert settings.cors_origins == ("http://test.local",)
