"""AetherOS Automation — Task Scheduler.

Cron-like scheduling for recurring tasks and workflows.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("automation.scheduler")


class CronParser:
    """Parses cron expressions for scheduling."""

    @staticmethod
    def parse(expression: str) -> Dict[str, List[int]]:
        """Parse a 5-field cron expression into lists of valid values."""
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")

        fields = ["minute", "hour", "day", "month", "weekday"]
        ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
        result = {}

        for i, (field_name, (lo, hi)) in enumerate(zip(fields, ranges)):
            result[field_name] = CronParser._parse_field(parts[i], lo, hi)

        return result

    @staticmethod
    def _parse_field(field: str, lo: int, hi: int) -> List[int]:
        if field == "*":
            return list(range(lo, hi + 1))

        values = set()
        for part in field.split(","):
            if "/" in part:
                base, step = part.split("/")
                step = int(step)
                start = lo if base == "*" else int(base)
                for v in range(start, hi + 1, step):
                    values.add(v)
            elif "-" in part:
                start, end = map(int, part.split("-"))
                for v in range(start, end + 1):
                    values.add(v)
            else:
                values.add(int(part))

        return sorted(v for v in values if lo <= v <= hi)

    @staticmethod
    def matches(expression: str, dt: datetime) -> bool:
        """Check if a datetime matches a cron expression."""
        parsed = CronParser.parse(expression)
        return (
            dt.minute in parsed["minute"]
            and dt.hour in parsed["hour"]
            and dt.day in parsed["day"]
            and dt.month in parsed["month"]
            and dt.weekday() in parsed["weekday"]
        )


@dataclass
class ScheduledTask:
    """A scheduled task with cron expression."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    cron_expression: str = "* * * * *"
    handler: Optional[Callable] = None
    is_enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    max_runs: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def should_run(self, now: datetime) -> bool:
        if not self.is_enabled:
            return False
        if self.max_runs and self.run_count >= self.max_runs:
            return False
        if self.last_run and (now - self.last_run).total_seconds() < 60:
            return False
        return CronParser.matches(self.cron_expression, now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "cron": self.cron_expression,
            "enabled": self.is_enabled,
            "run_count": self.run_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }


class TaskScheduler:
    """Cron-based task scheduler."""

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self._tasks: Dict[str, ScheduledTask] = {}
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def add_task(self, task: ScheduledTask) -> str:
        with self._lock:
            self._tasks[task.task_id] = task
        return task.task_id

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def start(self) -> None:
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("TaskScheduler started")

    def stop(self) -> None:
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_loop(self) -> None:
        while self._is_running:
            now = datetime.utcnow()
            with self._lock:
                tasks = list(self._tasks.values())
            for task in tasks:
                if task.should_run(now):
                    self._execute_task(task, now)
            time.sleep(self.check_interval)

    def _execute_task(self, task: ScheduledTask, now: datetime) -> None:
        try:
            if task.handler:
                task.handler()
            task.last_run = now
            task.run_count += 1
            logger.info(f"Scheduled task executed: {task.name}")
        except Exception as e:
            logger.error(f"Scheduled task '{task.name}' failed: {e}")

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in self._tasks.values()]
