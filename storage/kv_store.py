"""AetherOS Storage — Key-Value Store.

Thread-safe persistent key-value storage with TTL support.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("storage.kv")


class KeyValueStore:
    """Persistent key-value store with TTL support."""

    def __init__(self, persist_path: Optional[str] = None):
        self.persist_path = persist_path or os.path.expanduser("~/.aetheros/kv_store.json")
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        with self._lock:
            entry = {"value": value, "created_at": time.time()}
            if ttl_seconds:
                entry["expires_at"] = time.time() + ttl_seconds
            self._data[key] = entry

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return default
            if "expires_at" in entry and time.time() > entry["expires_at"]:
                del self._data[key]
                return default
            return entry["value"]

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def save(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            with open(self.persist_path, "w") as f:
                json.dump(self._data, f)
            return True
        except Exception as e:
            logger.error(f"KV store save failed: {e}")
            return False

    def load(self) -> bool:
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path, "r") as f:
                    self._data = json.load(f)
                return True
            return False
        except Exception as e:
            logger.error(f"KV store load failed: {e}")
            return False
