"""AetherOS Security — Honeypot Intrusion Detection System.

Creates and manages decoy files, directories, and services to detect,
trap, and log unauthorized access attempts. Integrates with the
blockchain audit ledger for tamper-proof evidence recording.

Honeypot Types:
    - File Honeypots: Decoy files that trigger alerts when accessed
    - Directory Honeypots: Bait directories with enticing names
    - Credential Honeypots: Fake credential files to detect theft
    - Service Honeypots: Simulated vulnerable services (ports)
    - Network Honeypots: Fake network shares and endpoints

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                  HoneypotOrchestrator                        │
    │  ┌──────────────┐  ┌────────────────┐  ┌────────────────┐  │
    │  │ File         │  │ Directory      │  │ Credential     │  │
    │  │ Honeypot     │  │ Honeypot       │  │ Honeypot       │  │
    │  └──────┬───────┘  └───────┬────────┘  └───────┬────────┘  │
    │         └──────────────────┼────────────────────┘           │
    │                   ┌────────▼────────┐                       │
    │                   │ Access Monitor  │                       │
    │                   │ & Event Engine  │                       │
    │                   └────────┬────────┘                       │
    │                   ┌────────▼────────┐                       │
    │                   │ Alert Manager   │→ Blockchain Ledger    │
    │                   └─────────────────┘                       │
    └──────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import stat
import string
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("security.honeypot")


# ═══════════════════════════════════════════════════════════════════════════
# Enums & Models
# ═══════════════════════════════════════════════════════════════════════════

class HoneypotType(Enum):
    """Types of honeypot traps."""
    FILE = "file"
    DIRECTORY = "directory"
    CREDENTIAL = "credential"
    SERVICE = "service"
    NETWORK_SHARE = "network_share"
    DATABASE = "database"
    API_ENDPOINT = "api_endpoint"


class TrapStatus(Enum):
    """Current status of a honeypot trap."""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    EXPIRED = "expired"
    COMPROMISED = "compromised"


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HoneypotTrap:
    """Definition of a single honeypot trap."""
    trap_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trap_type: HoneypotType = HoneypotType.FILE
    name: str = ""
    path: str = ""
    description: str = ""
    status: TrapStatus = TrapStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_checked: Optional[datetime] = None
    trigger_count: int = 0
    content_hash: str = ""
    alert_severity: AlertSeverity = AlertSeverity.HIGH
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_regenerate: bool = True
    ttl_hours: Optional[int] = None

    @property
    def is_expired(self) -> bool:
        if self.ttl_hours is None:
            return False
        delta = datetime.utcnow() - self.created_at
        return delta.total_seconds() > self.ttl_hours * 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trap_id": self.trap_id,
            "trap_type": self.trap_type.value,
            "name": self.name,
            "path": self.path,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "trigger_count": self.trigger_count,
            "alert_severity": self.alert_severity.value,
            "auto_regenerate": self.auto_regenerate,
        }


@dataclass
class HoneypotAlert:
    """Alert generated when a honeypot trap is triggered."""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trap_id: str = ""
    trap_type: HoneypotType = HoneypotType.FILE
    timestamp: datetime = field(default_factory=datetime.utcnow)
    severity: AlertSeverity = AlertSeverity.HIGH
    description: str = ""
    source_info: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    is_acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "trap_id": self.trap_id,
            "trap_type": self.trap_type.value,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "description": self.description,
            "source_info": self.source_info,
            "evidence": self.evidence,
            "is_acknowledged": self.is_acknowledged,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Bait Content Generators
# ═══════════════════════════════════════════════════════════════════════════

class BaitContentGenerator:
    """Generates realistic-looking decoy content for honeypot traps."""

    FAKE_PASSWORDS_DB = """# Internal Password Database - CONFIDENTIAL
# Last Updated: {date}
# DO NOT SHARE - Admin Eyes Only

[production-servers]
db-master.internal    admin       Pr0d@Dm1n#2025!
db-replica-01         readonly    R3pl1ca$ecure99
web-proxy-01          root        Pr0xy@cce$$123

[development]
dev-jenkins.local     jenkins     J3nk1ns@Dev2025
staging-api.local     deployer    $tag1ng_D3ploy!
ci-runner-01          gitlab-ci   C1Runn3r#Token99

[cloud-services]
aws-console           iam-admin   AWS@dm1n!Pr0d2025
gcp-project           svc-acct    GCP$vcAcct#Key42
azure-portal          admin       Azur3P0rtal!2025

[vpn-access]
corp-vpn.company.com  vpn-user    VPN@cc3$$2025!
remote-gateway        admin       G4tew4y#Admin99
"""

    FAKE_SSH_KEYS = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtz
c2gtZWQyNTUxOQAAACDa3F8KzTxKj4x9l2KvG8mNpYqrZ9JzF1xA2hBnK9qmDQ
AAAJhF7ZqzRe2as0AAAAtzc2gtZWQyNTUxOQAAACDa3F8KzTxKj4x9l2KvG8mNpY
qrZ9JzF1xA2hBnK9qmDQAAAECqQE5nLB7PIJzGl1lKZmFxFJ8dN5qlhH2Ka0E5
{more_fake_key_data}
-----END OPENSSH PRIVATE KEY-----
"""

    FAKE_ENV_FILE = """# Environment Configuration - Production
# Auto-generated: {date}

DATABASE_URL=postgresql://admin:Pr0d@Dm1n#2025@db.internal:5432/production
REDIS_URL=redis://:R3d1s$ecure@cache.internal:6379/0
SECRET_KEY=sk_live_aetheros_{random_hex}
API_KEY=ak_prod_{random_hex}
JWT_SECRET={random_hex_long}
STRIPE_KEY=sk_live_51Hq{random_alnum}
AWS_ACCESS_KEY_ID=AKIA{random_upper}
AWS_SECRET_ACCESS_KEY={random_hex_long}
SMTP_PASSWORD=Sm7p@Pr0d2025!
ENCRYPTION_KEY={random_hex_long}
GITHUB_TOKEN=ghp_{random_alnum}
SLACK_WEBHOOK=https://hooks.slack.com/services/T{random_alnum}/B{random_alnum}
"""

    FAKE_FINANCIAL_CSV = """Date,Account,Description,Amount,Balance
{date},CORP-001,Wire Transfer - Vendor Payment,-45000.00,1234567.89
{date},CORP-001,ACH Deposit - Client Invoice,125000.00,1359567.89
{date},CORP-002,Payroll Processing,-89750.00,567432.11
{date},CORP-001,Investment Return,15230.45,1374798.34
{date},CORP-003,Equipment Purchase,-34500.00,432932.11
"""

    BAIT_FILE_NAMES = [
        "passwords.txt", "credentials.csv", "secret_keys.env",
        ".env.production", "ssh_keys_backup.txt", "api_tokens.json",
        "financial_report_2025.csv", "employee_data.xlsx",
        "database_backup.sql", "master_key.pem",
        "vpn_config.ovpn", "admin_access.conf",
        "internal_ips.txt", "server_inventory.yaml",
        "encryption_keys.json", "wallet_seed.txt",
        "recovery_codes.txt", "oauth_secrets.json",
    ]

    BAIT_DIR_NAMES = [
        "backups", ".secret", "confidential", "admin_tools",
        "internal_docs", "financial", "hr_data", "credentials",
        "ssl_certs", "private_keys", "database_dumps",
        "customer_data", "legal", "executive_reports",
        "security_audit", "penetration_test_results",
    ]

    @classmethod
    def generate_content(cls, content_type: str = "passwords") -> str:
        """Generate realistic bait content."""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        random_hex = hashlib.md5(os.urandom(16)).hexdigest()[:20]
        random_hex_long = hashlib.sha256(os.urandom(32)).hexdigest()
        random_alnum = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
        random_upper = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

        templates = {
            "passwords": cls.FAKE_PASSWORDS_DB,
            "ssh_keys": cls.FAKE_SSH_KEYS,
            "env": cls.FAKE_ENV_FILE,
            "financial": cls.FAKE_FINANCIAL_CSV,
        }

        template = templates.get(content_type, cls.FAKE_PASSWORDS_DB)
        content = template.format(
            date=now,
            random_hex=random_hex,
            random_hex_long=random_hex_long,
            random_alnum=random_alnum,
            random_upper=random_upper,
            more_fake_key_data=random_hex_long[:40],
        )
        return content

    @classmethod
    def get_random_file_name(cls) -> str:
        return random.choice(cls.BAIT_FILE_NAMES)

    @classmethod
    def get_random_dir_name(cls) -> str:
        return random.choice(cls.BAIT_DIR_NAMES)


# ═══════════════════════════════════════════════════════════════════════════
# File Honeypot
# ═══════════════════════════════════════════════════════════════════════════

class FileHoneypot:
    """Creates and monitors decoy files."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._traps: Dict[str, HoneypotTrap] = {}
        self._lock = threading.Lock()

    def create_trap(
        self,
        name: Optional[str] = None,
        content_type: str = "passwords",
        subdirectory: str = "",
        alert_severity: AlertSeverity = AlertSeverity.HIGH,
    ) -> HoneypotTrap:
        """Create a decoy file trap."""
        name = name or BaitContentGenerator.get_random_file_name()
        content = BaitContentGenerator.generate_content(content_type)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        trap_dir = os.path.join(self.base_dir, subdirectory) if subdirectory else self.base_dir
        os.makedirs(trap_dir, exist_ok=True)
        filepath = os.path.join(trap_dir, name)

        try:
            with open(filepath, "w") as f:
                f.write(content)
            # Make it look tempting but track access
            os.chmod(filepath, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as e:
            logger.error(f"Failed to create file honeypot at {filepath}: {e}")

        trap = HoneypotTrap(
            trap_type=HoneypotType.FILE,
            name=name,
            path=filepath,
            description=f"Decoy {content_type} file",
            content_hash=content_hash,
            alert_severity=alert_severity,
            metadata={"content_type": content_type, "size": len(content)},
        )

        with self._lock:
            self._traps[trap.trap_id] = trap

        logger.info(f"File honeypot created: {filepath}")
        return trap

    def check_trap(self, trap_id: str) -> Optional[HoneypotAlert]:
        """Check if a file trap has been accessed or modified."""
        with self._lock:
            trap = self._traps.get(trap_id)
            if not trap:
                return None

        trap.last_checked = datetime.utcnow()

        if not os.path.exists(trap.path):
            # File was deleted — definitely suspicious
            alert = HoneypotAlert(
                trap_id=trap_id,
                trap_type=HoneypotType.FILE,
                severity=AlertSeverity.CRITICAL,
                description=f"Honeypot file DELETED: {trap.path}",
                evidence={"original_hash": trap.content_hash, "action": "deleted"},
            )
            trap.status = TrapStatus.TRIGGERED
            trap.trigger_count += 1
            return alert

        # Check for modification
        try:
            with open(trap.path, "r") as f:
                current_content = f.read()
            current_hash = hashlib.sha256(current_content.encode()).hexdigest()
            if current_hash != trap.content_hash:
                alert = HoneypotAlert(
                    trap_id=trap_id,
                    trap_type=HoneypotType.FILE,
                    severity=AlertSeverity.HIGH,
                    description=f"Honeypot file MODIFIED: {trap.path}",
                    evidence={
                        "original_hash": trap.content_hash,
                        "current_hash": current_hash,
                        "action": "modified",
                    },
                )
                trap.status = TrapStatus.TRIGGERED
                trap.trigger_count += 1
                return alert

            # Check access time
            stat_info = os.stat(trap.path)
            atime = datetime.fromtimestamp(stat_info.st_atime)
            if trap.last_checked and atime > trap.last_checked:
                alert = HoneypotAlert(
                    trap_id=trap_id,
                    trap_type=HoneypotType.FILE,
                    severity=AlertSeverity.MEDIUM,
                    description=f"Honeypot file ACCESSED: {trap.path}",
                    evidence={
                        "access_time": atime.isoformat(),
                        "action": "read",
                    },
                )
                trap.trigger_count += 1
                return alert

        except Exception as e:
            logger.error(f"Error checking file trap {trap_id}: {e}")

        return None

    def list_traps(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in self._traps.values()]

    def remove_trap(self, trap_id: str) -> bool:
        with self._lock:
            trap = self._traps.pop(trap_id, None)
        if trap and os.path.exists(trap.path):
            try:
                os.remove(trap.path)
            except OSError:
                pass
            return True
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Directory Honeypot
# ═══════════════════════════════════════════════════════════════════════════

class DirectoryHoneypot:
    """Creates and monitors decoy directories."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._traps: Dict[str, HoneypotTrap] = {}
        self._file_honeypot = FileHoneypot(base_dir)
        self._lock = threading.Lock()

    def create_trap(
        self,
        name: Optional[str] = None,
        depth: int = 2,
        files_per_dir: int = 3,
    ) -> HoneypotTrap:
        """Create a decoy directory with nested structure."""
        name = name or BaitContentGenerator.get_random_dir_name()
        dir_path = os.path.join(self.base_dir, name)
        os.makedirs(dir_path, exist_ok=True)

        # Create nested structure
        content_types = ["passwords", "ssh_keys", "env", "financial"]
        created_files = []

        for d in range(depth):
            sub_name = BaitContentGenerator.get_random_dir_name()
            sub_path = os.path.join(dir_path, sub_name) if d > 0 else dir_path
            os.makedirs(sub_path, exist_ok=True)

            for _ in range(files_per_dir):
                ct = random.choice(content_types)
                file_trap = self._file_honeypot.create_trap(
                    content_type=ct, subdirectory=os.path.relpath(sub_path, self.base_dir)
                )
                created_files.append(file_trap.trap_id)

        # Hash the directory listing for change detection
        listing = sorted(os.listdir(dir_path))
        listing_hash = hashlib.sha256(json.dumps(listing).encode()).hexdigest()

        trap = HoneypotTrap(
            trap_type=HoneypotType.DIRECTORY,
            name=name,
            path=dir_path,
            description=f"Decoy directory with {len(created_files)} bait files",
            content_hash=listing_hash,
            metadata={"file_traps": created_files, "depth": depth},
        )

        with self._lock:
            self._traps[trap.trap_id] = trap

        logger.info(f"Directory honeypot created: {dir_path} ({len(created_files)} files)")
        return trap

    def check_all(self) -> List[HoneypotAlert]:
        """Check all directory traps and their file children."""
        alerts = []
        with self._lock:
            trap_ids = list(self._traps.keys())

        for tid in trap_ids:
            trap = self._traps.get(tid)
            if not trap:
                continue

            # Check directory listing changes
            if os.path.exists(trap.path):
                current_listing = sorted(os.listdir(trap.path))
                current_hash = hashlib.sha256(json.dumps(current_listing).encode()).hexdigest()
                if current_hash != trap.content_hash:
                    alert = HoneypotAlert(
                        trap_id=tid,
                        trap_type=HoneypotType.DIRECTORY,
                        severity=AlertSeverity.HIGH,
                        description=f"Directory honeypot MODIFIED: {trap.path}",
                        evidence={"action": "listing_changed"},
                    )
                    alerts.append(alert)
                    trap.trigger_count += 1
            else:
                alert = HoneypotAlert(
                    trap_id=tid,
                    trap_type=HoneypotType.DIRECTORY,
                    severity=AlertSeverity.CRITICAL,
                    description=f"Directory honeypot DELETED: {trap.path}",
                )
                alerts.append(alert)

            # Check child file traps
            for ftid in trap.metadata.get("file_traps", []):
                file_alert = self._file_honeypot.check_trap(ftid)
                if file_alert:
                    alerts.append(file_alert)

        return alerts

    def list_traps(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in self._traps.values()]


# ═══════════════════════════════════════════════════════════════════════════
# Credential Honeypot
# ═══════════════════════════════════════════════════════════════════════════

class CredentialHoneypot:
    """Creates fake credential files that alert when used or accessed."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._traps: Dict[str, HoneypotTrap] = {}
        self._canary_tokens: Dict[str, str] = {}  # token → trap_id
        self._lock = threading.Lock()

    def create_canary_credentials(
        self,
        service_name: str = "internal-api",
        username: str = "admin",
    ) -> HoneypotTrap:
        """Create canary credentials that trigger an alert when used."""
        token = f"canary_{hashlib.md5(os.urandom(16)).hexdigest()[:16]}"
        fake_password = f"{''.join(random.choices(string.ascii_letters + string.digits, k=16))}!"

        content = json.dumps({
            "service": service_name,
            "credentials": {
                "username": username,
                "password": fake_password,
                "api_key": token,
                "endpoint": f"https://{service_name}.internal.aetheros.io/api/v1",
            },
            "last_rotated": datetime.utcnow().isoformat(),
            "notes": "Production credentials — rotate quarterly",
        }, indent=2)

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        filepath = os.path.join(self.base_dir, f".{service_name}_creds.json")
        os.makedirs(self.base_dir, exist_ok=True)

        try:
            with open(filepath, "w") as f:
                f.write(content)
        except OSError as e:
            logger.error(f"Failed to create credential honeypot: {e}")

        trap = HoneypotTrap(
            trap_type=HoneypotType.CREDENTIAL,
            name=f"{service_name}_credentials",
            path=filepath,
            content_hash=content_hash,
            alert_severity=AlertSeverity.CRITICAL,
            metadata={
                "service": service_name,
                "canary_token": token,
                "username": username,
            },
        )

        with self._lock:
            self._traps[trap.trap_id] = trap
            self._canary_tokens[token] = trap.trap_id

        logger.info(f"Credential honeypot created for service '{service_name}'")
        return trap

    def check_token_usage(self, token: str) -> Optional[HoneypotAlert]:
        """Check if a canary token has been used."""
        with self._lock:
            trap_id = self._canary_tokens.get(token)
            if not trap_id:
                return None
            trap = self._traps.get(trap_id)
            if not trap:
                return None

        alert = HoneypotAlert(
            trap_id=trap_id,
            trap_type=HoneypotType.CREDENTIAL,
            severity=AlertSeverity.CRITICAL,
            description=f"CANARY TOKEN USED: {trap.name}",
            evidence={
                "token": token[:8] + "...",
                "service": trap.metadata.get("service"),
            },
        )
        trap.status = TrapStatus.COMPROMISED
        trap.trigger_count += 1
        return alert


# ═══════════════════════════════════════════════════════════════════════════
# Alert Manager
# ═══════════════════════════════════════════════════════════════════════════

class HoneypotAlertManager:
    """Manages honeypot alerts, notifications, and response actions."""

    def __init__(self):
        self._alerts: deque = deque(maxlen=1000)
        self._callbacks: List[Callable[[HoneypotAlert], None]] = []
        self._severity_counts: Dict[str, int] = {s.value: 0 for s in AlertSeverity}
        self._lock = threading.Lock()

    def process_alert(self, alert: HoneypotAlert) -> None:
        """Process a new honeypot alert."""
        with self._lock:
            self._alerts.append(alert)
            self._severity_counts[alert.severity.value] += 1

        logger.warning(
            f"HONEYPOT ALERT [{alert.severity.value.upper()}]: {alert.description}"
        )

        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    def register_callback(self, callback: Callable[[HoneypotAlert], None]) -> None:
        self._callbacks.append(callback)

    def get_alerts(self, limit: int = 50, severity: Optional[AlertSeverity] = None) -> List[Dict[str, Any]]:
        with self._lock:
            alerts = list(self._alerts)
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return [a.to_dict() for a in alerts[-limit:]]

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_alerts": len(self._alerts),
                "severity_counts": dict(self._severity_counts),
                "unacknowledged": sum(1 for a in self._alerts if not a.is_acknowledged),
            }


# ═══════════════════════════════════════════════════════════════════════════
# Honeypot Orchestrator (Main Interface)
# ═══════════════════════════════════════════════════════════════════════════

class HoneypotOrchestrator:
    """Main honeypot management system.

    Orchestrates the creation, monitoring, and alerting for all honeypot types.

    Usage:
        orchestrator = HoneypotOrchestrator()
        orchestrator.deploy_standard_traps()
        orchestrator.start_monitoring()
        # ...
        orchestrator.stop_monitoring()
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        monitoring_interval: float = 60.0,
        on_alert: Optional[Callable[[HoneypotAlert], None]] = None,
    ):
        self.base_dir = base_dir or os.path.expanduser("~/.aetheros/honeypots")
        self.monitoring_interval = monitoring_interval
        self.file_honeypot = FileHoneypot(self.base_dir)
        self.dir_honeypot = DirectoryHoneypot(self.base_dir)
        self.cred_honeypot = CredentialHoneypot(self.base_dir)
        self.alert_manager = HoneypotAlertManager()
        if on_alert:
            self.alert_manager.register_callback(on_alert)
        self._is_monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._deployed_traps: List[str] = []
        logger.info("HoneypotOrchestrator initialized")

    def deploy_standard_traps(self) -> Dict[str, int]:
        """Deploy a standard set of honeypot traps."""
        counts = {"files": 0, "directories": 0, "credentials": 0}

        # File honeypots
        for content_type in ["passwords", "ssh_keys", "env", "financial"]:
            trap = self.file_honeypot.create_trap(content_type=content_type)
            self._deployed_traps.append(trap.trap_id)
            counts["files"] += 1

        # Extra file traps with enticing names
        for name in ["admin_passwords.txt", ".env.production", "backup_keys.pem"]:
            trap = self.file_honeypot.create_trap(name=name, content_type="passwords")
            self._deployed_traps.append(trap.trap_id)
            counts["files"] += 1

        # Directory honeypots
        for dir_name in ["backups", "confidential", "admin_tools"]:
            trap = self.dir_honeypot.create_trap(name=dir_name, depth=2, files_per_dir=3)
            self._deployed_traps.append(trap.trap_id)
            counts["directories"] += 1

        # Credential honeypots
        for service in ["internal-api", "database-admin", "cloud-console"]:
            trap = self.cred_honeypot.create_canary_credentials(service_name=service)
            self._deployed_traps.append(trap.trap_id)
            counts["credentials"] += 1

        logger.info(f"Standard traps deployed: {counts}")
        return counts

    def start_monitoring(self) -> None:
        """Start background monitoring of all traps."""
        self._is_monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Honeypot monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._is_monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10.0)
        logger.info("Honeypot monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._is_monitoring:
            try:
                # Check file traps
                for trap_info in self.file_honeypot.list_traps():
                    alert = self.file_honeypot.check_trap(trap_info["trap_id"])
                    if alert:
                        self.alert_manager.process_alert(alert)

                # Check directory traps
                dir_alerts = self.dir_honeypot.check_all()
                for alert in dir_alerts:
                    self.alert_manager.process_alert(alert)

                time.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(5.0)

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_monitoring": self._is_monitoring,
            "base_dir": self.base_dir,
            "deployed_traps": len(self._deployed_traps),
            "file_traps": len(self.file_honeypot.list_traps()),
            "dir_traps": len(self.dir_honeypot.list_traps()),
            "cred_traps": len(self.cred_honeypot._traps),
            "alerts": self.alert_manager.get_summary(),
        }
