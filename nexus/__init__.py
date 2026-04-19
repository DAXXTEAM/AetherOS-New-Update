"""AetherOS Nexus Module — Voice Command & Vision Presence Detection.

The Nexus module provides multimodal interaction capabilities:
- Voice command processing with speech recognition and TTS feedback
- Webcam-based presence detection with automatic lockdown mode
- Gesture recognition pipeline for touchless control
- Ambient sound classification for environmental awareness
"""
from nexus.voice import (
    VoiceCommandProcessor,
    VoiceCommandRegistry,
    VoiceResponse,
    VoiceFeedbackEngine,
    SpeechToTextEngine,
    TextToSpeechEngine,
    WakeWordDetector,
    VoiceCommandResult,
    VoiceProfile,
    VoiceAuthenticator,
)
from nexus.vision import (
    VisionPresenceDetector,
    LockdownManager,
    FaceRecognizer,
    GestureRecognizer,
    PresenceEvent,
    PresenceState,
    CameraManager,
    FrameProcessor,
    VisionPipeline,
    MotionDetector,
)
from nexus.gesture import (
    GestureEngine,
    GestureMapping,
    GestureTracker,
    HandLandmarkDetector,
    GestureClassifier,
    GestureAction,
)
from nexus.ambient import (
    AmbientSoundClassifier,
    SoundEvent,
    SoundProfile,
    NoiseFilter,
    AudioFeatureExtractor,
    EnvironmentClassifier,
)
from nexus.multimodal import (
    MultimodalFusion,
    ModalityWeight,
    FusionStrategy,
    InputStreamManager,
    ContextAwareRouter,
    ModalityPriority,
)

__all__ = [
    "VoiceCommandProcessor", "VoiceCommandRegistry", "VoiceResponse",
    "VoiceFeedbackEngine", "SpeechToTextEngine", "TextToSpeechEngine",
    "WakeWordDetector", "VoiceCommandResult", "VoiceProfile", "VoiceAuthenticator",
    "VisionPresenceDetector", "LockdownManager", "FaceRecognizer",
    "GestureRecognizer", "PresenceEvent", "PresenceState", "CameraManager",
    "FrameProcessor", "VisionPipeline", "MotionDetector",
    "GestureEngine", "GestureMapping", "GestureTracker",
    "HandLandmarkDetector", "GestureClassifier", "GestureAction",
    "AmbientSoundClassifier", "SoundEvent", "SoundProfile",
    "NoiseFilter", "AudioFeatureExtractor", "EnvironmentClassifier",
    "MultimodalFusion", "ModalityWeight", "FusionStrategy",
    "InputStreamManager", "ContextAwareRouter", "ModalityPriority",
]
