"""AetherOS Nexus   Multimodal Fusion Engine.

Fuses inputs from voice, vision, gesture, and ambient sound classifiers
into a unified context for intelligent system control.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.multimodal")


class Modality(enum.Enum):
    VOICE = "voice"
    VISION = "vision"
    GESTURE = "gesture"
    AMBIENT = "ambient"


class FusionStrategy(enum.Enum):
    WEIGHTED_AVERAGE = "weighted_average"
    MAJORITY_VOTE = "majority_vote"
    CONFIDENCE_MAX = "confidence_max"
    CASCADING = "cascading"


@dataclass
class ModalityWeight:
    modality: Modality
    weight: float = 1.0
    is_active: bool = True
    last_update: datetime = field(default_factory=datetime.utcnow)
    reliability_score: float = 1.0


@dataclass
class ModalityPriority:
    priority_order: List[Modality] = field(default_factory=lambda: [
        Modality.VOICE, Modality.VISION, Modality.GESTURE, Modality.AMBIENT
    ])

    def get_priority(self, modality: Modality) -> int:
        try:
            return len(self.priority_order) - self.priority_order.index(modality)
        except ValueError:
            return 0


@dataclass
class FusedInput:
    """Result of multimodal fusion."""
    input_id: str = ""
    intent: str = ""
    confidence: float = 0.0
    contributing_modalities: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class InputStreamManager:
    """Manages input streams from multiple modalities."""

    def __init__(self):
        self._streams: Dict[Modality, deque] = {m: deque(maxlen=100) for m in Modality}
        self._lock = threading.Lock()

    def push(self, modality: Modality, data: Dict[str, Any]) -> None:
        with self._lock:
            data["_timestamp"] = time.time()
            self._streams[modality].append(data)

    def get_recent(self, modality: Modality, window_seconds: float = 5.0) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.time()
            return [
                d for d in self._streams[modality]
                if now - d.get("_timestamp", 0) <= window_seconds
            ]

    def get_all_recent(self, window_seconds: float = 5.0) -> Dict[str, List[Dict[str, Any]]]:
        return {m.value: self.get_recent(m, window_seconds) for m in Modality}


class ContextAwareRouter:
    """Routes fused inputs to appropriate handlers based on system context."""

    def __init__(self):
        self._routes: Dict[str, Callable] = {}
        self._context: Dict[str, Any] = {}

    def register_route(self, intent: str, handler: Callable) -> None:
        self._routes[intent] = handler

    def update_context(self, key: str, value: Any) -> None:
        self._context[key] = value

    def route(self, fused_input: FusedInput) -> Optional[Any]:
        handler = self._routes.get(fused_input.intent)
        if handler:
            return handler(fused_input, self._context)
        return None


class MultimodalFusion:
    """Fuses multiple modality inputs into unified system commands.

    Implements configurable fusion strategies to combine voice, vision,
    gesture, and ambient inputs into a single coherent intent.
    """

    def __init__(
        self,
        strategy: FusionStrategy = FusionStrategy.WEIGHTED_AVERAGE,
        config: Optional[Dict[str, Any]] = None,
    ):
        config = config or {}
        self.strategy = strategy
        self.stream_manager = InputStreamManager()
        self.router = ContextAwareRouter()
        self.priority = ModalityPriority()
        self._weights: Dict[Modality, ModalityWeight] = {
            Modality.VOICE: ModalityWeight(Modality.VOICE, weight=1.0),
            Modality.VISION: ModalityWeight(Modality.VISION, weight=0.8),
            Modality.GESTURE: ModalityWeight(Modality.GESTURE, weight=0.6),
            Modality.AMBIENT: ModalityWeight(Modality.AMBIENT, weight=0.3),
        }
        self._fusion_history: deque = deque(maxlen=200)
        self._callbacks: List[Callable[[FusedInput], None]] = []

    def fuse(self, window_seconds: float = 3.0) -> Optional[FusedInput]:
        """Perform multimodal fusion on recent inputs."""
        all_recent = self.stream_manager.get_all_recent(window_seconds)

        active_inputs = {
            k: v for k, v in all_recent.items() if v
        }
        if not active_inputs:
            return None

        if self.strategy == FusionStrategy.WEIGHTED_AVERAGE:
            return self._fuse_weighted(active_inputs)
        elif self.strategy == FusionStrategy.CONFIDENCE_MAX:
            return self._fuse_max_confidence(active_inputs)
        elif self.strategy == FusionStrategy.CASCADING:
            return self._fuse_cascading(active_inputs)
        return None

    def _fuse_weighted(self, inputs: Dict[str, List]) -> FusedInput:
        """Weighted average fusion."""
        intents: Dict[str, float] = {}
        contributing = []

        for modality_str, events in inputs.items():
            modality = Modality(modality_str)
            weight = self._weights.get(modality, ModalityWeight(modality)).weight

            for event in events:
                intent = event.get("intent", "")
                conf = event.get("confidence", 0.5)
                if intent:
                    intents[intent] = intents.get(intent, 0) + conf * weight
                    contributing.append(modality_str)

        if not intents:
            return FusedInput(contributing_modalities=contributing)

        best_intent = max(intents, key=intents.get)
        fused = FusedInput(
            intent=best_intent,
            confidence=min(1.0, intents[best_intent]),
            contributing_modalities=list(set(contributing)),
        )
        self._fusion_history.append(fused)
        return fused

    def _fuse_max_confidence(self, inputs: Dict[str, List]) -> FusedInput:
        """Max confidence fusion   picks the most confident single input."""
        best_intent = ""
        best_conf = 0.0
        best_modality = ""

        for modality_str, events in inputs.items():
            for event in events:
                conf = event.get("confidence", 0)
                if conf > best_conf:
                    best_conf = conf
                    best_intent = event.get("intent", "")
                    best_modality = modality_str

        return FusedInput(
            intent=best_intent,
            confidence=best_conf,
            contributing_modalities=[best_modality] if best_modality else [],
        )

    def _fuse_cascading(self, inputs: Dict[str, List]) -> FusedInput:
        """Cascading fusion   check modalities in priority order."""
        for modality in self.priority.priority_order:
            events = inputs.get(modality.value, [])
            for event in events:
                if event.get("confidence", 0) > 0.5:
                    return FusedInput(
                        intent=event.get("intent", ""),
                        confidence=event.get("confidence", 0),
                        contributing_modalities=[modality.value],
                    )
        return FusedInput()

    def push_input(self, modality: Modality, data: Dict[str, Any]) -> None:
        self.stream_manager.push(modality, data)

    def register_callback(self, callback: Callable[[FusedInput], None]) -> None:
        self._callbacks.append(callback)

    def set_weight(self, modality: Modality, weight: float) -> None:
        if modality in self._weights:
            self._weights[modality].weight = max(0.0, min(weight, 2.0))

    def get_status(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "weights": {m.value: w.weight for m, w in self._weights.items()},
            "fusion_count": len(self._fusion_history),
        }
