"""AetherOS Automation Module — Workflow automation, scheduling, macros."""
from automation.workflows import WorkflowEngine, Workflow, WorkflowStep, StepType
from automation.macros import MacroEngine, Macro, MacroAction, MacroTrigger
from automation.scheduler import TaskScheduler, ScheduledTask, CronParser

__all__ = [
    "WorkflowEngine", "Workflow", "WorkflowStep", "StepType",
    "MacroEngine", "Macro", "MacroAction", "MacroTrigger",
    "TaskScheduler", "ScheduledTask", "CronParser",
]
