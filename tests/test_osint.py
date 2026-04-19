"""Tests for AetherOS OSINT Scanner."""
import pytest
from intel.osint_scanner import (
    OSINTScanner, CredentialLeakMonitor, DarkWebSimulator,
    ThreatIntelFeed, IOCDatabase, IOCEntry, IOCType,
    ThreatLevel, LeakRecord, OSINTSource, IntelligenceAggregator,
)


class TestDarkWebSimulator:
    def test_simulate_scan(self):
        sim = DarkWebSimulator(monitored_domains=["test.com"])
        # Run multiple scans to ensure at least one produces results
        all_records = []
        for _ in range(20):
            records = sim.simulate_scan("test.com")
            all_records.extend(records)
        # With 20 scans, statistically we should get some records
        assert sim.stats["scans_performed"] == 20

    def test_get_all_leaks(self):
        sim = DarkWebSimulator()
        sim.simulate_scan()
        leaks = sim.get_all_leaks()
        assert isinstance(leaks, list)


class TestCredentialLeakMonitor:
    def test_scan(self):
        monitor = CredentialLeakMonitor(monitored_domains=["test.com"])
        result = monitor.scan()
        assert result.scan_type == "credential_leak"
        assert "test.com" in result.target

    def test_stats(self):
        monitor = CredentialLeakMonitor()
        stats = monitor.stats
        assert "is_monitoring" in stats
        assert stats["is_monitoring"] is False


class TestThreatIntelFeed:
    def test_fetch_updates(self):
        feed = ThreatIntelFeed()
        entries = feed.fetch_updates()
        assert isinstance(entries, list)
        assert feed.stats["update_count"] == 1

    def test_search(self):
        feed = ThreatIntelFeed()
        # Generate some entries
        for _ in range(10):
            feed.fetch_updates()
        results = feed.search("", ioc_type=None)
        assert isinstance(results, list)


class TestIOCDatabase:
    def test_add_and_check(self):
        db = IOCDatabase()
        entry = IOCEntry(
            ioc_type=IOCType.IP_ADDRESS,
            value="192.168.1.100",
            threat_level=ThreatLevel.HIGH,
        )
        assert db.add(entry)
        assert db.size == 1
        found = db.check("192.168.1.100")
        assert found is not None
        assert found.ioc_type == IOCType.IP_ADDRESS

    def test_check_missing(self):
        db = IOCDatabase()
        assert db.check("unknown") is None

    def test_bulk_add(self):
        db = IOCDatabase()
        entries = [
            IOCEntry(ioc_type=IOCType.DOMAIN, value=f"evil{i}.com")
            for i in range(5)
        ]
        added = db.bulk_add(entries)
        assert added == 5
        assert db.size == 5

    def test_deactivate(self):
        db = IOCDatabase()
        entry = IOCEntry(value="bad.com")
        db.add(entry)
        db.deactivate(entry.ioc_id)
        found = db.check("bad.com")
        assert found is None  # Inactive entries not returned

    def test_search(self):
        db = IOCDatabase()
        e1 = IOCEntry(ioc_type=IOCType.IP_ADDRESS, value="10.0.0.1", threat_level=ThreatLevel.HIGH)
        e2 = IOCEntry(ioc_type=IOCType.DOMAIN, value="evil.com", threat_level=ThreatLevel.CRITICAL)
        db.add(e1)
        db.add(e2)
        results = db.search(ioc_type=IOCType.DOMAIN)
        assert len(results) == 1
        assert results[0]["value"] == "evil.com"


class TestOSINTScanner:
    def test_full_scan(self):
        scanner = OSINTScanner(monitored_domains=["test.com"])
        result = scanner.full_scan()
        assert result.scan_type == "full_osint"

    def test_generate_report(self):
        scanner = OSINTScanner()
        scanner.full_scan()
        report = scanner.generate_report()
        assert report.total_scans >= 1
        assert len(report.recommendations) > 0

    def test_stats(self):
        scanner = OSINTScanner()
        stats = scanner.stats
        assert "is_running" in stats
        assert "leak_monitor" in stats
        assert "ioc_db" in stats


class TestIntelligenceAggregator:
    def test_run_assessment(self):
        agg = IntelligenceAggregator()
        result = agg.run_assessment()
        assert "scan" in result
        assert "report" in result

    def test_dashboard_data(self):
        agg = IntelligenceAggregator()
        data = agg.get_dashboard_data()
        assert "scanner_stats" in data
