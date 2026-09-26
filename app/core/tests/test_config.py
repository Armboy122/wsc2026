"""Settings are limited to the Voice + deterministic Knowledge architecture."""

from dataclasses import fields
from pathlib import Path

import pytest

from app.core.config import Settings, load_settings


def test_default_settings() -> None:
    settings = Settings.from_env({})
    assert settings.app_env == "development"
    assert settings.log_level == "info"
    assert settings.gemini_api_key is None
    assert settings.live_model == "gemini-3.8-live"
    assert settings.live_voice == "Puck"
    assert settings.knowledge_source_root == (
        Path(__file__).resolve().parents[3] / "knowledge" / "source"
    )
    assert settings.knowledge_index_dir == (
        Path(__file__).resolve().parents[3] / ".cache" / "knowledge-index"
    )
    assert settings.knowledge_embedder == "bge-m3"


def test_env_override() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "GEMINI_API_KEY": "sk-test",
            "GEMINI_LIVE_MODEL": "gemini-live-other",
            "GEMINI_LIVE_VOICE": "Kore",
            "KNOWLEDGE_SOURCE_ROOT": "/srv/pea-knowledge",
            "KNOWLEDGE_INDEX_DIR": "/var/cache/pea-index",
            "KNOWLEDGE_EMBEDDER": "Fake",
        }
    )
    assert settings.app_env == "production"
    assert settings.log_level == "warning"
    assert settings.gemini_api_key == "sk-test"
    assert settings.live_model == "gemini-live-other"
    assert settings.live_voice == "Kore"
    assert settings.knowledge_source_root == Path("/srv/pea-knowledge")
    assert settings.knowledge_index_dir == Path("/var/cache/pea-index")
    assert settings.knowledge_embedder == "fake"


def test_unknown_knowledge_embedder_is_rejected() -> None:
    with pytest.raises(ValueError, match="KNOWLEDGE_EMBEDDER"):
        Settings.from_env({"KNOWLEDGE_EMBEDDER": "gemini-embedding"})


def test_only_voice_and_knowledge_settings_exist() -> None:
    assert {field.name for field in fields(Settings)} == {
        "app_env",
        "log_level",
        "gemini_api_key",
        "live_model",
        "live_voice",
        "knowledge_source_root",
        "knowledge_index_dir",
        "knowledge_embedder",
    }


def test_obsolete_environment_is_ignored() -> None:
    settings = Settings.from_env(
        {
            "VOICE_RUNTIME": "legacy",
            "MAIN_LLM_PROVIDER": "gemini",
            "LLM_ADAPTER_NAME": "gemini",
            "JUDGE_LLM_PROVIDER": "demo",
            "KNOWLEDGE_LLM_API_KEY": "knowledge-secret",
            "OMS_BASE_URL": "http://oms.example",
            "OMS_API_KEY": "oms-secret",
            "VOC_API_KEY": "voc-secret",
            "LINE_CHANNEL_SECRET": "line-secret",
            "LINE_CHANNEL_ACCESS_TOKEN": "line-token",
            "CORS_ORIGINS": "https://example.com",
        }
    )
    for removed in (
        "voice_runtime", "main_llm", "judge_llm", "llm_adapter_name", "knowledge_llm",
        "oms_base_url", "oms_api_key", "voc_base_url", "voc_api_key",
        "voc_consent_notice_version", "line_channel_secret", "line_channel_access_token",
        "cors_origins",
    ):
        assert not hasattr(settings, removed)
    text = repr(settings)
    for secret in ("knowledge-secret", "oms-secret", "voc-secret", "line-secret", "line-token"):
        assert secret not in text


def test_empty_api_key_is_normalized_to_none() -> None:
    assert Settings.from_env({"GEMINI_API_KEY": ""}).gemini_api_key is None


def test_load_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("APP_ENV", "LOG_LEVEL", "GEMINI_API_KEY", "KNOWLEDGE_SOURCE_ROOT"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nAPP_ENV=test\nLOG_LEVEL=debug\n\n"
        "GEMINI_API_KEY=dotenv-key\nKNOWLEDGE_SOURCE_ROOT=/dotenv/knowledge\n"
    )
    settings = load_settings(env_file)
    assert settings.app_env == "test"
    assert settings.log_level == "debug"
    assert settings.gemini_api_key == "dotenv-key"
    assert settings.knowledge_source_root == Path("/dotenv/knowledge")


def test_real_environment_precedes_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=from-dotenv\nLOG_LEVEL=debug\nGEMINI_API_KEY=dotenv-key\n")
    monkeypatch.setenv("APP_ENV", "from-env")
    monkeypatch.setenv("GEMINI_API_KEY", "real-key")

    settings = load_settings(env_file)
    assert settings.app_env == "from-env"
    assert settings.log_level == "debug"
    assert settings.gemini_api_key == "real-key"


def test_settings_repr_does_not_expose_secrets() -> None:
    settings = Settings.from_env(
        {"GEMINI_API_KEY": "super-secret", "KNOWLEDGE_SOURCE_ROOT": "/private/knowledge"}
    )
    text = repr(settings)
    assert "super-secret" not in text
    assert "/private/knowledge" in text
    assert "[REDACTED]" in text
    assert str(settings) == text
