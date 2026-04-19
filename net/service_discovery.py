"""Service Discovery   Registry for mesh services and capabilities."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("aetheros.net.discovery")


@dataclass
class ServiceEndpoint:
    """A registered service endpoint."""
    service_id: str = field(default_factory=lambda: f"svc-{uuid.uuid4().hex[:8]}")
    name: str = ""
    address: str = ""
    port: int = 0
    protocol: str = "tcp"
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    health_check_url: str = ""
    registered_at: float = field(default_factory=time.time)
    last_health_check: float = 0
    healthy: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "address": f"{self.address}:{self.port}",
            "protocol": self.protocol,
            "version": self.version,
            "healthy": self.healthy,
            "tags": self.tags,
        }


class ServiceRegistry:
    """Central service registry for the mesh network."""

    def __init__(self):
        self._services: dict[str, ServiceEndpoint] = {}
        self._by_name: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._watchers: dict[str, list] = {}

    def register(self, service: ServiceEndpoint) -> str:
        with self._lock:
            self._services[service.service_id] = service
            if service.name not in self._by_name:
                self._by_name[service.name] = []
            self._by_name[service.name].append(service.service_id)
            self._notify_watchers(service.name, "registered", service)
        logger.info(f"Service registered: {service.name} at {service.address}:{service.port}")
        return service.service_id

    def deregister(self, service_id: str) -> bool:
        with self._lock:
            service = self._services.pop(service_id, None)
            if service:
                if service.name in self._by_name:
                    self._by_name[service.name] = [
                        sid for sid in self._by_name[service.name] if sid != service_id
                    ]
                self._notify_watchers(service.name, "deregistered", service)
                return True
        return False

    def discover(self, name: str, healthy_only: bool = True) -> list[ServiceEndpoint]:
        with self._lock:
            sids = self._by_name.get(name, [])
            services = [self._services[sid] for sid in sids if sid in self._services]
            if healthy_only:
                services = [s for s in services if s.healthy]
            return services

    def discover_by_tag(self, tag: str) -> list[ServiceEndpoint]:
        with self._lock:
            return [s for s in self._services.values() if tag in s.tags]

    def update_health(self, service_id: str, healthy: bool) -> None:
        with self._lock:
            service = self._services.get(service_id)
            if service:
                service.healthy = healthy
                service.last_health_check = time.time()

    def watch(self, name: str, callback) -> None:
        if name not in self._watchers:
            self._watchers[name] = []
        self._watchers[name].append(callback)

    def _notify_watchers(self, name: str, event: str, service: ServiceEndpoint) -> None:
        for cb in self._watchers.get(name, []):
            try:
                cb(event, service)
            except Exception as e:
                logger.error(f"Watcher callback error: {e}")

    def get_all_services(self) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self._services.values()]

    def get_stats(self) -> dict:
        with self._lock:
            healthy = sum(1 for s in self._services.values() if s.healthy)
            return {
                "total_services": len(self._services),
                "healthy_services": healthy,
                "service_names": list(self._by_name.keys()),
            }
