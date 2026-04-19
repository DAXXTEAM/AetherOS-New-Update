"""Tests for AetherOS Plugin System."""
import pytest
from plugins.base import BasePlugin, PluginHook, PluginCapability
from plugins.manager import PluginManager, PluginState
from plugins.registry import PluginRegistry, PluginDependency


class SamplePlugin(BasePlugin):
    @property
    def name(self):
        return "sample-plugin"

    @property
    def version(self):
        return "1.0.0"

    @property
    def description(self):
        return "A sample test plugin"

    @property
    def capabilities(self):
        return [PluginCapability.TOOL]

    @property
    def hooks(self):
        return [PluginHook.ON_BOOT, PluginHook.ON_TASK_START]

    def activate(self, config):
        return True

    def deactivate(self):
        return True

    def on_hook(self, hook, data):
        return {"plugin": self.name, "hook": hook.value}


class FailingPlugin(BasePlugin):
    @property
    def name(self):
        return "failing-plugin"

    @property
    def version(self):
        return "0.1.0"

    def activate(self, config):
        raise RuntimeError("Activation failed!")

    def deactivate(self):
        return True


class TestPluginManager:
    def test_register(self):
        pm = PluginManager()
        plugin = SamplePlugin()
        assert pm.register(plugin)
        plugins = pm.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "sample-plugin"

    def test_duplicate_register(self):
        pm = PluginManager()
        plugin = SamplePlugin()
        assert pm.register(plugin)
        assert not pm.register(plugin)  # Duplicate

    def test_activate(self):
        pm = PluginManager()
        pm.register(SamplePlugin())
        assert pm.activate("sample-plugin")
        plugins = pm.list_plugins()
        assert plugins[0]["state"] == "active"

    def test_deactivate(self):
        pm = PluginManager()
        pm.register(SamplePlugin())
        pm.activate("sample-plugin")
        assert pm.deactivate("sample-plugin")
        plugins = pm.list_plugins()
        assert plugins[0]["state"] == "loaded"

    def test_failing_activation(self):
        pm = PluginManager()
        pm.register(FailingPlugin())
        assert not pm.activate("failing-plugin")
        plugins = pm.list_plugins()
        assert plugins[0]["state"] == "error"

    def test_fire_hook(self):
        pm = PluginManager()
        pm.register(SamplePlugin())
        pm.activate("sample-plugin")
        results = pm.fire_hook(PluginHook.ON_BOOT, {"test": True})
        assert len(results) == 1
        assert results[0]["plugin"] == "sample-plugin"

    def test_shutdown_all(self):
        pm = PluginManager()
        pm.register(SamplePlugin())
        pm.activate("sample-plugin")
        pm.shutdown_all()
        plugins = pm.list_plugins()
        assert plugins[0]["state"] == "loaded"


class TestPluginRegistry:
    def test_register_and_install(self):
        reg = PluginRegistry()
        reg.register_available("test-plugin", {"version": "1.0"})
        assert not reg.is_installed("test-plugin")
        reg.mark_installed("test-plugin")
        assert reg.is_installed("test-plugin")

    def test_list_available(self):
        reg = PluginRegistry()
        reg.register_available("p1", {"version": "1.0"})
        reg.register_available("p2", {"version": "2.0"})
        available = reg.list_available()
        assert len(available) == 2
