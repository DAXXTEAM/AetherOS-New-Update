"""Tests for pipeline module."""
import os
import pytest

from core.pipeline import Pipeline, PipelineStep, PipelineBuilder
from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps


@pytest.fixture
def registry(tmp_path):
    reg = ToolRegistry()
    reg.register(FileOps(allowed_dirs=[str(tmp_path), "/tmp"], sandbox=True))
    reg.register(ShellOps(sandbox=True, working_dir=str(tmp_path)))
    return reg


class TestPipeline:
    @pytest.mark.asyncio
    async def test_simple_pipeline(self, registry, tmp_path):
        pipe = Pipeline("test", registry)
        pipe.add("echo", "shell_ops", "run", command="echo hello")
        result = await pipe.execute()
        assert result["succeeded"] >= 1

    @pytest.mark.asyncio
    async def test_multi_step_pipeline(self, registry, tmp_path):
        path = str(tmp_path / "pipe_test.txt")
        pipe = Pipeline("multi", registry)
        pipe.add("write", "file_ops", "write", path=path, content="pipeline data")
        pipe.add("read", "file_ops", "read", path=path)
        result = await pipe.execute()
        assert result["executed"] == 2
        assert result["succeeded"] == 2

    @pytest.mark.asyncio
    async def test_conditional_step(self, registry, tmp_path):
        pipe = Pipeline("conditional", registry)
        pipe.add_step(PipelineStep(
            name="always",
            tool_name="shell_ops",
            action="run",
            args={"command": "echo always"},
        ))
        pipe.add_step(PipelineStep(
            name="never",
            tool_name="shell_ops",
            action="run",
            args={"command": "echo never"},
            condition=lambda ctx: False,
        ))
        result = await pipe.execute()
        assert result["executed"] == 1


class TestPipelineBuilder:
    @pytest.mark.asyncio
    async def test_system_check(self, registry):
        builder = PipelineBuilder(registry)
        pipe = builder.system_check()
        result = await pipe.execute()
        assert result["total_steps"] >= 3
        assert result["succeeded"] >= 1


class TestPolicyEngine:
    def test_default_rules(self):
        from security.policy import PolicyEngine, ResourceType
        engine = PolicyEngine()
        rules = engine.list_rules()
        assert len(rules) > 0

    def test_deny_shadow(self):
        from security.policy import PolicyEngine, ResourceType
        engine = PolicyEngine()
        decision = engine.evaluate_file_access("/etc/shadow")
        assert not decision.is_allowed

    def test_allow_tmp(self):
        from security.policy import PolicyEngine, ResourceType
        engine = PolicyEngine()
        decision = engine.evaluate_file_access("/tmp/test.txt")
        assert decision.is_allowed

    def test_command_evaluation(self):
        from security.policy import PolicyEngine
        engine = PolicyEngine()
        decision = engine.evaluate_command("ls -la")
        assert decision.is_allowed

    def test_dangerous_command(self):
        from security.policy import PolicyEngine
        engine = PolicyEngine()
        decision = engine.evaluate_command("rm -rf *")
        assert not decision.is_allowed


class TestScheduler:
    @pytest.mark.asyncio
    async def test_schedule_once(self):
        from core.scheduler import TaskScheduler
        from core.task import Task
        sched = TaskScheduler()
        sid = sched.schedule_once(lambda: Task(objective="test"), delay_seconds=0)
        tasks = await sched.tick()
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_schedule_interval(self):
        from core.scheduler import TaskScheduler
        from core.task import Task
        sched = TaskScheduler()
        sid = sched.schedule_interval(lambda: Task(objective="recurring"), 
                                       interval_seconds=0.1, max_runs=2)
        tasks1 = await sched.tick()
        assert len(tasks1) == 1
        import asyncio
        await asyncio.sleep(0.2)
        tasks2 = await sched.tick()
        assert len(tasks2) == 1

    def test_cancel(self):
        from core.scheduler import TaskScheduler
        from core.task import Task
        sched = TaskScheduler()
        sid = sched.schedule_once(lambda: Task(objective="cancel me"), delay_seconds=100)
        assert sched.cancel(sid)

    def test_list_scheduled(self):
        from core.scheduler import TaskScheduler
        from core.task import Task
        sched = TaskScheduler()
        sched.schedule_once(lambda: Task(objective="t1"), delay_seconds=100)
        sched.schedule_once(lambda: Task(objective="t2"), delay_seconds=200)
        listed = sched.list_scheduled()
        assert len(listed) == 2


class TestEmbeddings:
    def test_embed(self):
        from memory.embeddings import SimpleEmbedder
        emb = SimpleEmbedder(dimensions=64)
        vec = emb.embed("Hello world")
        assert len(vec) == 64
        assert any(v != 0 for v in vec)

    def test_similarity(self):
        from memory.embeddings import SimpleEmbedder
        emb = SimpleEmbedder(dimensions=128)
        v1 = emb.embed("Python programming language")
        v2 = emb.embed("Python coding language")
        v3 = emb.embed("Banana fruit yellow")
        sim_close = emb.similarity(v1, v2)
        sim_far = emb.similarity(v1, v3)
        assert sim_close > sim_far

    def test_empty_text(self):
        from memory.embeddings import SimpleEmbedder
        emb = SimpleEmbedder()
        vec = emb.embed("")
        assert all(v == 0 for v in vec)

    def test_chunker(self):
        from memory.embeddings import TextChunker
        chunker = TextChunker(chunk_size=50, overlap=10)
        text = "This is a test. " * 20
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 100  # Some slack

    def test_chunker_metadata(self):
        from memory.embeddings import TextChunker
        chunker = TextChunker(chunk_size=30)
        text = "First sentence. Second sentence. Third sentence."
        result = chunker.chunk_with_metadata(text, source="test")
        assert all("index" in r for r in result)
        assert all(r["source"] == "test" for r in result)


class TestSystemOps:
    @pytest.mark.asyncio
    async def test_system_info(self):
        from tools.system_ops import SystemOps
        ops = SystemOps()
        result = await ops.execute(action="info")
        assert result.success
        assert "os" in result.metadata

    @pytest.mark.asyncio
    async def test_resources(self):
        from tools.system_ops import SystemOps
        ops = SystemOps()
        result = await ops.execute(action="resources")
        assert result.success
        assert "disk_total_gb" in result.metadata

    @pytest.mark.asyncio
    async def test_python_info(self):
        from tools.system_ops import SystemOps
        ops = SystemOps()
        result = await ops.execute(action="python")
        assert result.success
        assert "packages" in result.metadata

    @pytest.mark.asyncio
    async def test_env_check(self):
        from tools.system_ops import SystemOps
        ops = SystemOps()
        result = await ops.execute(action="env_check")
        assert result.success
        assert "all_pass" in result.metadata


class TestAgentTeam:
    @pytest.mark.asyncio
    async def test_team_creation(self):
        from agents.team import AgentTeam
        from agents.architect import ArchitectAgent
        from core.event_bus import EventBus
        from core.model_manager import ModelManager
        from core.state import SystemState
        from config.settings import ModelConfig

        bus = EventBus()
        state = SystemState()
        model = ModelManager(ModelConfig())
        team = AgentTeam("test_team", bus)
        arch = ArchitectAgent(model, bus, state)
        team.add_agent(arch)
        assert team.get_agent("architect") is not None
        status = team.get_status()
        assert "architect" in status["agents"]

    @pytest.mark.asyncio
    async def test_team_messaging(self):
        from agents.team import AgentTeam
        from agents.base import AgentMessage
        from agents.architect import ArchitectAgent
        from core.event_bus import EventBus
        from core.model_manager import ModelManager
        from core.state import SystemState
        from config.settings import ModelConfig

        bus = EventBus()
        state = SystemState()
        model = ModelManager(ModelConfig())
        team = AgentTeam("msg_team", bus)
        team.add_agent(ArchitectAgent(model, bus, state))
        
        msg = AgentMessage(sender="user", recipient="architect", content="Test task")
        response = await team.send_message(msg)
        assert response is not None
        metrics = team.get_metrics()
        assert metrics["metrics"]["messages_exchanged"] >= 1
