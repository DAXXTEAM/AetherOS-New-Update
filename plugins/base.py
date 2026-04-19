"""AetherOS Plugins — Base plugin interface."""
from __future__ import annotations

import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plugins.base")


class PluginCapability(enum.Enum):
    TOOL = "tool"
    AGENT = "agent"
    SECURITY = "security"
    UI_WIDGET = "ui_widget"
    DATA_SOURCE = "data_source"
    NOTIFICATION = "notification"
    STORAGE = "storage"
    ANALYTICS = "analytics"


class PluginHook(enum.Enum):
    ON_BOOT = "on_boot"
    ON_SHUTDOWN = "on_shutdown"
    ON_TASK_START = "on_task_start"
    ON_TASK_COMPLETE = "on_task_complete"
    ON_SECURITY_EVENT = "on_security_event"
    ON_AGENT_MESSAGE = "on_agent_message"
    ON_EVOLUTION = "on_evolution"
    PRE_COMMAND = "pre_command"
    POST_COMMAND = "post_command"


class BasePlugin(ABC):
    """Base class for all AetherOS plugins."""

    def __init__(self):
        self._is_active = False
        self._config: Dict[str, Any] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        ...

    @property
    def description(self) -> str:
        return ""

    @property
    def capabilities(self) -> List[PluginCapability]:
        return []

    @property
    def hooks(self) -> List[PluginHook]:
        return []

    @abstractmethod
    def activate(self, config: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def deactivate(self) -> bool:
        ...

    def on_hook(self, hook: PluginHook, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    @property
    def is_active(self) -> bool:
        return self._is_active

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "is_active": self._is_active,
            "capabilities": [c.value for c in self.capabilities],
            "hooks": [h.value for h in self.hooks],
        }
