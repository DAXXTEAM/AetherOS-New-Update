"""Tests for AetherOS Telemetry Module."""
import pytest
import time
from telemetry.metrics import MetricsCollector, MetricPoint, MetricType, MetricAggregation
from telemetry.alerting import AlertEngine, AlertRule, AlertCondition, AlertSeverity, AlertState


class TestMetricPoint:
    def test_create(self):
        point = MetricPoint(name="test.metric", value=42.0)
        assert point.name == "test.metric"
        assert point.value == 42.0

    def test_to_dict(self):
        point = MetricPoint(name="cpu", value=0.75, unit="percent")
        d = point.to_dict()
        assert d["name"] == "cpu"
        assert d["value"] == 0.75


class TestMetricAggregation:
    def test_update(self):
        agg = MetricAggregation(name="test")
        agg.update(10.0)
        agg.update(20.0)
        agg.update(30.0)
        assert agg.count == 3
        assert agg.min_val == 10.0
        assert agg.max_val == 30.0
        assert abs(agg.avg_val - 20.0) < 0.01


class TestMetricsCollector:
    def test_record_and_query(self):
        mc = MetricsCollector()
        mc.record(MetricPoint("test.gauge", 42.0))
        mc.record(MetricPoint("test.gauge", 43.0))
        series = mc.get_series("test.gauge", last_seconds=60)
        assert len(series) == 2

    def test_increment(self):
        mc = MetricsCollector()
        mc.increment("test.counter")
        mc.increment("test.counter")
        agg = mc.get_aggregation("test.counter")
        assert agg is not None
        assert agg["count"] == 2

    def test_get_metric_names(self):
        mc = MetricsCollector()
        mc.record_value("metric_a", 1.0)
        mc.record_value("metric_b", 2.0)
        names = mc.get_metric_names()
        assert "metric_a" in names
        assert "metric_b" in names

    def test_stats(self):
        mc = MetricsCollector()
        stats = mc.stats
        assert "is_collecting" in stats
        assert stats["is_collecting"] is False


class TestAlertCondition:
    def test_greater_than(self):
        cond = AlertCondition("test", ">", 10.0)
        assert cond.evaluate(15.0)
        assert not cond.evaluate(5.0)

    def test_less_than(self):
        cond = AlertCondition("test", "<", 10.0)
        assert cond.evaluate(5.0)
        assert not cond.evaluate(15.0)

    def test_equal(self):
        cond = AlertCondition("test", "==", 10.0)
        assert cond.evaluate(10.0)
        assert not cond.evaluate(11.0)


class TestAlertEngine:
    def test_evaluate_fires(self):
        engine = AlertEngine()
        engine.add_rule(AlertRule(
            name="test_alert",
            condition=AlertCondition("test.metric", ">", 50.0),
            severity=AlertSeverity.WARNING,
            cooldown_seconds=0,
        ))
        notifications = engine.evaluate("test.metric", 100.0)
        assert len(notifications) >= 1
        assert notifications[0].rule_name == "test_alert"

    def test_evaluate_no_fire(self):
        engine = AlertEngine()
        engine.add_rule(AlertRule(
            name="test_alert",
            condition=AlertCondition("test.metric", ">", 50.0),
        ))
        notifications = engine.evaluate("test.metric", 25.0)
        assert len(notifications) == 0

    def test_cooldown(self):
        engine = AlertEngine()
        engine.add_rule(AlertRule(
            name="cooldown_test",
            condition=AlertCondition("test.metric", ">", 0),
            cooldown_seconds=3600,
        ))
        n1 = engine.evaluate("test.metric", 100.0)
        n2 = engine.evaluate("test.metric", 100.0)
        assert len(n1) >= 1
        assert len(n2) == 0  # Cooldown active

    def test_callback(self):
        engine = AlertEngine()
        received = []
        engine.register_callback(lambda n: received.append(n))
        engine.add_rule(AlertRule(
            name="cb_test",
            condition=AlertCondition("m", ">", 0),
            cooldown_seconds=0,
        ))
        engine.evaluate("m", 1.0)
        assert len(received) >= 1
