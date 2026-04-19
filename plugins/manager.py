"""AetherOS Plugins — Plugin Manager."""
from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from plugins.base import BasePlugin, PluginHook, PluginCapability

logger = logging.getLogger("plugins.manager")


class PluginState(enum.Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginInfo:
    """Metadata about a loaded plugin."""
    name: str
    version: str
    state: PluginState = PluginState.UNLOADED
    loaded_at: Optional[datetime] = None
    error: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "state": self.state.value,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "error": self.error,
        }


class PluginManager:
    """Manages plugin lifecycle: loading, activation, hooks, and shutdown."""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._info: Dict[str, PluginInfo] = {}
        self._hook_handlers: Dict[PluginHook, List[str]] = {h: [] for h in PluginHook}
        self._lock = threading.Lock()
        logger.info("PluginManager initialized")

    def register(self, plugin: BasePlugin, config: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            name = plugin.name
            if name in self._plugins:
                logger.warning(f"Plugin '{name}' already registered")
                return False

            self._plugins[name] = plugin
            self._info[name] = PluginInfo(
                name=name, version=plugin.version, state=PluginState.LOADED,
                loaded_at=datetime.utcnow(), config=config or {},
            )

            for hook in plugin.hooks:
                self._hook_handlers[hook].append(name)

            logger.info(f"Plugin registered: {name} v{plugin.version}")
            return True

    def activate(self, name: str) -> bool:
        with self._lock:
            plugin = self._plugins.get(name)
            info = self._info.get(name)
            if not plugin or not info:
                return False
            try:
                success = plugin.activate(info.config)
                if success:
                    info.state = PluginState.ACTIVE
                    plugin._is_active = True
                    logger.info(f"Plugin activated: {name}")
                else:
                    info.state = PluginState.ERROR
                    info.error = "Activation returned False"
                return success
            except Exception as e:
                info.state = PluginState.ERROR
                info.error = str(e)
                logger.error(f"Plugin activation failed for '{name}': {e}")
                return False

    def deactivate(self, name: str) -> bool:
        with self._lock:
            plugin = self._plugins.get(name)
            info = self._info.get(name)
            if not plugin or not info:
                return False
            try:
                plugin.deactivate()
                plugin._is_active = False
                info.state = PluginState.LOADED
                return True
            except Exception as e:
                logger.error(f"Plugin deactivation error for '{name}': {e}")
                return False

    def fire_hook(self, hook: PluginHook, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = []
        with self._lock:
            handlers = list(self._hook_handlers.get(hook, []))
        for name in handlers:
            plugin = self._plugins.get(name)
            if plugin and plugin.is_active:
                try:
                    result = plugin.on_hook(hook, data)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Hook error in '{name}': {e}")
        return results

    def list_plugins(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [info.to_dict() for info in self._info.values()]

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def shutdown_all(self) -> None:
        for name in list(self._plugins.keys()):
            self.deactivate(name)
        logger.info("All plugins shut down")
