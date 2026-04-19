"""Tests for AetherOS Honeypot System."""
import os
import pytest
import tempfile
import shutil
from security.honeypot import (
    HoneypotOrchestrator, FileHoneypot, DirectoryHoneypot,
    CredentialHoneypot, HoneypotAlertManager, BaitContentGenerator,
    HoneypotType, TrapStatus, AlertSeverity, HoneypotAlert,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="aetheros_honeypot_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestBaitContentGenerator:
    def test_generate_passwords(self):
        content = BaitContentGenerator.generate_content("passwords")
        assert "Password Database" in content or "password" in content.lower()
        assert len(content) > 100

    def test_generate_env(self):
        content = BaitContentGenerator.generate_content("env")
        assert "DATABASE_URL" in content
        assert "SECRET_KEY" in content

    def test_generate_ssh_keys(self):
        content = BaitContentGenerator.generate_content("ssh_keys")
        assert "OPENSSH" in content

    def test_generate_financial(self):
        content = BaitContentGenerator.generate_content("financial")
        assert "Amount" in content

    def test_random_file_name(self):
        name = BaitContentGenerator.get_random_file_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_random_dir_name(self):
        name = BaitContentGenerator.get_random_dir_name()
        assert isinstance(name, str)
        assert len(name) > 0


class TestFileHoneypot:
    def test_create_trap(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        trap = hp.create_trap(name="test_passwords.txt", content_type="passwords")
        assert trap.trap_type == HoneypotType.FILE
        assert trap.name == "test_passwords.txt"
        assert os.path.exists(trap.path)

    def test_check_unmodified_trap(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        trap = hp.create_trap(name="test.txt", content_type="env")
        alert = hp.check_trap(trap.trap_id)
        # Should be None or access alert depending on filesystem
        # No modification = likely no alert
        assert alert is None or alert.severity in (AlertSeverity.MEDIUM, AlertSeverity.LOW)

    def test_check_modified_trap(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        trap = hp.create_trap(name="test_mod.txt")
        # Modify the file
        with open(trap.path, "w") as f:
            f.write("TAMPERED CONTENT")
        alert = hp.check_trap(trap.trap_id)
        assert alert is not None
        assert alert.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL)

    def test_check_deleted_trap(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        trap = hp.create_trap(name="test_del.txt")
        os.remove(trap.path)
        alert = hp.check_trap(trap.trap_id)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL
        assert "DELETED" in alert.description

    def test_list_traps(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        hp.create_trap(name="trap1.txt")
        hp.create_trap(name="trap2.txt")
        traps = hp.list_traps()
        assert len(traps) == 2

    def test_remove_trap(self, temp_dir):
        hp = FileHoneypot(temp_dir)
        trap = hp.create_trap(name="removable.txt")
        assert os.path.exists(trap.path)
        hp.remove_trap(trap.trap_id)
        assert not os.path.exists(trap.path)


class TestDirectoryHoneypot:
    def test_create_directory_trap(self, temp_dir):
        dhp = DirectoryHoneypot(temp_dir)
        trap = dhp.create_trap(name="secret_data", depth=2, files_per_dir=2)
        assert trap.trap_type == HoneypotType.DIRECTORY
        assert os.path.isdir(trap.path)
        assert len(trap.metadata.get("file_traps", [])) > 0

    def test_check_all(self, temp_dir):
        dhp = DirectoryHoneypot(temp_dir)
        dhp.create_trap(name="bait_dir", depth=1, files_per_dir=2)
        alerts = dhp.check_all()
        # Fresh traps shouldn't trigger
        assert isinstance(alerts, list)


class TestCredentialHoneypot:
    def test_create_canary(self, temp_dir):
        chp = CredentialHoneypot(temp_dir)
        trap = chp.create_canary_credentials(service_name="test-api")
        assert trap.trap_type == HoneypotType.CREDENTIAL
        assert os.path.exists(trap.path)
        assert "canary_" in trap.metadata.get("canary_token", "")

    def test_check_token_usage(self, temp_dir):
        chp = CredentialHoneypot(temp_dir)
        trap = chp.create_canary_credentials(service_name="my-api")
        token = trap.metadata["canary_token"]
        alert = chp.check_token_usage(token)
        assert alert is not None
        assert alert.severity == AlertSeverity.CRITICAL
        assert "CANARY TOKEN" in alert.description

    def test_unknown_token(self, temp_dir):
        chp = CredentialHoneypot(temp_dir)
        alert = chp.check_token_usage("unknown_token")
        assert alert is None


class TestHoneypotOrchestrator:
    def test_deploy_standard(self, temp_dir):
        orch = HoneypotOrchestrator(base_dir=temp_dir)
        counts = orch.deploy_standard_traps()
        assert counts["files"] > 0
        assert counts["directories"] > 0
        assert counts["credentials"] > 0

    def test_get_status(self, temp_dir):
        orch = HoneypotOrchestrator(base_dir=temp_dir)
        status = orch.get_status()
        assert "is_monitoring" in status
        assert "deployed_traps" in status


class TestHoneypotAlertManager:
    def test_process_alert(self):
        mgr = HoneypotAlertManager()
        alert = HoneypotAlert(
            trap_id="test",
            severity=AlertSeverity.HIGH,
            description="Test alert",
        )
        mgr.process_alert(alert)
        summary = mgr.get_summary()
        assert summary["total_alerts"] == 1
        assert summary["severity_counts"]["high"] == 1

    def test_callback_fired(self):
        mgr = HoneypotAlertManager()
        fired = []
        mgr.register_callback(lambda a: fired.append(a))
        alert = HoneypotAlert(severity=AlertSeverity.CRITICAL, description="test")
        mgr.process_alert(alert)
        assert len(fired) == 1
