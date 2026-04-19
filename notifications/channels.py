"""AetherOS Notifications   Delivery Channels."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

logger = logging.getLogger("notifications.channels")


class NotificationChannel(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def send(self, title: str, message: str, data: Dict[str, Any] = None) -> bool: ...


class ConsoleChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "console"

    def send(self, title: str, message: str, data: Dict[str, Any] = None) -> bool:
        logger.info(f"[NOTIFICATION] {title}: {message}")
        return True


class EmailChannel(NotificationChannel):
    def __init__(self, smtp_host: str = "", smtp_port: int = 587):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    @property
    def name(self) -> str:
        return "email"

    def send(self, title: str, message: str, data: Dict[str, Any] = None) -> bool:
        logger.info(f"[EMAIL] {title}: {message} (simulated)")
        return True


class WebhookChannel(NotificationChannel):
    def __init__(self, url: str = ""):
        self.url = url

    @property
    def name(self) -> str:
        return "webhook"

    def send(self, title: str, message: str, data: Dict[str, Any] = None) -> bool:
        logger.info(f"[WEBHOOK   {self.url}] {title}: {message} (simulated)")
        return True
