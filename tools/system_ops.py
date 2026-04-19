"""System monitoring and information operations."""
from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import time
from datetime import datetime

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.system_ops")


class SystemOps(BaseTool):
    """System information and monitoring operations."""

    def __init__(self):
        super().__init__("system_ops", "System monitoring and information")
        self._boot_time = time.time()

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "info")
        dispatch = {
            "info": self._system_info,
            "resources": self._resource_usage,
            "network": self._network_info,
            "python": self._python_info,
            "env_check": self._environment_check,
            "uptime": self._uptime,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "system_ops",
            "description": "System information and monitoring",
            "parameters": {
                "action": {
                    "type": "string",
                    "enum": ["info", "resources", "network", "python", "env_check", "uptime"],
                },
            },
        }

    async def _system_info(self, args: dict) -> ToolResult:
        info = {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "hostname": socket.gethostname(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
        }
        output = "\n".join(f"{k}: {v}" for k, v in info.items())
        return ToolResult(success=True, output=output, metadata=info)

    async def _resource_usage(self, args: dict) -> ToolResult:
        try:
            disk = shutil.disk_usage("/")
            info = {
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "disk_usage_percent": round(disk.used / disk.total * 100, 1),
            }

            # Try to get memory info from /proc
            try:
                with open("/proc/meminfo") as f:
                    mem_lines = f.readlines()
                mem_info = {}
                for line in mem_lines[:5]:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().replace(" kB", "")
                        try:
                            mem_info[key] = int(val)
                        except ValueError:
                            pass
                if "MemTotal" in mem_info:
                    info["mem_total_mb"] = round(mem_info["MemTotal"] / 1024, 0)
                if "MemAvailable" in mem_info:
                    info["mem_available_mb"] = round(mem_info["MemAvailable"] / 1024, 0)
                if "MemTotal" in mem_info and "MemAvailable" in mem_info:
                    info["mem_usage_percent"] = round(
                        (1 - mem_info["MemAvailable"] / mem_info["MemTotal"]) * 100, 1
                    )
            except FileNotFoundError:
                pass

            # CPU load average
            try:
                load = os.getloadavg()
                info["load_1m"] = round(load[0], 2)
                info["load_5m"] = round(load[1], 2)
                info["load_15m"] = round(load[2], 2)
            except (OSError, AttributeError):
                pass

            output = "\n".join(f"{k}: {v}" for k, v in info.items())
            return ToolResult(success=True, output=output, metadata=info)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _network_info(self, args: dict) -> ToolResult:
        info = {
            "hostname": socket.gethostname(),
        }
        try:
            info["fqdn"] = socket.getfqdn()
            info["ip_addresses"] = socket.gethostbyname_ex(socket.gethostname())[2]
        except socket.gaierror:
            info["ip_addresses"] = ["Unable to resolve"]

        output = "\n".join(f"{k}: {v}" for k, v in info.items())
        return ToolResult(success=True, output=output, metadata=info)

    async def _python_info(self, args: dict) -> ToolResult:
        import sys
        info = {
            "version": sys.version,
            "executable": sys.executable,
            "path": "\n  ".join(sys.path[:5]),
            "platform": sys.platform,
        }

        # Check key packages
        packages = ["chromadb", "langgraph", "langchain", "pydantic", "cryptography"]
        installed = {}
        for pkg in packages:
            try:
                mod = __import__(pkg)
                ver = getattr(mod, "__version__", "installed")
                installed[pkg] = ver
            except ImportError:
                installed[pkg] = "NOT INSTALLED"

        info["packages"] = installed
        output = "\n".join(f"{k}: {v}" for k, v in info.items())
        output += "\n\nPackages:\n" + "\n".join(f"  {k}: {v}" for k, v in installed.items())
        return ToolResult(success=True, output=output, metadata={**info, "packages": installed})

    async def _environment_check(self, args: dict) -> ToolResult:
        checks = []

        # Python version
        import sys
        py_ver = sys.version_info
        checks.append(("Python 3.10+", py_ver >= (3, 10), f"{py_ver.major}.{py_ver.minor}"))

        # Required packages
        for pkg in ["chromadb", "langgraph", "pydantic", "cryptography"]:
            try:
                __import__(pkg)
                checks.append((f"Package: {pkg}", True, "installed"))
            except ImportError:
                checks.append((f"Package: {pkg}", False, "missing"))

        # Directories
        dirs = [os.path.expanduser("~/.aetheros"), "/tmp"]
        for d in dirs:
            writable = os.access(d, os.W_OK) if os.path.exists(d) else False
            checks.append((f"Directory: {d}", writable or not os.path.exists(d),
                           "writable" if writable else "not writable/missing"))

        # Disk space
        disk = shutil.disk_usage("/")
        has_space = disk.free > 1024**3  # > 1GB free
        checks.append(("Disk space (>1GB)", has_space, f"{disk.free // (1024**3)}GB free"))

        output = "\n".join(
            f"{'✅' if ok else '❌'} {name}: {detail}"
            for name, ok, detail in checks
        )
        all_ok = all(ok for _, ok, _ in checks)
        return ToolResult(
            success=True,
            output=f"Environment Check: {'ALL PASS' if all_ok else 'ISSUES FOUND'}\n\n{output}",
            metadata={"all_pass": all_ok, "checks": len(checks)},
        )

    async def _uptime(self, args: dict) -> ToolResult:
        uptime = time.time() - self._boot_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        output = f"AetherOS uptime: {hours}h {minutes}m {seconds}s"
        return ToolResult(success=True, output=output, metadata={"uptime_seconds": uptime})
