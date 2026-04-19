"""Central event bus for inter-component communication."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("aetheros.core.events")


class EventType(Enum):
    # System lifecycle
    SYSTEM_BOOT = auto()
    SYSTEM_SHUTDOWN = auto()
    SYSTEM_ERROR = auto()

    # Task lifecycle
    TASK_CREATED = auto()
    TASK_STARTED = auto()
    TASK_PROGRESS = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    TASK_CANCELLED = auto()

    # Agent events
    AGENT_ACTIVATED = auto()
    AGENT_DEACTIVATED = auto()
    AGENT_MESSAGE = auto()

    # Security
    SECURITY_ALERT = auto()
    KILL_SWITCH_ENGAGED = auto()
    AUDIT_LOG = auto()

    # Model events
    MODEL_SWITCHED = auto()
    MODEL_ERROR = auto()

    # Memory events
    MEMORY_STORED = auto()
    MEMORY_RETRIEVED = auto()

    # GUI events
    GUI_LOG = auto()
    GUI_STATUS_UPDATE = auto()


@dataclass
class Event:
    """Represents a system event."""
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0


Listener = Callable[[Event], Coroutine[Any, Any, None]] | Callable[[Event], None]


class EventBus:
    """Publish-subscribe event bus with async support."""

    def __init__(self):
        self._listeners: dict[EventType, list[Listener]] = {}
        self._global_listeners: list[Listener] = []
        self._history: list[Event] = []
        self._max_history = 1000
        self._lock = asyncio.Lock() if asyncio.get_event_loop_policy() else None

    def subscribe(self, event_type: EventType, listener: Listener) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)
        logger.debug(f"Subscribed {listener.__name__} to {event_type.name}")

    def subscribe_all(self, listener: Listener) -> None:
        self._global_listeners.append(listener)

    def unsubscribe(self, event_type: EventType, listener: Listener) -> None:
        if event_type in self._listeners:
            self._listeners[event_type] = [
                l for l in self._listeners[event_type] if l != listener
            ]

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        listeners = self._listeners.get(event.event_type, []) + self._global_listeners
        for listener in listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Event listener error for {event.event_type.name}: {e}")

    def publish_sync(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        listeners = self._listeners.get(event.event_type, []) + self._global_listeners
        for listener in listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)
            except Exception as e:
                logger.error(f"Sync event listener error: {e}")

    def get_history(self, event_type: Optional[EventType] = None, last_n: int = 50) -> list[Event]:
        if event_type:
            filtered = [e for e in self._history if e.event_type == event_type]
            return filtered[-last_n:]
        return self._history[-last_n:]

    def clear_history(self) -> None:
        self._history.clear()
