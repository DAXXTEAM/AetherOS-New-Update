"""Tests for configuration module."""
import os
import pytest
from config.settings import AetherConfig, ModelConfig, SecurityConfig, MemoryConfig, ModelProvider
from config.constants import SYSTEM_NAME, SYSTEM_VERSION


class TestModelConfig:
    def test_default_provider(self):
        cfg = ModelConfig()
        assert cfg.provider == ModelProvider.OPENAI

    def test_default_model_name_resolved(self):
        cfg = ModelConfig(provider=ModelProvider.OPENAI)
        assert cfg.model_name == "gpt-4o"

    def test_anthropic_default_model(self):
        cfg = ModelConfig(provider=ModelProvider.ANTHROPIC)
        assert "claude" in cfg.model_name

    def test_temperature_bounds(self):
        with pytest.raises(Exception):
            ModelConfig(temperature=3.0)

    def test_max_tokens_bounds(self):
        cfg = ModelConfig(max_tokens=1000)
        assert cfg.max_tokens == 1000

    def test_custom_model_name(self):
        cfg = ModelConfig(provider=ModelProvider.OLLAMA, model_name="codellama:7b")
        assert cfg.model_name == "codellama:7b"


class TestSecurityConfig:
    def test_defaults(self):
        cfg = SecurityConfig()
        assert cfg.enable_quantum_safe is True
        assert cfg.enable_kill_switch is True
        assert cfg.sandbox_mode is True

    def test_allowed_directories(self):
        cfg = SecurityConfig()
        assert len(cfg.allowed_directories) >= 1


class TestAetherConfig:
    def test_ensure_dirs(self, tmp_path):
        cfg = AetherConfig(
            log_dir=str(tmp_path / "logs"),
            workspace_dir=str(tmp_path / "workspace"),
            memory=MemoryConfig(persist_directory=str(tmp_path / "chromadb")),
        )
        cfg.ensure_dirs()
        assert os.path.isdir(str(tmp_path / "logs"))
        assert os.path.isdir(str(tmp_path / "workspace"))
        assert os.path.isdir(str(tmp_path / "chromadb"))


class TestConstants:
    def test_system_name(self):
        assert SYSTEM_NAME == "AetherOS"

    def test_system_version(self):
        assert SYSTEM_VERSION == "2.0.0"
