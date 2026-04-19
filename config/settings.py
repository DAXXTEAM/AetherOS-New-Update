"""Configuration settings with validation via Pydantic."""
from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from config.constants import (
    DEFAULT_MODELS,
    PROVIDER_OPENAI,
    CHROMA_PERSIST_DIR,
    MAX_SHELL_TIMEOUT,
    LOG_DIR,
)


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class ModelConfig(BaseModel):
    """Configuration for LLM model selection."""
    provider: ModelProvider = ModelProvider.OLLAMA
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    timeout: int = Field(default=60, ge=1, le=600)

    @model_validator(mode="after")
    def _resolve_defaults(self) -> "ModelConfig":
        if self.model_name is None:
            self.model_name = DEFAULT_MODELS.get(self.provider.value, "gpt-4o")
        if self.api_key is None:
            env_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GOOGLE_API_KEY",
                "ollama": None,
            }
            env_var = env_map.get(self.provider.value)
            if env_var:
                self.api_key = os.environ.get(env_var, "")
            else:
                self.api_key = ""
        return self


class SecurityConfig(BaseModel):
    """Security-related configuration."""
    enable_quantum_safe: bool = True
    enable_kill_switch: bool = True
    shell_timeout: int = Field(default=MAX_SHELL_TIMEOUT, ge=1, le=600)
    sandbox_mode: bool = False
    allowed_directories: list[str] = Field(default_factory=lambda: [
        os.path.expanduser("~"),
        "/tmp",
    ])
    command_whitelist_enabled: bool = False
    audit_log_enabled: bool = True
    max_concurrent_tasks: int = Field(default=5, ge=1, le=50)


class MemoryConfig(BaseModel):
    """Memory/ChromaDB configuration."""
    persist_directory: str = CHROMA_PERSIST_DIR
    collection_name: str = "aether_memory"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_results: int = Field(default=10, ge=1, le=100)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class AetherConfig(BaseModel):
    """Master configuration for AetherOS."""
    model: ModelConfig = Field(default_factory=ModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    log_dir: str = LOG_DIR
    debug: bool = False
    workspace_dir: str = Field(default_factory=lambda: os.path.expanduser("~/aetheros_workspace"))

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        for d in [self.log_dir, self.memory.persist_directory, self.workspace_dir]:
            os.makedirs(d, exist_ok=True)
