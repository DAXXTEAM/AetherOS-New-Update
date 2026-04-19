"""Tests for AetherOS Diagnostics Module."""
import pytest
from diagnostics.health import HealthChecker, HealthStatus, ComponentHealth
from diagnostics.profiler import Profiler, ProfileSession
from diagnostics.debugger import DebugLogger, TraceCollector


class TestHealthChecker:
    def test_check_all(self):
        hc = HealthChecker()
        results = hc.check_all()
        assert "disk_space" in results
        assert "memory" in results
        assert "cpu_load" in results

    def test_overall_status(self):
        hc = HealthChecker()
        hc.check_all()
        status = hc.get_overall_status()
        assert status in HealthStatus

    def test_report(self):
        hc = HealthChecker()
        hc.check_all()
        report = hc.get_report()
        assert "overall" in report
        assert "components" in report


class TestProfiler:
    def test_timer(self):
        p = Profiler()
        p.start_timer("test_op")
        import time
        time.sleep(0.01)
        duration = p.stop_timer("test_op")
        assert duration > 0

    def test_stats(self):
        p = Profiler()
        for _ in range(5):
            p.start_timer("op")
            p.stop_timer("op")
        stats = p.get_stats("op")
        assert stats["count"] == 5

    def test_session(self):
        p = Profiler()
        sid = p.start_session("test")
        p.start_timer("a")
        p.stop_timer("a")
        session = p.end_session()
        assert session is not None
        assert len(session.results) == 1


class TestTraceCollector:
    def test_trace(self):
        tc = TraceCollector()
        tc.start()
        tc.trace("test", "action1")
        tc.trace("test", "action2")
        traces = tc.get_traces()
        assert len(traces) == 2

    def test_inactive(self):
        tc = TraceCollector()
        tc.trace("test", "action")
        assert len(tc.get_traces()) == 0


class TestDebugLogger:
    def test_capture_snapshot(self):
        dl = DebugLogger()
        snap = dl.capture_snapshot("test", {"key": "value"}, "test message")
        assert snap.component == "test"
        snaps = dl.get_snapshots()
        assert len(snaps) == 1
