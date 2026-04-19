"""AetherOS Nexus — Gesture Recognition Engine.

Hand gesture detection and classification for touchless system control.
Uses hand landmark detection and gesture classification pipeline.
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

logger = logging.getLogger("nexus.gesture")


class GestureType(enum.Enum):
    """Recognized gesture types."""
    NONE = "none"
    WAVE = "wave"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    OPEN_PALM = "open_palm"
    CLOSED_FIST = "closed_fist"
    POINT_UP = "point_up"
    POINT_RIGHT = "point_right"
    PEACE = "peace"
    OK_SIGN = "ok_sign"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    PINCH = "pinch"
    SPREAD = "spread"
    ROTATE_CW = "rotate_clockwise"
    ROTATE_CCW = "rotate_counterclockwise"


@dataclass
class HandLandmark:
    """Single hand landmark point."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    visibility: float = 1.0
    name: str = ""


@dataclass
class HandDetection:
    """Detected hand with landmarks."""
    hand_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    is_left: bool = True
    landmarks: List[HandLandmark] = field(default_factory=list)
    confidence: float = 0.0
    bounding_box: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h

    @property
    def wrist(self) -> Optional[HandLandmark]:
        return self.landmarks[0] if self.landmarks else None

    @property
    def fingertips(self) -> List[HandLandmark]:
        indices = [4, 8, 12, 16, 20]
        return [self.landmarks[i] for i in indices if i < len(self.landmarks)]


@dataclass
class GestureAction:
    """Action to execute when a gesture is recognized."""
    gesture: GestureType
    action_name: str
    handler: Optional[Callable] = None
    description: str = ""
    min_confidence: float = 0.7
    cooldown_ms: int = 500
    is_enabled: bool = True


@dataclass
class GestureEvent:
    """Recognized gesture event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    gesture: GestureType = GestureType.NONE
    confidence: float = 0.0
    hand: Optional[HandDetection] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class HandLandmarkDetector:
    """Detects hand landmarks in video frames.

    In production, wraps MediaPipe Hands. Here provides the API contract
    and simulation support.
    """

    LANDMARK_NAMES = [
        "wrist", "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
        "index_mcp", "index_pip", "index_dip", "index_tip",
        "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
        "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
        "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
    ]

    def __init__(self, max_hands: int = 2, min_detection_confidence: float = 0.5):
        self.max_hands = max_hands
        self.min_detection_confidence = min_detection_confidence
        self._detector = None
        self._detection_count = 0

    def initialize(self) -> bool:
        try:
            import mediapipe as mp
            self._detector = mp.solutions.hands.Hands(
                max_num_hands=self.max_hands,
                min_detection_confidence=self.min_detection_confidence,
            )
            logger.info("MediaPipe Hands initialized")
            return True
        except ImportError:
            logger.warning("MediaPipe not available, hand detection in simulation mode")
            return True

    def detect(self, frame: Any) -> List[HandDetection]:
        """Detect hands in a frame."""
        self._detection_count += 1
        if self._detector is not None:
            # Real detection path (requires MediaPipe + numpy frame)
            pass
        # Simulation: no hands detected
        return []

    @property
    def stats(self) -> Dict[str, Any]:
        return {"detections": self._detection_count, "has_detector": self._detector is not None}


class GestureClassifier:
    """Classifies hand landmarks into gesture types."""

    def __init__(self, sensitivity: float = 0.7):
        self.sensitivity = sensitivity
        self._classification_count = 0

    def classify(self, hand: HandDetection) -> Tuple[GestureType, float]:
        """Classify a detected hand into a gesture type."""
        self._classification_count += 1
        if not hand.landmarks or len(hand.landmarks) < 21:
            return (GestureType.NONE, 0.0)

        tips = hand.fingertips
        wrist = hand.wrist

        if not wrist or len(tips) < 5:
            return (GestureType.NONE, 0.0)

        # Compute finger extension states
        extended = []
        for tip in tips:
            dist = ((tip.x - wrist.x)**2 + (tip.y - wrist.y)**2) ** 0.5
            extended.append(dist > 0.15)

        ext_count = sum(extended)

        # Classify based on finger states
        if ext_count == 5:
            return (GestureType.OPEN_PALM, 0.85)
        elif ext_count == 0:
            return (GestureType.CLOSED_FIST, 0.85)
        elif ext_count == 1 and extended[1]:  # Index only
            return (GestureType.POINT_UP, 0.80)
        elif ext_count == 2 and extended[1] and extended[2]:
            return (GestureType.PEACE, 0.80)
        elif ext_count == 1 and extended[0]:  # Thumb only
            if tips[0].y < wrist.y:
                return (GestureType.THUMBS_UP, 0.75)
            else:
                return (GestureType.THUMBS_DOWN, 0.75)

        return (GestureType.NONE, 0.0)


class GestureMapping:
    """Maps gestures to system actions."""

    def __init__(self):
        self._mappings: Dict[GestureType, GestureAction] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            GestureAction(GestureType.THUMBS_UP, "confirm", description="Confirm/approve action"),
            GestureAction(GestureType.THUMBS_DOWN, "reject", description="Reject/cancel action"),
            GestureAction(GestureType.OPEN_PALM, "stop", description="Stop current operation"),
            GestureAction(GestureType.CLOSED_FIST, "pause", description="Pause current operation"),
            GestureAction(GestureType.WAVE, "greeting", description="Wake/greet system"),
            GestureAction(GestureType.SWIPE_LEFT, "prev", description="Previous item/page"),
            GestureAction(GestureType.SWIPE_RIGHT, "next", description="Next item/page"),
        ]
        for action in defaults:
            self._mappings[action.gesture] = action

    def get_action(self, gesture: GestureType) -> Optional[GestureAction]:
        return self._mappings.get(gesture)

    def set_action(self, action: GestureAction) -> None:
        self._mappings[action.gesture] = action

    def list_mappings(self) -> List[Dict[str, Any]]:
        return [
            {"gesture": g.value, "action": a.action_name, "description": a.description}
            for g, a in self._mappings.items()
        ]


class GestureTracker:
    """Tracks gestures over time for temporal gesture detection (swipes, etc.)."""

    def __init__(self, history_frames: int = 15):
        self.history_frames = history_frames
        self._hand_positions: deque = deque(maxlen=history_frames)
        self._last_gesture_time: Dict[str, float] = {}

    def update(self, hands: List[HandDetection]) -> Optional[GestureType]:
        """Update tracker with new hand detections and check for temporal gestures."""
        now = time.time()
        if hands:
            wrist = hands[0].wrist
            if wrist:
                self._hand_positions.append((now, wrist.x, wrist.y))

        if len(self._hand_positions) < 5:
            return None

        # Check for swipe gestures
        positions = list(self._hand_positions)
        dx = positions[-1][1] - positions[0][1]
        dy = positions[-1][2] - positions[0][2]
        dt = positions[-1][0] - positions[0][0]

        if dt < 0.1 or dt > 2.0:
            return None

        speed = (dx**2 + dy**2) ** 0.5 / dt

        if speed > 0.3:
            if abs(dx) > abs(dy):
                gesture = GestureType.SWIPE_RIGHT if dx > 0 else GestureType.SWIPE_LEFT
            else:
                gesture = GestureType.SWIPE_DOWN if dy > 0 else GestureType.SWIPE_UP

            key = gesture.value
            if key in self._last_gesture_time and now - self._last_gesture_time[key] < 1.0:
                return None
            self._last_gesture_time[key] = now
            return gesture

        return None


class GestureEngine:
    """Main gesture recognition engine combining detection, classification, and tracking."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.landmark_detector = HandLandmarkDetector(
            max_hands=config.get("max_hands", 2),
        )
        self.classifier = GestureClassifier(
            sensitivity=config.get("sensitivity", 0.7),
        )
        self.tracker = GestureTracker()
        self.mapping = GestureMapping()
        self._event_history: deque = deque(maxlen=200)
        self._callbacks: List[Callable[[GestureEvent], None]] = []
        self._is_active = False

    def initialize(self) -> bool:
        self.landmark_detector.initialize()
        self._is_active = True
        return True

    def process_frame(self, frame: Any) -> Optional[GestureEvent]:
        """Process a video frame for gesture recognition."""
        if not self._is_active:
            return None

        hands = self.landmark_detector.detect(frame)
        if not hands:
            # Check tracker for temporal gestures even without new detection
            temporal = self.tracker.update([])
            if temporal:
                event = GestureEvent(gesture=temporal, confidence=0.7)
                self._emit_event(event)
                return event
            return None

        # Classify static gestures
        for hand in hands:
            gesture, confidence = self.classifier.classify(hand)
            if gesture != GestureType.NONE and confidence > 0.6:
                event = GestureEvent(gesture=gesture, confidence=confidence, hand=hand)
                self._emit_event(event)
                return event

        # Check temporal gestures
        temporal = self.tracker.update(hands)
        if temporal:
            event = GestureEvent(gesture=temporal, confidence=0.7)
            self._emit_event(event)
            return event

        return None

    def _emit_event(self, event: GestureEvent) -> None:
        self._event_history.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Gesture callback error: {e}")

    def register_callback(self, callback: Callable[[GestureEvent], None]) -> None:
        self._callbacks.append(callback)

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            {"gesture": e.gesture.value, "confidence": e.confidence, "timestamp": e.timestamp.isoformat()}
            for e in list(self._event_history)[-limit:]
        ]
