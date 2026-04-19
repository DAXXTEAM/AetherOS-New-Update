"""AetherOS Plugin System   Dynamic extension loading and management."""
from plugins.manager import PluginManager, PluginInfo, PluginState
from plugins.base import BasePlugin, PluginHook, PluginCapability
from plugins.registry import PluginRegistry, PluginDependency

__all__ = [
    "PluginManager", "PluginInfo", "PluginState",
    "BasePlugin", "PluginHook", "PluginCapability",
    "PluginRegistry", "PluginDependency",
]
