"""AetherOS Diagnostics — Performance Profiler.

Code profiling and performance measurement utilities.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("diagnostics.profiler")


@dataclass
class ProfileResult:
    """Result of a profiling measurement."""
    name: str
    duration_ms: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "metadata": self.metadata,
        }


@dataclass
class ProfileSession:
    """A profiling session with multiple measurements."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    results: List[ProfileResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    @property
    def total_duration_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "measurements": len(self.results),
            "total_ms": round(self.total_duration_ms, 3),
            "results": [r.to_dict() for r in self.results],
        }


class Profiler:
    """Performance profiler with timing and statistics."""

    def __init__(self):
        self._active_timers: Dict[str, float] = {}
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._sessions: Dict[str, ProfileSession] = {}
        self._current_session: Optional[ProfileSession] = None

    def start_timer(self, name: str) -> None:
        self._active_timers[name] = time.perf_counter()

    def stop_timer(self, name: str) -> float:
        start = self._active_timers.pop(name, None)
        if start is None:
            return 0.0
        duration_ms = (time.perf_counter() - start) * 1000
        self._history[name].append(duration_ms)
        if self._current_session:
            self._current_session.results.append(
                ProfileResult(name=name, duration_ms=duration_ms)
            )
        return duration_ms

    def measure(self, name: str):
        """Context manager for timing a block."""
        return _TimerContext(self, name)

    def start_session(self, name: str = "") -> str:
        session = ProfileSession(name=name)
        self._sessions[session.session_id] = session
        self._current_session = session
        return session.session_id

    def end_session(self) -> Optional[ProfileSession]:
        session = self._current_session
        if session:
            session.ended_at = datetime.utcnow()
            self._current_session = None
        return session

    def get_stats(self, name: str) -> Dict[str, float]:
        timings = self._history.get(name, [])
        if not timings:
            return {}
        return {
            "count": len(timings),
            "avg_ms": sum(timings) / len(timings),
            "min_ms": min(timings),
            "max_ms": max(timings),
            "total_ms": sum(timings),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        return {name: self.get_stats(name) for name in self._history}


class _TimerContext:
    def __init__(self, profiler: Profiler, name: str):
        self.profiler = profiler
        self.name = name

    def __enter__(self):
        self.profiler.start_timer(self.name)
        return self

    def __exit__(self, *args):
        self.profiler.stop_timer(self.name)
