"""Tests for security module."""
import os
import time
import pytest

from security.crypto import (
    QuantumSafeCrypto, CryptoSuite, KyberSimulator, DilithiumSimulator,
    AESEncryptor, CryptoAlgorithm, KeyPair,
)
from security.kill_switch import KillSwitch, KillSwitchStatus
from security.audit import AuditLogger, AuditEntry, AuditCategory, AuditSeverity


class TestKyberSimulator:
    def test_keygen(self):
        kp = KyberSimulator.keygen(CryptoAlgorithm.KYBER_768)
        assert kp.public_key
        assert kp.private_key
        assert kp.algorithm == "kyber-768"

    def test_encapsulate_decapsulate(self):
        kp = KyberSimulator.keygen(CryptoAlgorithm.KYBER_768)
        shared_enc, ct = KyberSimulator.encapsulate(kp.public_key)
        shared_dec = KyberSimulator.decapsulate(kp.private_key, ct)
        assert shared_enc == shared_dec

    def test_different_security_levels(self):
        for algo in [CryptoAlgorithm.KYBER_512, CryptoAlgorithm.KYBER_768, CryptoAlgorithm.KYBER_1024]:
            kp = KyberSimulator.keygen(algo)
            shared, ct = KyberSimulator.encapsulate(kp.public_key, algo)
            recovered = KyberSimulator.decapsulate(kp.private_key, ct, algo)
            assert shared == recovered


class TestDilithiumSimulator:
    def test_keygen(self):
        kp = DilithiumSimulator.keygen(CryptoAlgorithm.DILITHIUM_3)
        assert kp.public_key
        assert kp.private_key

    def test_sign_verify(self):
        kp = DilithiumSimulator.keygen(CryptoAlgorithm.DILITHIUM_3)
        message = b"Test message for signing"
        sig = DilithiumSimulator.sign(kp.private_key, message)
        assert DilithiumSimulator.verify(kp.public_key, message, sig)

    def test_invalid_signature(self):
        kp = DilithiumSimulator.keygen(CryptoAlgorithm.DILITHIUM_3)
        message = b"Original message"
        sig = DilithiumSimulator.sign(kp.private_key, message)
        assert not DilithiumSimulator.verify(kp.public_key, b"Tampered message", sig)

    def test_different_levels(self):
        for algo in [CryptoAlgorithm.DILITHIUM_2, CryptoAlgorithm.DILITHIUM_3, CryptoAlgorithm.DILITHIUM_5]:
            kp = DilithiumSimulator.keygen(algo)
            sig = DilithiumSimulator.sign(kp.private_key, b"test", algo)
            assert DilithiumSimulator.verify(kp.public_key, b"test", sig, algo)


class TestAESEncryptor:
    def test_encrypt_decrypt(self):
        key = os.urandom(32)
        plaintext = b"Secret message"
        ct = AESEncryptor.encrypt(key, plaintext)
        recovered = AESEncryptor.decrypt(key, ct)
        assert recovered == plaintext

    def test_with_associated_data(self):
        key = os.urandom(32)
        plaintext = b"Message with AD"
        ad = b"associated data"
        ct = AESEncryptor.encrypt(key, plaintext, ad)
        recovered = AESEncryptor.decrypt(key, ct, ad)
        assert recovered == plaintext

    def test_wrong_key_fails(self):
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        ct = AESEncryptor.encrypt(key1, b"secret")
        with pytest.raises(Exception):
            AESEncryptor.decrypt(key2, ct)

    def test_short_key_padding(self):
        key = b"short"
        ct = AESEncryptor.encrypt(key, b"data")
        recovered = AESEncryptor.decrypt(key, ct)
        assert recovered == b"data"


class TestQuantumSafeCrypto:
    @pytest.fixture
    def crypto(self):
        return QuantumSafeCrypto()

    def test_initialization(self, crypto):
        status = crypto.get_status()
        assert status["kem_initialized"]
        assert status["sig_initialized"]

    def test_encrypt_decrypt(self, crypto):
        encrypted = crypto.encrypt("Hello Quantum World")
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == "Hello Quantum World"

    def test_sign_verify(self, crypto):
        message = "Signed message"
        sig = crypto.sign(message)
        assert crypto.verify(message, sig)

    def test_tampered_message_fails(self, crypto):
        sig = crypto.sign("original")
        assert not crypto.verify("tampered", sig)

    def test_cross_party_encryption(self):
        alice = QuantumSafeCrypto()
        bob = QuantumSafeCrypto()
        encrypted = alice.encrypt("Secret for Bob", bob.public_kem_key)
        decrypted = bob.decrypt(encrypted)
        assert decrypted == "Secret for Bob"


class TestKillSwitch:
    @pytest.fixture(autouse=True)
    def cleanup_kill_file(self):
        from config.constants import KILL_SWITCH_FILE
        yield
        if os.path.exists(KILL_SWITCH_FILE):
            os.remove(KILL_SWITCH_FILE)

    def test_initial_state(self):
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        assert ks.status == KillSwitchStatus.ARMED

    def test_disabled(self):
        ks = KillSwitch(enabled=False)
        assert ks.status == KillSwitchStatus.DISARMED

    def test_engage(self):
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        result = ks.engage("test", "unit test")
        assert result is True
        assert ks.is_engaged

    def test_disengage(self):
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        ks.engage("test", "test")
        time.sleep(5.1)  # Must wait minimum engagement time
        result = ks.disengage("auth-token")
        assert result is True
        assert ks.status == KillSwitchStatus.COOLDOWN

    def test_callback(self):
        triggered = []
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        ks.register_callback(lambda e: triggered.append(e))
        ks.engage("test", "callback test")
        assert len(triggered) == 1

    def test_history(self):
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        ks.engage("test", "history test")
        history = ks.get_history()
        assert len(history) >= 1

    def test_heartbeat(self):
        ks = KillSwitch(enabled=True, watchdog_timeout=9999)
        ks.heartbeat()
        status = ks.get_status()
        assert status["last_heartbeat_age"] < 1.0


class TestAuditLogger:
    @pytest.fixture
    def audit(self, tmp_path):
        return AuditLogger(log_dir=str(tmp_path))

    def test_log_entry(self, audit):
        entry = audit.log(
            category=AuditCategory.COMMAND_EXECUTION,
            action="test_command",
            target="echo hello",
        )
        assert entry.entry_id
        assert entry.entry_hash

    def test_chain_integrity(self, audit):
        audit.log(AuditCategory.COMMAND_EXECUTION, "cmd1", "target1")
        audit.log(AuditCategory.FILE_ACCESS, "read", "/tmp/file")
        audit.log(AuditCategory.NETWORK_ACCESS, "fetch", "https://example.com")
        valid, tampered = audit.verify_chain()
        assert valid
        assert len(tampered) == 0

    def test_log_command(self, audit):
        entry = audit.log_command("ls -la /tmp")
        assert entry.category == AuditCategory.COMMAND_EXECUTION

    def test_log_security_event(self, audit):
        entry = audit.log_security_event(
            "suspicious_activity",
            severity=AuditSeverity.CRITICAL,
        )
        assert entry.severity == AuditSeverity.CRITICAL

    def test_query_entries(self, audit):
        audit.log(AuditCategory.COMMAND_EXECUTION, "cmd1")
        audit.log(AuditCategory.FILE_ACCESS, "read")
        audit.log(AuditCategory.COMMAND_EXECUTION, "cmd2")
        entries = audit.get_entries(category=AuditCategory.COMMAND_EXECUTION)
        assert len(entries) == 2

    def test_stats(self, audit):
        audit.log(AuditCategory.COMMAND_EXECUTION, "cmd1")
        audit.log(AuditCategory.FILE_ACCESS, "read")
        stats = audit.get_stats()
        assert stats["total_entries"] == 2
        assert stats["chain_valid"]

    def test_file_persistence(self, audit, tmp_path):
        audit.log(AuditCategory.COMMAND_EXECUTION, "persistent")
        log_files = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
        assert len(log_files) >= 1
