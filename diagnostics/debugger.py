"""AetherOS Diagnostics   Debug Logging & Tracing.

Advanced debug logging with snapshot capture and trace collection.
"""
from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("diagnostics.debugger")


@dataclass
class DebugSnapshot:
    """System state snapshot for debugging."""
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    component: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "component": self.component,
            "state": self.state,
            "message": self.message,
            "has_trace": bool(self.stack_trace),
        }


class TraceCollector:
    """Collects execution traces for debugging."""

    def __init__(self, max_traces: int = 1000):
        self._traces: deque = deque(maxlen=max_traces)
        self._is_active = False

    def start(self) -> None:
        self._is_active = True

    def stop(self) -> None:
        self._is_active = False

    def trace(self, component: str, action: str, data: Optional[Dict] = None) -> None:
        if not self._is_active:
            return
        self._traces.append({
            "timestamp": datetime.utcnow().isoformat(),
            "component": component,
            "action": action,
            "data": data or {},
        })

    def get_traces(self, component: Optional[str] = None, limit: int = 50) -> List[Dict]:
        traces = list(self._traces)
        if component:
            traces = [t for t in traces if t["component"] == component]
        return traces[-limit:]

    def clear(self) -> None:
        self._traces.clear()


class DebugLogger:
    """Enhanced debug logging with snapshots and traces."""

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or os.path.expanduser("~/.aetheros/debug")
        self._snapshots: deque = deque(maxlen=500)
        self.tracer = TraceCollector()

    def capture_snapshot(
        self,
        component: str,
        state: Dict[str, Any],
        message: str = "",
        include_trace: bool = False,
    ) -> DebugSnapshot:
        snapshot = DebugSnapshot(
            component=component,
            state=state,
            message=message,
            stack_trace=traceback.format_stack() if include_trace else "",
        )
        self._snapshots.append(snapshot)
        return snapshot

    def get_snapshots(self, component: Optional[str] = None, limit: int = 20) -> List[Dict]:
        snaps = list(self._snapshots)
        if component:
            snaps = [s for s in snaps if s.component == component]
        return [s.to_dict() for s in snaps[-limit:]]

    def export_debug_bundle(self, filepath: Optional[str] = None) -> str:
        """Export all debug data to a JSON file."""
        filepath = filepath or os.path.join(
            self.persist_dir, f"debug_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {
            "exported_at": datetime.utcnow().isoformat(),
            "snapshots": [s.to_dict() for s in self._snapshots],
            "traces": self.tracer.get_traces(limit=500),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return filepath
