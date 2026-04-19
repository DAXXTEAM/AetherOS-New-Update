"""AetherOS Nexus   Voice Command Processing Engine.

Provides speech recognition, text-to-speech feedback, wake word detection,
voice authentication, and a command registry for natural language control.

Architecture:
     
                     VoiceCommandProcessor                      
                 
         WakeWord       SpeechToText      CommandRouter     
         Detector        Engine                               
                 
                                                               
                 
         Voice Auth      TextToSpeech      Command           
                         Engine             Registry          
                 
     
"""
from __future__ import annotations

import asyncio
import enum
import hashlib
import json
import logging
import os
import queue
import re
import struct
import threading
import time
import uuid
import wave
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    Any, Callable, Dict, List, Optional, Set, Tuple, Union,
)

logger = logging.getLogger("nexus.voice")


#  
# Data Models
#  

class VoiceCommandStatus(enum.Enum):
    """Status of a processed voice command."""
    PENDING = "pending"
    RECOGNIZED = "recognized"
    AUTHENTICATED = "authenticated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class AudioFormat(enum.Enum):
    """Supported audio formats for processing."""
    WAV = "wav"
    PCM_16 = "pcm_16"
    PCM_32 = "pcm_32"
    FLAC = "flac"
    OGG = "ogg"
    MP3 = "mp3"


@dataclass
class VoiceProfile:
    """Voice biometric profile for speaker identification."""
    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_name: str = ""
    voice_embeddings: List[List[float]] = field(default_factory=list)
    enrollment_samples: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_verified: Optional[datetime] = None
    confidence_threshold: float = 0.85
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_embedding(self, embedding: List[float]) -> None:
        """Add a voice embedding sample to the profile."""
        self.voice_embeddings.append(embedding)
        self.enrollment_samples += 1

    def get_average_embedding(self) -> List[float]:
        """Compute the centroid of all enrolled embeddings."""
        if not self.voice_embeddings:
            return []
        dim = len(self.voice_embeddings[0])
        avg = [0.0] * dim
        for emb in self.voice_embeddings:
            for i in range(dim):
                avg[i] += emb[i]
        return [v / len(self.voice_embeddings) for v in avg]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_name": self.user_name,
            "enrollment_samples": self.enrollment_samples,
            "created_at": self.created_at.isoformat(),
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "confidence_threshold": self.confidence_threshold,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceProfile":
        profile = cls(
            profile_id=data.get("profile_id", str(uuid.uuid4())),
            user_name=data.get("user_name", ""),
            enrollment_samples=data.get("enrollment_samples", 0),
            confidence_threshold=data.get("confidence_threshold", 0.85),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
        )
        if data.get("created_at"):
            profile.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("last_verified"):
            profile.last_verified = datetime.fromisoformat(data["last_verified"])
        return profile


@dataclass
class VoiceCommandResult:
    """Result of a voice command processing cycle."""
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: str = ""
    normalized_text: str = ""
    confidence: float = 0.0
    intent: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    status: VoiceCommandStatus = VoiceCommandStatus.PENDING
    speaker_id: Optional[str] = None
    processing_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    response_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "confidence": self.confidence,
            "intent": self.intent,
            "entities": self.entities,
            "status": self.status.value,
            "speaker_id": self.speaker_id,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "response_text": self.response_text,
        }


@dataclass
class VoiceResponse:
    """Structured response to be spoken back to the user."""
    text: str
    ssml: Optional[str] = None
    emotion: str = "neutral"
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 0.8
    language: str = "en"
    priority: int = 5

    def to_ssml(self) -> str:
        """Convert to SSML format for advanced TTS."""
        if self.ssml:
            return self.ssml
        rate = "medium"
        if self.speed < 0.8:
            rate = "slow"
        elif self.speed > 1.2:
            rate = "fast"
        pitch_val = "medium"
        if self.pitch < 0.8:
            pitch_val = "low"
        elif self.pitch > 1.2:
            pitch_val = "high"
        return (
            f'<speak>'
            f'<prosody rate="{rate}" pitch="{pitch_val}" '
            f'volume="{int(self.volume * 100)}%">'
            f'{self.text}'
            f'</prosody>'
            f'</speak>'
        )


#  
# Audio Processing Utilities
#  

class AudioBuffer:
    """Thread-safe circular audio buffer for streaming processing."""

    def __init__(self, max_duration_seconds: float = 30.0, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.max_samples = int(max_duration_seconds * sample_rate)
        self._buffer: List[float] = []
        self._lock = threading.Lock()
        self._write_pos = 0
        self._total_written = 0

    def write(self, samples: List[float]) -> int:
        """Write audio samples to the buffer. Returns number written."""
        with self._lock:
            self._buffer.extend(samples)
            # Trim to max size, keeping most recent
            if len(self._buffer) > self.max_samples:
                self._buffer = self._buffer[-self.max_samples:]
            self._total_written += len(samples)
            return len(samples)

    def read(self, num_samples: Optional[int] = None) -> List[float]:
        """Read samples from the buffer."""
        with self._lock:
            if num_samples is None:
                return list(self._buffer)
            return list(self._buffer[-num_samples:])

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._write_pos = 0

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return len(self._buffer) / self.sample_rate if self.sample_rate else 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._buffer) == 0


class AudioPreprocessor:
    """Audio signal preprocessing for speech recognition."""

    def __init__(self, sample_rate: int = 16000, frame_size: int = 512):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._noise_profile: Optional[List[float]] = None
        self._agc_target = 0.5
        self._agc_gain = 1.0

    def normalize(self, samples: List[float]) -> List[float]:
        """Normalize audio to [-1.0, 1.0] range."""
        if not samples:
            return samples
        peak = max(abs(s) for s in samples) or 1.0
        return [s / peak for s in samples]

    def apply_agc(self, samples: List[float]) -> List[float]:
        """Apply automatic gain control."""
        if not samples:
            return samples
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        if rms > 0:
            desired_gain = self._agc_target / rms
            self._agc_gain = 0.9 * self._agc_gain + 0.1 * desired_gain
            self._agc_gain = max(0.1, min(self._agc_gain, 10.0))
        return [s * self._agc_gain for s in samples]

    def remove_dc_offset(self, samples: List[float]) -> List[float]:
        """Remove DC offset from audio signal."""
        if not samples:
            return samples
        mean = sum(samples) / len(samples)
        return [s - mean for s in samples]

    def apply_preemphasis(self, samples: List[float], coeff: float = 0.97) -> List[float]:
        """Apply pre-emphasis filter for speech enhancement."""
        if len(samples) < 2:
            return samples
        result = [samples[0]]
        for i in range(1, len(samples)):
            result.append(samples[i] - coeff * samples[i - 1])
        return result

    def compute_energy(self, samples: List[float]) -> float:
        """Compute frame energy (RMS)."""
        if not samples:
            return 0.0
        return (sum(s * s for s in samples) / len(samples)) ** 0.5

    def detect_voice_activity(self, samples: List[float], threshold: float = 0.02) -> bool:
        """Simple energy-based voice activity detection."""
        energy = self.compute_energy(samples)
        return energy > threshold

    def frame_audio(self, samples: List[float], overlap: float = 0.5) -> List[List[float]]:
        """Split audio into overlapping frames."""
        step = int(self.frame_size * (1.0 - overlap))
        frames = []
        for i in range(0, len(samples) - self.frame_size + 1, step):
            frames.append(samples[i:i + self.frame_size])
        return frames

    def compute_mfcc_features(self, samples: List[float], num_coeffs: int = 13) -> List[List[float]]:
        """Compute simplified MFCC-like features for voice processing.

        This is a lightweight approximation suitable for wake word detection
        and voice fingerprinting without requiring scipy/librosa.
        """
        frames = self.frame_audio(samples)
        features = []
        for frame in frames:
            energy = self.compute_energy(frame)
            zero_crossings = sum(
                1 for i in range(1, len(frame)) if frame[i] * frame[i-1] < 0
            )
            zcr = zero_crossings / len(frame) if frame else 0
            # Simplified spectral features
            coeffs = [energy, zcr]
            # Add sub-band energies as feature approximation
            band_size = max(1, len(frame) // (num_coeffs - 2))
            for b in range(num_coeffs - 2):
                start = b * band_size
                end = min(start + band_size, len(frame))
                band = frame[start:end]
                coeffs.append(self.compute_energy(band))
            features.append(coeffs[:num_coeffs])
        return features

    def estimate_noise_profile(self, noise_samples: List[float]) -> None:
        """Estimate background noise profile for spectral subtraction."""
        frames = self.frame_audio(noise_samples)
        if not frames:
            return
        profile = [0.0] * self.frame_size
        for frame in frames:
            for i, v in enumerate(frame):
                profile[i] += abs(v)
        self._noise_profile = [v / len(frames) for v in profile]

    def apply_noise_reduction(self, samples: List[float]) -> List[float]:
        """Apply basic spectral subtraction noise reduction."""
        if self._noise_profile is None:
            return samples
        frames = self.frame_audio(samples, overlap=0.0)
        result = []
        for frame in frames:
            cleaned = []
            for i, v in enumerate(frame):
                noise = self._noise_profile[i] if i < len(self._noise_profile) else 0
                if abs(v) > noise * 1.5:
                    cleaned.append(v)
                else:
                    cleaned.append(v * 0.1)
            result.extend(cleaned)
        return result


#  
# Wake Word Detection
#  

class WakeWordDetector:
    """Detects wake words/phrases to activate the voice command system.

    Uses a sliding window approach with MFCC features and template matching
    to detect predefined wake words like "Hey Aether" or "Aether, wake up".
    """

    DEFAULT_WAKE_WORDS = [
        "hey aether", "aether", "ok aether", "aether wake up",
        "activate aether", "hello aether", "aether listen",
    ]

    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        sensitivity: float = 0.7,
        sample_rate: int = 16000,
        cooldown_seconds: float = 2.0,
    ):
        self.wake_words = wake_words or self.DEFAULT_WAKE_WORDS
        self.sensitivity = max(0.1, min(sensitivity, 1.0))
        self.sample_rate = sample_rate
        self.cooldown_seconds = cooldown_seconds
        self._preprocessor = AudioPreprocessor(sample_rate=sample_rate)
        self._last_detection_time: float = 0.0
        self._detection_count = 0
        self._is_listening = False
        self._callbacks: List[Callable[[str, float], None]] = []
        self._templates: Dict[str, List[List[float]]] = {}
        self._lock = threading.Lock()
        logger.info(
            f"WakeWordDetector initialized with {len(self.wake_words)} wake words, "
            f"sensitivity={self.sensitivity}"
        )

    def register_callback(self, callback: Callable[[str, float], None]) -> None:
        """Register a callback for wake word detection events."""
        self._callbacks.append(callback)

    def start_listening(self) -> None:
        """Start the wake word detection loop."""
        self._is_listening = True
        logger.info("Wake word detection started")

    def stop_listening(self) -> None:
        """Stop the wake word detection loop."""
        self._is_listening = False
        logger.info("Wake word detection stopped")

    def enroll_wake_word(self, word: str, audio_samples: List[float]) -> bool:
        """Enroll a custom wake word with audio template."""
        features = self._preprocessor.compute_mfcc_features(audio_samples)
        if not features:
            return False
        with self._lock:
            self._templates[word.lower()] = features
        logger.info(f"Enrolled wake word template: '{word}'")
        return True

    def process_audio_chunk(self, samples: List[float]) -> Optional[Tuple[str, float]]:
        """Process an audio chunk and check for wake words.

        Returns (detected_word, confidence) if wake word detected, else None.
        """
        if not self._is_listening:
            return None

        now = time.time()
        if now - self._last_detection_time < self.cooldown_seconds:
            return None

        # Preprocess
        processed = self._preprocessor.remove_dc_offset(samples)
        processed = self._preprocessor.apply_agc(processed)

        # Check voice activity
        if not self._preprocessor.detect_voice_activity(processed, threshold=0.01):
            return None

        # Compute features
        features = self._preprocessor.compute_mfcc_features(processed)
        if not features:
            return None

        # Template matching against enrolled words
        best_match = None
        best_score = 0.0

        with self._lock:
            for word, template in self._templates.items():
                score = self._template_match(features, template)
                if score > best_score:
                    best_score = score
                    best_match = word

        # Apply sensitivity threshold
        threshold = 1.0 - self.sensitivity
        if best_match and best_score > threshold:
            self._last_detection_time = now
            self._detection_count += 1
            # Notify callbacks
            for cb in self._callbacks:
                try:
                    cb(best_match, best_score)
                except Exception as e:
                    logger.error(f"Wake word callback error: {e}")
            logger.info(f"Wake word detected: '{best_match}' (confidence={best_score:.3f})")
            return (best_match, best_score)

        return None

    def _template_match(self, features: List[List[float]], template: List[List[float]]) -> float:
        """Simple DTW-inspired template matching score."""
        if not features or not template:
            return 0.0
        # Use frame-level cosine similarity
        min_len = min(len(features), len(template))
        total_sim = 0.0
        for i in range(min_len):
            sim = self._cosine_similarity(features[i], template[i])
            total_sim += sim
        return total_sim / min_len if min_len > 0 else 0.0

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @property
    def detection_count(self) -> int:
        return self._detection_count

    @property
    def is_listening(self) -> bool:
        return self._is_listening


#  
# Speech-to-Text Engine
#  

class SpeechToTextEngine:
    """Multi-backend speech recognition engine.

    Supports multiple STT backends with automatic fallback:
    - Local: SpeechRecognition library (Google, Sphinx, Whisper)
    - Remote: API-based recognition (configurable endpoints)
    - Hybrid: Local VAD + remote recognition for efficiency
    """

    class Backend(enum.Enum):
        GOOGLE = "google"
        SPHINX = "sphinx"
        WHISPER = "whisper"
        VOSK = "vosk"
        AZURE = "azure"
        AWS = "aws"

    def __init__(
        self,
        backend: Optional[Backend] = None,
        language: str = "en-US",
        sample_rate: int = 16000,
        max_alternatives: int = 3,
    ):
        self.backend = backend or self.Backend.GOOGLE
        self.language = language
        self.sample_rate = sample_rate
        self.max_alternatives = max_alternatives
        self._preprocessor = AudioPreprocessor(sample_rate=sample_rate)
        self._recognizer = None
        self._is_initialized = False
        self._recognition_count = 0
        self._total_audio_seconds = 0.0
        self._error_count = 0
        self._lock = threading.Lock()
        logger.info(f"SpeechToTextEngine created with backend={self.backend.value}")

    def initialize(self) -> bool:
        """Initialize the STT engine and load models."""
        try:
            # Try to import speech_recognition
            try:
                import speech_recognition as sr
                self._recognizer = sr.Recognizer()
                self._recognizer.dynamic_energy_threshold = True
                self._recognizer.energy_threshold = 300
                self._recognizer.pause_threshold = 0.8
                self._is_initialized = True
                logger.info("SpeechRecognition library loaded successfully")
            except ImportError:
                # Fallback to simulation mode
                logger.warning(
                    "SpeechRecognition not available, running in simulation mode"
                )
                self._is_initialized = True

            return True
        except Exception as e:
            logger.error(f"Failed to initialize STT engine: {e}")
            self._error_count += 1
            return False

    async def recognize(
        self,
        audio_data: Union[List[float], bytes],
        timeout: float = 10.0,
    ) -> VoiceCommandResult:
        """Recognize speech from audio data.

        Args:
            audio_data: Audio samples (float list) or raw bytes
            timeout: Maximum recognition time in seconds

        Returns:
            VoiceCommandResult with transcription and metadata
        """
        start_time = time.time()
        result = VoiceCommandResult()

        if not self._is_initialized:
            self.initialize()

        try:
            if isinstance(audio_data, list):
                duration = len(audio_data) / self.sample_rate
                self._total_audio_seconds += duration

            # Try real recognition
            if self._recognizer is not None:
                try:
                    import speech_recognition as sr
                    if isinstance(audio_data, list):
                        # Convert float samples to AudioData
                        int_samples = [int(s * 32767) for s in audio_data]
                        raw_bytes = struct.pack(f"{len(int_samples)}h", *int_samples)
                        audio = sr.AudioData(raw_bytes, self.sample_rate, 2)
                    elif isinstance(audio_data, bytes):
                        audio = sr.AudioData(audio_data, self.sample_rate, 2)
                    else:
                        raise ValueError("Unsupported audio data type")

                    if self.backend == self.Backend.GOOGLE:
                        text = self._recognizer.recognize_google(
                            audio, language=self.language,
                            show_all=False,
                        )
                    elif self.backend == self.Backend.SPHINX:
                        text = self._recognizer.recognize_sphinx(audio)
                    else:
                        text = self._recognizer.recognize_google(audio, language=self.language)

                    result.raw_text = text
                    result.normalized_text = self._normalize_text(text)
                    result.confidence = 0.85
                    result.status = VoiceCommandStatus.RECOGNIZED
                except ImportError:
                    result = self._simulate_recognition(audio_data)
                except Exception as rec_err:
                    logger.warning(f"Recognition failed: {rec_err}")
                    result = self._simulate_recognition(audio_data)
            else:
                result = self._simulate_recognition(audio_data)

            self._recognition_count += 1

        except Exception as e:
            result.status = VoiceCommandStatus.FAILED
            result.error = str(e)
            self._error_count += 1
            logger.error(f"Speech recognition error: {e}")

        result.processing_time_ms = (time.time() - start_time) * 1000
        return result

    def _simulate_recognition(self, audio_data: Any) -> VoiceCommandResult:
        """Simulate recognition when no backend is available."""
        result = VoiceCommandResult()
        # Generate deterministic "recognized" text based on audio characteristics
        if isinstance(audio_data, list) and audio_data:
            energy = sum(abs(s) for s in audio_data[:100]) / min(100, len(audio_data))
            if energy > 0.1:
                result.raw_text = "[voice command detected - simulation mode]"
                result.normalized_text = "voice command detected"
                result.confidence = 0.5
                result.status = VoiceCommandStatus.RECOGNIZED
            else:
                result.raw_text = ""
                result.status = VoiceCommandStatus.FAILED
                result.error = "No speech detected (low energy)"
        else:
            result.raw_text = "[simulated recognition]"
            result.normalized_text = "simulated recognition"
            result.confidence = 0.3
            result.status = VoiceCommandStatus.RECOGNIZED
        return result

    def _normalize_text(self, text: str) -> str:
        """Normalize recognized text for command matching."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.value,
            "is_initialized": self._is_initialized,
            "recognition_count": self._recognition_count,
            "total_audio_seconds": round(self._total_audio_seconds, 2),
            "error_count": self._error_count,
        }


#  
# Text-to-Speech Engine
#  

class TextToSpeechEngine:
    """Multi-backend text-to-speech engine for voice feedback.

    Supports pyttsx3 for offline TTS and extensible for cloud TTS APIs.
    """

    class Backend(enum.Enum):
        PYTTSX3 = "pyttsx3"
        ESPEAK = "espeak"
        GTTS = "gtts"
        AZURE = "azure"
        AWS_POLLY = "aws_polly"

    def __init__(
        self,
        backend: Optional[Backend] = None,
        voice_id: Optional[str] = None,
        rate: int = 175,
        volume: float = 0.9,
        language: str = "en",
    ):
        self.backend = backend or self.Backend.PYTTSX3
        self.voice_id = voice_id
        self.rate = rate
        self.volume = max(0.0, min(volume, 1.0))
        self.language = language
        self._engine = None
        self._is_initialized = False
        self._speech_count = 0
        self._total_chars = 0
        self._queue: queue.Queue = queue.Queue()
        self._speaking = False
        self._lock = threading.Lock()
        logger.info(f"TextToSpeechEngine created with backend={self.backend.value}")

    def initialize(self) -> bool:
        """Initialize the TTS engine."""
        try:
            if self.backend == self.Backend.PYTTSX3:
                try:
                    import pyttsx3
                    self._engine = pyttsx3.init()
                    self._engine.setProperty("rate", self.rate)
                    self._engine.setProperty("volume", self.volume)
                    voices = self._engine.getProperty("voices")
                    if self.voice_id:
                        for voice in voices:
                            if self.voice_id in voice.id:
                                self._engine.setProperty("voice", voice.id)
                                break
                    self._is_initialized = True
                    logger.info("pyttsx3 engine initialized")
                except ImportError:
                    logger.warning("pyttsx3 not available, TTS in simulation mode")
                    self._is_initialized = True
            else:
                self._is_initialized = True
            return True
        except Exception as e:
            logger.error(f"TTS initialization failed: {e}")
            return False

    async def speak(self, response: VoiceResponse) -> bool:
        """Speak a response asynchronously."""
        if not self._is_initialized:
            self.initialize()

        try:
            with self._lock:
                self._speaking = True

            if self._engine is not None:
                # Real TTS
                self._engine.say(response.text)
                # Run in thread to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None, self._engine.runAndWait
                )
            else:
                # Simulation mode   just log
                logger.info(f"[TTS-SIM] Speaking: '{response.text}'")
                await asyncio.sleep(len(response.text) * 0.05)  # Simulate speech time

            self._speech_count += 1
            self._total_chars += len(response.text)

            with self._lock:
                self._speaking = False

            return True

        except Exception as e:
            logger.error(f"TTS speak error: {e}")
            with self._lock:
                self._speaking = False
            return False

    def speak_sync(self, text: str) -> bool:
        """Synchronous speak for non-async contexts."""
        if not self._is_initialized:
            self.initialize()
        try:
            if self._engine is not None:
                self._engine.say(text)
                self._engine.runAndWait()
            else:
                logger.info(f"[TTS-SIM] Speaking: '{text}'")
            self._speech_count += 1
            self._total_chars += len(text)
            return True
        except Exception as e:
            logger.error(f"TTS sync speak error: {e}")
            return False

    def set_voice(self, voice_id: str) -> None:
        """Change the active voice."""
        self.voice_id = voice_id
        if self._engine:
            try:
                self._engine.setProperty("voice", voice_id)
            except Exception as e:
                logger.warning(f"Failed to set voice {voice_id}: {e}")

    def list_voices(self) -> List[Dict[str, str]]:
        """List available TTS voices."""
        if self._engine is None:
            return [{"id": "default", "name": "Default (Simulation)", "lang": "en"}]
        try:
            voices = self._engine.getProperty("voices")
            return [
                {"id": v.id, "name": v.name, "lang": ",".join(v.languages) if v.languages else "unknown"}
                for v in voices
            ]
        except Exception:
            return []

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.value,
            "is_initialized": self._is_initialized,
            "speech_count": self._speech_count,
            "total_chars_spoken": self._total_chars,
        }


#  
# Voice Authenticator
#  

class VoiceAuthenticator:
    """Speaker identification and verification using voice biometrics.

    Maintains a database of voice profiles and verifies speakers by comparing
    voice embeddings computed from MFCC features.
    """

    def __init__(
        self,
        profiles_dir: Optional[str] = None,
        min_enrollment_samples: int = 3,
        verification_threshold: float = 0.75,
    ):
        self.profiles_dir = profiles_dir or os.path.expanduser("~/.aetheros/voice_profiles")
        self.min_enrollment_samples = min_enrollment_samples
        self.verification_threshold = verification_threshold
        self._profiles: Dict[str, VoiceProfile] = {}
        self._preprocessor = AudioPreprocessor()
        self._lock = threading.Lock()

    def enroll(self, user_name: str, audio_samples: List[float]) -> Optional[str]:
        """Enroll a user voice sample. Returns profile_id."""
        features = self._preprocessor.compute_mfcc_features(audio_samples)
        if not features:
            logger.warning(f"Cannot enroll '{user_name}': no features extracted")
            return None

        # Average features into single embedding
        dim = len(features[0])
        embedding = [0.0] * dim
        for feat in features:
            for i in range(min(dim, len(feat))):
                embedding[i] += feat[i]
        embedding = [v / len(features) for v in embedding]

        with self._lock:
            # Find existing profile or create new
            profile = None
            for p in self._profiles.values():
                if p.user_name == user_name:
                    profile = p
                    break

            if profile is None:
                profile = VoiceProfile(user_name=user_name)
                self._profiles[profile.profile_id] = profile

            profile.add_embedding(embedding)
            logger.info(
                f"Enrolled voice sample for '{user_name}' "
                f"(samples: {profile.enrollment_samples})"
            )
            return profile.profile_id

    def verify(self, audio_samples: List[float], claimed_user: Optional[str] = None) -> Tuple[bool, Optional[str], float]:
        """Verify speaker identity.

        Returns (is_verified, user_name, confidence).
        """
        features = self._preprocessor.compute_mfcc_features(audio_samples)
        if not features:
            return (False, None, 0.0)

        dim = len(features[0])
        test_embedding = [0.0] * dim
        for feat in features:
            for i in range(min(dim, len(feat))):
                test_embedding[i] += feat[i]
        test_embedding = [v / len(features) for v in test_embedding]

        best_match = None
        best_score = 0.0

        with self._lock:
            candidates = self._profiles.values()
            if claimed_user:
                candidates = [p for p in candidates if p.user_name == claimed_user]

            for profile in candidates:
                if not profile.is_active or profile.enrollment_samples < self.min_enrollment_samples:
                    continue
                avg_emb = profile.get_average_embedding()
                if not avg_emb:
                    continue
                score = WakeWordDetector._cosine_similarity(test_embedding, avg_emb)
                if score > best_score:
                    best_score = score
                    best_match = profile

        if best_match and best_score >= self.verification_threshold:
            best_match.last_verified = datetime.utcnow()
            return (True, best_match.user_name, best_score)

        return (False, None, best_score)

    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        with self._lock:
            return self._profiles.get(profile_id)

    def list_profiles(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in self._profiles.values()]

    def remove_profile(self, profile_id: str) -> bool:
        with self._lock:
            if profile_id in self._profiles:
                del self._profiles[profile_id]
                return True
            return False


#  
# Voice Command Registry & Router
#  

class VoiceCommandRegistry:
    """Registry for voice commands with intent matching and entity extraction.

    Commands are registered with patterns and handlers. Incoming voice text
    is matched against patterns to determine intent and extract entities.
    """

    @dataclass
    class CommandDefinition:
        intent: str
        patterns: List[str]
        handler: Optional[Callable] = None
        description: str = ""
        requires_auth: bool = False
        entity_extractors: Dict[str, str] = field(default_factory=dict)
        aliases: List[str] = field(default_factory=list)
        category: str = "general"
        priority: int = 5

    def __init__(self):
        self._commands: Dict[str, "VoiceCommandRegistry.CommandDefinition"] = {}
        self._categories: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.Lock()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in voice commands."""
        defaults = [
            self.CommandDefinition(
                intent="system_status",
                patterns=["system status", "how are you", "status report", "health check"],
                description="Get current system status and health",
                category="system",
            ),
            self.CommandDefinition(
                intent="run_task",
                patterns=["run task", "execute", "do", "perform", "start task"],
                description="Execute a task by voice",
                requires_auth=True,
                category="tasks",
            ),
            self.CommandDefinition(
                intent="security_scan",
                patterns=["security scan", "scan for threats", "check security", "threat scan"],
                description="Run a security scan",
                requires_auth=True,
                category="security",
            ),
            self.CommandDefinition(
                intent="lockdown",
                patterns=["lockdown", "lock down", "emergency lock", "secure system"],
                description="Activate emergency lockdown mode",
                requires_auth=True,
                category="security",
                priority=10,
            ),
            self.CommandDefinition(
                intent="help",
                patterns=["help", "what can you do", "commands", "list commands"],
                description="Show available voice commands",
                category="general",
            ),
            self.CommandDefinition(
                intent="stop",
                patterns=["stop", "cancel", "abort", "halt", "stop listening"],
                description="Stop current operation",
                category="control",
                priority=9,
            ),
            self.CommandDefinition(
                intent="evolution",
                patterns=["evolve", "self improve", "run evolution", "upgrade"],
                description="Trigger self-evolution cycle",
                requires_auth=True,
                category="system",
            ),
            self.CommandDefinition(
                intent="mesh_status",
                patterns=["mesh status", "network status", "connected nodes", "peer status"],
                description="Show mesh network status",
                category="network",
            ),
            self.CommandDefinition(
                intent="quantum_rng",
                patterns=["generate random", "quantum random", "random number"],
                description="Generate quantum random numbers",
                category="quantum",
            ),
            self.CommandDefinition(
                intent="memory_search",
                patterns=["remember", "recall", "search memory", "what do you know about"],
                description="Search system memory",
                category="memory",
            ),
        ]
        for cmd in defaults:
            self.register(cmd)

    def register(self, command: CommandDefinition) -> None:
        """Register a voice command."""
        with self._lock:
            self._commands[command.intent] = command
            self._categories[command.category].append(command.intent)

    def unregister(self, intent: str) -> bool:
        with self._lock:
            if intent in self._commands:
                cmd = self._commands.pop(intent)
                if cmd.category in self._categories:
                    self._categories[cmd.category] = [
                        i for i in self._categories[cmd.category] if i != intent
                    ]
                return True
            return False

    def match(self, text: str) -> Tuple[Optional[str], float, Dict[str, Any]]:
        """Match text against registered commands.

        Returns (intent, confidence, entities).
        """
        text_lower = text.lower().strip()
        if not text_lower:
            return (None, 0.0, {})

        best_intent = None
        best_score = 0.0
        best_entities: Dict[str, Any] = {}

        with self._lock:
            for intent, cmd in self._commands.items():
                for pattern in cmd.patterns + cmd.aliases:
                    score = self._pattern_score(text_lower, pattern.lower())
                    if score > best_score:
                        best_score = score
                        best_intent = intent
                        # Extract remaining text as entity
                        remainder = text_lower
                        for pat_word in pattern.lower().split():
                            remainder = remainder.replace(pat_word, "").strip()
                        if remainder:
                            best_entities = {"query": remainder}

        return (best_intent, best_score, best_entities)

    def _pattern_score(self, text: str, pattern: str) -> float:
        """Score how well text matches a pattern."""
        if pattern in text:
            return 0.9 + (len(pattern) / max(len(text), 1)) * 0.1
        pattern_words = pattern.split()
        text_words = text.split()
        if not pattern_words:
            return 0.0
        matches = sum(1 for pw in pattern_words if pw in text_words)
        return matches / len(pattern_words) * 0.8

    def get_command(self, intent: str) -> Optional[CommandDefinition]:
        with self._lock:
            return self._commands.get(intent)

    def list_commands(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "intent": cmd.intent,
                    "patterns": cmd.patterns,
                    "description": cmd.description,
                    "requires_auth": cmd.requires_auth,
                    "category": cmd.category,
                }
                for cmd in self._commands.values()
            ]

    def get_categories(self) -> Dict[str, List[str]]:
        with self._lock:
            return dict(self._categories)


#  
# Voice Feedback Engine
#  

class VoiceFeedbackEngine:
    """Manages contextual voice feedback with emotional modulation.

    Generates appropriate spoken responses based on system state,
    command results, and contextual cues.
    """

    RESPONSE_TEMPLATES = {
        "greeting": [
            "Hello! AetherOS is ready and listening.",
            "Greetings. All systems operational.",
            "AetherOS online. How can I help?",
        ],
        "acknowledgment": [
            "Understood.",
            "Processing your request.",
            "On it.",
            "Roger that.",
        ],
        "success": [
            "Task completed successfully.",
            "Done. Everything looks good.",
            "Operation completed without issues.",
        ],
        "error": [
            "An error occurred. Please check the logs.",
            "Something went wrong. I\'ll investigate.",
            "Operation failed. Retrying might help.",
        ],
        "security_alert": [
            "Security alert! Potential threat detected.",
            "Warning: Unauthorized activity detected.",
            "Security breach attempt identified.",
        ],
        "lockdown": [
            "Lockdown mode activated. All non-essential operations suspended.",
            "Emergency lockdown engaged. System secured.",
        ],
        "farewell": [
            "Shutting down voice interface. Goodbye.",
            "Voice control deactivated. AetherOS continues in background.",
        ],
    }

    def __init__(self, tts_engine: Optional[TextToSpeechEngine] = None):
        self.tts = tts_engine or TextToSpeechEngine()
        self._history: List[Dict[str, Any]] = []
        self._response_idx: Dict[str, int] = defaultdict(int)

    def get_response(self, category: str, **kwargs: Any) -> VoiceResponse:
        """Get a contextual voice response."""
        templates = self.RESPONSE_TEMPLATES.get(category, self.RESPONSE_TEMPLATES["acknowledgment"])
        idx = self._response_idx[category] % len(templates)
        self._response_idx[category] = idx + 1
        text = templates[idx]

        # Apply any dynamic substitutions
        for key, value in kwargs.items():
            text = text.replace(f"{{{key}}}", str(value))

        emotion = "neutral"
        if category in ("error", "security_alert"):
            emotion = "urgent"
        elif category == "success":
            emotion = "positive"
        elif category == "lockdown":
            emotion = "serious"

        return VoiceResponse(text=text, emotion=emotion)

    async def deliver(self, category: str, **kwargs: Any) -> bool:
        """Get and speak a response."""
        response = self.get_response(category, **kwargs)
        self._history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "category": category,
            "text": response.text,
        })
        return await self.tts.speak(response)


#  
# Main Voice Command Processor
#  

class VoiceCommandProcessor:
    """Central voice command processing pipeline.

    Orchestrates wake word detection   speech recognition   command matching
      authentication   execution   voice feedback in a unified pipeline.

    Usage:
        processor = VoiceCommandProcessor()
        processor.initialize()
        processor.start()
        # ... processor runs in background thread ...
        processor.stop()
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        on_command: Optional[Callable[[VoiceCommandResult], None]] = None,
    ):
        config = config or {}
        self.stt = SpeechToTextEngine(
            language=config.get("language", "en-US"),
            sample_rate=config.get("sample_rate", 16000),
        )
        self.tts = TextToSpeechEngine(
            rate=config.get("tts_rate", 175),
            volume=config.get("tts_volume", 0.9),
            language=config.get("language", "en")[:2],
        )
        self.wake_word = WakeWordDetector(
            sensitivity=config.get("wake_sensitivity", 0.7),
        )
        self.registry = VoiceCommandRegistry()
        self.authenticator = VoiceAuthenticator()
        self.feedback = VoiceFeedbackEngine(tts_engine=self.tts)
        self._on_command = on_command
        self._audio_buffer = AudioBuffer()
        self._is_active = False
        self._is_listening_for_command = False
        self._command_timeout = config.get("command_timeout", 10.0)
        self._history: List[VoiceCommandResult] = []
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        logger.info("VoiceCommandProcessor initialized")

    def initialize(self) -> bool:
        """Initialize all subsystems."""
        self.stt.initialize()
        self.tts.initialize()
        self.wake_word.start_listening()
        self.wake_word.register_callback(self._on_wake_word)
        logger.info("VoiceCommandProcessor fully initialized")
        return True

    def start(self) -> None:
        """Start the voice command processing loop."""
        self._is_active = True
        self._worker_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Voice command processing started")

    def stop(self) -> None:
        """Stop the voice command processing loop."""
        self._is_active = False
        self.wake_word.stop_listening()
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("Voice command processing stopped")

    def _processing_loop(self) -> None:
        """Main processing loop running in background thread."""
        while self._is_active:
            try:
                if not self._audio_buffer.is_empty:
                    samples = self._audio_buffer.read()
                    self.wake_word.process_audio_chunk(samples)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Processing loop error: {e}")

    def _on_wake_word(self, word: str, confidence: float) -> None:
        """Callback when wake word is detected."""
        logger.info(f"Wake word '{word}' detected (confidence={confidence:.2f})")
        self._is_listening_for_command = True

    async def process_voice_input(self, audio_samples: List[float]) -> Optional[VoiceCommandResult]:
        """Process voice audio input through the full pipeline."""
        if not self._is_active:
            return None

        # Step 1: Speech to text
        stt_result = await self.stt.recognize(audio_samples)
        if stt_result.status != VoiceCommandStatus.RECOGNIZED:
            return stt_result

        # Step 2: Match to command
        intent, confidence, entities = self.registry.match(stt_result.normalized_text)
        stt_result.intent = intent or ""
        stt_result.confidence = confidence
        stt_result.entities = entities

        if not intent:
            stt_result.status = VoiceCommandStatus.FAILED
            stt_result.error = "No matching command found"
            return stt_result

        # Step 3: Check authentication
        cmd_def = self.registry.get_command(intent)
        if cmd_def and cmd_def.requires_auth:
            verified, user, auth_conf = self.authenticator.verify(audio_samples)
            if verified:
                stt_result.speaker_id = user
                stt_result.status = VoiceCommandStatus.AUTHENTICATED
            else:
                stt_result.status = VoiceCommandStatus.REJECTED
                stt_result.error = "Voice authentication failed"
                await self.feedback.deliver("error")
                return stt_result

        # Step 4: Execute command
        stt_result.status = VoiceCommandStatus.EXECUTING
        if cmd_def and cmd_def.handler:
            try:
                result = cmd_def.handler(stt_result)
                if isinstance(result, str):
                    stt_result.response_text = result
                stt_result.status = VoiceCommandStatus.COMPLETED
            except Exception as e:
                stt_result.status = VoiceCommandStatus.FAILED
                stt_result.error = str(e)
        else:
            stt_result.status = VoiceCommandStatus.COMPLETED
            stt_result.response_text = f"Command \'{intent}\' acknowledged"

        # Step 5: Voice feedback
        if stt_result.status == VoiceCommandStatus.COMPLETED:
            await self.feedback.deliver("success")
        else:
            await self.feedback.deliver("error")

        # Record in history
        with self._lock:
            self._history.append(stt_result)

        if self._on_command:
            self._on_command(stt_result)

        return stt_result

    def feed_audio(self, samples: List[float]) -> int:
        """Feed audio samples into the processing pipeline."""
        return self._audio_buffer.write(samples)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._history[-limit:]]

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "is_active": self._is_active,
            "stt_stats": self.stt.stats,
            "tts_stats": self.tts.stats,
            "wake_word_detections": self.wake_word.detection_count,
            "commands_processed": len(self._history),
            "registered_commands": len(self.registry.list_commands()),
        }
