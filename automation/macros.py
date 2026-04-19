"""AetherOS Automation — Macro System.

Record and replay sequences of commands as macros.
"""
from __future__ import annotations

import enum
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("automation.macros")


class MacroTrigger(enum.Enum):
    MANUAL = "manual"
    HOTKEY = "hotkey"
    VOICE = "voice"
    GESTURE = "gesture"
    SCHEDULE = "schedule"
    EVENT = "event"


@dataclass
class MacroAction:
    """Single action within a macro."""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    delay_ms: int = 0
    condition: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "type": self.action_type,
            "params": self.params,
            "delay_ms": self.delay_ms,
        }


@dataclass
class Macro:
    """A sequence of actions that can be recorded and replayed."""
    macro_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    actions: List[MacroAction] = field(default_factory=list)
    trigger: MacroTrigger = MacroTrigger.MANUAL
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True
    execution_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_executed: Optional[datetime] = None

    def add_action(self, action: MacroAction) -> None:
        self.actions.append(action)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "macro_id": self.macro_id,
            "name": self.name,
            "actions_count": len(self.actions),
            "trigger": self.trigger.value,
            "is_enabled": self.is_enabled,
            "execution_count": self.execution_count,
        }


class MacroEngine:
    """Records, stores, and replays macros."""

    def __init__(self):
        self._macros: Dict[str, Macro] = {}
        self._recording: Optional[Macro] = None
        self._is_recording = False
        self._action_handlers: Dict[str, Callable] = {}
        self._lock = __import__("threading").Lock()
        logger.info("MacroEngine initialized")

    def start_recording(self, name: str) -> str:
        """Start recording a new macro."""
        macro = Macro(name=name)
        self._recording = macro
        self._is_recording = True
        logger.info(f"Started recording macro: {name}")
        return macro.macro_id

    def record_action(self, action_type: str, params: Dict[str, Any] = None) -> None:
        """Record an action to the current macro."""
        if not self._is_recording or not self._recording:
            return
        action = MacroAction(action_type=action_type, params=params or {})
        self._recording.add_action(action)

    def stop_recording(self) -> Optional[str]:
        """Stop recording and save the macro."""
        if not self._recording:
            return None
        macro = self._recording
        self._is_recording = False
        self._recording = None
        with self._lock:
            self._macros[macro.macro_id] = macro
        logger.info(f"Macro recorded: {macro.name} ({len(macro.actions)} actions)")
        return macro.macro_id

    def play(self, macro_id: str) -> bool:
        """Execute a macro."""
        with self._lock:
            macro = self._macros.get(macro_id)
            if not macro or not macro.is_enabled:
                return False

        for action in macro.actions:
            if action.delay_ms > 0:
                import time
                time.sleep(action.delay_ms / 1000.0)
            handler = self._action_handlers.get(action.action_type)
            if handler:
                try:
                    handler(action.params)
                except Exception as e:
                    logger.error(f"Macro action error: {e}")
                    return False

        macro.execution_count += 1
        macro.last_executed = datetime.utcnow()
        return True

    def register_handler(self, action_type: str, handler: Callable) -> None:
        self._action_handlers[action_type] = handler

    def list_macros(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [m.to_dict() for m in self._macros.values()]

    def delete_macro(self, macro_id: str) -> bool:
        with self._lock:
            return self._macros.pop(macro_id, None) is not None

    @property
    def is_recording(self) -> bool:
        return self._is_recording
