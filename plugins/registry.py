"""AetherOS Plugins — Plugin Registry & Dependency Management."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class PluginDependency:
    name: str
    version: str = ""
    optional: bool = False


class PluginRegistry:
    """Registry of available plugins with dependency resolution."""

    def __init__(self):
        self._available: Dict[str, Dict[str, Any]] = {}
        self._installed: Set[str] = set()

    def register_available(self, name: str, info: Dict[str, Any]) -> None:
        self._available[name] = info

    def mark_installed(self, name: str) -> None:
        self._installed.add(name)

    def is_installed(self, name: str) -> bool:
        return name in self._installed

    def resolve_dependencies(self, name: str) -> List[str]:
        info = self._available.get(name, {})
        deps = info.get("dependencies", [])
        order = []
        for dep in deps:
            dep_name = dep if isinstance(dep, str) else dep.get("name", "")
            if dep_name and dep_name not in self._installed:
                order.extend(self.resolve_dependencies(dep_name))
                order.append(dep_name)
        return order

    def list_available(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "installed": name in self._installed, **info}
            for name, info in self._available.items()
        ]
