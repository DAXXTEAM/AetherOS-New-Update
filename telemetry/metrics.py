"""AetherOS Telemetry   Metrics Collection & Aggregation.

Collects system metrics including CPU, memory, disk, network usage,
and application-level metrics like task throughput, agent performance,
and security event rates.
"""
from __future__ import annotations

import enum
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("telemetry.metrics")


class MetricType(enum.Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    RATE = "rate"


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    metric_type: MetricType = MetricType.GAUGE
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "type": self.metric_type.value,
            "labels": self.labels,
            "unit": self.unit,
        }


@dataclass
class MetricAggregation:
    """Aggregated metric statistics."""
    name: str
    count: int = 0
    sum_val: float = 0.0
    min_val: float = float("inf")
    max_val: float = float("-inf")
    avg_val: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    period_seconds: float = 60.0

    def update(self, value: float) -> None:
        self.count += 1
        self.sum_val += value
        self.min_val = min(self.min_val, value)
        self.max_val = max(self.max_val, value)
        self.avg_val = self.sum_val / self.count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "sum": round(self.sum_val, 4),
            "min": round(self.min_val, 4) if self.min_val != float("inf") else None,
            "max": round(self.max_val, 4) if self.max_val != float("-inf") else None,
            "avg": round(self.avg_val, 4),
        }


class MetricsCollector:
    """Central metrics collection and aggregation engine.

    Collects both system-level and application-level metrics,
    stores time-series data, and provides aggregation queries.
    """

    def __init__(
        self,
        retention_seconds: float = 3600,
        collection_interval: float = 10.0,
    ):
        self.retention_seconds = retention_seconds
        self.collection_interval = collection_interval
        self._series: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._aggregations: Dict[str, MetricAggregation] = {}
        self._is_collecting = False
        self._collector_thread: Optional[threading.Thread] = None
        self._custom_collectors: List[Callable[[], List[MetricPoint]]] = []
        self._lock = threading.Lock()
        logger.info("MetricsCollector initialized")

    def start(self) -> None:
        self._is_collecting = True
        self._collector_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._collector_thread.start()
        logger.info("Metrics collection started")

    def stop(self) -> None:
        self._is_collecting = False
        if self._collector_thread:
            self._collector_thread.join(timeout=5.0)

    def _collection_loop(self) -> None:
        while self._is_collecting:
            try:
                self._collect_system_metrics()
                for collector in self._custom_collectors:
                    try:
                        points = collector()
                        for point in points:
                            self.record(point)
                    except Exception as e:
                        logger.error(f"Custom collector error: {e}")
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Collection loop error: {e}")

    def _collect_system_metrics(self) -> None:
        """Collect system-level metrics."""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            self.record(MetricPoint("system.cpu.user_time", usage.ru_utime, unit="seconds"))
            self.record(MetricPoint("system.cpu.system_time", usage.ru_stime, unit="seconds"))
            self.record(MetricPoint("system.memory.max_rss", usage.ru_maxrss, unit="kb"))
        except Exception:
            pass

        # Disk usage
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            self.record(MetricPoint("system.disk.total_bytes", total, unit="bytes"))
            self.record(MetricPoint("system.disk.used_bytes", used, unit="bytes"))
            self.record(MetricPoint("system.disk.free_bytes", free, unit="bytes"))
            if total > 0:
                self.record(MetricPoint("system.disk.usage_percent", used / total * 100, unit="percent"))
        except Exception:
            pass

        # Load average
        try:
            load = os.getloadavg()
            self.record(MetricPoint("system.load.1min", load[0]))
            self.record(MetricPoint("system.load.5min", load[1]))
            self.record(MetricPoint("system.load.15min", load[2]))
        except Exception:
            pass

    def record(self, point: MetricPoint) -> None:
        """Record a metric data point."""
        with self._lock:
            self._series[point.name].append(point)
            if point.name not in self._aggregations:
                self._aggregations[point.name] = MetricAggregation(name=point.name)
            self._aggregations[point.name].update(point.value)

    def record_value(self, name: str, value: float, **labels: str) -> None:
        """Shorthand to record a simple gauge value."""
        self.record(MetricPoint(name=name, value=value, labels=labels))

    def increment(self, name: str, amount: float = 1.0) -> None:
        """Increment a counter metric."""
        self.record(MetricPoint(name=name, value=amount, metric_type=MetricType.COUNTER))

    def get_series(self, name: str, last_seconds: float = 300) -> List[Dict[str, Any]]:
        """Get recent data points for a metric."""
        cutoff = time.time() - last_seconds
        with self._lock:
            points = self._series.get(name, [])
            return [p.to_dict() for p in points if p.timestamp >= cutoff]

    def get_aggregation(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            agg = self._aggregations.get(name)
            return agg.to_dict() if agg else None

    def get_all_aggregations(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {name: agg.to_dict() for name, agg in self._aggregations.items()}

    def register_collector(self, collector: Callable[[], List[MetricPoint]]) -> None:
        self._custom_collectors.append(collector)

    def get_metric_names(self) -> List[str]:
        with self._lock:
            return list(self._series.keys())

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_collecting": self._is_collecting,
                "metric_count": len(self._series),
                "total_points": sum(len(s) for s in self._series.values()),
                "custom_collectors": len(self._custom_collectors),
            }
