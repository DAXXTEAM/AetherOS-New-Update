"""Tests for memory module."""
import os
import pytest
import tempfile

from memory.chroma_store import ChromaMemoryStore, MemoryEntry
from memory.context import ContextManager, ConversationContext
from memory.preferences import PreferenceStore


class TestChromaMemoryStore:
    @pytest.fixture
    def store(self, tmp_path):
        return ChromaMemoryStore(
            persist_dir=str(tmp_path / "chromadb"),
            collection_name="test_memory",
        )

    def test_initialization(self, store):
        assert store.is_available
        stats = store.get_stats()
        assert stats["available"]

    def test_store_and_search(self, store):
        store.store_text("Python is a great programming language", category="knowledge")
        store.store_text("JavaScript is used for web development", category="knowledge")
        store.store_text("My favorite color is blue", category="preference")

        results = store.search("programming language")
        assert len(results) > 0
        assert any("Python" in r["content"] for r in results)

    def test_store_entry(self, store):
        entry = MemoryEntry(
            content="Test memory entry",
            category="test",
            importance=0.9,
            tags=["unit-test"],
        )
        success = store.store(entry)
        assert success

    def test_get_by_id(self, store):
        entry_id = store.store_text("Specific entry", category="test")
        retrieved = store.get_by_id(entry_id)
        assert retrieved is not None
        assert "Specific entry" in retrieved["content"]

    def test_delete(self, store):
        entry_id = store.store_text("Delete me", category="test")
        assert store.delete(entry_id)
        assert store.get_by_id(entry_id) is None

    def test_category_search(self, store):
        store.store_text("Cat fact 1", category="animals")
        store.store_text("Dog fact 1", category="animals")
        store.store_text("Python fact", category="tech")

        results = store.search("facts", category="animals")
        assert all(r["metadata"].get("category") == "animals" for r in results)

    def test_list_categories(self, store):
        store.store_text("entry1", category="cat_a")
        store.store_text("entry2", category="cat_b")
        cats = store.list_categories()
        assert "cat_a" in cats
        assert "cat_b" in cats

    def test_stats(self, store):
        store.store_text("test1")
        store.store_text("test2")
        stats = store.get_stats()
        assert stats["total_entries"] >= 2

    def test_clear(self, store):
        store.store_text("to be cleared")
        assert store.clear()
        assert store.get_stats()["total_entries"] == 0


class TestContextManager:
    def test_create_context(self):
        cm = ContextManager()
        ctx = cm.create_context("test1", system_prompt="You are helpful")
        assert ctx.context_id == "test1"
        assert ctx.system_prompt == "You are helpful"

    def test_add_messages(self):
        cm = ContextManager()
        ctx = cm.create_context("test")
        ctx.add_message("user", "Hello")
        ctx.add_message("assistant", "Hi there")
        assert len(ctx.messages) == 2

    def test_context_trimming(self):
        cm = ContextManager()
        ctx = cm.create_context("test", max_tokens=100)
        for i in range(50):
            ctx.add_message("user", f"Message {i} with some content to fill tokens " * 3)
        assert ctx.total_tokens <= 100 + 100  # Some slack

    def test_to_messages(self):
        cm = ContextManager()
        ctx = cm.create_context("test", system_prompt="System")
        ctx.add_message("user", "Hello")
        msgs = ctx.to_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_multiple_contexts(self):
        cm = ContextManager()
        cm.create_context("ctx1")
        cm.create_context("ctx2")
        assert len(cm.list_contexts()) == 2

    def test_active_context(self):
        cm = ContextManager()
        cm.create_context("ctx1")
        cm.create_context("ctx2")
        assert cm.active.context_id == "ctx2"

    def test_delete_context(self):
        cm = ContextManager()
        cm.create_context("ctx1")
        assert cm.delete_context("ctx1")
        assert cm.get_context("ctx1") is None

    def test_get_or_create(self):
        cm = ContextManager()
        ctx1 = cm.get_or_create("auto", system_prompt="test")
        ctx2 = cm.get_or_create("auto")
        assert ctx1 is ctx2


class TestPreferenceStore:
    @pytest.fixture
    def prefs(self, tmp_path):
        store = ChromaMemoryStore(str(tmp_path / "prefs"), "prefs")
        return PreferenceStore(store)

    def test_set_and_get(self, prefs):
        prefs.set_preference("theme", "dark")
        assert prefs.get_preference("theme") == "dark"

    def test_default_value(self, prefs):
        assert prefs.get_preference("nonexistent", "default") == "default"

    def test_complex_value(self, prefs):
        prefs.set_preference("settings", {"font_size": 14, "lang": "en"})
        val = prefs.get_preference("settings")
        assert val["font_size"] == 14

    def test_delete(self, prefs):
        prefs.set_preference("temp", "value")
        assert prefs.delete_preference("temp")

    def test_list_preferences(self, prefs):
        prefs.set_preference("pref1", "val1")
        prefs.set_preference("pref2", "val2")
        all_prefs = prefs.list_preferences()
        assert "pref1" in all_prefs or "pref2" in all_prefs
