"""Logging configuration for AetherOS."""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

from config.constants import LOG_DIR, LOG_FORMAT, LOG_DATE_FORMAT


class AetherLogHandler(logging.Handler):
    """Custom handler that stores log records for GUI consumption."""

    def __init__(self, max_records: int = 5000):
        super().__init__()
        self._records: list[dict] = []
        self._max_records = max_records
        self._callbacks: list = []

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).strftime(LOG_DATE_FORMAT),
            "level": record.levelname,
            "name": record.name,
            "message": self.format(record),
        }
        self._records.append(entry)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]
        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    def get_records(self, last_n: int = 100) -> list[dict]:
        return self._records[-last_n:]

    def register_callback(self, callback) -> None:
        self._callbacks.append(callback)

    def unregister_callback(self, callback) -> None:
        self._callbacks = [cb for cb in self._callbacks if cb != callback]


# Global handler instance
_gui_handler: Optional[AetherLogHandler] = None


def get_gui_handler() -> AetherLogHandler:
    global _gui_handler
    if _gui_handler is None:
        _gui_handler = AetherLogHandler()
        _gui_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    return _gui_handler


def setup_logging(
    log_dir: str = LOG_DIR,
    level: int = logging.INFO,
    enable_file: bool = True,
    enable_gui: bool = True,
) -> logging.Logger:
    """Set up the root AetherOS logger."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("aetheros")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    if enable_file:
        log_file = os.path.join(log_dir, f"aetheros_{datetime.now():%Y%m%d}.log")
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10_000_000, backupCount=5
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # GUI handler
    if enable_gui:
        gui_handler = get_gui_handler()
        gui_handler.setLevel(level)
        logger.addHandler(gui_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under aetheros namespace."""
    return logging.getLogger(f"aetheros.{name}")
