"""AetherOS Intelligence — OSINT Scanner & Credential Leak Monitor.

Simulates deep-web/OSINT monitoring for credential leaks, threat intelligence
gathering, and Indicator of Compromise (IOC) database management.

Components:
    - CredentialLeakMonitor: Monitors for leaked credentials
    - DarkWebSimulator: Simulates dark web monitoring feeds
    - ThreatIntelFeed: Aggregates threat intelligence from sources
    - IOCDatabase: Manages Indicators of Compromise
    - IntelligenceAggregator: Combines all intel sources

This is a simulation framework — no actual dark web access is performed.
All data is synthetic for demonstration and testing purposes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import string
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("intel.osint")


# ═══════════════════════════════════════════════════════════════════════════
# Enums & Models
# ═══════════════════════════════════════════════════════════════════════════

class OSINTSource(Enum):
    """Sources of OSINT intelligence."""
    PASTE_SITES = "paste_sites"
    DARK_WEB_FORUMS = "dark_web_forums"
    DATA_BREACH_DB = "data_breach_db"
    SOCIAL_MEDIA = "social_media"
    CODE_REPOS = "code_repos"
    DNS_RECORDS = "dns_records"
    CERTIFICATE_LOGS = "certificate_logs"
    SHODAN = "shodan"
    THREAT_FEEDS = "threat_feeds"
    WHOIS = "whois"


class ThreatLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class IOCType(Enum):
    """Indicator of Compromise types."""
    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    URL = "url"
    EMAIL = "email"
    FILE_HASH = "file_hash"
    REGISTRY_KEY = "registry_key"
    MUTEX = "mutex"
    USER_AGENT = "user_agent"
    SSL_CERT_HASH = "ssl_cert_hash"
    BITCOIN_ADDRESS = "bitcoin_address"


@dataclass
class LeakRecord:
    """A single credential leak record."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: OSINTSource = OSINTSource.PASTE_SITES
    email: str = ""
    domain: str = ""
    password_hash: str = ""
    plaintext_available: bool = False
    breach_name: str = ""
    breach_date: str = ""
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    severity: ThreatLevel = ThreatLevel.HIGH
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source": self.source.value,
            "email": self.email,
            "domain": self.domain,
            "password_hash": self.password_hash[:16] + "..." if self.password_hash else "",
            "plaintext_available": self.plaintext_available,
            "breach_name": self.breach_name,
            "breach_date": self.breach_date,
            "discovered_at": self.discovered_at.isoformat(),
            "severity": self.severity.value,
        }


@dataclass
class IOCEntry:
    """Indicator of Compromise entry."""
    ioc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ioc_type: IOCType = IOCType.IP_ADDRESS
    value: str = ""
    threat_level: ThreatLevel = ThreatLevel.MEDIUM
    source: str = ""
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)
    description: str = ""
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ioc_id": self.ioc_id,
            "ioc_type": self.ioc_type.value,
            "value": self.value,
            "threat_level": self.threat_level.value,
            "source": self.source,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "tags": self.tags,
            "description": self.description,
            "is_active": self.is_active,
        }


@dataclass
class ScanResult:
    """Result of an OSINT scan."""
    scan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scan_type: str = ""
    target: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    threat_level: ThreatLevel = ThreatLevel.NONE
    summary: str = ""
    sources_checked: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "scan_type": self.scan_type,
            "target": self.target,
            "timestamp": self.timestamp.isoformat(),
            "findings_count": len(self.findings),
            "findings": self.findings,
            "threat_level": self.threat_level.value,
            "summary": self.summary,
            "sources_checked": self.sources_checked,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ThreatIntelReport:
    """Aggregated threat intelligence report."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = field(default_factory=datetime.utcnow)
    period_hours: int = 24
    total_scans: int = 0
    new_leaks: int = 0
    new_iocs: int = 0
    overall_threat_level: ThreatLevel = ThreatLevel.NONE
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    scan_results: List[ScanResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "period_hours": self.period_hours,
            "total_scans": self.total_scans,
            "new_leaks": self.new_leaks,
            "new_iocs": self.new_iocs,
            "overall_threat_level": self.overall_threat_level.value,
            "key_findings": self.key_findings,
            "recommendations": self.recommendations,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Dark Web Simulator
# ═══════════════════════════════════════════════════════════════════════════

class DarkWebSimulator:
    """Simulates dark web monitoring for credential leaks.

    Generates realistic-looking synthetic breach data for testing
    the monitoring pipeline. No actual dark web access is performed.
    """

    BREACH_NAMES = [
        "MegaCorp Data Breach 2025", "CloudProvider Incident",
        "SocialNet Leak", "FinanceApp Exposure", "RetailChain Hack",
        "GamePlatform Breach", "HealthData Incident", "GovPortal Leak",
        "EmailProvider Breach", "StreamingService Hack",
    ]

    PASTE_SOURCES = [
        "pastebin_sim", "ghostbin_sim", "privatebin_sim",
        "dpaste_sim", "hastebin_sim",
    ]

    def __init__(self, monitored_domains: Optional[List[str]] = None):
        self.monitored_domains = monitored_domains or ["aetheros.io", "daxxteam.io"]
        self._leak_db: List[LeakRecord] = []
        self._scan_count = 0
        self._lock = threading.Lock()

    def simulate_scan(self, domain: Optional[str] = None) -> List[LeakRecord]:
        """Simulate a dark web scan for a domain."""
        self._scan_count += 1
        target_domain = domain or random.choice(self.monitored_domains)
        records = []

        # Randomly generate 0-3 synthetic leak records
        count = random.choices([0, 1, 2, 3], weights=[60, 25, 10, 5])[0]

        for _ in range(count):
            username = ''.join(random.choices(string.ascii_lowercase, k=8))
            email = f"{username}@{target_domain}"
            pw_hash = hashlib.sha256(os.urandom(32)).hexdigest()

            record = LeakRecord(
                source=random.choice([OSINTSource.PASTE_SITES, OSINTSource.DARK_WEB_FORUMS, OSINTSource.DATA_BREACH_DB]),
                email=email,
                domain=target_domain,
                password_hash=pw_hash,
                plaintext_available=random.random() < 0.2,
                breach_name=random.choice(self.BREACH_NAMES),
                breach_date=(datetime.utcnow() - timedelta(days=random.randint(1, 365))).strftime("%Y-%m-%d"),
                severity=random.choice([ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL]),
            )
            records.append(record)

        with self._lock:
            self._leak_db.extend(records)

        return records

    def get_all_leaks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._leak_db]

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_leaks": len(self._leak_db),
                "scans_performed": self._scan_count,
                "monitored_domains": self.monitored_domains,
            }


# ═══════════════════════════════════════════════════════════════════════════
# Credential Leak Monitor
# ═══════════════════════════════════════════════════════════════════════════

class CredentialLeakMonitor:
    """Monitors for credential leaks across OSINT sources.

    Continuously scans simulated sources for leaked credentials
    matching monitored domains and email addresses.
    """

    def __init__(
        self,
        monitored_domains: Optional[List[str]] = None,
        monitored_emails: Optional[List[str]] = None,
        scan_interval: float = 3600.0,  # 1 hour
    ):
        self.monitored_domains = monitored_domains or ["aetheros.io"]
        self.monitored_emails = monitored_emails or []
        self.scan_interval = scan_interval
        self._dark_web = DarkWebSimulator(monitored_domains=self.monitored_domains)
        self._known_leaks: Set[str] = set()
        self._new_leak_callbacks: List[Callable[[LeakRecord], None]] = []
        self._is_monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        logger.info(f"CredentialLeakMonitor initialized for {self.monitored_domains}")

    def start(self) -> None:
        self._is_monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Credential leak monitoring started")

    def stop(self) -> None:
        self._is_monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10.0)

    def _monitor_loop(self) -> None:
        while self._is_monitoring:
            try:
                self.scan()
                time.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"Leak monitor error: {e}")
                time.sleep(60)

    def scan(self) -> ScanResult:
        """Perform a credential leak scan."""
        start = time.time()
        all_records = []

        for domain in self.monitored_domains:
            records = self._dark_web.simulate_scan(domain)
            all_records.extend(records)

        # Filter for new leaks
        new_leaks = []
        for record in all_records:
            key = f"{record.email}:{record.password_hash[:16]}"
            if key not in self._known_leaks:
                self._known_leaks.add(key)
                new_leaks.append(record)
                for cb in self._new_leak_callbacks:
                    try:
                        cb(record)
                    except Exception as e:
                        logger.error(f"Leak callback error: {e}")

        max_threat = ThreatLevel.NONE
        for r in new_leaks:
            if r.severity.value > max_threat.value:
                max_threat = r.severity

        result = ScanResult(
            scan_type="credential_leak",
            target=",".join(self.monitored_domains),
            findings=[r.to_dict() for r in new_leaks],
            threat_level=max_threat,
            summary=f"Found {len(new_leaks)} new credential leaks across {len(self.monitored_domains)} domains",
            sources_checked=[s.value for s in OSINTSource],
            duration_ms=(time.time() - start) * 1000,
        )
        return result

    def register_leak_callback(self, callback: Callable[[LeakRecord], None]) -> None:
        self._new_leak_callbacks.append(callback)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "is_monitoring": self._is_monitoring,
            "known_leaks": len(self._known_leaks),
            "dark_web_stats": self._dark_web.stats,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Threat Intelligence Feed
# ═══════════════════════════════════════════════════════════════════════════

class ThreatIntelFeed:
    """Aggregates threat intelligence from multiple sources."""

    SIMULATED_FEEDS = [
        "AlienVault OTX (Simulated)",
        "VirusTotal (Simulated)",
        "Abuse.ch (Simulated)",
        "Emerging Threats (Simulated)",
        "MISP Community (Simulated)",
    ]

    def __init__(self):
        self._entries: deque = deque(maxlen=10000)
        self._sources: List[str] = list(self.SIMULATED_FEEDS)
        self._update_count = 0

    def fetch_updates(self) -> List[IOCEntry]:
        """Fetch simulated threat intelligence updates."""
        self._update_count += 1
        entries = []

        # Generate 0-5 synthetic IOC entries
        count = random.randint(0, 5)
        for _ in range(count):
            ioc_type = random.choice(list(IOCType))
            value = self._generate_ioc_value(ioc_type)
            entry = IOCEntry(
                ioc_type=ioc_type,
                value=value,
                threat_level=random.choice(list(ThreatLevel)),
                source=random.choice(self._sources),
                tags=random.sample(["malware", "botnet", "phishing", "c2", "ransomware", "apt"], k=random.randint(1, 3)),
                description=f"Simulated threat intel: {ioc_type.value} indicator",
            )
            entries.append(entry)
            self._entries.append(entry)

        return entries

    def _generate_ioc_value(self, ioc_type: IOCType) -> str:
        """Generate a realistic-looking IOC value."""
        if ioc_type == IOCType.IP_ADDRESS:
            return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        elif ioc_type == IOCType.DOMAIN:
            tlds = [".com", ".net", ".ru", ".cn", ".xyz", ".top"]
            name = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 12)))
            return name + random.choice(tlds)
        elif ioc_type == IOCType.URL:
            domain = self._generate_ioc_value(IOCType.DOMAIN)
            path = ''.join(random.choices(string.ascii_lowercase + "/", k=random.randint(5, 20)))
            return f"http://{domain}/{path}"
        elif ioc_type == IOCType.EMAIL:
            user = ''.join(random.choices(string.ascii_lowercase, k=8))
            domain = self._generate_ioc_value(IOCType.DOMAIN)
            return f"{user}@{domain}"
        elif ioc_type == IOCType.FILE_HASH:
            return hashlib.sha256(os.urandom(32)).hexdigest()
        else:
            return hashlib.md5(os.urandom(16)).hexdigest()

    def search(self, query: str, ioc_type: Optional[IOCType] = None) -> List[Dict[str, Any]]:
        results = []
        for entry in self._entries:
            if ioc_type and entry.ioc_type != ioc_type:
                continue
            if query.lower() in entry.value.lower() or query.lower() in entry.description.lower():
                results.append(entry.to_dict())
        return results

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "update_count": self._update_count,
            "sources": self._sources,
        }


# ═══════════════════════════════════════════════════════════════════════════
# IOC Database
# ═══════════════════════════════════════════════════════════════════════════

class IOCDatabase:
    """Local Indicator of Compromise database."""

    def __init__(self, persist_path: Optional[str] = None):
        self.persist_path = persist_path or os.path.expanduser("~/.aetheros/ioc_db.json")
        self._entries: Dict[str, IOCEntry] = {}
        self._by_type: Dict[IOCType, Set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def add(self, entry: IOCEntry) -> bool:
        with self._lock:
            if entry.ioc_id in self._entries:
                return False
            self._entries[entry.ioc_id] = entry
            self._by_type[entry.ioc_type].add(entry.ioc_id)
            return True

    def bulk_add(self, entries: List[IOCEntry]) -> int:
        added = 0
        for entry in entries:
            if self.add(entry):
                added += 1
        return added

    def check(self, value: str) -> Optional[IOCEntry]:
        """Check if a value matches any known IOC."""
        with self._lock:
            for entry in self._entries.values():
                if entry.value == value and entry.is_active:
                    return entry
        return None

    def search(
        self,
        query: str = "",
        ioc_type: Optional[IOCType] = None,
        threat_level: Optional[ThreatLevel] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        results = []
        with self._lock:
            for entry in self._entries.values():
                if active_only and not entry.is_active:
                    continue
                if ioc_type and entry.ioc_type != ioc_type:
                    continue
                if threat_level and entry.threat_level != threat_level:
                    continue
                if query and query.lower() not in entry.value.lower():
                    continue
                results.append(entry.to_dict())
        return results

    def deactivate(self, ioc_id: str) -> bool:
        with self._lock:
            if ioc_id in self._entries:
                self._entries[ioc_id].is_active = False
                return True
            return False

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            type_counts = {t.value: len(ids) for t, ids in self._by_type.items()}
            active = sum(1 for e in self._entries.values() if e.is_active)
            return {
                "total_iocs": len(self._entries),
                "active_iocs": active,
                "by_type": type_counts,
            }


# ═══════════════════════════════════════════════════════════════════════════
# OSINT Scanner (Main Interface)
# ═══════════════════════════════════════════════════════════════════════════

class OSINTScanner:
    """Main OSINT scanning engine combining all intelligence sources.

    Usage:
        scanner = OSINTScanner(monitored_domains=["company.com"])
        scanner.start()

        # Manual scan
        result = scanner.full_scan()

        # Get report
        report = scanner.generate_report()

        scanner.stop()
    """

    def __init__(
        self,
        monitored_domains: Optional[List[str]] = None,
        monitored_emails: Optional[List[str]] = None,
        scan_interval: float = 3600.0,
    ):
        self.leak_monitor = CredentialLeakMonitor(
            monitored_domains=monitored_domains,
            monitored_emails=monitored_emails,
            scan_interval=scan_interval,
        )
        self.threat_feed = ThreatIntelFeed()
        self.ioc_db = IOCDatabase()
        self._scan_history: deque = deque(maxlen=100)
        self._callbacks: List[Callable[[ScanResult], None]] = []
        self._is_running = False
        logger.info("OSINTScanner initialized")

    def start(self) -> None:
        self._is_running = True
        self.leak_monitor.start()
        logger.info("OSINT Scanner started")

    def stop(self) -> None:
        self._is_running = False
        self.leak_monitor.stop()
        logger.info("OSINT Scanner stopped")

    def full_scan(self) -> ScanResult:
        """Perform a comprehensive OSINT scan."""
        start = time.time()
        findings = []

        # Credential leak scan
        leak_result = self.leak_monitor.scan()
        findings.extend(leak_result.findings)

        # Threat intelligence update
        new_iocs = self.threat_feed.fetch_updates()
        self.ioc_db.bulk_add(new_iocs)
        for ioc in new_iocs:
            findings.append(ioc.to_dict())

        max_threat = ThreatLevel.NONE
        for f in findings:
            level = f.get("threat_level", 0)
            if isinstance(level, int) and level > max_threat.value:
                max_threat = ThreatLevel(level)
            elif isinstance(level, str):
                try:
                    tl = ThreatLevel[level.upper()]
                    if tl.value > max_threat.value:
                        max_threat = tl
                except (KeyError, ValueError):
                    pass

        result = ScanResult(
            scan_type="full_osint",
            target="all_monitored",
            findings=findings,
            threat_level=max_threat,
            summary=f"Full OSINT scan complete: {len(findings)} findings",
            sources_checked=[s.value for s in OSINTSource],
            duration_ms=(time.time() - start) * 1000,
        )

        self._scan_history.append(result)
        for cb in self._callbacks:
            try:
                cb(result)
            except Exception as e:
                logger.error(f"Scan callback error: {e}")

        return result

    def generate_report(self, period_hours: int = 24) -> ThreatIntelReport:
        """Generate an aggregated threat intelligence report."""
        cutoff = datetime.utcnow() - timedelta(hours=period_hours)
        recent_scans = [
            s for s in self._scan_history
            if s.timestamp >= cutoff
        ]

        total_findings = sum(len(s.findings) for s in recent_scans)
        max_threat = ThreatLevel.NONE
        for s in recent_scans:
            if s.threat_level.value > max_threat.value:
                max_threat = s.threat_level

        report = ThreatIntelReport(
            period_hours=period_hours,
            total_scans=len(recent_scans),
            new_leaks=len(self.leak_monitor._known_leaks),
            new_iocs=self.ioc_db.size,
            overall_threat_level=max_threat,
            key_findings=[
                f"{total_findings} total findings across {len(recent_scans)} scans",
                f"IOC database contains {self.ioc_db.size} indicators",
                f"Threat level: {max_threat.name}",
            ],
            recommendations=[
                "Review all new credential leaks for affected accounts",
                "Update firewall rules with new IOC IP addresses",
                "Rotate credentials for any domains with detected leaks",
                "Monitor identified IOC domains for additional activity",
            ],
            scan_results=recent_scans,
        )
        return report

    def register_callback(self, callback: Callable[[ScanResult], None]) -> None:
        self._callbacks.append(callback)

    def check_ioc(self, value: str) -> Optional[Dict[str, Any]]:
        """Check if a value matches a known IOC."""
        entry = self.ioc_db.check(value)
        return entry.to_dict() if entry else None

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "is_running": self._is_running,
            "leak_monitor": self.leak_monitor.stats,
            "threat_feed": self.threat_feed.stats,
            "ioc_db": self.ioc_db.get_stats(),
            "scan_history": len(self._scan_history),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Intelligence Aggregator
# ═══════════════════════════════════════════════════════════════════════════

class IntelligenceAggregator:
    """High-level intelligence aggregation across all OSINT components."""

    def __init__(self, scanner: Optional[OSINTScanner] = None):
        self.scanner = scanner or OSINTScanner()
        self._reports: deque = deque(maxlen=50)

    def run_assessment(self) -> Dict[str, Any]:
        """Run a complete intelligence assessment."""
        scan = self.scanner.full_scan()
        report = self.scanner.generate_report()
        self._reports.append(report)

        return {
            "scan": scan.to_dict(),
            "report": report.to_dict(),
            "overall_stats": self.scanner.stats,
        }

    def get_dashboard_data(self) -> Dict[str, Any]:
        return {
            "scanner_stats": self.scanner.stats,
            "recent_reports": [r.to_dict() for r in list(self._reports)[-5:]],
            "ioc_summary": self.scanner.ioc_db.get_stats(),
        }
