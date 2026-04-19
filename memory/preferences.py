"""User preference storage backed by ChromaDB."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from memory.chroma_store import ChromaMemoryStore, MemoryEntry

logger = logging.getLogger("aetheros.memory.preferences")


class PreferenceStore:
    """Stores and retrieves user preferences using ChromaDB."""

    CATEGORY = "user_preference"

    def __init__(self, memory_store: ChromaMemoryStore):
        self._store = memory_store
        self._cache: dict[str, Any] = {}

    def set_preference(self, key: str, value: Any, description: str = "") -> bool:
        """Set a user preference."""
        content = f"User preference: {key} = {json.dumps(value)}"
        if description:
            content += f" ({description})"

        entry_id = f"pref-{key}"
        entry = MemoryEntry(
            content=content,
            category=self.CATEGORY,
            entry_id=entry_id,
            importance=0.8,
            tags=["preference", key],
            metadata={"key": key, "value": json.dumps(value), "description": description},
        )
        success = self._store.store(entry)
        if success:
            self._cache[key] = value
        return success

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference by key."""
        if key in self._cache:
            return self._cache[key]

        entry = self._store.get_by_id(f"pref-{key}")
        if entry and entry.get("metadata"):
            try:
                value = json.loads(entry["metadata"].get("value", "null"))
                self._cache[key] = value
                return value
            except (json.JSONDecodeError, KeyError):
                pass
        return default

    def delete_preference(self, key: str) -> bool:
        """Delete a preference."""
        self._cache.pop(key, None)
        return self._store.delete(f"pref-{key}")

    def list_preferences(self) -> dict[str, Any]:
        """List all preferences."""
        results = self._store.search("user preference", n_results=100, category=self.CATEGORY)
        prefs = {}
        for r in results:
            meta = r.get("metadata", {})
            key = meta.get("key", "")
            if key:
                try:
                    prefs[key] = json.loads(meta.get("value", "null"))
                except json.JSONDecodeError:
                    prefs[key] = meta.get("value")
        return prefs

    def search_preferences(self, query: str, n_results: int = 5) -> list[dict]:
        """Search preferences by relevance."""
        return self._store.search(
            f"user preference {query}",
            n_results=n_results,
            category=self.CATEGORY,
        )
