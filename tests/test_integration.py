"""Integration tests for AetherOS system."""
import asyncio
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import AetherConfig, ModelConfig, MemoryConfig
from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager
from core.orchestrator import Orchestrator
from core.state import SystemState
from core.task import Task
from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps
from security.crypto import QuantumSafeCrypto
from security.kill_switch import KillSwitch
from security.audit import AuditLogger
from memory.chroma_store import ChromaMemoryStore
from memory.context import ContextManager


class TestFullPipeline:
    """End-to-end integration tests."""

    @pytest.fixture
    def system(self, tmp_path):
        config = AetherConfig(
            log_dir=str(tmp_path / "logs"),
            workspace_dir=str(tmp_path / "workspace"),
            memory=MemoryConfig(persist_directory=str(tmp_path / "chromadb")),
        )
        config.ensure_dirs()

        event_bus = EventBus()
        state = SystemState()
        model = ModelManager(config.model)

        registry = ToolRegistry()
        registry.register(FileOps(allowed_dirs=[str(tmp_path), "/tmp"], sandbox=True))
        registry.register(ShellOps(sandbox=True, working_dir=str(tmp_path / "workspace")))

        orchestrator = Orchestrator(model, event_bus, state, registry)
        memory = ChromaMemoryStore(str(tmp_path / "chromadb"), "test_collection")
        crypto = QuantumSafeCrypto()
        audit = AuditLogger(log_dir=str(tmp_path / "audit"))

        return {
            "config": config,
            "event_bus": event_bus,
            "state": state,
            "model": model,
            "orchestrator": orchestrator,
            "memory": memory,
            "crypto": crypto,
            "audit": audit,
            "tmp_path": tmp_path,
        }

    @pytest.mark.asyncio
    async def test_full_task_execution(self, system):
        """Test complete task execution pipeline."""
        task = Task(objective="List files in the workspace directory")
        result = await system["orchestrator"].run_task(task)
        assert result.task_id
        assert result.output

    @pytest.mark.asyncio
    async def test_event_flow(self, system):
        """Test that events flow correctly through the system."""
        events_received = []

        async def collector(event: Event):
            events_received.append(event)

        system["event_bus"].subscribe_all(collector)

        task = Task(objective="Test event flow")
        await system["orchestrator"].run_task(task)

        event_types = [e.event_type for e in events_received]
        assert EventType.AGENT_ACTIVATED in event_types

    def test_crypto_roundtrip(self, system):
        """Test encryption and signing roundtrip."""
        crypto = system["crypto"]
        encrypted = crypto.encrypt("Secret message")
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == "Secret message"

        sig = crypto.sign("Signed content")
        assert crypto.verify("Signed content", sig)

    def test_memory_integration(self, system):
        """Test memory store and retrieval."""
        mem = system["memory"]
        mem.store_text("User prefers dark mode", category="preference", importance=0.9)
        mem.store_text("Task: create Python project completed", category="task_history")

        results = mem.search("dark mode preference")
        assert len(results) > 0

    def test_audit_integrity(self, system):
        """Test audit chain integrity."""
        audit = system["audit"]
        from security.audit import AuditCategory
        audit.log(AuditCategory.COMMAND_EXECUTION, "cmd1", "target1")
        audit.log(AuditCategory.FILE_ACCESS, "read", "/tmp/test")
        audit.log(AuditCategory.SECURITY_EVENT, "check", "system")

        valid, tampered = audit.verify_chain()
        assert valid

    def test_system_state_tracking(self, system):
        """Test that system state updates correctly."""
        state = system["state"]
        state.register_agent("test_agent", "tester")
        state.update_status("executing")
        state.add_task("t1", {"name": "test"})

        status = state.to_dict()
        assert status["status"] == "executing"
        assert status["active_tasks"] == 1
        assert "test_agent" in status["agents"]

    @pytest.mark.asyncio
    async def test_system_status_report(self, system):
        """Test generating a full status report."""
        state = system["state"]
        model = system["model"]
        memory = system["memory"]

        state.register_agent("architect", "planning")
        state.register_agent("executor", "execution")

        status = {
            "state": state.to_dict(),
            "model": model.get_status(),
            "memory": memory.get_stats(),
        }
        assert "state" in status
        assert "model" in status
        assert "memory" in status
