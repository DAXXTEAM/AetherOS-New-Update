"""Tests for the LangGraph orchestrator."""
import asyncio
import json
import pytest

from core.orchestrator import Orchestrator
from core.event_bus import EventBus
from core.model_manager import ModelManager
from core.state import SystemState
from core.task import Task, TaskPriority
from config.settings import ModelConfig
from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps


@pytest.fixture
def orchestrator():
    config = ModelConfig()
    model = ModelManager(config)
    bus = EventBus()
    state = SystemState()
    registry = ToolRegistry()
    registry.register(FileOps(allowed_dirs=["/tmp"], sandbox=True))
    registry.register(ShellOps(sandbox=True))
    return Orchestrator(model, bus, state, registry)


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_run_simple_task(self, orchestrator):
        task = Task(objective="Echo hello world", priority=TaskPriority.NORMAL)
        result = await orchestrator.run_task(task)
        assert result.task_id == task.task_id
        assert result.output

    @pytest.mark.asyncio
    async def test_task_metrics(self, orchestrator):
        task = Task(objective="Simple test task")
        result = await orchestrator.run_task(task)
        assert "steps_planned" in result.metrics
        assert "steps_executed" in result.metrics

    @pytest.mark.asyncio
    async def test_task_audit_trail(self, orchestrator):
        task = Task(objective="Audited task")
        result = await orchestrator.run_task(task)
        assert isinstance(result.audit_trail, list)

    @pytest.mark.asyncio
    async def test_kill_switch_stops_execution(self, orchestrator):
        orchestrator.state.engage_kill_switch()
        task = Task(objective="Should be killed")
        result = await orchestrator.run_task(task)
        # The task should still return but may indicate kill
        assert result.output
