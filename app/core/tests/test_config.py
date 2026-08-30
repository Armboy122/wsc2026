"""Tests for platform configuration loading."""

from pathlib import Path

import pytest

from app.core.config import Settings, load_settings


def test_default_settings() -> None:
    settings = Settings.from_env({})
    assert settings.app_env == "development"
    assert settings.log_level == "info"
    assert "http://localhost:3000" in settings.cors_origins
    assert settings.llm_adapter_name == "demo"
    assert settings.knowledge_backend_name == "gemini_file_search"
    assert settings.gemini_api_key is None
    assert settings.file_search_store is None
    assert settings.file_search_model is None


def test_env_override() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "CORS_ORIGINS": "https://demo.example.com",
            "LLM_ADAPTER_NAME": "judge",
            "KNOWLEDGE_BACKEND_NAME": "other",
            "GEMINI_API_KEY": "sk-test",
            "GEMINI_FILE_SEARCH_STORE": "store-123",
            "GEMINI_FILE_SEARCH_MODEL": "models/gemini-2.0-flash",
        }
    )
    assert settings.app_env == "production"
    assert settings.log_level == "warning"
    assert settings.cors_origins == ("https://demo.example.com",)
    assert settings.llm_adapter_name == "judge"
    assert settings.knowledge_backend_name == "other"
    assert settings.gemini_api_key == "sk-test"
    assert settings.file_search_store == "store-123"
    assert settings.file_search_model == "models/gemini-2.0-flash"


def test_empty_secret_values_are_normalized_to_none() -> None:
    settings = Settings.from_env(
        {
            "GEMINI_API_KEY": "",
            "GEMINI_FILE_SEARCH_STORE": "   ",
            "GEMINI_FILE_SEARCH_MODEL": "",
        }
    )
    assert settings.gemini_api_key is None
    assert settings.file_search_store is None
    assert settings.file_search_model is None


def test_load_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=test\nLOG_LEVEL=debug\nCORS_ORIGINS=http://test.local\n"
        "GEMINI_API_KEY=dotenv-key\nGEMINI_FILE_SEARCH_STORE=dotenv-store\n"
    )
    settings = load_settings(env_file)
    assert settings.app_env == "test"
    assert settings.log_level == "debug"
    assert settings.cors_origins == ("http://test.local",)
    assert settings.llm_adapter_name == "demo"
    assert settings.gemini_api_key == "dotenv-key"
    assert settings.file_search_store == "dotenv-store"
    assert settings.file_search_model is None


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
    assert settings.log_level == "debug"  # not overridden; taken from dotenv
    assert settings.llm_adapter_name == "scripted"  # from dotenv
    assert settings.gemini_api_key == "real-key"


def test_settings_repr_does_not_expose_secrets() -> None:
    settings = Settings.from_env(
        {
            "GEMINI_API_KEY": "super-secret",
            "GEMINI_FILE_SEARCH_STORE": "my-store",
            "GEMINI_FILE_SEARCH_MODEL": "models/gemini-pro",
        }
    )
    text = repr(settings)
    assert "super-secret" not in text
    assert "my-store" not in text
    assert "models/gemini-pro" not in text
    assert "[REDACTED]" in text


def test_settings_str_matches_repr() -> None:
    settings = Settings.from_env({"GEMINI_API_KEY": "another-secret"})
    assert str(settings) == repr(settings)
