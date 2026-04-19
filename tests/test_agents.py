"""Tests for agent module."""
import asyncio
import json
import pytest

from agents.base import AgentMessage
from agents.architect import ArchitectAgent
from agents.executor import ExecutorAgent
from agents.auditor import AuditorAgent
from core.event_bus import EventBus
from core.model_manager import ModelManager
from core.state import SystemState
from config.settings import ModelConfig
from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps
from security.audit import AuditLogger


@pytest.fixture
def model():
    return ModelManager(ModelConfig())


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def state():
    return SystemState()


@pytest.fixture
def tools():
    registry = ToolRegistry()
    registry.register(FileOps(allowed_dirs=["/tmp"], sandbox=True))
    registry.register(ShellOps(sandbox=True))
    return registry


class TestArchitectAgent:
    @pytest.mark.asyncio
    async def test_process_message(self, model, bus, state):
        architect = ArchitectAgent(model, bus, state)
        msg = AgentMessage(
            sender="user",
            recipient="architect",
            content="Create a directory structure for a web app",
        )
        response = await architect.process(msg)
        assert response.sender == "architect"
        assert response.message_type == "plan"

        plan = json.loads(response.content)
        assert "plan" in plan

    @pytest.mark.asyncio
    async def test_status(self, model, bus, state):
        architect = ArchitectAgent(model, bus, state)
        status = architect.get_status()
        assert status["role"] == "planning"
        assert status["name"] == "architect"


class TestExecutorAgent:
    @pytest.mark.asyncio
    async def test_process_step(self, model, bus, state, tools):
        executor = ExecutorAgent(model, bus, state, tools)
        step = {
            "description": "List files in /tmp",
            "tool": "shell_ops",
            "args": {"action": "run", "command": "echo test_output"},
        }
        msg = AgentMessage(
            sender="orchestrator",
            recipient="executor",
            content=json.dumps(step),
            message_type="step",
        )
        response = await executor.process(msg)
        result = json.loads(response.content)
        assert result["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_execute_step_direct(self, model, bus, state, tools):
        executor = ExecutorAgent(model, bus, state, tools)
        result = await executor.execute_step({
            "description": "Echo test",
            "tool": "shell_ops",
            "args": {"action": "run", "command": "echo direct_test"},
        })
        assert "status" in result


class TestAuditorAgent:
    @pytest.mark.asyncio
    async def test_audit_result(self, model, bus, state, tmp_path):
        audit_logger = AuditLogger(log_dir=str(tmp_path))
        auditor = AuditorAgent(model, bus, state, audit_logger)
        msg = AgentMessage(
            sender="executor",
            recipient="auditor",
            content=json.dumps({
                "step": 1,
                "description": "Listed directory",
                "result": "file1.txt\nfile2.txt",
                "status": "completed",
            }),
            message_type="execution_result",
            metadata={"step": "list_directory"},
        )
        response = await auditor.process(msg)
        result = json.loads(response.content)
        assert "audit_result" in result

    @pytest.mark.asyncio
    async def test_pre_execution_check(self, model, bus, state, tmp_path):
        audit_logger = AuditLogger(log_dir=str(tmp_path))
        auditor = AuditorAgent(model, bus, state, audit_logger)
        result = await auditor.pre_execution_check({
            "description": "Read a file",
            "tool": "file_ops",
            "args": {"action": "read", "path": "/tmp/test.txt"},
        })
        assert "audit_result" in result

    def test_audit_summary(self, model, bus, state, tmp_path):
        audit_logger = AuditLogger(log_dir=str(tmp_path))
        auditor = AuditorAgent(model, bus, state, audit_logger)
        summary = auditor.get_audit_summary()
        assert "total_entries" in summary


class TestAgentMessage:
    def test_creation(self):
        msg = AgentMessage(
            sender="test",
            recipient="other",
            content="Hello",
        )
        assert msg.message_id
        assert msg.timestamp

    def test_to_dict(self):
        msg = AgentMessage(sender="a", recipient="b", content="test")
        d = msg.to_dict()
        assert d["sender"] == "a"
        assert d["recipient"] == "b"
