"""AetherOS Telemetry — Alert Engine.

Threshold-based alerting on collected metrics with
configurable rules, conditions, and notification channels.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("telemetry.alerting")


class AlertSeverity(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(enum.Enum):
    OK = "ok"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class AlertCondition:
    """Condition that triggers an alert."""
    metric_name: str
    operator: str = ">"  # >, <, >=, <=, ==, !=
    threshold: float = 0.0
    duration_seconds: float = 0.0  # Must be true for this duration

    def evaluate(self, value: float) -> bool:
        ops = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        op_func = ops.get(self.operator, lambda a, b: False)
        return op_func(value, self.threshold)


@dataclass
class AlertRule:
    """An alert rule with conditions and notification config."""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    condition: AlertCondition = field(default_factory=AlertCondition)
    severity: AlertSeverity = AlertSeverity.WARNING
    is_enabled: bool = True
    cooldown_seconds: float = 300.0
    last_fired: Optional[float] = None
    state: AlertState = AlertState.OK


@dataclass
class AlertNotification:
    """A fired alert notification."""
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    rule_name: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    message: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "is_acknowledged": self.is_acknowledged,
        }


class AlertEngine:
    """Evaluates alert rules against current metrics and fires notifications."""

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._notifications: deque = deque(maxlen=500)
        self._callbacks: List[Callable[[AlertNotification], None]] = []
        self._lock = threading.Lock()
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        defaults = [
            AlertRule(
                name="high_cpu_load",
                condition=AlertCondition("system.load.1min", ">", 4.0),
                severity=AlertSeverity.WARNING,
                description="CPU load average > 4.0",
            ),
            AlertRule(
                name="disk_space_low",
                condition=AlertCondition("system.disk.usage_percent", ">", 90.0),
                severity=AlertSeverity.ERROR,
                description="Disk usage > 90%",
            ),
            AlertRule(
                name="high_memory",
                condition=AlertCondition("system.memory.max_rss", ">", 2_000_000),
                severity=AlertSeverity.WARNING,
                description="Memory usage > 2GB",
            ),
        ]
        for rule in defaults:
            self._rules[rule.rule_id] = rule

    def add_rule(self, rule: AlertRule) -> None:
        with self._lock:
            self._rules[rule.rule_id] = rule

    def evaluate(self, metric_name: str, value: float) -> List[AlertNotification]:
        """Evaluate all matching rules for a metric value."""
        notifications = []
        now = time.time()

        with self._lock:
            for rule in self._rules.values():
                if not rule.is_enabled:
                    continue
                if rule.condition.metric_name != metric_name:
                    continue
                if rule.condition.evaluate(value):
                    if rule.last_fired and (now - rule.last_fired) < rule.cooldown_seconds:
                        continue
                    rule.last_fired = now
                    rule.state = AlertState.FIRING
                    notif = AlertNotification(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=f"Alert: {rule.name} — {metric_name}={value} {rule.condition.operator} {rule.condition.threshold}",
                        metric_value=value,
                        threshold=rule.condition.threshold,
                    )
                    notifications.append(notif)
                    self._notifications.append(notif)
                elif rule.state == AlertState.FIRING:
                    rule.state = AlertState.RESOLVED

        for notif in notifications:
            for cb in self._callbacks:
                try:
                    cb(notif)
                except Exception as e:
                    logger.error(f"Alert callback error: {e}")

        return notifications

    def register_callback(self, callback: Callable[[AlertNotification], None]) -> None:
        self._callbacks.append(callback)

    def get_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in list(self._notifications)[-limit:]]

    def get_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"rule_id": r.rule_id, "name": r.name, "severity": r.severity.value,
                 "state": r.state.value, "enabled": r.is_enabled}
                for r in self._rules.values()
            ]
