"""AetherOS Nexus   Ambient Sound Classification.

Classifies environmental sounds for contextual awareness:
- Conversation detection (multiple speakers)
- Alert sounds (alarms, notifications)
- Environmental noise profiling
- Anomaly detection (glass breaking, shouting)
"""
from __future__ import annotations

import enum
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.ambient")


class SoundCategory(enum.Enum):
    """Ambient sound categories."""
    SILENCE = "silence"
    SPEECH = "speech"
    MUSIC = "music"
    TYPING = "typing"
    MACHINERY = "machinery"
    NATURE = "nature"
    TRAFFIC = "traffic"
    ALARM = "alarm"
    GLASS_BREAK = "glass_break"
    DOOR = "door"
    FOOTSTEPS = "footsteps"
    UNKNOWN = "unknown"


class EnvironmentType(enum.Enum):
    """Classified environment type."""
    OFFICE = "office"
    HOME = "home"
    OUTDOOR = "outdoor"
    VEHICLE = "vehicle"
    INDUSTRIAL = "industrial"
    QUIET_ROOM = "quiet_room"
    UNKNOWN = "unknown"


@dataclass
class SoundEvent:
    """Detected sound event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: SoundCategory = SoundCategory.UNKNOWN
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    energy_db: float = 0.0
    is_anomaly: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "category": self.category.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "energy_db": self.energy_db,
            "is_anomaly": self.is_anomaly,
        }


@dataclass
class SoundProfile:
    """Baseline sound profile for an environment."""
    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "default"
    avg_energy_db: float = 0.0
    dominant_category: SoundCategory = SoundCategory.UNKNOWN
    category_distribution: Dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def update(self, energy_db: float, category: SoundCategory) -> None:
        alpha = 1.0 / (self.sample_count + 1)
        self.avg_energy_db = (1 - alpha) * self.avg_energy_db + alpha * energy_db
        cat_key = category.value
        self.category_distribution[cat_key] = self.category_distribution.get(cat_key, 0) + 1
        self.sample_count += 1
        # Update dominant category
        if self.category_distribution:
            self.dominant_category = SoundCategory(
                max(self.category_distribution, key=self.category_distribution.get)
            )


class AudioFeatureExtractor:
    """Extracts features from audio for classification."""

    def __init__(self, sample_rate: int = 16000, frame_size: int = 1024):
        self.sample_rate = sample_rate
        self.frame_size = frame_size

    def compute_energy_db(self, samples: List[float]) -> float:
        if not samples:
            return -100.0
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        if rms <= 0:
            return -100.0
        import math
        return 20 * math.log10(rms + 1e-10)

    def compute_zero_crossing_rate(self, samples: List[float]) -> float:
        if len(samples) < 2:
            return 0.0
        crossings = sum(1 for i in range(1, len(samples)) if samples[i] * samples[i-1] < 0)
        return crossings / len(samples)

    def compute_spectral_centroid(self, samples: List[float]) -> float:
        """Compute simplified spectral centroid."""
        if not samples:
            return 0.0
        abs_samples = [abs(s) for s in samples]
        total = sum(abs_samples)
        if total == 0:
            return 0.0
        weighted_sum = sum(i * v for i, v in enumerate(abs_samples))
        return weighted_sum / total

    def compute_spectral_rolloff(self, samples: List[float], threshold: float = 0.85) -> float:
        """Compute spectral rolloff frequency approximation."""
        if not samples:
            return 0.0
        abs_samples = [abs(s) for s in samples]
        total = sum(abs_samples)
        if total == 0:
            return 0.0
        cumsum = 0.0
        for i, v in enumerate(abs_samples):
            cumsum += v
            if cumsum >= total * threshold:
                return i / len(abs_samples)
        return 1.0

    def extract_features(self, samples: List[float]) -> Dict[str, float]:
        """Extract a feature vector from audio samples."""
        return {
            "energy_db": self.compute_energy_db(samples),
            "zcr": self.compute_zero_crossing_rate(samples),
            "spectral_centroid": self.compute_spectral_centroid(samples),
            "spectral_rolloff": self.compute_spectral_rolloff(samples),
            "duration_ms": len(samples) / self.sample_rate * 1000,
        }


class NoiseFilter:
    """Adaptive noise filtering for ambient sound processing."""

    def __init__(self, alpha: float = 0.02):
        self.alpha = alpha
        self._noise_floor: Optional[float] = None
        self._sample_count = 0

    def update(self, energy_db: float) -> None:
        if self._noise_floor is None:
            self._noise_floor = energy_db
        else:
            self._noise_floor = (1 - self.alpha) * self._noise_floor + self.alpha * energy_db
        self._sample_count += 1

    def is_above_noise(self, energy_db: float, margin_db: float = 6.0) -> bool:
        if self._noise_floor is None:
            return True
        return energy_db > self._noise_floor + margin_db

    @property
    def noise_floor(self) -> float:
        return self._noise_floor or -60.0


class EnvironmentClassifier:
    """Classifies the current environment based on sound profile."""

    def __init__(self):
        self._profile = SoundProfile()
        self._recent_categories: deque = deque(maxlen=50)

    def update(self, event: SoundEvent) -> EnvironmentType:
        self._profile.update(event.energy_db, event.category)
        self._recent_categories.append(event.category)
        return self.classify()

    def classify(self) -> EnvironmentType:
        if not self._recent_categories:
            return EnvironmentType.UNKNOWN

        cats = list(self._recent_categories)
        speech_ratio = sum(1 for c in cats if c == SoundCategory.SPEECH) / len(cats)
        typing_ratio = sum(1 for c in cats if c == SoundCategory.TYPING) / len(cats)
        silence_ratio = sum(1 for c in cats if c == SoundCategory.SILENCE) / len(cats)
        traffic_ratio = sum(1 for c in cats if c == SoundCategory.TRAFFIC) / len(cats)

        if typing_ratio > 0.3 and speech_ratio > 0.1:
            return EnvironmentType.OFFICE
        elif silence_ratio > 0.5:
            return EnvironmentType.QUIET_ROOM
        elif traffic_ratio > 0.3:
            return EnvironmentType.OUTDOOR
        elif speech_ratio > 0.4:
            return EnvironmentType.HOME
        return EnvironmentType.UNKNOWN


class AmbientSoundClassifier:
    """Main ambient sound classification engine."""

    def __init__(self, sample_rate: int = 16000, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.sample_rate = sample_rate
        self.feature_extractor = AudioFeatureExtractor(sample_rate=sample_rate)
        self.noise_filter = NoiseFilter()
        self.env_classifier = EnvironmentClassifier()
        self._event_history: deque = deque(maxlen=500)
        self._callbacks: List[Callable[[SoundEvent], None]] = []
        self._is_active = False
        self._anomaly_threshold_db = config.get("anomaly_threshold_db", 20.0)

    def process_audio(self, samples: List[float]) -> Optional[SoundEvent]:
        """Process audio samples and classify the sound."""
        if not self._is_active:
            return None

        features = self.feature_extractor.extract_features(samples)
        energy = features["energy_db"]
        zcr = features["zcr"]
        centroid = features["spectral_centroid"]

        self.noise_filter.update(energy)

        # Simple classification rules
        category = SoundCategory.SILENCE
        confidence = 0.5

        if not self.noise_filter.is_above_noise(energy, margin_db=3.0):
            category = SoundCategory.SILENCE
            confidence = 0.9
        elif zcr > 0.3 and centroid > 0.5:
            category = SoundCategory.SPEECH
            confidence = 0.7
        elif zcr < 0.1 and centroid < 0.3:
            category = SoundCategory.MACHINERY
            confidence = 0.6
        elif 0.1 <= zcr <= 0.3:
            category = SoundCategory.MUSIC
            confidence = 0.5

        # Anomaly detection
        is_anomaly = (
            self.noise_filter.is_above_noise(energy, margin_db=self._anomaly_threshold_db)
        )

        event = SoundEvent(
            category=category,
            confidence=confidence,
            energy_db=energy,
            duration_ms=features["duration_ms"],
            is_anomaly=is_anomaly,
        )

        self._event_history.append(event)
        self.env_classifier.update(event)

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Sound event callback error: {e}")

        return event

    def start(self) -> None:
        self._is_active = True
        logger.info("Ambient sound classifier started")

    def stop(self) -> None:
        self._is_active = False
        logger.info("Ambient sound classifier stopped")

    def register_callback(self, callback: Callable[[SoundEvent], None]) -> None:
        self._callbacks.append(callback)

    def get_environment(self) -> str:
        return self.env_classifier.classify().value

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in list(self._event_history)[-limit:]]

    @property
    def is_active(self) -> bool:
        return self._is_active
