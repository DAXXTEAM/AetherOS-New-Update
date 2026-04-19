"""Tests for AetherOS Nexus Module (Voice + Vision)."""
import pytest
import asyncio
from nexus.voice import (
    VoiceCommandProcessor, VoiceCommandRegistry, VoiceResponse,
    SpeechToTextEngine, TextToSpeechEngine, WakeWordDetector,
    VoiceCommandResult, VoiceProfile, VoiceAuthenticator,
    AudioBuffer, AudioPreprocessor, VoiceFeedbackEngine,
    VoiceCommandStatus,
)
from nexus.vision import (
    VisionPresenceDetector, LockdownManager, FaceRecognizer,
    MotionDetector, FrameProcessor, CameraManager,
    PresenceEvent, PresenceState, LockdownLevel, BoundingBox,
    FaceProfile as VisionFaceProfile,
)


class TestAudioBuffer:
    def test_write_and_read(self):
        buf = AudioBuffer(max_duration_seconds=1.0, sample_rate=100)
        samples = [0.5] * 50
        written = buf.write(samples)
        assert written == 50
        read = buf.read()
        assert len(read) == 50

    def test_overflow(self):
        buf = AudioBuffer(max_duration_seconds=0.1, sample_rate=100)
        samples = [0.5] * 200
        buf.write(samples)
        assert buf.size <= 10  # max = 0.1 * 100 = 10

    def test_clear(self):
        buf = AudioBuffer()
        buf.write([1.0] * 100)
        buf.clear()
        assert buf.is_empty

    def test_duration(self):
        buf = AudioBuffer(sample_rate=1000)
        buf.write([0.1] * 500)
        assert abs(buf.duration_seconds - 0.5) < 0.01


class TestAudioPreprocessor:
    def test_normalize(self):
        pp = AudioPreprocessor()
        samples = [0.5, -1.0, 0.3, -0.7]
        normalized = pp.normalize(samples)
        assert max(abs(s) for s in normalized) <= 1.0 + 1e-9

    def test_remove_dc_offset(self):
        pp = AudioPreprocessor()
        samples = [1.5, 1.7, 1.3, 1.6]
        result = pp.remove_dc_offset(samples)
        mean = sum(result) / len(result)
        assert abs(mean) < 0.01

    def test_voice_activity_detection(self):
        pp = AudioPreprocessor()
        assert not pp.detect_voice_activity([0.001, -0.001, 0.002])
        assert pp.detect_voice_activity([0.5, -0.6, 0.7, -0.8])

    def test_compute_energy(self):
        pp = AudioPreprocessor()
        assert pp.compute_energy([]) == 0.0
        energy = pp.compute_energy([1.0, 1.0, 1.0])
        assert energy == 1.0

    def test_mfcc_features(self):
        pp = AudioPreprocessor(frame_size=32)
        samples = [0.5 * (i % 7) / 7 for i in range(256)]
        features = pp.compute_mfcc_features(samples)
        assert len(features) > 0
        assert len(features[0]) == 13


class TestWakeWordDetector:
    def test_initialization(self):
        wwd = WakeWordDetector()
        assert len(wwd.wake_words) > 0
        assert not wwd.is_listening

    def test_start_stop(self):
        wwd = WakeWordDetector()
        wwd.start_listening()
        assert wwd.is_listening
        wwd.stop_listening()
        assert not wwd.is_listening

    def test_enroll_wake_word(self):
        wwd = WakeWordDetector()
        samples = [0.3 * (i % 5) / 5 for i in range(1000)]
        result = wwd.enroll_wake_word("custom word", samples)
        assert result

    def test_callback_registration(self):
        wwd = WakeWordDetector()
        fired = []
        wwd.register_callback(lambda word, conf: fired.append(word))
        # Just verify registration doesn't crash
        assert len(fired) == 0


class TestVoiceCommandRegistry:
    def test_default_commands(self):
        registry = VoiceCommandRegistry()
        commands = registry.list_commands()
        assert len(commands) > 0
        intents = [c["intent"] for c in commands]
        assert "system_status" in intents
        assert "help" in intents

    def test_match(self):
        registry = VoiceCommandRegistry()
        intent, confidence, entities = registry.match("system status")
        assert intent == "system_status"
        assert confidence > 0.5

    def test_match_lockdown(self):
        registry = VoiceCommandRegistry()
        intent, conf, _ = registry.match("lockdown")
        assert intent == "lockdown"

    def test_no_match(self):
        registry = VoiceCommandRegistry()
        intent, conf, _ = registry.match("")
        assert intent is None

    def test_categories(self):
        registry = VoiceCommandRegistry()
        cats = registry.get_categories()
        assert "system" in cats
        assert "security" in cats


class TestVoiceResponse:
    def test_to_ssml(self):
        response = VoiceResponse(text="Hello world")
        ssml = response.to_ssml()
        assert "<speak>" in ssml
        assert "Hello world" in ssml


class TestVoiceProfile:
    def test_add_embedding(self):
        profile = VoiceProfile(user_name="test_user")
        profile.add_embedding([0.1, 0.2, 0.3])
        profile.add_embedding([0.4, 0.5, 0.6])
        assert profile.enrollment_samples == 2

    def test_average_embedding(self):
        profile = VoiceProfile()
        profile.add_embedding([1.0, 2.0])
        profile.add_embedding([3.0, 4.0])
        avg = profile.get_average_embedding()
        assert abs(avg[0] - 2.0) < 0.01
        assert abs(avg[1] - 3.0) < 0.01

    def test_serialization(self):
        profile = VoiceProfile(user_name="test")
        d = profile.to_dict()
        p2 = VoiceProfile.from_dict(d)
        assert p2.user_name == "test"


class TestBoundingBox:
    def test_center(self):
        bb = BoundingBox(x=10, y=20, width=100, height=50)
        assert bb.center == (60, 45)

    def test_area(self):
        bb = BoundingBox(width=10, height=20)
        assert bb.area == 200

    def test_iou_no_overlap(self):
        bb1 = BoundingBox(x=0, y=0, width=10, height=10)
        bb2 = BoundingBox(x=100, y=100, width=10, height=10)
        assert bb1.iou(bb2) == 0.0

    def test_iou_full_overlap(self):
        bb = BoundingBox(x=0, y=0, width=10, height=10)
        assert abs(bb.iou(bb) - 1.0) < 0.01


class TestFrameProcessor:
    def test_grayscale(self):
        fp = FrameProcessor()
        frame = [[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [128, 128, 128]]]
        gray = fp.to_grayscale(frame)
        assert len(gray) == 2
        assert len(gray[0]) == 2

    def test_frame_hash(self):
        fp = FrameProcessor()
        frame = [[[100, 150, 200] for _ in range(10)] for _ in range(10)]
        h = fp.compute_frame_hash(frame)
        assert len(h) == 16


class TestMotionDetector:
    def test_process_first_frame(self):
        md = MotionDetector()
        frame = [[[100, 100, 100] for _ in range(20)] for _ in range(20)]
        motion, level, regions = md.process_frame(frame)
        assert not motion  # First frame never has motion

    def test_motion_detection(self):
        md = MotionDetector(sensitivity=0.9)
        frame1 = [[[50, 50, 50] for _ in range(20)] for _ in range(20)]
        frame2 = [[[200, 200, 200] for _ in range(20)] for _ in range(20)]
        md.process_frame(frame1)
        motion, level, regions = md.process_frame(frame2)
        # Large change should detect motion
        assert motion or level > 0


class TestLockdownManager:
    def test_initial_state(self):
        lm = LockdownManager()
        assert lm.current_level == LockdownLevel.NONE

    def test_force_lockdown(self):
        lm = LockdownManager()
        lm.force_lockdown(LockdownLevel.HARD)
        assert lm.current_level == LockdownLevel.HARD

    def test_release(self):
        lm = LockdownManager()
        lm.force_lockdown(LockdownLevel.CRITICAL)
        lm.release_lockdown()
        assert lm.current_level == LockdownLevel.NONE

    def test_unauthorized_event(self):
        lm = LockdownManager()
        event = PresenceEvent(
            event_type="unauthorized",
            state_after=PresenceState.UNAUTHORIZED,
        )
        lm.on_presence_event(event)
        assert lm.current_level == LockdownLevel.CRITICAL

    def test_status(self):
        lm = LockdownManager()
        status = lm.get_status()
        assert "level" in status
        assert status["level"] == "NONE"
