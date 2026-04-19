"""AetherOS Telemetry   Dashboard Data Provider.

Provides formatted data for the GUI dashboard widgets.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from telemetry.metrics import MetricsCollector


@dataclass
class ChartSeries:
    """Data series for chart rendering."""
    name: str
    data_points: List[Dict[str, float]] = field(default_factory=list)
    color: str = "#00ff88"
    chart_type: str = "line"


@dataclass
class WidgetData:
    """Data for a single dashboard widget."""
    widget_id: str
    title: str
    value: Any = None
    unit: str = ""
    trend: str = "stable"  # up, down, stable
    chart: Optional[ChartSeries] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DashboardDataProvider:
    """Provides data for dashboard rendering."""

    def __init__(self, metrics: Optional[MetricsCollector] = None):
        self.metrics = metrics or MetricsCollector()

    def get_system_overview(self) -> List[WidgetData]:
        widgets = []
        aggs = self.metrics.get_all_aggregations()

        load = aggs.get("system.load.1min", {})
        widgets.append(WidgetData(
            widget_id="cpu_load", title="CPU Load",
            value=round(load.get("avg", 0), 2), unit="avg",
        ))

        disk = aggs.get("system.disk.usage_percent", {})
        widgets.append(WidgetData(
            widget_id="disk_usage", title="Disk Usage",
            value=round(disk.get("avg", 0), 1), unit="%",
        ))

        mem = aggs.get("system.memory.max_rss", {})
        widgets.append(WidgetData(
            widget_id="memory", title="Memory (RSS)",
            value=round(mem.get("max", 0) / 1024, 1), unit="MB",
        ))

        return widgets

    def get_metric_chart(self, metric_name: str, period_seconds: float = 300) -> ChartSeries:
        points = self.metrics.get_series(metric_name, last_seconds=period_seconds)
        return ChartSeries(
            name=metric_name,
            data_points=[{"t": p["timestamp"], "v": p["value"]} for p in points],
        )
