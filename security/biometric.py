"""Biometric Integration   YoKiMo biometric command approval system.

Implements multi-factor biometric authentication for high-security operations:
- Voiceprint verification (simulated)
- Behavioral biometrics (typing patterns, command patterns)
- Hardware token simulation (FIDO2/WebAuthn)
- Biometric challenge-response protocol
- Continuous authentication monitoring
- Risk-based step-up authentication

The 'YoKiMo' logic provides a personality-aware authentication layer
that adapts to user behavior over time.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import random
import secrets
import struct
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Optional

logger = logging.getLogger("aetheros.security.biometric")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class AuthenticationLevel(Enum):
    NONE = 0
    BASIC = 1
    ELEVATED = 2
    BIOMETRIC = 3
    MULTI_FACTOR = 4
    MAXIMUM = 5


class BiometricType(Enum):
    VOICEPRINT = "voiceprint"
    TYPING_PATTERN = "typing_pattern"
    COMMAND_PATTERN = "command_pattern"
    HARDWARE_TOKEN = "hardware_token"
    BEHAVIORAL = "behavioral"


class AuthResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CHALLENGE = "challenge"
    LOCKED = "locked"
    TIMEOUT = "timeout"


@dataclass
class BiometricProfile:
    """User's biometric profile for authentication."""
    profile_id: str = field(default_factory=lambda: f"bio-{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    voiceprint_hash: str = ""
    typing_pattern: dict[str, float] = field(default_factory=dict)
    command_history_hash: str = ""
    behavioral_baseline: dict[str, Any] = field(default_factory=dict)
    hardware_token_id: str = ""
    challenge_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    last_verified: Optional[datetime] = None
    verification_count: int = 0
    failure_count: int = 0
    locked_until: Optional[datetime] = None

    def is_locked(self) -> bool:
        if self.locked_until and datetime.now() < self.locked_until:
            return True
        if self.locked_until and datetime.now() >= self.locked_until:
            self.locked_until = None
            self.failure_count = 0
        return False

    def record_success(self) -> None:
        self.last_verified = datetime.now()
        self.verification_count += 1
        self.failure_count = 0

    def record_failure(self, max_failures: int = 5,
                       lockout_minutes: int = 15) -> bool:
        self.failure_count += 1
        if self.failure_count >= max_failures:
            self.locked_until = datetime.now() + timedelta(minutes=lockout_minutes)
            logger.warning(f"Biometric profile {self.profile_id} locked for {lockout_minutes}min")
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "has_voiceprint": bool(self.voiceprint_hash),
            "has_typing_pattern": bool(self.typing_pattern),
            "has_hardware_token": bool(self.hardware_token_id),
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "verification_count": self.verification_count,
            "is_locked": self.is_locked(),
        }


@dataclass
class AuthenticationChallenge:
    """A challenge issued for biometric verification."""
    challenge_id: str = field(default_factory=lambda: f"chal-{uuid.uuid4().hex[:8]}")
    biometric_type: BiometricType = BiometricType.BEHAVIORAL
    challenge_data: str = ""
    expected_response_hash: str = ""
    issued_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    resolved: bool = False
    result: Optional[AuthResult] = None

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "type": self.biometric_type.value,
            "challenge": self.challenge_data,
            "expires_at": self.expires_at.isoformat(),
            "resolved": self.resolved,
        }


@dataclass
class AuthSession:
    """An active authentication session."""
    session_id: str = field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:10]}")
    user_id: str = ""
    level: AuthenticationLevel = AuthenticationLevel.NONE
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=1))
    factors_verified: list[BiometricType] = field(default_factory=list)
    continuous_score: float = 1.0
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at and self.continuous_score > 0.3

    def add_factor(self, factor: BiometricType) -> None:
        if factor not in self.factors_verified:
            self.factors_verified.append(factor)
            self.level = AuthenticationLevel(
                min(len(self.factors_verified) + 1, AuthenticationLevel.MAXIMUM.value)
            )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "level": self.level.name,
            "factors": [f.value for f in self.factors_verified],
            "continuous_score": round(self.continuous_score, 3),
            "risk_score": round(self.risk_score, 3),
            "valid": self.is_valid,
            "expires_at": self.expires_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Typing Pattern Analyzer
# ---------------------------------------------------------------------------

class TypingPatternAnalyzer:
    """Analyzes typing patterns for behavioral biometric authentication."""

    def __init__(self, min_samples: int = 10, threshold: float = 0.75):
        self.min_samples = min_samples
        self.threshold = threshold
        self._baselines: dict[str, dict] = {}

    def enroll(self, user_id: str, keystroke_timings: list[float]) -> dict:
        """Enroll a user's typing pattern baseline."""
        if len(keystroke_timings) < self.min_samples:
            return {"error": f"Need at least {self.min_samples} timing samples"}

        stats = self._compute_stats(keystroke_timings)
        self._baselines[user_id] = stats
        return {"enrolled": True, "stats": stats}

    def verify(self, user_id: str, keystroke_timings: list[float]) -> tuple[bool, float]:
        """Verify a typing pattern against baseline."""
        baseline = self._baselines.get(user_id)
        if not baseline:
            return False, 0.0

        if len(keystroke_timings) < 5:
            return False, 0.0

        current = self._compute_stats(keystroke_timings)
        similarity = self._compute_similarity(baseline, current)
        return similarity >= self.threshold, similarity

    def _compute_stats(self, timings: list[float]) -> dict:
        """Compute statistical features of keystroke timings."""
        if not timings:
            return {}
        mean = sum(timings) / len(timings)
        variance = sum((t - mean) ** 2 for t in timings) / max(len(timings) - 1, 1)
        std_dev = math.sqrt(variance)

        sorted_t = sorted(timings)
        median = sorted_t[len(sorted_t) // 2]

        # Digraph features (consecutive key intervals)
        digraphs = [timings[i + 1] - timings[i] for i in range(len(timings) - 1)]
        dig_mean = sum(digraphs) / len(digraphs) if digraphs else 0

        return {
            "mean": mean,
            "std_dev": std_dev,
            "median": median,
            "min": min(timings),
            "max": max(timings),
            "digraph_mean": dig_mean,
            "sample_count": len(timings),
        }

    def _compute_similarity(self, baseline: dict, current: dict) -> float:
        """Compute similarity between baseline and current typing pattern."""
        features = ["mean", "std_dev", "median", "digraph_mean"]
        total_diff = 0.0
        count = 0

        for feat in features:
            b_val = baseline.get(feat, 0)
            c_val = current.get(feat, 0)
            if b_val != 0:
                diff = abs(b_val - c_val) / abs(b_val)
                total_diff += diff
                count += 1

        if count == 0:
            return 0.0
        avg_diff = total_diff / count
        return max(0.0, 1.0 - avg_diff)


# ---------------------------------------------------------------------------
# Command Pattern Analyzer
# ---------------------------------------------------------------------------

class CommandPatternAnalyzer:
    """Analyzes command usage patterns for behavioral authentication."""

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self._baselines: dict[str, dict] = {}
        self._current_patterns: dict[str, deque] = {}

    def record_command(self, user_id: str, command: str) -> None:
        """Record a command for pattern analysis."""
        if user_id not in self._current_patterns:
            self._current_patterns[user_id] = deque(maxlen=self.window_size)
        self._current_patterns[user_id].append({
            "command": command,
            "timestamp": time.time(),
        })

    def build_baseline(self, user_id: str) -> dict:
        """Build a baseline from recorded commands."""
        if user_id not in self._current_patterns:
            return {}

        commands = list(self._current_patterns[user_id])
        cmd_freq = {}
        for entry in commands:
            cmd = entry["command"].split()[0] if entry["command"] else ""
            cmd_freq[cmd] = cmd_freq.get(cmd, 0) + 1

        total = sum(cmd_freq.values())
        distribution = {k: v / total for k, v in cmd_freq.items()}

        # Time-of-day pattern
        hours = [datetime.fromtimestamp(e["timestamp"]).hour for e in commands]
        hour_dist = {}
        for h in hours:
            hour_dist[h] = hour_dist.get(h, 0) + 1
        for h in hour_dist:
            hour_dist[h] /= len(hours)

        baseline = {
            "command_distribution": distribution,
            "hour_distribution": hour_dist,
            "avg_command_length": sum(len(e["command"]) for e in commands) / max(len(commands), 1),
            "unique_commands": len(cmd_freq),
        }
        self._baselines[user_id] = baseline
        return baseline

    def verify(self, user_id: str, threshold: float = 0.6) -> tuple[bool, float]:
        """Verify current behavior against baseline."""
        baseline = self._baselines.get(user_id)
        if not baseline or user_id not in self._current_patterns:
            return False, 0.0

        current = list(self._current_patterns[user_id])[-20:]
        if len(current) < 5:
            return False, 0.0

        # Compare command distributions
        cmd_freq = {}
        for entry in current:
            cmd = entry["command"].split()[0] if entry["command"] else ""
            cmd_freq[cmd] = cmd_freq.get(cmd, 0) + 1
        total = sum(cmd_freq.values())
        current_dist = {k: v / total for k, v in cmd_freq.items()}

        # KL divergence approximation
        overlap = 0.0
        for cmd, freq in current_dist.items():
            if cmd in baseline["command_distribution"]:
                overlap += min(freq, baseline["command_distribution"][cmd])

        return overlap >= threshold, overlap


# ---------------------------------------------------------------------------
# Hardware Token Simulator
# ---------------------------------------------------------------------------

class HardwareTokenSimulator:
    """Simulates FIDO2/WebAuthn hardware token operations."""

    def __init__(self):
        self._registered_tokens: dict[str, dict] = {}
        self._challenges: dict[str, str] = {}

    def register_token(self, user_id: str) -> dict:
        """Register a new hardware token for a user."""
        token_id = f"hwtoken-{uuid.uuid4().hex[:10]}"
        secret = secrets.token_hex(32)
        public_key = hashlib.sha256(secret.encode()).hexdigest()

        self._registered_tokens[user_id] = {
            "token_id": token_id,
            "public_key": public_key,
            "secret": secret,
            "registered_at": datetime.now().isoformat(),
            "usage_count": 0,
        }
        return {"token_id": token_id, "public_key": public_key}

    def create_challenge(self, user_id: str) -> Optional[str]:
        """Create an authentication challenge for the user's token."""
        if user_id not in self._registered_tokens:
            return None
        challenge = secrets.token_hex(32)
        self._challenges[user_id] = challenge
        return challenge

    def verify_response(self, user_id: str, response: str) -> bool:
        """Verify a challenge-response from the hardware token."""
        token = self._registered_tokens.get(user_id)
        challenge = self._challenges.pop(user_id, None)
        if not token or not challenge:
            return False

        expected = hmac.new(
            token["secret"].encode(), challenge.encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, response):
            token["usage_count"] += 1
            return True
        return False

    def get_registered_tokens(self) -> list[dict]:
        return [
            {"user_id": uid, "token_id": t["token_id"], "usage_count": t["usage_count"]}
            for uid, t in self._registered_tokens.items()
        ]


# ---------------------------------------------------------------------------
# YoKiMo   Personality-Aware Biometric Authentication
# ---------------------------------------------------------------------------

class YoKiMoBiometricEngine:
    """YoKiMo biometric command approval system.

    Provides adaptive, personality-aware authentication that:
    - Learns user behavior patterns over time
    - Adjusts security levels based on risk
    - Supports multi-factor biometric verification
    - Implements continuous authentication
    """

    # Operations requiring biometric approval
    CRITICAL_OPERATIONS = {
        "kill_switch": AuthenticationLevel.MAXIMUM,
        "system_shutdown": AuthenticationLevel.MULTI_FACTOR,
        "config_change": AuthenticationLevel.BIOMETRIC,
        "file_delete": AuthenticationLevel.ELEVATED,
        "network_rule": AuthenticationLevel.BIOMETRIC,
        "code_deploy": AuthenticationLevel.MULTI_FACTOR,
        "secret_access": AuthenticationLevel.MAXIMUM,
        "agent_modify": AuthenticationLevel.ELEVATED,
        "memory_clear": AuthenticationLevel.BIOMETRIC,
        "mesh_join": AuthenticationLevel.ELEVATED,
    }

    def __init__(
        self,
        max_failures: int = 5,
        lockout_minutes: int = 15,
        session_duration_hours: float = 1.0,
        continuous_auth: bool = True,
    ):
        self.max_failures = max_failures
        self.lockout_minutes = lockout_minutes
        self.session_duration = timedelta(hours=session_duration_hours)
        self.continuous_auth = continuous_auth

        self._profiles: dict[str, BiometricProfile] = {}
        self._sessions: dict[str, AuthSession] = {}
        self._active_challenges: dict[str, AuthenticationChallenge] = {}

        self.typing_analyzer = TypingPatternAnalyzer()
        self.command_analyzer = CommandPatternAnalyzer()
        self.hardware_tokens = HardwareTokenSimulator()

        self._auth_log: deque[dict] = deque(maxlen=5000)
        self._stats = {
            "total_auth_attempts": 0,
            "successful_auths": 0,
            "failed_auths": 0,
            "lockouts": 0,
            "challenges_issued": 0,
        }

        logger.info("YoKiMo Biometric Engine initialized")

    def enroll_user(self, user_id: str, voiceprint_data: Optional[str] = None,
                    typing_samples: Optional[list[float]] = None) -> dict:
        """Enroll a user in the biometric system."""
        profile = BiometricProfile(
            user_id=user_id,
            voiceprint_hash=hashlib.sha256(voiceprint_data.encode()).hexdigest() if voiceprint_data else "",
        )

        if typing_samples:
            self.typing_analyzer.enroll(user_id, typing_samples)
            profile.typing_pattern = self.typing_analyzer._baselines.get(user_id, {})

        token = self.hardware_tokens.register_token(user_id)
        profile.hardware_token_id = token["token_id"]

        self._profiles[user_id] = profile
        self._log_auth_event(user_id, "enrollment", "success")
        return {
            "enrolled": True,
            "profile": profile.to_dict(),
            "hardware_token": token,
        }

    def authenticate(self, user_id: str,
                     factors: Optional[dict[str, Any]] = None) -> dict:
        """Authenticate a user with provided factors."""
        self._stats["total_auth_attempts"] += 1
        profile = self._profiles.get(user_id)
        if not profile:
            self._stats["failed_auths"] += 1
            return {"result": AuthResult.FAILURE.value, "reason": "User not enrolled"}

        if profile.is_locked():
            return {"result": AuthResult.LOCKED.value, "reason": "Account locked"}

        factors = factors or {}
        verified_factors = []

        # Verify typing pattern
        if "typing_timings" in factors:
            ok, score = self.typing_analyzer.verify(user_id, factors["typing_timings"])
            if ok:
                verified_factors.append(BiometricType.TYPING_PATTERN)

        # Verify voiceprint
        if "voiceprint" in factors and profile.voiceprint_hash:
            vp_hash = hashlib.sha256(factors["voiceprint"].encode()).hexdigest()
            if hmac.compare_digest(vp_hash, profile.voiceprint_hash):
                verified_factors.append(BiometricType.VOICEPRINT)

        # Verify hardware token
        if "token_response" in factors:
            if self.hardware_tokens.verify_response(user_id, factors["token_response"]):
                verified_factors.append(BiometricType.HARDWARE_TOKEN)

        # Verify command pattern
        if "verify_behavior" in factors:
            ok, score = self.command_analyzer.verify(user_id)
            if ok:
                verified_factors.append(BiometricType.BEHAVIORAL)

        if verified_factors:
            profile.record_success()
            session = self._create_session(user_id, verified_factors)
            self._stats["successful_auths"] += 1
            self._log_auth_event(user_id, "authentication", "success", {
                "factors": [f.value for f in verified_factors],
            })
            return {
                "result": AuthResult.SUCCESS.value,
                "session": session.to_dict(),
                "factors_verified": [f.value for f in verified_factors],
            }

        locked = profile.record_failure(self.max_failures, self.lockout_minutes)
        self._stats["failed_auths"] += 1
        if locked:
            self._stats["lockouts"] += 1
        self._log_auth_event(user_id, "authentication", "failure")
        return {
            "result": AuthResult.FAILURE.value,
            "reason": "No valid biometric factors provided",
            "locked": locked,
        }

    def approve_operation(self, session_id: str, operation: str) -> dict:
        """Check if an operation is approved for the current session."""
        session = self._sessions.get(session_id)
        if not session or not session.is_valid:
            return {
                "approved": False,
                "reason": "Invalid or expired session",
                "required_level": self.CRITICAL_OPERATIONS.get(operation, AuthenticationLevel.BASIC).name,
            }

        required_level = self.CRITICAL_OPERATIONS.get(operation, AuthenticationLevel.BASIC)
        if session.level.value >= required_level.value:
            self._log_auth_event(session.user_id, f"operation_approved:{operation}", "success")
            return {
                "approved": True,
                "operation": operation,
                "session_level": session.level.name,
                "required_level": required_level.name,
            }

        # Issue step-up challenge
        challenge = self._create_challenge(session.user_id, BiometricType.HARDWARE_TOKEN)
        self._stats["challenges_issued"] += 1
        return {
            "approved": False,
            "reason": "Insufficient authentication level",
            "session_level": session.level.name,
            "required_level": required_level.name,
            "challenge": challenge.to_dict() if challenge else None,
        }

    def continuous_verify(self, session_id: str,
                          current_behavior: Optional[dict] = None) -> float:
        """Update continuous authentication score."""
        session = self._sessions.get(session_id)
        if not session:
            return 0.0

        if not self.continuous_auth:
            return session.continuous_score

        if current_behavior:
            # Score decays over time without fresh behavior verification
            time_factor = max(0.5, 1.0 - (datetime.now() - session.created_at).total_seconds() / 3600)
            behavior_score = current_behavior.get("confidence", 0.8)
            session.continuous_score = min(1.0, time_factor * behavior_score)
        else:
            elapsed = (datetime.now() - session.created_at).total_seconds()
            decay_rate = 0.01
            session.continuous_score = max(0.0, 1.0 - elapsed * decay_rate / 60)

        return session.continuous_score

    def _create_session(self, user_id: str,
                        factors: list[BiometricType]) -> AuthSession:
        """Create a new authenticated session."""
        session = AuthSession(
            user_id=user_id,
            expires_at=datetime.now() + self.session_duration,
        )
        for factor in factors:
            session.add_factor(factor)
        self._sessions[session.session_id] = session
        return session

    def _create_challenge(self, user_id: str,
                          bio_type: BiometricType) -> Optional[AuthenticationChallenge]:
        """Create an authentication challenge."""
        if bio_type == BiometricType.HARDWARE_TOKEN:
            challenge_data = self.hardware_tokens.create_challenge(user_id)
            if not challenge_data:
                return None
            challenge = AuthenticationChallenge(
                biometric_type=bio_type,
                challenge_data=challenge_data,
            )
        else:
            challenge = AuthenticationChallenge(
                biometric_type=bio_type,
                challenge_data=secrets.token_hex(16),
            )
        self._active_challenges[challenge.challenge_id] = challenge
        return challenge

    def _log_auth_event(self, user_id: str, action: str,
                        result: str, details: Optional[dict] = None) -> None:
        self._auth_log.append({
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "action": action,
            "result": result,
            "details": details or {},
        })

    def get_session(self, session_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        return session.to_dict() if session else None

    def revoke_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def get_profile(self, user_id: str) -> Optional[dict]:
        profile = self._profiles.get(user_id)
        return profile.to_dict() if profile else None

    def get_auth_log(self, last_n: int = 50) -> list[dict]:
        return list(self._auth_log)[-last_n:]

    def get_stats(self) -> dict:
        return {
            "enrolled_users": len(self._profiles),
            "active_sessions": sum(1 for s in self._sessions.values() if s.is_valid),
            "hardware_tokens": len(self.hardware_tokens._registered_tokens),
            **self._stats,
        }

    def get_status(self) -> dict:
        return {
            "engine": "YoKiMo Biometric",
            "continuous_auth": self.continuous_auth,
            "enrolled_users": len(self._profiles),
            "active_sessions": len(self._sessions),
            "stats": self._stats,
        }
