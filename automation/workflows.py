"""AetherOS Automation   Workflow Engine.

Defines and executes multi-step automated workflows with
conditional branching, parallel execution, and error handling.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("automation.workflows")


class StepType(enum.Enum):
    TASK = "task"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    DELAY = "delay"
    LOOP = "loop"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    SCRIPT = "script"


class WorkflowStatus(enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    step_type: StepType = StepType.TASK
    handler: Optional[Callable] = None
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 300.0
    retry_count: int = 0
    max_retries: int = 3
    on_failure: str = "stop"  # stop, skip, retry
    next_steps: List[str] = field(default_factory=list)
    condition: Optional[str] = None
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def execute(self, context: Dict[str, Any]) -> Any:
        """Execute this step."""
        self.started_at = datetime.utcnow()
        self.status = "running"
        try:
            if self.handler:
                self.result = self.handler(context, self.params)
            elif self.step_type == StepType.DELAY:
                time.sleep(self.params.get("seconds", 1))
                self.result = True
            else:
                self.result = True

            self.status = "completed"
            self.completed_at = datetime.utcnow()
            return self.result
        except Exception as e:
            self.error = str(e)
            self.retry_count += 1
            if self.retry_count < self.max_retries and self.on_failure == "retry":
                self.status = "retrying"
                return self.execute(context)
            self.status = "failed"
            self.completed_at = datetime.utcnow()
            raise

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "type": self.step_type.value,
            "status": self.status,
            "timeout": self.timeout_seconds,
            "retries": f"{self.retry_count}/{self.max_retries}",
            "error": self.error,
        }


@dataclass
class Workflow:
    """A complete workflow definition."""
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.DRAFT
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == "completed")
        return completed / len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "status": self.status.value,
            "step_count": len(self.steps),
            "progress": round(self.progress * 100, 1),
            "steps": [s.to_dict() for s in self.steps],
        }


class WorkflowEngine:
    """Executes and manages workflows."""

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}
        self._execution_history: deque = deque(maxlen=100)
        self._lock = threading.Lock()
        logger.info("WorkflowEngine initialized")

    def register(self, workflow: Workflow) -> str:
        with self._lock:
            self._workflows[workflow.workflow_id] = workflow
        return workflow.workflow_id

    def execute(self, workflow_id: str) -> bool:
        """Execute a workflow synchronously."""
        with self._lock:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return False

        wf.status = WorkflowStatus.RUNNING
        wf.started_at = datetime.utcnow()

        for step in wf.steps:
            if wf.status == WorkflowStatus.CANCELLED:
                break
            try:
                if step.condition:
                    if not self._evaluate_condition(step.condition, wf.context):
                        step.status = "skipped"
                        continue
                result = step.execute(wf.context)
                wf.context[f"step_{step.step_id}_result"] = result
            except Exception as e:
                logger.error(f"Workflow step '{step.name}' failed: {e}")
                if step.on_failure == "stop":
                    wf.status = WorkflowStatus.FAILED
                    return False
                elif step.on_failure == "skip":
                    continue

        if wf.status != WorkflowStatus.FAILED:
            wf.status = WorkflowStatus.COMPLETED
        wf.completed_at = datetime.utcnow()
        self._execution_history.append(wf.to_dict())
        return wf.status == WorkflowStatus.COMPLETED

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple condition string against context."""
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return True

    def cancel(self, workflow_id: str) -> bool:
        with self._lock:
            wf = self._workflows.get(workflow_id)
            if wf:
                wf.status = WorkflowStatus.CANCELLED
                return True
            return False

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            wf = self._workflows.get(workflow_id)
            return wf.to_dict() if wf else None

    def list_workflows(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [wf.to_dict() for wf in self._workflows.values()]
