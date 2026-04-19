"""Tests for AetherOS Utility Modules."""
import pytest
import time
from utils.hashing import HashUtils
from utils.formatting import FormatUtils
from utils.timing import Timer, RateLimiter
from utils.retry import RetryPolicy, retry_with_backoff


class TestHashUtils:
    def test_sha256(self):
        h = HashUtils.sha256("hello")
        assert len(h) == 64

    def test_hmac(self):
        h = HashUtils.hmac_sha256("key", "message")
        assert len(h) == 64

    def test_random_token(self):
        t1 = HashUtils.random_token()
        t2 = HashUtils.random_token()
        assert t1 != t2
        assert len(t1) == 64


class TestFormatUtils:
    def test_human_bytes(self):
        assert "1.0 KB" == FormatUtils.human_bytes(1024)
        assert "1.0 MB" == FormatUtils.human_bytes(1024 * 1024)

    def test_human_duration(self):
        assert "500ms" == FormatUtils.human_duration(0.5)
        assert "2.0m" == FormatUtils.human_duration(120)

    def test_truncate(self):
        assert FormatUtils.truncate("hello", 10) == "hello"
        assert len(FormatUtils.truncate("a" * 200, 50)) == 50

    def test_table(self):
        result = FormatUtils.table(["Name", "Age"], [["Alice", "30"]])
        assert "Alice" in result
        assert "Name" in result


class TestTimer:
    def test_basic(self):
        t = Timer()
        t.start()
        time.sleep(0.01)
        elapsed = t.stop()
        assert elapsed > 0

    def test_context_manager(self):
        with Timer() as t:
            time.sleep(0.01)
        assert t.elapsed_ms > 0


class TestRateLimiter:
    def test_acquire(self):
        rl = RateLimiter(rate=100, burst=5)
        assert rl.acquire()
        assert rl.acquire()


class TestRetryPolicy:
    def test_delay(self):
        policy = RetryPolicy(base_delay=1.0, exponential=True, jitter=False)
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 4.0

    def test_retry_success(self):
        call_count = [0]
        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("not yet")
            return "ok"

        result = retry_with_backoff(
            flaky, RetryPolicy(max_retries=5, base_delay=0.001, jitter=False, exponential=False)
        )
        assert result == "ok"
        assert call_count[0] == 3
