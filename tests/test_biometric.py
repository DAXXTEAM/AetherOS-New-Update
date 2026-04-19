"""Tests for the Biometric Integration (YoKiMo)."""
import time
import pytest
from security.biometric import (
    YoKiMoBiometricEngine, BiometricProfile, AuthenticationLevel,
    BiometricType, AuthResult, TypingPatternAnalyzer, CommandPatternAnalyzer,
    HardwareTokenSimulator, AuthSession,
)


class TestTypingPatternAnalyzer:
    def test_enroll(self):
        analyzer = TypingPatternAnalyzer()
        timings = [0.1, 0.15, 0.12, 0.11, 0.14, 0.13, 0.12, 0.15, 0.11, 0.13]
        result = analyzer.enroll("user-1", timings)
        assert result.get("enrolled")

    def test_verify_matching(self):
        analyzer = TypingPatternAnalyzer(threshold=0.5)
        timings = [0.1, 0.15, 0.12, 0.11, 0.14, 0.13, 0.12, 0.15, 0.11, 0.13]
        analyzer.enroll("user-1", timings)
        ok, score = analyzer.verify("user-1", [0.11, 0.14, 0.13, 0.12, 0.15])
        assert score > 0

    def test_verify_not_enrolled(self):
        analyzer = TypingPatternAnalyzer()
        ok, score = analyzer.verify("unknown", [0.1, 0.2, 0.3, 0.4, 0.5])
        assert not ok
        assert score == 0.0

    def test_enroll_too_few_samples(self):
        analyzer = TypingPatternAnalyzer(min_samples=10)
        result = analyzer.enroll("user-1", [0.1, 0.2])
        assert "error" in result


class TestHardwareTokenSimulator:
    def test_register_and_challenge(self):
        tokens = HardwareTokenSimulator()
        reg = tokens.register_token("user-1")
        assert "token_id" in reg

        challenge = tokens.create_challenge("user-1")
        assert challenge is not None

    def test_verify_correct(self):
        import hmac, hashlib
        tokens = HardwareTokenSimulator()
        tokens.register_token("user-1")
        secret = tokens._registered_tokens["user-1"]["secret"]
        challenge = tokens.create_challenge("user-1")

        response = hmac.new(secret.encode(), challenge.encode(), hashlib.sha256).hexdigest()
        assert tokens.verify_response("user-1", response)

    def test_verify_wrong(self):
        tokens = HardwareTokenSimulator()
        tokens.register_token("user-1")
        tokens.create_challenge("user-1")
        assert not tokens.verify_response("user-1", "wrong-response")

    def test_challenge_unregistered(self):
        tokens = HardwareTokenSimulator()
        assert tokens.create_challenge("unknown") is None


class TestYoKiMoBiometricEngine:
    def test_enroll_user(self):
        engine = YoKiMoBiometricEngine()
        result = engine.enroll_user("user-1", voiceprint_data="test-voice")
        assert result["enrolled"]
        assert "profile" in result
        assert "hardware_token" in result

    def test_authenticate_voiceprint(self):
        engine = YoKiMoBiometricEngine()
        engine.enroll_user("user-1", voiceprint_data="test-voice")
        result = engine.authenticate("user-1", {"voiceprint": "test-voice"})
        assert result["result"] == AuthResult.SUCCESS.value

    def test_authenticate_wrong_voiceprint(self):
        engine = YoKiMoBiometricEngine()
        engine.enroll_user("user-1", voiceprint_data="correct-voice")
        result = engine.authenticate("user-1", {"voiceprint": "wrong-voice"})
        assert result["result"] == AuthResult.FAILURE.value

    def test_authenticate_unenrolled(self):
        engine = YoKiMoBiometricEngine()
        result = engine.authenticate("unknown-user")
        assert result["result"] == AuthResult.FAILURE.value

    def test_lockout(self):
        engine = YoKiMoBiometricEngine(max_failures=3, lockout_minutes=1)
        engine.enroll_user("user-1", voiceprint_data="voice")
        for _ in range(3):
            engine.authenticate("user-1", {"voiceprint": "wrong"})
        result = engine.authenticate("user-1", {"voiceprint": "voice"})
        assert result["result"] == AuthResult.LOCKED.value

    def test_approve_operation(self):
        engine = YoKiMoBiometricEngine()
        engine.enroll_user("user-1", voiceprint_data="voice")
        auth = engine.authenticate("user-1", {"voiceprint": "voice"})
        session_id = auth["session"]["session_id"]

        approval = engine.approve_operation(session_id, "file_delete")
        # Single factor = BASIC level, file_delete needs ELEVATED
        assert "approved" in approval

    def test_session_management(self):
        engine = YoKiMoBiometricEngine()
        engine.enroll_user("user-1", voiceprint_data="voice")
        auth = engine.authenticate("user-1", {"voiceprint": "voice"})
        session_id = auth["session"]["session_id"]

        session = engine.get_session(session_id)
        assert session is not None
        assert session["valid"]

        assert engine.revoke_session(session_id)
        assert engine.get_session(session_id) is None

    def test_continuous_verify(self):
        engine = YoKiMoBiometricEngine()
        engine.enroll_user("user-1", voiceprint_data="voice")
        auth = engine.authenticate("user-1", {"voiceprint": "voice"})
        session_id = auth["session"]["session_id"]

        score = engine.continuous_verify(session_id, {"confidence": 0.9})
        assert score > 0

    def test_get_stats(self):
        engine = YoKiMoBiometricEngine()
        stats = engine.get_stats()
        assert "enrolled_users" in stats
        assert "total_auth_attempts" in stats


class TestBiometricProfile:
    def test_locking(self):
        from datetime import datetime, timedelta
        profile = BiometricProfile(user_id="test")
        assert not profile.is_locked()
        profile.locked_until = datetime.now() + timedelta(minutes=5)
        assert profile.is_locked()

    def test_record_success(self):
        profile = BiometricProfile(user_id="test")
        profile.failure_count = 3
        profile.record_success()
        assert profile.failure_count == 0
        assert profile.last_verified is not None

    def test_record_failure_lockout(self):
        profile = BiometricProfile(user_id="test")
        for _ in range(4):
            profile.record_failure(max_failures=5)
        assert not profile.is_locked()
        profile.record_failure(max_failures=5)
        assert profile.is_locked()
