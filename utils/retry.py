"""AetherOS Utils   Retry Logic."""
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type

logger = logging.getLogger("utils.retry")


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential: bool = True
    jitter: bool = True
    retry_on: tuple = (Exception,)

    def get_delay(self, attempt: int) -> float:
        if self.exponential:
            delay = self.base_delay * (2 ** attempt)
        else:
            delay = self.base_delay
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay


def retry_with_backoff(
    func: Callable,
    policy: Optional[RetryPolicy] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute a function with retry and exponential backoff."""
    policy = policy or RetryPolicy()
    last_error = None

    for attempt in range(policy.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except policy.retry_on as e:
            last_error = e
            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{policy.max_retries} for {func.__name__}: "
                    f"{e}. Waiting {delay:.1f}s"
                )
                time.sleep(delay)
            else:
                logger.error(f"All {policy.max_retries} retries exhausted for {func.__name__}")

    raise last_error
