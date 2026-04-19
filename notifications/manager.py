"""AetherOS Notifications   Notification Manager."""
from __future__ import annotations

import enum
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from notifications.channels import NotificationChannel, ConsoleChannel

logger = logging.getLogger("notifications.manager")


class NotificationPriority(enum.Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class Notification:
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    message: str = ""
    priority: NotificationPriority = NotificationPriority.NORMAL
    channel: str = "console"
    created_at: datetime = field(default_factory=datetime.utcnow)
    delivered: bool = False
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.notification_id,
            "title": self.title,
            "priority": self.priority.name,
            "channel": self.channel,
            "delivered": self.delivered,
            "created_at": self.created_at.isoformat(),
        }


class NotificationManager:
    """Manages notification delivery across channels."""

    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {
            "console": ConsoleChannel(),
        }
        self._history: deque = deque(maxlen=500)
        self._delivery_count = 0

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels[channel.name] = channel

    def send(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channel: str = "console",
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        ch = self._channels.get(channel)
        if not ch:
            logger.warning(f"Unknown channel: {channel}")
            return False

        notif = Notification(
            title=title, message=message, priority=priority,
            channel=channel, data=data or {},
        )
        success = ch.send(title, message, data)
        notif.delivered = success
        self._history.append(notif)
        if success:
            self._delivery_count += 1
        return success

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in list(self._history)[-limit:]]

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "channels": list(self._channels.keys()),
            "total_delivered": self._delivery_count,
            "history_size": len(self._history),
        }
