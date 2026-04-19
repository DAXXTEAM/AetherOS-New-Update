"""AetherOS Diagnostics — Health Check System.

Comprehensive system health monitoring with component-level status tracking.
"""
from __future__ import annotations

import enum
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("diagnostics.health")


class HealthStatus(enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    response_time_ms: float = 0.0
    last_checked: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "response_time_ms": round(self.response_time_ms, 2),
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
        }


class HealthChecker:
    """System health checker with component registration."""

    def __init__(self, check_interval: float = 60.0):
        self.check_interval = check_interval
        self._checks: Dict[str, Callable[[], ComponentHealth]] = {}
        self._results: Dict[str, ComponentHealth] = {}
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default health checks."""
        self.register("disk_space", self._check_disk_space)
        self.register("memory", self._check_memory)
        self.register("cpu_load", self._check_cpu_load)

    def register(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        self._checks[name] = check_fn

    def check_all(self) -> Dict[str, ComponentHealth]:
        """Run all health checks."""
        results = {}
        for name, check_fn in self._checks.items():
            start = time.time()
            try:
                result = check_fn()
                result.response_time_ms = (time.time() - start) * 1000
                result.last_checked = datetime.utcnow()
            except Exception as e:
                result = ComponentHealth(
                    name=name, status=HealthStatus.UNHEALTHY,
                    message=str(e),
                    response_time_ms=(time.time() - start) * 1000,
                    last_checked=datetime.utcnow(),
                )
            results[name] = result

        with self._lock:
            self._results = results
        return results

    def get_overall_status(self) -> HealthStatus:
        """Get the overall system health status."""
        with self._lock:
            if not self._results:
                return HealthStatus.UNKNOWN
            statuses = [r.status for r in self._results.values()]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        return HealthStatus.DEGRADED

    def get_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "overall": self.get_overall_status().value,
                "components": {name: r.to_dict() for name, r in self._results.items()},
                "timestamp": datetime.utcnow().isoformat(),
            }

    def start(self) -> None:
        self._is_running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _monitor_loop(self) -> None:
        while self._is_running:
            self.check_all()
            time.sleep(self.check_interval)

    @staticmethod
    def _check_disk_space() -> ComponentHealth:
        try:
            st = os.statvfs("/")
            usage = (st.f_blocks - st.f_bavail) / st.f_blocks * 100
            status = HealthStatus.HEALTHY if usage < 85 else (
                HealthStatus.DEGRADED if usage < 95 else HealthStatus.UNHEALTHY
            )
            return ComponentHealth(
                name="disk_space", status=status,
                message=f"Disk usage: {usage:.1f}%",
                metadata={"usage_percent": round(usage, 1)},
            )
        except Exception as e:
            return ComponentHealth(name="disk_space", status=HealthStatus.UNKNOWN, message=str(e))

    @staticmethod
    def _check_memory() -> ComponentHealth:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = usage.ru_maxrss / 1024
            status = HealthStatus.HEALTHY if rss_mb < 1024 else (
                HealthStatus.DEGRADED if rss_mb < 2048 else HealthStatus.UNHEALTHY
            )
            return ComponentHealth(
                name="memory", status=status,
                message=f"RSS: {rss_mb:.0f} MB",
                metadata={"rss_mb": round(rss_mb, 1)},
            )
        except Exception as e:
            return ComponentHealth(name="memory", status=HealthStatus.UNKNOWN, message=str(e))

    @staticmethod
    def _check_cpu_load() -> ComponentHealth:
        try:
            load = os.getloadavg()[0]
            ncpu = os.cpu_count() or 1
            ratio = load / ncpu
            status = HealthStatus.HEALTHY if ratio < 0.7 else (
                HealthStatus.DEGRADED if ratio < 0.9 else HealthStatus.UNHEALTHY
            )
            return ComponentHealth(
                name="cpu_load", status=status,
                message=f"Load: {load:.2f} ({ncpu} CPUs)",
                metadata={"load_1min": load, "cpus": ncpu},
            )
        except Exception as e:
            return ComponentHealth(name="cpu_load", status=HealthStatus.UNKNOWN, message=str(e))
