"""System state management for AetherOS."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from config.constants import STATUS_IDLE


@dataclass
class AgentState:
    """State of an individual agent."""
    name: str
    role: str
    status: str = STATUS_IDLE
    current_task_id: Optional[str] = None
    messages_processed: int = 0
    errors: int = 0
    last_active: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "current_task": self.current_task_id,
            "messages_processed": self.messages_processed,
            "errors": self.errors,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }


@dataclass
class SystemState:
    """Global system state, thread-safe."""
    status: str = STATUS_IDLE
    boot_time: datetime = field(default_factory=datetime.now)
    active_tasks: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, AgentState] = field(default_factory=dict)
    model_provider: str = "openai"
    model_name: str = "gpt-4o"
    kill_switch_active: bool = False
    total_tasks_completed: int = 0
    total_errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    def register_agent(self, name: str, role: str) -> None:
        with self._lock:
            self.agents[name] = AgentState(name=name, role=role)

    def update_agent(self, name: str, **kwargs) -> None:
        with self._lock:
            if name in self.agents:
                for k, v in kwargs.items():
                    if hasattr(self.agents[name], k):
                        setattr(self.agents[name], k, v)

    def add_task(self, task_id: str, task_data: dict) -> None:
        with self._lock:
            self.active_tasks[task_id] = task_data

    def remove_task(self, task_id: str) -> None:
        with self._lock:
            self.active_tasks.pop(task_id, None)
            self.total_tasks_completed += 1

    def increment_errors(self) -> None:
        with self._lock:
            self.total_errors += 1

    def engage_kill_switch(self) -> None:
        with self._lock:
            self.kill_switch_active = True
            self.status = "killed"

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "uptime_seconds": (datetime.now() - self.boot_time).total_seconds(),
                "active_tasks": len(self.active_tasks),
                "agents": {n: a.to_dict() for n, a in self.agents.items()},
                "model": f"{self.model_provider}/{self.model_name}",
                "kill_switch": self.kill_switch_active,
                "tasks_completed": self.total_tasks_completed,
                "total_errors": self.total_errors,
            }
