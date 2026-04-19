"""ChromaDB-based long-term memory store."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from config.constants import CHROMA_PERSIST_DIR, CHROMA_COLLECTION

logger = logging.getLogger("aetheros.memory.chroma")


@dataclass
class MemoryEntry:
    """A memory record to be stored."""
    content: str
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.entry_id:
            self.entry_id = str(uuid.uuid4())[:12]

    def to_metadata(self) -> dict:
        """Flatten to ChromaDB metadata (only str/int/float/bool)."""
        return {
            "category": self.category,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "tags": ",".join(self.tags),
            **{k: str(v) if not isinstance(v, (str, int, float, bool)) else v
               for k, v in self.metadata.items()},
        }


class ChromaMemoryStore:
    """Persistent memory using ChromaDB for semantic search."""

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR,
                 collection_name: str = CHROMA_COLLECTION):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        os.makedirs(persist_dir, exist_ok=True)
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ChromaDB initialized: {self.persist_dir}, "
                f"collection={self.collection_name}, "
                f"entries={self._collection.count()}"
            )
        except Exception as e:
            logger.error(f"ChromaDB initialization failed: {e}")
            self._client = None
            self._collection = None

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry."""
        if not self.is_available:
            logger.warning("ChromaDB not available, memory not stored")
            return False
        try:
            self._collection.upsert(
                ids=[entry.entry_id],
                documents=[entry.content],
                metadatas=[entry.to_metadata()],
            )
            logger.debug(f"Stored memory: {entry.entry_id} [{entry.category}]")
            return True
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False

    def store_text(self, text: str, category: str = "general",
                   tags: Optional[list[str]] = None, importance: float = 0.5,
                   metadata: Optional[dict] = None) -> str:
        """Convenience method to store text."""
        entry = MemoryEntry(
            content=text,
            category=category,
            tags=tags or [],
            importance=importance,
            metadata=metadata or {},
        )
        self.store(entry)
        return entry.entry_id

    def search(self, query: str, n_results: int = 10,
               category: Optional[str] = None,
               min_importance: float = 0.0) -> list[dict]:
        """Semantic search for memories."""
        if not self.is_available:
            return []
        try:
            where_filter = {}
            if category:
                where_filter["category"] = category
            if min_importance > 0:
                where_filter["importance"] = {"$gte": min_importance}

            kwargs = {"query_texts": [query], "n_results": min(n_results, 100)}
            if where_filter:
                kwargs["where"] = where_filter

            results = self._collection.query(**kwargs)

            entries = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0
                    entries.append({
                        "id": results["ids"][0][i],
                        "content": doc,
                        "metadata": meta,
                        "similarity": 1 - distance,
                    })
            return entries
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    def get_by_id(self, entry_id: str) -> Optional[dict]:
        """Retrieve a specific memory entry."""
        if not self.is_available:
            return None
        try:
            result = self._collection.get(ids=[entry_id])
            if result["documents"]:
                return {
                    "id": entry_id,
                    "content": result["documents"][0],
                    "metadata": result["metadatas"][0] if result["metadatas"] else {},
                }
            return None
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return None

    def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        if not self.is_available:
            return False
        try:
            self._collection.delete(ids=[entry_id])
            return True
        except Exception as e:
            logger.error(f"Memory deletion failed: {e}")
            return False

    def list_categories(self) -> list[str]:
        """List all memory categories."""
        if not self.is_available:
            return []
        try:
            result = self._collection.get(include=["metadatas"])
            cats = set()
            for meta in (result["metadatas"] or []):
                if "category" in meta:
                    cats.add(meta["category"])
            return sorted(cats)
        except Exception as e:
            logger.error(f"Category listing failed: {e}")
            return []

    def get_stats(self) -> dict:
        """Get memory store statistics."""
        if not self.is_available:
            return {"available": False}
        try:
            count = self._collection.count()
            categories = self.list_categories()
            return {
                "available": True,
                "total_entries": count,
                "categories": categories,
                "persist_dir": self.persist_dir,
                "collection": self.collection_name,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def clear(self) -> bool:
        """Clear all memories (dangerous!)."""
        if not self.is_available:
            return False
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.warning("Memory store cleared!")
            return True
        except Exception as e:
            logger.error(f"Memory clear failed: {e}")
            return False
