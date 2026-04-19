"""Security audit logging system."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

logger = logging.getLogger("aetheros.security.audit")


class AuditSeverity(Enum):
    INFO = auto()
    WARNING = auto()
    CRITICAL = auto()
    ALERT = auto()


class AuditCategory(Enum):
    COMMAND_EXECUTION = "command_execution"
    FILE_ACCESS = "file_access"
    NETWORK_ACCESS = "network_access"
    MODEL_INTERACTION = "model_interaction"
    AUTHENTICATION = "authentication"
    CONFIGURATION_CHANGE = "configuration_change"
    SECURITY_EVENT = "security_event"
    SYSTEM_EVENT = "system_event"


@dataclass
class AuditEntry:
    """A single audit log entry with integrity hash."""
    entry_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    category: AuditCategory = AuditCategory.SYSTEM_EVENT
    severity: AuditSeverity = AuditSeverity.INFO
    actor: str = "system"
    action: str = ""
    target: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    result: str = "success"
    previous_hash: str = ""
    entry_hash: str = ""

    def __post_init__(self):
        if not self.entry_id:
            self.entry_id = f"audit-{int(self.timestamp.timestamp() * 1000)}"

    def compute_hash(self, previous_hash: str = "") -> str:
        """Compute integrity hash for this entry."""
        self.previous_hash = previous_hash
        data = (
            f"{self.entry_id}|{self.timestamp.isoformat()}|{self.category.value}|"
            f"{self.severity.name}|{self.actor}|{self.action}|{self.target}|"
            f"{json.dumps(self.details, sort_keys=True)}|{self.result}|{previous_hash}"
        )
        self.entry_hash = hashlib.sha256(data.encode()).hexdigest()
        return self.entry_hash

    def to_dict(self) -> dict:
        return {
            "id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.name,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "details": self.details,
            "result": self.result,
            "hash": self.entry_hash,
        }


class AuditLogger:
    """Thread-safe audit logger with chain integrity."""

    def __init__(self, log_dir: Optional[str] = None, max_entries: int = 10000):
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._last_hash = "genesis"
        self._log_dir = log_dir or os.path.expanduser("~/.aetheros/audit")
        os.makedirs(self._log_dir, exist_ok=True)
        self._log_file = os.path.join(
            self._log_dir, f"audit_{datetime.now():%Y%m%d}.jsonl"
        )
        self._tamper_alerts: list[dict] = []

    def log(self, category: AuditCategory, action: str, target: str = "",
            actor: str = "system", severity: AuditSeverity = AuditSeverity.INFO,
            details: Optional[dict] = None, result: str = "success") -> AuditEntry:
        """Log an audit entry."""
        entry = AuditEntry(
            category=category,
            severity=severity,
            actor=actor,
            action=action,
            target=target,
            details=details or {},
            result=result,
        )

        with self._lock:
            entry.compute_hash(self._last_hash)
            self._last_hash = entry.entry_hash
            self._entries.append(entry)

            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

            # Write to file
            try:
                with open(self._log_file, "a") as f:
                    f.write(json.dumps(entry.to_dict()) + "\n")
            except OSError as e:
                logger.error(f"Failed to write audit log: {e}")

        if severity in (AuditSeverity.CRITICAL, AuditSeverity.ALERT):
            logger.warning(f"  AUDIT [{severity.name}] {actor}: {action}   {target}")

        return entry

    def log_command(self, command: str, actor: str = "executor",
                    result: str = "success", details: Optional[dict] = None) -> AuditEntry:
        return self.log(
            category=AuditCategory.COMMAND_EXECUTION,
            action="shell_execute",
            target=command[:200],
            actor=actor,
            details=details or {"full_command": command},
            result=result,
        )

    def log_file_access(self, path: str, operation: str, actor: str = "system",
                        result: str = "success") -> AuditEntry:
        return self.log(
            category=AuditCategory.FILE_ACCESS,
            action=operation,
            target=path,
            actor=actor,
            result=result,
        )

    def log_security_event(self, event: str, severity: AuditSeverity = AuditSeverity.WARNING,
                           details: Optional[dict] = None) -> AuditEntry:
        return self.log(
            category=AuditCategory.SECURITY_EVENT,
            action=event,
            severity=severity,
            details=details or {},
        )

    def verify_chain(self) -> tuple[bool, list[int]]:
        """Verify the integrity chain of all entries."""
        tampered = []
        prev_hash = "genesis"
        for i, entry in enumerate(self._entries):
            expected = entry.entry_hash
            entry.compute_hash(prev_hash)
            if entry.entry_hash != expected:
                tampered.append(i)
            prev_hash = entry.entry_hash
        return len(tampered) == 0, tampered

    def get_entries(self, category: Optional[AuditCategory] = None,
                    severity: Optional[AuditSeverity] = None,
                    actor: Optional[str] = None,
                    last_n: int = 100) -> list[dict]:
        """Query audit entries with filters."""
        with self._lock:
            filtered = self._entries
            if category:
                filtered = [e for e in filtered if e.category == category]
            if severity:
                filtered = [e for e in filtered if e.severity == severity]
            if actor:
                filtered = [e for e in filtered if e.actor == actor]
            return [e.to_dict() for e in filtered[-last_n:]]

    def get_stats(self) -> dict:
        """Get audit statistics."""
        with self._lock:
            by_category = {}
            by_severity = {}
            for e in self._entries:
                by_category[e.category.value] = by_category.get(e.category.value, 0) + 1
                by_severity[e.severity.name] = by_severity.get(e.severity.name, 0) + 1
            valid, tampered = self.verify_chain()
            return {
                "total_entries": len(self._entries),
                "by_category": by_category,
                "by_severity": by_severity,
                "chain_valid": valid,
                "tampered_entries": len(tampered),
                "log_file": self._log_file,
            }
