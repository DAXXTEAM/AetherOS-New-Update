"""Tests for AetherOS Automation Module."""
import pytest
from automation.workflows import WorkflowEngine, Workflow, WorkflowStep, StepType, WorkflowStatus
from automation.macros import MacroEngine, Macro, MacroAction, MacroTrigger
from automation.scheduler import TaskScheduler, ScheduledTask, CronParser


class TestCronParser:
    def test_parse_all_stars(self):
        parsed = CronParser.parse("* * * * *")
        assert len(parsed["minute"]) == 60
        assert len(parsed["hour"]) == 24

    def test_parse_specific(self):
        parsed = CronParser.parse("30 9 * * 1-5")
        assert parsed["minute"] == [30]
        assert parsed["hour"] == [9]
        assert parsed["weekday"] == [1, 2, 3, 4, 5]

    def test_parse_step(self):
        parsed = CronParser.parse("*/15 * * * *")
        assert 0 in parsed["minute"]
        assert 15 in parsed["minute"]
        assert 30 in parsed["minute"]
        assert 45 in parsed["minute"]


class TestWorkflow:
    def test_create_workflow(self):
        wf = Workflow(name="test_wf")
        wf.add_step(WorkflowStep(name="step1"))
        wf.add_step(WorkflowStep(name="step2"))
        assert len(wf.steps) == 2
        assert wf.progress == 0.0

    def test_execute_workflow(self):
        engine = WorkflowEngine()
        wf = Workflow(name="test")
        wf.add_step(WorkflowStep(name="s1", handler=lambda ctx, p: True))
        wf.add_step(WorkflowStep(name="s2", handler=lambda ctx, p: "done"))
        wf_id = engine.register(wf)
        result = engine.execute(wf_id)
        assert result
        assert wf.status == WorkflowStatus.COMPLETED


class TestMacroEngine:
    def test_record_and_list(self):
        me = MacroEngine()
        me.start_recording("test_macro")
        me.record_action("click", {"x": 100, "y": 200})
        me.record_action("type", {"text": "hello"})
        macro_id = me.stop_recording()
        assert macro_id
        macros = me.list_macros()
        assert len(macros) == 1
        assert macros[0]["actions_count"] == 2


class TestScheduledTask:
    def test_create(self):
        task = ScheduledTask(name="daily_scan", cron_expression="0 9 * * *")
        assert task.is_enabled
        assert task.run_count == 0
