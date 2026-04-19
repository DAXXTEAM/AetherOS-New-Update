"""Shared test fixtures for AetherOS."""
import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import AetherConfig, ModelConfig, SecurityConfig, MemoryConfig, ModelProvider
from core.event_bus import EventBus
from core.model_manager import ModelManager
from core.state import SystemState
from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps


@pytest.fixture
def config():
    return AetherConfig(
        model=ModelConfig(provider=ModelProvider.OPENAI),
        debug=True,
    )

@pytest.fixture
def event_bus():
    return EventBus()

@pytest.fixture
def system_state():
    return SystemState()

@pytest.fixture
def model_manager(config):
    return ModelManager(config.model)

@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    registry.register(FileOps(allowed_dirs=["/tmp", os.path.expanduser("~")], sandbox=True))
    registry.register(ShellOps(sandbox=True))
    return registry

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory(prefix="aether_test_") as td:
        yield td
