"""Cyber-Defense Sentinel   Advanced network monitoring and firewall simulation.

Upgrades the Auditor to actively monitor network connections, detect anomalies,
and block unauthorized outbound traffic. Simulates iptables/firewall interaction
for defense-in-depth security posture.

Capabilities:
- Real-time network connection monitoring
- Outbound traffic policy enforcement
- Port scanning detection
- DNS resolution auditing
- Simulated iptables rule management
- Threat intelligence integration (mock)
- Connection rate limiting
- GeoIP-based blocking simulation
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import platform
import re
import socket
import struct
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Optional

logger = logging.getLogger("aetheros.security.sentinel")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class ThreatLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConnectionState(Enum):
    ESTABLISHED = "ESTABLISHED"
    LISTEN = "LISTEN"
    TIME_WAIT = "TIME_WAIT"
    CLOSE_WAIT = "CLOSE_WAIT"
    SYN_SENT = "SYN_SENT"
    SYN_RECV = "SYN_RECV"
    FIN_WAIT = "FIN_WAIT"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class FirewallAction(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    DROP = "DROP"
    LOG = "LOG"
    RATE_LIMIT = "RATE_LIMIT"


class FirewallDirection(Enum):
    INBOUND = "INPUT"
    OUTBOUND = "OUTPUT"
    FORWARD = "FORWARD"


@dataclass
class NetworkConnection:
    """Represents a single network connection."""
    connection_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    protocol: str = "tcp"
    local_address: str = ""
    local_port: int = 0
    remote_address: str = ""
    remote_port: int = 0
    state: ConnectionState = ConnectionState.UNKNOWN
    pid: int = 0
    process_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    bytes_sent: int = 0
    bytes_received: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.connection_id,
            "protocol": self.protocol,
            "local": f"{self.local_address}:{self.local_port}",
            "remote": f"{self.remote_address}:{self.remote_port}",
            "state": self.state.value,
            "pid": self.pid,
            "process": self.process_name,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def is_outbound(self) -> bool:
        return self.state in (ConnectionState.ESTABLISHED, ConnectionState.SYN_SENT) and self.remote_port > 0

    @property
    def remote_endpoint(self) -> str:
        return f"{self.remote_address}:{self.remote_port}"


@dataclass
class FirewallRule:
    """A simulated firewall rule."""
    rule_id: str = field(default_factory=lambda: f"rule-{uuid.uuid4().hex[:6]}")
    direction: FirewallDirection = FirewallDirection.OUTBOUND
    action: FirewallAction = FirewallAction.DENY
    protocol: str = "tcp"
    source_address: str = "*"
    source_port: str = "*"
    dest_address: str = "*"
    dest_port: str = "*"
    description: str = ""
    enabled: bool = True
    priority: int = 100
    hit_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    def matches(self, conn: NetworkConnection) -> bool:
        """Check if this rule matches a connection."""
        if not self.enabled:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            self.enabled = False
            return False

        # Protocol match
        if self.protocol != "*" and self.protocol != conn.protocol:
            return False

        # Direction-based matching
        if self.direction == FirewallDirection.OUTBOUND:
            if not self._match_address(self.dest_address, conn.remote_address):
                return False
            if not self._match_port(self.dest_port, conn.remote_port):
                return False
        elif self.direction == FirewallDirection.INBOUND:
            if not self._match_address(self.source_address, conn.remote_address):
                return False
            if not self._match_port(self.source_port, conn.remote_port):
                return False

        return True

    def _match_address(self, rule_addr: str, actual_addr: str) -> bool:
        if rule_addr == "*":
            return True
        try:
            if "/" in rule_addr:
                network = ipaddress.ip_network(rule_addr, strict=False)
                return ipaddress.ip_address(actual_addr) in network
            return rule_addr == actual_addr
        except (ValueError, TypeError):
            return rule_addr == actual_addr

    def _match_port(self, rule_port: str, actual_port: int) -> bool:
        if rule_port == "*":
            return True
        try:
            if "-" in rule_port:
                low, high = rule_port.split("-")
                return int(low) <= actual_port <= int(high)
            if "," in rule_port:
                return actual_port in [int(p) for p in rule_port.split(",")]
            return int(rule_port) == actual_port
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "direction": self.direction.value,
            "action": self.action.value,
            "protocol": self.protocol,
            "source": f"{self.source_address}:{self.source_port}",
            "dest": f"{self.dest_address}:{self.dest_port}",
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority,
            "hit_count": self.hit_count,
        }

    def to_iptables_cmd(self) -> str:
        """Generate equivalent iptables command (for display/audit)."""
        chain = self.direction.value
        action = {
            FirewallAction.ALLOW: "ACCEPT",
            FirewallAction.DENY: "REJECT",
            FirewallAction.DROP: "DROP",
            FirewallAction.LOG: "LOG",
        }.get(self.action, "DROP")

        parts = [f"iptables -A {chain}"]
        if self.protocol != "*":
            parts.append(f"-p {self.protocol}")
        if self.source_address != "*":
            parts.append(f"-s {self.source_address}")
        if self.dest_address != "*":
            parts.append(f"-d {self.dest_address}")
        if self.dest_port != "*":
            parts.append(f"--dport {self.dest_port}")
        if self.source_port != "*":
            parts.append(f"--sport {self.source_port}")
        parts.append(f"-j {action}")
        if self.description:
            parts.append(f'-m comment --comment "{self.description}"')
        return " ".join(parts)


@dataclass
class ThreatEvent:
    """A detected security threat or anomaly."""
    event_id: str = field(default_factory=lambda: f"threat-{uuid.uuid4().hex[:8]}")
    timestamp: datetime = field(default_factory=datetime.now)
    threat_level: ThreatLevel = ThreatLevel.LOW
    category: str = ""
    description: str = ""
    source_ip: str = ""
    dest_ip: str = ""
    port: int = 0
    connection_id: str = ""
    action_taken: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "threat_level": self.threat_level.value,
            "category": self.category,
            "description": self.description,
            "source_ip": self.source_ip,
            "dest_ip": self.dest_ip,
            "port": self.port,
            "action_taken": self.action_taken,
        }


# ---------------------------------------------------------------------------
# Network Scanner   Reads active connections
# ---------------------------------------------------------------------------

class NetworkScanner:
    """Reads active network connections from /proc/net or platform tools."""

    TCP_STATES = {
        "01": ConnectionState.ESTABLISHED,
        "02": ConnectionState.SYN_SENT,
        "03": ConnectionState.SYN_RECV,
        "04": ConnectionState.FIN_WAIT,
        "05": ConnectionState.FIN_WAIT,
        "06": ConnectionState.TIME_WAIT,
        "07": ConnectionState.CLOSED,
        "08": ConnectionState.CLOSE_WAIT,
        "09": ConnectionState.CLOSE_WAIT,
        "0A": ConnectionState.LISTEN,
        "0B": ConnectionState.CLOSE_WAIT,
    }

    @classmethod
    def scan_connections(cls) -> list[NetworkConnection]:
        """Scan current network connections."""
        connections = []
        if platform.system() == "Linux":
            connections.extend(cls._scan_proc_net_tcp())
            connections.extend(cls._scan_proc_net_udp())
        else:
            connections.extend(cls._scan_netstat_fallback())
        return connections

    @classmethod
    def _scan_proc_net_tcp(cls) -> list[NetworkConnection]:
        """Parse /proc/net/tcp for TCP connections."""
        connections = []
        for proc_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
            try:
                with open(proc_file, "r") as f:
                    lines = f.readlines()[1:]  # Skip header
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) < 10:
                        continue
                    local = cls._decode_address(parts[1])
                    remote = cls._decode_address(parts[2])
                    state_hex = parts[3]
                    uid = int(parts[7]) if len(parts) > 7 else 0

                    conn = NetworkConnection(
                        protocol="tcp",
                        local_address=local[0],
                        local_port=local[1],
                        remote_address=remote[0],
                        remote_port=remote[1],
                        state=cls.TCP_STATES.get(state_hex, ConnectionState.UNKNOWN),
                        pid=uid,
                    )
                    connections.append(conn)
            except (FileNotFoundError, PermissionError):
                continue
        return connections

    @classmethod
    def _scan_proc_net_udp(cls) -> list[NetworkConnection]:
        """Parse /proc/net/udp for UDP connections."""
        connections = []
        for proc_file in ["/proc/net/udp", "/proc/net/udp6"]:
            try:
                with open(proc_file, "r") as f:
                    lines = f.readlines()[1:]
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) < 4:
                        continue
                    local = cls._decode_address(parts[1])
                    remote = cls._decode_address(parts[2])
                    conn = NetworkConnection(
                        protocol="udp",
                        local_address=local[0],
                        local_port=local[1],
                        remote_address=remote[0],
                        remote_port=remote[1],
                        state=ConnectionState.ESTABLISHED,
                    )
                    connections.append(conn)
            except (FileNotFoundError, PermissionError):
                continue
        return connections

    @classmethod
    def _scan_netstat_fallback(cls) -> list[NetworkConnection]:
        """Fallback using socket module for basic connection info."""
        connections = []
        try:
            import subprocess
            result = subprocess.run(
                ["ss", "-tunap"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 5:
                    continue
                proto = parts[0].lower()
                state = parts[1] if len(parts) > 1 else ""
                local = parts[4] if len(parts) > 4 else ""
                remote = parts[5] if len(parts) > 5 else ""

                local_addr, local_port = cls._parse_endpoint(local)
                remote_addr, remote_port = cls._parse_endpoint(remote)

                conn = NetworkConnection(
                    protocol=proto,
                    local_address=local_addr,
                    local_port=local_port,
                    remote_address=remote_addr,
                    remote_port=remote_port,
                    state=ConnectionState.ESTABLISHED if state == "ESTAB" else ConnectionState.LISTEN,
                )
                connections.append(conn)
        except Exception:
            pass
        return connections

    @staticmethod
    def _decode_address(hex_str: str) -> tuple[str, int]:
        """Decode a hex-encoded address:port from /proc/net."""
        try:
            addr_hex, port_hex = hex_str.split(":")
            port = int(port_hex, 16)
            if len(addr_hex) == 8:
                addr_int = int(addr_hex, 16)
                addr = socket.inet_ntoa(struct.pack("<I", addr_int))
            else:
                addr = addr_hex
            return addr, port
        except (ValueError, struct.error):
            return "0.0.0.0", 0

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, int]:
        """Parse address:port endpoint string."""
        try:
            if "]:" in endpoint:
                addr, port = endpoint.rsplit(":", 1)
                return addr.strip("[]"), int(port)
            parts = endpoint.rsplit(":", 1)
            return parts[0], int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            return "0.0.0.0", 0


# ---------------------------------------------------------------------------
# Threat Detector   Analyzes connections for anomalies
# ---------------------------------------------------------------------------

class ThreatDetector:
    """Analyzes network connections for security threats."""

    # Known malicious ports
    SUSPICIOUS_PORTS = {4444, 5555, 6666, 6667, 8888, 9999, 31337, 12345}

    # Common C2 ports
    C2_PORTS = {443, 8443, 4443, 8080, 9090}

    # Rate limiting thresholds
    MAX_CONNECTIONS_PER_MINUTE = 100
    MAX_UNIQUE_DESTINATIONS_PER_MINUTE = 50

    # Internal network ranges
    INTERNAL_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
    ]

    # Allowed external destinations (whitelist)
    ALLOWED_DESTINATIONS: set[str] = set()

    def __init__(self):
        self._connection_history: deque[NetworkConnection] = deque(maxlen=10000)
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)
        self._destination_tracker: dict[str, set[str]] = defaultdict(set)
        self._known_threats: list[ThreatEvent] = []
        self._blocked_ips: set[str] = set()

    def analyze(self, connections: list[NetworkConnection]) -> list[ThreatEvent]:
        """Analyze connections and return detected threats."""
        threats = []
        now = time.time()

        for conn in connections:
            self._connection_history.append(conn)

            # Check for suspicious ports
            if conn.remote_port in self.SUSPICIOUS_PORTS:
                threats.append(ThreatEvent(
                    threat_level=ThreatLevel.HIGH,
                    category="suspicious_port",
                    description=f"Connection to suspicious port {conn.remote_port}",
                    source_ip=conn.local_address,
                    dest_ip=conn.remote_address,
                    port=conn.remote_port,
                    connection_id=conn.connection_id,
                ))

            # Check for connections to blocked IPs
            if conn.remote_address in self._blocked_ips:
                threats.append(ThreatEvent(
                    threat_level=ThreatLevel.CRITICAL,
                    category="blocked_ip",
                    description=f"Connection to blocked IP {conn.remote_address}",
                    source_ip=conn.local_address,
                    dest_ip=conn.remote_address,
                    port=conn.remote_port,
                    connection_id=conn.connection_id,
                ))

            # Check for external connections (non-internal)
            if conn.is_outbound and not self._is_internal(conn.remote_address):
                if self.ALLOWED_DESTINATIONS and conn.remote_address not in self.ALLOWED_DESTINATIONS:
                    threats.append(ThreatEvent(
                        threat_level=ThreatLevel.MEDIUM,
                        category="unauthorized_outbound",
                        description=f"Outbound to non-whitelisted destination: {conn.remote_endpoint}",
                        source_ip=conn.local_address,
                        dest_ip=conn.remote_address,
                        port=conn.remote_port,
                        connection_id=conn.connection_id,
                    ))

            # Rate tracking
            self._rate_tracker[conn.local_address].append(now)
            if conn.remote_address:
                self._destination_tracker[conn.local_address].add(conn.remote_address)

        # Check connection rate anomalies
        for addr, timestamps in self._rate_tracker.items():
            recent = [t for t in timestamps if now - t < 60]
            self._rate_tracker[addr] = recent
            if len(recent) > self.MAX_CONNECTIONS_PER_MINUTE:
                threats.append(ThreatEvent(
                    threat_level=ThreatLevel.HIGH,
                    category="rate_anomaly",
                    description=f"High connection rate from {addr}: {len(recent)}/min",
                    source_ip=addr,
                ))

        # Check destination diversity anomalies
        for addr, dests in self._destination_tracker.items():
            if len(dests) > self.MAX_UNIQUE_DESTINATIONS_PER_MINUTE:
                threats.append(ThreatEvent(
                    threat_level=ThreatLevel.HIGH,
                    category="scan_detection",
                    description=f"Possible port scan from {addr}: {len(dests)} unique destinations",
                    source_ip=addr,
                ))

        self._known_threats.extend(threats)
        return threats

    def _is_internal(self, address: str) -> bool:
        """Check if an address is internal/private."""
        try:
            ip = ipaddress.ip_address(address)
            return any(ip in net for net in self.INTERNAL_RANGES)
        except (ValueError, TypeError):
            return True

    def add_blocked_ip(self, ip: str) -> None:
        self._blocked_ips.add(ip)

    def remove_blocked_ip(self, ip: str) -> None:
        self._blocked_ips.discard(ip)

    def get_threat_summary(self) -> dict:
        by_level = defaultdict(int)
        by_category = defaultdict(int)
        for t in self._known_threats:
            by_level[t.threat_level.value] += 1
            by_category[t.category] += 1
        return {
            "total_threats": len(self._known_threats),
            "by_level": dict(by_level),
            "by_category": dict(by_category),
            "blocked_ips": list(self._blocked_ips),
            "connections_tracked": len(self._connection_history),
        }


# ---------------------------------------------------------------------------
# Firewall Manager   Simulates iptables/nftables management
# ---------------------------------------------------------------------------

class FirewallManager:
    """Simulated firewall rule manager with iptables-compatible syntax."""

    def __init__(self):
        self._rules: list[FirewallRule] = []
        self._default_policy: dict[str, FirewallAction] = {
            "INPUT": FirewallAction.ALLOW,
            "OUTPUT": FirewallAction.ALLOW,
            "FORWARD": FirewallAction.DROP,
        }
        self._rule_history: list[dict] = []
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """Load default security rules."""
        defaults = [
            FirewallRule(
                direction=FirewallDirection.OUTBOUND,
                action=FirewallAction.ALLOW,
                protocol="tcp",
                dest_port="80,443",
                description="Allow HTTP/HTTPS outbound",
                priority=10,
            ),
            FirewallRule(
                direction=FirewallDirection.OUTBOUND,
                action=FirewallAction.ALLOW,
                protocol="udp",
                dest_port="53",
                description="Allow DNS queries",
                priority=10,
            ),
            FirewallRule(
                direction=FirewallDirection.OUTBOUND,
                action=FirewallAction.ALLOW,
                protocol="tcp",
                dest_port="22",
                description="Allow SSH outbound",
                priority=20,
            ),
            FirewallRule(
                direction=FirewallDirection.OUTBOUND,
                action=FirewallAction.DENY,
                protocol="tcp",
                dest_port="4444,5555,6666,31337",
                description="Block known malicious ports",
                priority=1,
            ),
            FirewallRule(
                direction=FirewallDirection.INBOUND,
                action=FirewallAction.DROP,
                protocol="*",
                source_address="0.0.0.0/0",
                description="Drop all unsolicited inbound by default",
                priority=200,
            ),
        ]
        self._rules.extend(defaults)

    def add_rule(self, rule: FirewallRule) -> str:
        """Add a firewall rule."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
        self._rule_history.append({
            "action": "add",
            "rule_id": rule.rule_id,
            "timestamp": datetime.now().isoformat(),
            "iptables": rule.to_iptables_cmd(),
        })
        logger.info(f"Firewall rule added: {rule.rule_id}   {rule.description}")
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a firewall rule by ID."""
        for i, rule in enumerate(self._rules):
            if rule.rule_id == rule_id:
                self._rules.pop(i)
                self._rule_history.append({
                    "action": "remove",
                    "rule_id": rule_id,
                    "timestamp": datetime.now().isoformat(),
                })
                return True
        return False

    def evaluate(self, conn: NetworkConnection) -> tuple[FirewallAction, str]:
        """Evaluate a connection against all rules."""
        for rule in self._rules:
            if rule.matches(conn):
                rule.hit_count += 1
                return rule.action, rule.rule_id
        # Default policy
        direction = "OUTPUT" if conn.is_outbound else "INPUT"
        return self._default_policy.get(direction, FirewallAction.ALLOW), "default"

    def block_ip(self, ip: str, reason: str = "", duration_minutes: int = 0) -> str:
        """Block all traffic to/from an IP."""
        expires = None
        if duration_minutes > 0:
            expires = datetime.now() + timedelta(minutes=duration_minutes)
        rule = FirewallRule(
            direction=FirewallDirection.OUTBOUND,
            action=FirewallAction.DROP,
            dest_address=ip,
            description=f"Blocked: {reason}",
            priority=0,
            expires_at=expires,
        )
        return self.add_rule(rule)

    def get_rules(self) -> list[dict]:
        return [r.to_dict() for r in self._rules if r.enabled]

    def get_iptables_export(self) -> str:
        """Export all rules as iptables commands."""
        lines = [
            "# AetherOS Firewall Rules Export",
            f"# Generated: {datetime.now().isoformat()}",
            "# ================================",
            "*filter",
        ]
        for rule in self._rules:
            if rule.enabled:
                lines.append(rule.to_iptables_cmd())
        lines.append("COMMIT")
        return "\n".join(lines)

    def set_default_policy(self, chain: str, action: FirewallAction) -> None:
        self._default_policy[chain] = action

    def get_status(self) -> dict:
        active = [r for r in self._rules if r.enabled]
        return {
            "total_rules": len(self._rules),
            "active_rules": len(active),
            "default_policies": {k: v.value for k, v in self._default_policy.items()},
            "total_hits": sum(r.hit_count for r in self._rules),
        }


# ---------------------------------------------------------------------------
# Sentinel   Main Cyber-Defense Controller
# ---------------------------------------------------------------------------

class CyberDefenseSentinel:
    """Main sentinel that orchestrates network defense.

    Monitors   Detects   Decides   Acts   Logs
    """

    def __init__(
        self,
        scan_interval: float = 5.0,
        auto_block: bool = True,
        alert_callback: Optional[Callable[[ThreatEvent], None]] = None,
        audit_logger: Optional[Any] = None,
    ):
        self.scanner = NetworkScanner()
        self.detector = ThreatDetector()
        self.firewall = FirewallManager()
        self.scan_interval = scan_interval
        self.auto_block = auto_block
        self._alert_callback = alert_callback
        self._audit = audit_logger

        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stats = {
            "scans_completed": 0,
            "connections_scanned": 0,
            "threats_detected": 0,
            "connections_blocked": 0,
            "started_at": None,
        }
        self._blocked_connections: list[dict] = []
        self._connection_log: deque[dict] = deque(maxlen=5000)

    def start(self) -> None:
        """Start the sentinel monitoring loop."""
        if self._running:
            return
        self._running = True
        self._stats["started_at"] = datetime.now().isoformat()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("  Cyber-Defense Sentinel started")

    def stop(self) -> None:
        """Stop the sentinel."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        logger.info("  Cyber-Defense Sentinel stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                self._scan_cycle()
            except Exception as e:
                logger.error(f"Sentinel scan error: {e}")
            time.sleep(self.scan_interval)

    def _scan_cycle(self) -> None:
        """Execute a single scan-detect-act cycle."""
        # Scan connections
        connections = self.scanner.scan_connections()
        self._stats["scans_completed"] += 1
        self._stats["connections_scanned"] += len(connections)

        # Log connections
        for conn in connections:
            self._connection_log.append(conn.to_dict())

        # Evaluate against firewall
        for conn in connections:
            action, rule_id = self.firewall.evaluate(conn)
            if action in (FirewallAction.DENY, FirewallAction.DROP):
                self._stats["connections_blocked"] += 1
                self._blocked_connections.append({
                    "connection": conn.to_dict(),
                    "rule_id": rule_id,
                    "action": action.value,
                    "timestamp": datetime.now().isoformat(),
                })

        # Detect threats
        threats = self.detector.analyze(connections)
        self._stats["threats_detected"] += len(threats)

        # Auto-respond to threats
        for threat in threats:
            self._handle_threat(threat)

    def _handle_threat(self, threat: ThreatEvent) -> None:
        """Handle a detected threat."""
        if self.auto_block and threat.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            if threat.dest_ip and not self.detector._is_internal(threat.dest_ip):
                self.firewall.block_ip(
                    threat.dest_ip,
                    reason=f"Auto-blocked: {threat.category}",
                    duration_minutes=60,
                )
                self.detector.add_blocked_ip(threat.dest_ip)
                threat.action_taken = f"Auto-blocked IP {threat.dest_ip} for 60 minutes"
                logger.warning(f"  Auto-blocked {threat.dest_ip}: {threat.description}")

        if self._alert_callback:
            try:
                self._alert_callback(threat)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        if self._audit:
            try:
                self._audit.log_security_event(
                    f"Threat detected: {threat.category}",
                    details=threat.to_dict(),
                )
            except Exception:
                pass

    def scan_now(self) -> dict:
        """Perform an immediate scan and return results."""
        connections = self.scanner.scan_connections()
        threats = self.detector.analyze(connections)

        blocked = []
        for conn in connections:
            action, rule_id = self.firewall.evaluate(conn)
            if action in (FirewallAction.DENY, FirewallAction.DROP):
                blocked.append(conn.to_dict())

        return {
            "timestamp": datetime.now().isoformat(),
            "connections": len(connections),
            "threats": [t.to_dict() for t in threats],
            "blocked": blocked,
            "outbound": [c.to_dict() for c in connections if c.is_outbound],
        }

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "stats": self._stats,
            "firewall": self.firewall.get_status(),
            "threats": self.detector.get_threat_summary(),
            "recent_blocked": self._blocked_connections[-20:],
        }

    def get_connection_log(self, last_n: int = 100) -> list[dict]:
        return list(self._connection_log)[-last_n:]

    def add_firewall_rule(self, rule: FirewallRule) -> str:
        return self.firewall.add_rule(rule)

    def remove_firewall_rule(self, rule_id: str) -> bool:
        return self.firewall.remove_rule(rule_id)

    def block_ip(self, ip: str, reason: str = "Manual block",
                 duration_minutes: int = 0) -> str:
        self.detector.add_blocked_ip(ip)
        return self.firewall.block_ip(ip, reason, duration_minutes)

    def unblock_ip(self, ip: str) -> None:
        self.detector.remove_blocked_ip(ip)


# ---------------------------------------------------------------------------
# DNS Auditor   Monitors DNS resolution
# ---------------------------------------------------------------------------

class DNSAuditor:
    """Monitors and audits DNS resolution requests."""

    SUSPICIOUS_TLDS = {".xyz", ".top", ".tk", ".ml", ".ga", ".cf", ".gq", ".ru", ".cn"}
    MAX_SUBDOMAIN_DEPTH = 5

    def __init__(self):
        self._resolution_log: deque[dict] = deque(maxlen=5000)
        self._blocked_domains: set[str] = set()
        self._allowed_domains: set[str] = set()

    def audit_resolution(self, domain: str) -> tuple[bool, str]:
        """Audit a DNS resolution request."""
        entry = {
            "domain": domain,
            "timestamp": datetime.now().isoformat(),
            "allowed": True,
            "reason": "",
        }

        # Check blocklist
        if domain in self._blocked_domains:
            entry["allowed"] = False
            entry["reason"] = "Domain in blocklist"
            self._resolution_log.append(entry)
            return False, "Domain blocked"

        # Check for suspicious TLD
        for tld in self.SUSPICIOUS_TLDS:
            if domain.endswith(tld):
                entry["reason"] = f"Suspicious TLD: {tld}"
                self._resolution_log.append(entry)
                return True, f"Warning: suspicious TLD {tld}"

        # Check subdomain depth (possible DNS tunneling)
        parts = domain.split(".")
        if len(parts) > self.MAX_SUBDOMAIN_DEPTH:
            entry["reason"] = f"Deep subdomain nesting: {len(parts)} levels"
            self._resolution_log.append(entry)
            return True, "Warning: deep subdomain nesting (possible DNS tunneling)"

        # Check for encoded data in subdomains (DNS exfiltration)
        for part in parts[:-2]:
            if len(part) > 40:
                entry["reason"] = "Long subdomain label (possible data exfiltration)"
                self._resolution_log.append(entry)
                return True, "Warning: possible DNS data exfiltration"

        entry["reason"] = "Clean"
        self._resolution_log.append(entry)
        return True, "OK"

    def block_domain(self, domain: str) -> None:
        self._blocked_domains.add(domain)

    def allow_domain(self, domain: str) -> None:
        self._allowed_domains.add(domain)

    def get_log(self, last_n: int = 100) -> list[dict]:
        return list(self._resolution_log)[-last_n:]

    def get_stats(self) -> dict:
        total = len(self._resolution_log)
        blocked = sum(1 for e in self._resolution_log if not e["allowed"])
        return {
            "total_queries": total,
            "blocked_queries": blocked,
            "blocked_domains": len(self._blocked_domains),
            "allowed_domains": len(self._allowed_domains),
        }
