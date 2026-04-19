"""AetherOS Storage   Encrypted File Vault.

Secure file storage with metadata tracking.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("storage.vault")


@dataclass
class VaultEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    original_path: str = ""
    vault_path: str = ""
    file_hash: str = ""
    size_bytes: int = 0
    encrypted: bool = False
    stored_at: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "filename": self.filename,
            "file_hash": self.file_hash[:16] + "..." if self.file_hash else "",
            "size_bytes": self.size_bytes,
            "encrypted": self.encrypted,
            "stored_at": self.stored_at.isoformat(),
            "tags": self.tags,
        }


class FileVault:
    """Secure file storage vault."""

    def __init__(self, vault_dir: Optional[str] = None):
        self.vault_dir = vault_dir or os.path.expanduser("~/.aetheros/vault")
        self._entries: Dict[str, VaultEntry] = {}
        os.makedirs(self.vault_dir, exist_ok=True)

    def store(self, filepath: str, tags: Optional[List[str]] = None) -> Optional[str]:
        if not os.path.exists(filepath):
            return None
        file_hash = self._compute_hash(filepath)
        size = os.path.getsize(filepath)
        entry = VaultEntry(
            filename=os.path.basename(filepath),
            original_path=filepath,
            vault_path=os.path.join(self.vault_dir, f"{uuid.uuid4().hex}"),
            file_hash=file_hash,
            size_bytes=size,
            tags=tags or [],
        )
        try:
            import shutil
            shutil.copy2(filepath, entry.vault_path)
            self._entries[entry.entry_id] = entry
            return entry.entry_id
        except Exception as e:
            logger.error(f"Vault store failed: {e}")
            return None

    def retrieve(self, entry_id: str) -> Optional[str]:
        entry = self._entries.get(entry_id)
        if entry and os.path.exists(entry.vault_path):
            return entry.vault_path
        return None

    def list_entries(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries.values()]

    def _compute_hash(self, filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @property
    def entry_count(self) -> int:
        return len(self._entries)
