"""Tests for AetherOS Storage Module."""
import pytest
import tempfile
import os
from storage.kv_store import KeyValueStore
from storage.file_vault import FileVault


class TestKeyValueStore:
    def test_set_get(self):
        kv = KeyValueStore()
        kv.set("key1", "value1")
        assert kv.get("key1") == "value1"

    def test_default(self):
        kv = KeyValueStore()
        assert kv.get("missing", "default") == "default"

    def test_delete(self):
        kv = KeyValueStore()
        kv.set("k", "v")
        assert kv.delete("k")
        assert kv.get("k") is None

    def test_ttl(self):
        import time
        kv = KeyValueStore()
        kv.set("temp", "data", ttl_seconds=0.1)
        assert kv.get("temp") == "data"
        time.sleep(0.2)
        assert kv.get("temp") is None

    def test_keys(self):
        kv = KeyValueStore()
        kv.set("a", 1)
        kv.set("b", 2)
        assert set(kv.keys()) == {"a", "b"}


class TestFileVault:
    def test_store_and_retrieve(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            temp_path = f.name
        try:
            vault = FileVault(vault_dir=tempfile.mkdtemp())
            entry_id = vault.store(temp_path, tags=["test"])
            assert entry_id
            retrieved = vault.retrieve(entry_id)
            assert retrieved
            assert os.path.exists(retrieved)
        finally:
            os.unlink(temp_path)

    def test_list_entries(self):
        vault = FileVault(vault_dir=tempfile.mkdtemp())
        entries = vault.list_entries()
        assert isinstance(entries, list)
