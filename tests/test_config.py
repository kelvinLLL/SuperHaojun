"""Tests for config module."""

import os

import pytest

from superhaojun.config import ModelConfig, load_config, make_permissive_ssl_context


class TestModelConfig:
    def test_default_values(self) -> None:
        cfg = ModelConfig(
            provider="openai",
            model_id="gpt-4o",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
        assert cfg.provider == "openai"
        assert cfg.model_id == "gpt-4o"
        assert cfg.is_reasoning is False

    def test_reasoning_detection_gpt5(self) -> None:
        cfg = ModelConfig(
            provider="openai", model_id="gpt-5.4", base_url="x", api_key="k"
        )
        assert cfg.is_reasoning is True

    def test_reasoning_detection_o1(self) -> None:
        cfg = ModelConfig(
            provider="openai", model_id="o1-preview", base_url="x", api_key="k"
        )
        assert cfg.is_reasoning is True

    def test_reasoning_detection_o3(self) -> None:
        cfg = ModelConfig(
            provider="openai", model_id="o3-mini", base_url="x", api_key="k"
        )
        assert cfg.is_reasoning is True

    def test_non_reasoning_model(self) -> None:
        cfg = ModelConfig(
            provider="openai", model_id="gpt-4o-mini", base_url="x", api_key="k"
        )
        assert cfg.is_reasoning is False

    def test_frozen(self) -> None:
        cfg = ModelConfig(
            provider="openai", model_id="gpt-4o", base_url="x", api_key="k"
        )
        with pytest.raises(AttributeError):
            cfg.provider = "other"  # type: ignore[misc]

    def test_load_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
        monkeypatch.setenv("MODEL_ID", "gpt-5.4")
        monkeypatch.setenv("MODEL_PROVIDER", "custom")
        cfg = load_config()
        assert cfg.api_key == "test-key"
        assert cfg.base_url == "https://example.com/v1"
        assert cfg.model_id == "gpt-5.4"
        assert cfg.provider == "custom"
        assert cfg.is_reasoning is True

    def test_load_config_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("MODEL_ID", raising=False)
        monkeypatch.delenv("MODEL_PROVIDER", raising=False)
        # Prevent pydantic-settings from reading .env file
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.model_id == "gpt-4o"
        assert cfg.provider == "openai"

    def test_load_config_missing_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(Exception):
            load_config()


class TestSSL:
    def test_permissive_ssl_context(self) -> None:
        import ssl

        ctx = make_permissive_ssl_context()
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE
