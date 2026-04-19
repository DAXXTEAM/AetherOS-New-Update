"""AetherOS Utils — Timing Utilities."""
import threading
import time
from collections import deque
from typing import Optional


class Timer:
    """Simple timer for measuring durations."""

    def __init__(self):
        self._start: Optional[float] = None
        self._elapsed: float = 0.0

    def start(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def stop(self) -> float:
        if self._start:
            self._elapsed = time.perf_counter() - self._start
            self._start = None
        return self._elapsed

    @property
    def elapsed_ms(self) -> float:
        if self._start:
            return (time.perf_counter() - self._start) * 1000
        return self._elapsed * 1000

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_time = time.time()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_time
            self._last_time = now
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def wait(self) -> None:
        while not self.acquire():
            time.sleep(0.01)

    @property
    def available_tokens(self) -> float:
        return self._tokens
