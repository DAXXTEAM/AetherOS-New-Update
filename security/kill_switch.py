"""Hardware-ready kill switch logic."""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Callable, Optional

from config.constants import KILL_SWITCH_FILE

logger = logging.getLogger("aetheros.security.kill_switch")


class KillSwitchStatus(Enum):
    ARMED = auto()
    DISARMED = auto()
    ENGAGED = auto()
    COOLDOWN = auto()


@dataclass
class KillSwitchEvent:
    """Record of a kill switch event."""
    timestamp: datetime
    status: KillSwitchStatus
    trigger: str
    reason: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.name,
            "trigger": self.trigger,
            "reason": self.reason,
        }


class KillSwitch:
    """Emergency kill switch with hardware-ready interface.

    Monitors for:
    - File-based trigger (write to ~/.aetheros/.killswitch)
    - Signal-based trigger (SIGUSR1)
    - Programmatic trigger
    - Watchdog timeout (deadman's switch)
    """

    def __init__(self, enabled: bool = True, watchdog_timeout: int = 300,
                 cooldown_seconds: int = 30):
        self.enabled = enabled
        self.status = KillSwitchStatus.ARMED if enabled else KillSwitchStatus.DISARMED
        self.watchdog_timeout = watchdog_timeout
        self.cooldown_seconds = cooldown_seconds
        self._callbacks: list[Callable] = []
        self._history: list[KillSwitchEvent] = []
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_heartbeat = time.time()
        self._engaged_at: Optional[float] = None

        os.makedirs(os.path.dirname(KILL_SWITCH_FILE), exist_ok=True)

        if enabled:
            self._setup_signal_handler()

    def _setup_signal_handler(self) -> None:
        """Register signal handler as kill switch trigger."""
        try:
            # Handle cross-platform signals
            # SIGUSR1 is Unix-only, so we check for its existence
            if hasattr(signal, "SIGUSR1"):
                signal.signal(signal.SIGUSR1, self._signal_handler)
                logger.info("Kill switch signal handler registered (SIGUSR1)")
            else:
                logger.info("SIGUSR1 not available on this platform, skipping signal-based trigger")
        except (OSError, ValueError) as e:
            logger.warning(f"Could not register signal handler: {e}")
    def _signal_handler(self, signum, frame) -> None:
        self.engage("signal", f"Received signal {signum}")

    def register_callback(self, callback: Callable) -> None:
        """Register a callback for kill switch engagement."""
        self._callbacks.append(callback)

    def heartbeat(self) -> None:
        """Reset the watchdog timer."""
        self._last_heartbeat = time.time()

    def engage(self, trigger: str = "manual", reason: str = "User initiated") -> bool:
        """Engage the kill switch - stop all operations."""
        with self._lock:
            if self.status == KillSwitchStatus.ENGAGED:
                return True
            if self.status == KillSwitchStatus.COOLDOWN:
                logger.warning("Kill switch in cooldown period")
                return False

            self.status = KillSwitchStatus.ENGAGED
            self._engaged_at = time.time()

            event = KillSwitchEvent(
                timestamp=datetime.now(),
                status=KillSwitchStatus.ENGAGED,
                trigger=trigger,
                reason=reason,
            )
            self._history.append(event)

            # Write kill switch file
            try:
                with open(KILL_SWITCH_FILE, "w") as f:
                    json.dump(event.to_dict(), f)
            except OSError as e:
                logger.error(f"Could not write kill switch file: {e}")

            logger.critical(f"  KILL SWITCH ENGAGED - Trigger: {trigger}, Reason: {reason}")

            # Execute callbacks
            for cb in self._callbacks:
                try:
                    cb(event)
                except Exception as e:
                    logger.error(f"Kill switch callback error: {e}")

            return True

    def disengage(self, authorization: str = "") -> bool:
        """Disengage the kill switch after verification."""
        with self._lock:
            if self.status != KillSwitchStatus.ENGAGED:
                return True

            # Require minimum engagement time
            if self._engaged_at and (time.time() - self._engaged_at) < 5:
                logger.warning("Kill switch must remain engaged for at least 5 seconds")
                return False

            self.status = KillSwitchStatus.COOLDOWN
            event = KillSwitchEvent(
                timestamp=datetime.now(),
                status=KillSwitchStatus.COOLDOWN,
                trigger="disengage",
                reason=f"Disengaged with auth: {authorization[:8]}...",
            )
            self._history.append(event)

            # Remove kill switch file
            try:
                if os.path.exists(KILL_SWITCH_FILE):
                    os.remove(KILL_SWITCH_FILE)
            except OSError:
                pass

            # Start cooldown timer
            def _end_cooldown():
                time.sleep(self.cooldown_seconds)
                with self._lock:
                    if self.status == KillSwitchStatus.COOLDOWN:
                        self.status = KillSwitchStatus.ARMED
                        logger.info("Kill switch cooldown complete, re-armed")

            threading.Thread(target=_end_cooldown, daemon=True).start()
            logger.warning("Kill switch disengaged, entering cooldown")
            return True

    def start_monitoring(self) -> None:
        """Start background monitoring for file-based and watchdog triggers."""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Kill switch monitoring started")

    def stop_monitoring(self) -> None:
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self) -> None:
        """Monitor for file-based triggers and watchdog timeout."""
        while self._running:
            try:
                # Check file trigger
                if os.path.exists(KILL_SWITCH_FILE) and self.status != KillSwitchStatus.ENGAGED:
                    self.engage("file", f"Kill switch file detected: {KILL_SWITCH_FILE}")

                # Check watchdog timeout
                elapsed = time.time() - self._last_heartbeat
                if elapsed > self.watchdog_timeout and self.status == KillSwitchStatus.ARMED:
                    self.engage("watchdog", f"No heartbeat for {elapsed:.0f}s (timeout: {self.watchdog_timeout}s)")

            except Exception as e:
                logger.error(f"Kill switch monitor error: {e}")

            time.sleep(2)

    @property
    def is_engaged(self) -> bool:
        return self.status == KillSwitchStatus.ENGAGED

    def get_status(self) -> dict:
        return {
            "status": self.status.name,
            "enabled": self.enabled,
            "watchdog_timeout": self.watchdog_timeout,
            "last_heartbeat_age": time.time() - self._last_heartbeat,
            "history_count": len(self._history),
            "callbacks_registered": len(self._callbacks),
        }

    def get_history(self) -> list[dict]:
        return [e.to_dict() for e in self._history]
