"""Monitoring Operations Tool — System and application monitoring."""
from __future__ import annotations

import logging
import os
import platform
import time
from typing import Optional

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.monitor_ops")


class MonitorOps(BaseTool):
    """System and application monitoring operations."""

    def __init__(self):
        super().__init__("monitor_ops", "System monitoring, resource tracking, and health checks")
        self._metrics_history: list[dict] = []
        self._alerts: list[dict] = []

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "status")
        dispatch = {
            "status": self._system_status,
            "cpu": self._cpu_info,
            "memory": self._memory_info,
            "disk": self._disk_info,
            "network": self._network_info,
            "processes": self._process_list,
            "health": self._health_check,
            "uptime": self._uptime,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown monitor action: {action}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "monitor_ops",
            "description": "System monitoring and health checks",
            "parameters": {
                "action": {"type": "string", "enum": ["status", "cpu", "memory", "disk", "network", "processes", "health", "uptime"]},
            },
        }

    async def _system_status(self, args: dict) -> ToolResult:
        info = {
            "platform": platform.platform(),
            "hostname": platform.node(),
            "python": platform.python_version(),
            "arch": platform.machine(),
            "pid": os.getpid(),
        }
        return ToolResult(success=True, output=str(info))

    async def _cpu_info(self, args: dict) -> ToolResult:
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()[:3]
            with open("/proc/cpuinfo", "r") as f:
                cores = sum(1 for line in f if line.startswith("processor"))
            return ToolResult(success=True, output=f"Load: {', '.join(load)} | Cores: {cores}")
        except Exception:
            return ToolResult(success=True, output=f"CPU: {platform.processor() or 'unknown'}")

    async def _memory_info(self, args: dict) -> ToolResult:
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()[:5]
            info = {l.split(":")[0]: l.split(":")[1].strip() for l in lines if ":" in l}
            return ToolResult(success=True, output=str(info))
        except Exception:
            return ToolResult(success=True, output="Memory info unavailable")

    async def _disk_info(self, args: dict) -> ToolResult:
        import shutil
        total, used, free = shutil.disk_usage("/")
        return ToolResult(success=True, output=(
            f"Total: {total // (1024**3)}GB, Used: {used // (1024**3)}GB, "
            f"Free: {free // (1024**3)}GB ({free * 100 // total}%)"
        ))

    async def _network_info(self, args: dict) -> ToolResult:
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]
            interfaces = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    name = parts[0].strip()
                    stats = parts[1].split()
                    interfaces[name] = {
                        "rx_bytes": int(stats[0]),
                        "tx_bytes": int(stats[8]) if len(stats) > 8 else 0,
                    }
            return ToolResult(success=True, output=str(interfaces))
        except Exception:
            return ToolResult(success=True, output="Network info unavailable")

    async def _process_list(self, args: dict) -> ToolResult:
        try:
            import subprocess
            result = subprocess.run(["ps", "aux", "--sort=-pcpu"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.splitlines()[:11]
            return ToolResult(success=True, output="\n".join(lines))
        except Exception:
            return ToolResult(success=True, output=f"PID: {os.getpid()}")

    async def _health_check(self, args: dict) -> ToolResult:
        checks = {
            "system": True,
            "disk_space": True,
            "memory": True,
        }
        try:
            import shutil
            _, _, free = shutil.disk_usage("/")
            checks["disk_space"] = free > 1024 * 1024 * 100
        except Exception:
            pass
        all_healthy = all(checks.values())
        return ToolResult(success=True, output=f"Health: {'OK' if all_healthy else 'DEGRADED'} | {checks}")

    async def _uptime(self, args: dict) -> ToolResult:
        try:
            with open("/proc/uptime", "r") as f:
                uptime = float(f.read().split()[0])
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            return ToolResult(success=True, output=f"Uptime: {hours}h {minutes}m")
        except Exception:
            return ToolResult(success=True, output="Uptime unavailable")
