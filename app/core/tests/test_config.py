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
    assert settings.knowledge_source_root == (
        Path(__file__).resolve().parents[3] / "knowledge" / "source"
    )
    assert settings.gemini_long_context_model == "gemini-3.5-flash-lite"


def test_env_override() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "CORS_ORIGINS": "https://demo.example.com",
            "LLM_ADAPTER_NAME": "judge",
            "KNOWLEDGE_BACKEND_NAME": "other",
            "GEMINI_API_KEY": "sk-test",
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
    assert settings.knowledge_provider == "gemini"
    assert settings.knowledge_source_root == Path("/srv/pea-knowledge")
    assert settings.gemini_long_context_model == "gemini-3.6-pro"


def test_main_knowledge_and_judge_llm_configs_are_independent() -> None:
    settings = Settings.from_env(
        {
            "MAIN_LLM_PROVIDER": "gemini",
            "MAIN_LLM_MODEL": "gemini-2.5-flash",
            "GEMINI_API_KEY": "gemini-secret",
            "JUDGE_LLM_PROVIDER": "demo",
            "JUDGE_LLM_MODEL": "judge-model",
            "JUDGE_LLM_API_KEY": "judge-secret",
            "JUDGE_LLM_BASE_URL": "https://judge.example/v1/",
            "KNOWLEDGE_LLM_PROVIDER": "demo",
            "KNOWLEDGE_LLM_MODEL": "knowledge-model",
            "KNOWLEDGE_LLM_API_KEY": "knowledge-secret",
            "KNOWLEDGE_LLM_BASE_URL": "https://knowledge.example/v1/",
        }
    )

    assert settings.main_llm.provider == "gemini"
    assert settings.main_llm.model == "gemini-2.5-flash"
    assert settings.main_llm.api_key == "gemini-secret"
    assert settings.knowledge_llm.provider == "demo"
    assert settings.knowledge_llm.model == "knowledge-model"
    assert settings.knowledge_llm.api_key == "knowledge-secret"
    assert settings.knowledge_llm.base_url == "https://knowledge.example/v1"
    assert settings.judge_llm.provider == "demo"
    assert settings.judge_llm.model == "judge-model"
    assert settings.judge_llm.api_key == "judge-secret"
    assert settings.judge_llm.base_url == "https://judge.example/v1"


def test_legacy_main_llm_environment_is_still_supported() -> None:
    settings = Settings.from_env(
        {
            "LLM_ADAPTER_NAME": "gemini",
            "GEMINI_API_KEY": "legacy-secret",
            "MAIN_LLM_MODEL": "legacy-model",
        }
    )

    assert settings.main_llm.provider == "gemini"
    assert settings.main_llm.api_key == "legacy-secret"
    assert settings.main_llm.model == "legacy-model"


def test_empty_api_key_is_normalized_to_none() -> None:
    settings = Settings.from_env({"GEMINI_API_KEY": ""})
    assert settings.gemini_api_key is None


def test_load_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=test\nLOG_LEVEL=debug\nCORS_ORIGINS=http://test.local\n"
        "GEMINI_API_KEY=dotenv-key\nKNOWLEDGE_SOURCE_ROOT=/dotenv/knowledge\n"
        "GEMINI_LONG_CONTEXT_MODEL=gemini-3.6-pro\n"
    )
    settings = load_settings(env_file, tmp_path / "no-llm-settings.yaml")
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

    settings = load_settings(env_file, tmp_path / "no-llm-settings.yaml")
    assert settings.app_env == "from-env"
    assert settings.log_level == "debug"  # ไม่ถูกแทนค่า จึงใช้ค่าจาก dotenv
    assert settings.llm_adapter_name == "scripted"  # ใช้ค่าจาก dotenv
    assert settings.gemini_api_key == "real-key"


def test_settings_repr_does_not_expose_secrets() -> None:
    settings = Settings.from_env(
        {
            "GEMINI_API_KEY": "super-secret",
            "KNOWLEDGE_SOURCE_ROOT": "/private/knowledge",
            "GEMINI_LONG_CONTEXT_MODEL": "gemini-3.6-pro",
        }
    )
    text = repr(settings)
    assert "super-secret" not in text
    assert "/private/knowledge" in text
    assert "gemini-3.6-pro" in text
    assert "[REDACTED]" in text


def test_settings_str_matches_repr() -> None:
    settings = Settings.from_env({"GEMINI_API_KEY": "another-secret"})
    assert str(settings) == repr(settings)


def test_llm_settings_select_local_profile_and_keep_key_in_environment() -> None:
    settings = Settings.from_env(
        {"LOCAL_LLM_API_KEY": "local-secret"},
        {
            "providers": {
                "local": {
                    "api": "openai-compatible",
                    "api_key_env": "LOCAL_LLM_API_KEY",
                    "base_url": "https://gateway.example/v1",
                }
            },
            "roles": {
                "main": {
                    "provider": "local",
                    "model": "qwen3.8-27b",
                    "thinking": False,
                    "effort": "low",
                }
            },
        },
    )

    assert settings.main_llm.provider == "openai-compatible"
    assert settings.main_llm.model == "qwen3.8-27b"
    assert settings.main_llm.base_url == "https://gateway.example/v1"
    assert settings.main_llm.api_key == "local-secret"
    assert settings.main_llm.thinking is False
    assert settings.main_llm.effort == "low"
    assert "local-secret" not in repr(settings)


def test_llm_environment_overrides_settings_profile() -> None:
    settings = Settings.from_env(
        {"MAIN_LLM_PROVIDER": "local", "MAIN_LLM_THINKING": "true", "MAIN_LLM_EFFORT": "high"},
        {
            "providers": {"local": {"api": "openai-compatible", "base_url": "http://host/v1"}},
            "roles": {"main": {"provider": "gemini", "model": "configured-model"}},
        },
    )

    assert settings.main_llm.provider == "openai-compatible"
    assert settings.main_llm.thinking is True
    assert settings.main_llm.effort == "high"
