"""AetherOS API — WebSocket Handler.

Manages WebSocket connections for real-time updates.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("api.websocket")


@dataclass
class WSMessage:
    """WebSocket message."""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: str = "event"
    channel: str = "system"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_json(self) -> str:
        return json.dumps({
            "id": self.msg_id,
            "type": self.msg_type,
            "channel": self.channel,
            "data": self.data,
            "timestamp": self.timestamp,
        })


class WebSocketManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Set[str]] = {}  # channel -> set of conn_ids
        self._message_history: deque = deque(maxlen=1000)
        self._lock = threading.Lock()

    def register_connection(self, conn_id: str, connection: Any) -> None:
        with self._lock:
            self._connections[conn_id] = connection
        logger.info(f"WebSocket connected: {conn_id}")

    def unregister_connection(self, conn_id: str) -> None:
        with self._lock:
            self._connections.pop(conn_id, None)
            for channel_subs in self._subscriptions.values():
                channel_subs.discard(conn_id)
        logger.info(f"WebSocket disconnected: {conn_id}")

    def subscribe(self, conn_id: str, channel: str) -> None:
        with self._lock:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = set()
            self._subscriptions[channel].add(conn_id)

    def broadcast(self, message: WSMessage) -> int:
        """Broadcast a message to all subscribers of its channel."""
        self._message_history.append(message)
        with self._lock:
            subscribers = self._subscriptions.get(message.channel, set())
            sent = 0
            for conn_id in subscribers:
                conn = self._connections.get(conn_id)
                if conn:
                    try:
                        # In real impl, would call conn.send(message.to_json())
                        sent += 1
                    except Exception as e:
                        logger.error(f"WS send error to {conn_id}: {e}")
            return sent

    def get_connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def get_channels(self) -> List[str]:
        with self._lock:
            return list(self._subscriptions.keys())
