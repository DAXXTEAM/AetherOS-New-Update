"""Task definitions and lifecycle management."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional


class TaskStatus(Enum):
    PENDING = auto()
    PLANNING = auto()
    EXECUTING = auto()
    AUDITING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class TaskStep:
    """A single step within a task plan."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    tool_name: Optional[str] = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    requires_approval: bool = False
    approved: bool = False

    def mark_started(self) -> None:
        self.status = TaskStatus.EXECUTING
        self.started_at = datetime.now()

    def mark_completed(self, result: str) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class Task:
    """Represents a user task to be processed by the agent system."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    objective: str = ""
    context: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parent_task_id: Optional[str] = None
    subtasks: list[str] = field(default_factory=list)

    def add_step(self, description: str, tool_name: Optional[str] = None,
                 tool_args: Optional[dict] = None, requires_approval: bool = False) -> TaskStep:
        step = TaskStep(
            description=description,
            tool_name=tool_name,
            tool_args=tool_args or {},
            requires_approval=requires_approval,
        )
        self.steps.append(step)
        return step

    def mark_started(self) -> None:
        self.status = TaskStatus.EXECUTING
        self.started_at = datetime.now()

    def mark_completed(self, result: str) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        return completed / len(self.steps)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "status": self.status.name,
            "progress": self.progress,
            "steps": len(self.steps),
            "completed_steps": sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED),
            "created_at": self.created_at.isoformat(),
            "duration": self.duration_seconds,
        }


@dataclass
class TaskResult:
    """Result of a completed task."""
    task_id: str
    success: bool
    output: str = ""
    artifacts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
