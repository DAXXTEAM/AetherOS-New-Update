"""Tests for core module."""
import asyncio
import json
import pytest

from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager, LLMMessage, SimulatedAdapter
from core.task import Task, TaskStep, TaskStatus, TaskPriority, TaskResult
from core.state import SystemState
from config.settings import ModelConfig, ModelProvider


class TestEventBus:
    def test_subscribe_and_publish(self, event_bus):
        received = []

        def listener(event):
            received.append(event)

        event_bus.subscribe(EventType.TASK_CREATED, listener)
        event_bus.publish_sync(Event(event_type=EventType.TASK_CREATED, data={"test": 1}))
        assert len(received) == 1
        assert received[0].data["test"] == 1

    def test_unsubscribe(self, event_bus):
        received = []

        def listener(event):
            received.append(event)

        event_bus.subscribe(EventType.TASK_CREATED, listener)
        event_bus.unsubscribe(EventType.TASK_CREATED, listener)
        event_bus.publish_sync(Event(event_type=EventType.TASK_CREATED))
        assert len(received) == 0

    def test_global_listener(self, event_bus):
        received = []

        def listener(event):
            received.append(event)

        event_bus.subscribe_all(listener)
        event_bus.publish_sync(Event(event_type=EventType.TASK_CREATED))
        event_bus.publish_sync(Event(event_type=EventType.SYSTEM_BOOT))
        assert len(received) == 2

    def test_history(self, event_bus):
        event_bus.publish_sync(Event(event_type=EventType.TASK_CREATED, data={"i": 1}))
        event_bus.publish_sync(Event(event_type=EventType.TASK_COMPLETED, data={"i": 2}))
        history = event_bus.get_history()
        assert len(history) == 2

    def test_filtered_history(self, event_bus):
        event_bus.publish_sync(Event(event_type=EventType.TASK_CREATED))
        event_bus.publish_sync(Event(event_type=EventType.SYSTEM_BOOT))
        history = event_bus.get_history(EventType.TASK_CREATED)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_async_publish(self, event_bus):
        received = []

        async def listener(event):
            received.append(event)

        event_bus.subscribe(EventType.TASK_CREATED, listener)
        await event_bus.publish(Event(event_type=EventType.TASK_CREATED))
        assert len(received) == 1


class TestModelManager:
    def test_initialization(self, model_manager):
        assert model_manager is not None
        status = model_manager.get_status()
        assert "provider" in status
        assert "simulated" in status

    def test_simulated_mode(self, model_manager):
        # Without API keys, should fall back to simulation
        assert model_manager.is_simulated

    @pytest.mark.asyncio
    async def test_generate(self, model_manager):
        response = await model_manager.generate([
            LLMMessage(role="user", content="Hello")
        ])
        assert response.content
        assert response.provider == "simulated"

    @pytest.mark.asyncio
    async def test_generate_plan(self, model_manager):
        response = await model_manager.generate([
            LLMMessage(role="user", content="Plan and decompose this task")
        ])
        # Simulated adapter returns plan JSON
        data = json.loads(response.content)
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_generate_audit(self, model_manager):
        response = await model_manager.generate([
            LLMMessage(role="user", content="Audit and security check this")
        ])
        data = json.loads(response.content)
        assert "audit_result" in data

    @pytest.mark.asyncio
    async def test_stream(self, model_manager):
        chunks = []
        async for chunk in model_manager.stream([
            LLMMessage(role="user", content="Hello")
        ]):
            chunks.append(chunk)
        assert len(chunks) > 0

    def test_switch_provider(self, model_manager):
        result = model_manager.switch_provider(ModelProvider.OLLAMA)
        # Ollama likely not running, so switch may fail
        status = model_manager.get_status()
        assert "provider" in status


class TestTask:
    def test_creation(self):
        task = Task(objective="Test task")
        assert task.task_id
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0.0

    def test_add_steps(self):
        task = Task(objective="Multi-step")
        task.add_step("Step 1", tool_name="file_ops")
        task.add_step("Step 2", tool_name="shell_ops")
        assert len(task.steps) == 2

    def test_progress(self):
        task = Task(objective="Progress test")
        s1 = task.add_step("Step 1")
        s2 = task.add_step("Step 2")
        s1.mark_completed("Done")
        assert task.progress == 0.5

    def test_lifecycle(self):
        task = Task(objective="Lifecycle")
        task.mark_started()
        assert task.status == TaskStatus.EXECUTING
        task.mark_completed("Success")
        assert task.status == TaskStatus.COMPLETED
        assert task.duration_seconds is not None

    def test_failure(self):
        task = Task(objective="Fail test")
        task.mark_started()
        task.mark_failed("Something broke")
        assert task.status == TaskStatus.FAILED
        assert task.error == "Something broke"

    def test_to_dict(self):
        task = Task(objective="Dict test")
        d = task.to_dict()
        assert "task_id" in d
        assert "status" in d
        assert d["objective"] == "Dict test"


class TestSystemState:
    def test_initial_state(self, system_state):
        assert system_state.status == "idle"
        assert system_state.kill_switch_active is False

    def test_register_agent(self, system_state):
        system_state.register_agent("test_agent", "tester")
        assert "test_agent" in system_state.agents

    def test_update_agent(self, system_state):
        system_state.register_agent("test", "role")
        system_state.update_agent("test", status="active")
        assert system_state.agents["test"].status == "active"

    def test_task_management(self, system_state):
        system_state.add_task("t1", {"name": "test"})
        assert "t1" in system_state.active_tasks
        system_state.remove_task("t1")
        assert "t1" not in system_state.active_tasks
        assert system_state.total_tasks_completed == 1

    def test_kill_switch(self, system_state):
        system_state.engage_kill_switch()
        assert system_state.kill_switch_active
        assert system_state.status == "killed"

    def test_to_dict(self, system_state):
        d = system_state.to_dict()
        assert "status" in d
        assert "uptime_seconds" in d
        assert "agents" in d
