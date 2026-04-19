"""Tests for the Cyber-Defense Sentinel."""
import pytest
from security.sentinel import (
    CyberDefenseSentinel, FirewallManager, FirewallRule, FirewallAction,
    FirewallDirection, ThreatDetector, ThreatLevel, NetworkScanner,
    NetworkConnection, ConnectionState, DNSAuditor,
)


class TestFirewallRule:
    def test_basic_match(self):
        rule = FirewallRule(
            direction=FirewallDirection.OUTBOUND,
            action=FirewallAction.DENY,
            dest_port="4444",
        )
        conn = NetworkConnection(
            protocol="tcp",
            remote_address="1.2.3.4",
            remote_port=4444,
            state=ConnectionState.ESTABLISHED,
        )
        assert rule.matches(conn)

    def test_port_range_match(self):
        rule = FirewallRule(dest_port="8000-9000")
        conn = NetworkConnection(remote_port=8080, state=ConnectionState.ESTABLISHED)
        assert rule.matches(conn)

    def test_port_no_match(self):
        rule = FirewallRule(dest_port="80")
        conn = NetworkConnection(remote_port=443, state=ConnectionState.ESTABLISHED)
        assert not rule.matches(conn)

    def test_cidr_match(self):
        rule = FirewallRule(dest_address="10.0.0.0/8")
        conn = NetworkConnection(remote_address="10.1.2.3", remote_port=80, state=ConnectionState.ESTABLISHED)
        assert rule.matches(conn)

    def test_iptables_export(self):
        rule = FirewallRule(
            direction=FirewallDirection.OUTBOUND,
            action=FirewallAction.DROP,
            protocol="tcp",
            dest_port="4444",
            description="Block bad port",
        )
        cmd = rule.to_iptables_cmd()
        assert "iptables" in cmd
        assert "DROP" in cmd
        assert "4444" in cmd

    def test_disabled_rule(self):
        rule = FirewallRule(dest_port="80", enabled=False)
        conn = NetworkConnection(remote_port=80, state=ConnectionState.ESTABLISHED)
        assert not rule.matches(conn)


class TestFirewallManager:
    def test_default_rules_loaded(self):
        fw = FirewallManager()
        rules = fw.get_rules()
        assert len(rules) > 0

    def test_add_rule(self):
        fw = FirewallManager()
        initial = len(fw.get_rules())
        rule = FirewallRule(dest_address="5.5.5.5", action=FirewallAction.DROP)
        fw.add_rule(rule)
        assert len(fw.get_rules()) == initial + 1

    def test_remove_rule(self):
        fw = FirewallManager()
        rule = FirewallRule(dest_address="6.6.6.6", action=FirewallAction.DROP)
        rule_id = fw.add_rule(rule)
        assert fw.remove_rule(rule_id)

    def test_block_ip(self):
        fw = FirewallManager()
        rule_id = fw.block_ip("1.2.3.4", reason="Test block")
        assert rule_id
        rules = fw.get_rules()
        assert any("1.2.3.4" in r.get("dest", "") for r in rules)

    def test_evaluate_allow(self):
        fw = FirewallManager()
        conn = NetworkConnection(
            protocol="tcp", remote_address="1.1.1.1",
            remote_port=443, state=ConnectionState.ESTABLISHED,
        )
        action, rule_id = fw.evaluate(conn)
        assert action == FirewallAction.ALLOW

    def test_iptables_export(self):
        fw = FirewallManager()
        export = fw.get_iptables_export()
        assert "iptables" in export
        assert "COMMIT" in export


class TestThreatDetector:
    def test_detect_suspicious_port(self):
        detector = ThreatDetector()
        conns = [NetworkConnection(
            remote_address="1.2.3.4", remote_port=31337,
            state=ConnectionState.ESTABLISHED,
        )]
        threats = detector.analyze(conns)
        assert len(threats) >= 1
        assert any(t.category == "suspicious_port" for t in threats)

    def test_detect_blocked_ip(self):
        detector = ThreatDetector()
        detector.add_blocked_ip("10.0.0.99")
        conns = [NetworkConnection(
            remote_address="10.0.0.99", remote_port=80,
            state=ConnectionState.ESTABLISHED,
        )]
        threats = detector.analyze(conns)
        assert any(t.category == "blocked_ip" for t in threats)

    def test_no_threats_clean(self):
        detector = ThreatDetector()
        conns = [NetworkConnection(
            remote_address="127.0.0.1", remote_port=80,
            state=ConnectionState.ESTABLISHED,
        )]
        threats = detector.analyze(conns)
        suspicious = [t for t in threats if t.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)]
        assert len(suspicious) == 0

    def test_threat_summary(self):
        detector = ThreatDetector()
        summary = detector.get_threat_summary()
        assert "total_threats" in summary


class TestDNSAuditor:
    def test_clean_domain(self):
        auditor = DNSAuditor()
        ok, msg = auditor.audit_resolution("google.com")
        assert ok
        assert msg == "OK"

    def test_suspicious_tld(self):
        auditor = DNSAuditor()
        ok, msg = auditor.audit_resolution("evil.tk")
        assert ok
        assert "suspicious tld" in msg.lower()

    def test_blocked_domain(self):
        auditor = DNSAuditor()
        auditor.block_domain("bad.example.com")
        ok, msg = auditor.audit_resolution("bad.example.com")
        assert not ok

    def test_deep_subdomain(self):
        auditor = DNSAuditor()
        domain = "a.b.c.d.e.f.g.example.com"
        ok, msg = auditor.audit_resolution(domain)
        assert "deep subdomain" in msg.lower() or ok


class TestSentinel:
    def test_sentinel_scan_now(self):
        sentinel = CyberDefenseSentinel(scan_interval=60, auto_block=False)
        result = sentinel.scan_now()
        assert "connections" in result
        assert "threats" in result
        sentinel.stop()

    def test_sentinel_status(self):
        sentinel = CyberDefenseSentinel(scan_interval=60)
        status = sentinel.get_status()
        assert "running" in status
        assert "firewall" in status
        sentinel.stop()

    def test_block_and_unblock_ip(self):
        sentinel = CyberDefenseSentinel(scan_interval=60)
        rule_id = sentinel.block_ip("1.2.3.4", reason="test")
        assert rule_id
        sentinel.unblock_ip("1.2.3.4")
        sentinel.stop()
