"""Task scheduler for recurring and delayed task execution."""
from __future__ import annotations

import asyncio
import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Optional

from core.task import Task, TaskPriority

logger = logging.getLogger("aetheros.core.scheduler")


class ScheduleType(Enum):
    ONCE = auto()
    INTERVAL = auto()
    CRON = auto()


@dataclass(order=True)
class ScheduledTask:
    """A task scheduled for future execution."""
    next_run: float
    schedule_id: str = field(compare=False)
    task_factory: Callable[[], Task] = field(compare=False, repr=False)
    schedule_type: ScheduleType = field(compare=False, default=ScheduleType.ONCE)
    interval_seconds: float = field(compare=False, default=0)
    max_runs: int = field(compare=False, default=1)
    runs_completed: int = field(compare=False, default=0)
    enabled: bool = field(compare=False, default=True)
    created_at: float = field(compare=False, default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        if self.schedule_type == ScheduleType.ONCE:
            return self.runs_completed >= 1
        if self.max_runs > 0:
            return self.runs_completed >= self.max_runs
        return False


class TaskScheduler:
    """Simple task scheduler with priority queue."""

    def __init__(self, executor: Optional[Callable] = None):
        self._queue: list[ScheduledTask] = []
        self._tasks: dict[str, ScheduledTask] = {}
        self._executor = executor
        self._running = False
        self._lock = threading.Lock()
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"sched-{self._id_counter:04d}"

    def schedule_once(self, task_factory: Callable[[], Task],
                      delay_seconds: float = 0) -> str:
        """Schedule a one-time task."""
        sid = self._next_id()
        st = ScheduledTask(
            next_run=time.time() + delay_seconds,
            schedule_id=sid,
            task_factory=task_factory,
            schedule_type=ScheduleType.ONCE,
        )
        with self._lock:
            heapq.heappush(self._queue, st)
            self._tasks[sid] = st
        logger.info(f"Scheduled one-time task: {sid} (delay={delay_seconds}s)")
        return sid

    def schedule_interval(self, task_factory: Callable[[], Task],
                          interval_seconds: float, max_runs: int = 0,
                          initial_delay: float = 0) -> str:
        """Schedule a recurring task."""
        sid = self._next_id()
        st = ScheduledTask(
            next_run=time.time() + initial_delay,
            schedule_id=sid,
            task_factory=task_factory,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
        )
        with self._lock:
            heapq.heappush(self._queue, st)
            self._tasks[sid] = st
        logger.info(f"Scheduled interval task: {sid} (every {interval_seconds}s)")
        return sid

    def cancel(self, schedule_id: str) -> bool:
        """Cancel a scheduled task."""
        with self._lock:
            if schedule_id in self._tasks:
                self._tasks[schedule_id].enabled = False
                del self._tasks[schedule_id]
                return True
        return False

    def list_scheduled(self) -> list[dict]:
        """List all scheduled tasks."""
        with self._lock:
            return [
                {
                    "id": st.schedule_id,
                    "type": st.schedule_type.name,
                    "next_run": datetime.fromtimestamp(st.next_run).isoformat(),
                    "runs_completed": st.runs_completed,
                    "enabled": st.enabled,
                }
                for st in self._tasks.values()
                if not st.is_expired
            ]

    async def tick(self) -> list[Task]:
        """Process due tasks. Returns tasks ready for execution."""
        now = time.time()
        ready: list[Task] = []

        with self._lock:
            while self._queue and self._queue[0].next_run <= now:
                st = heapq.heappop(self._queue)
                if not st.enabled or st.is_expired:
                    continue

                try:
                    task = st.task_factory()
                    ready.append(task)
                    st.runs_completed += 1
                    logger.info(f"Scheduler: dispatching {st.schedule_id} (run #{st.runs_completed})")

                    if st.schedule_type == ScheduleType.INTERVAL and not st.is_expired:
                        st.next_run = now + st.interval_seconds
                        heapq.heappush(self._queue, st)
                except Exception as e:
                    logger.error(f"Scheduler task creation failed: {e}")

        return ready

    async def run_loop(self, check_interval: float = 1.0) -> None:
        """Run the scheduler loop."""
        self._running = True
        logger.info("Scheduler loop started")
        while self._running:
            tasks = await self.tick()
            if tasks and self._executor:
                for task in tasks:
                    try:
                        await self._executor(task)
                    except Exception as e:
                        logger.error(f"Scheduler executor error: {e}")
            await asyncio.sleep(check_interval)

    def stop(self) -> None:
        self._running = False
