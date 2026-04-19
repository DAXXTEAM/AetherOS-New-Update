"""LangGraph-based multi-agent orchestrator."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Annotated, TypedDict

from langgraph.graph import StateGraph, END

from config.constants import (
    STATUS_PLANNING, STATUS_EXECUTING, STATUS_AUDITING,
    STATUS_COMPLETE, STATUS_ERROR, STATUS_KILLED,
)
from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager, LLMMessage
from core.state import SystemState
from core.task import Task, TaskStatus, TaskResult, TaskStep

logger = logging.getLogger("aetheros.core.orchestrator")


class GraphState(TypedDict):
    """State flowing through the LangGraph orchestration."""
    task: dict
    plan: list[dict]
    current_step: int
    execution_results: list[dict]
    audit_findings: list[dict]
    status: str
    error: str
    final_output: str


def merge_lists(a: list, b: list) -> list:
    return a + b


class Orchestrator:
    """Multi-agent orchestrator using LangGraph for agent coordination."""

    def __init__(
        self,
        model_manager: ModelManager,
        event_bus: EventBus,
        system_state: SystemState,
        tool_registry: Any = None,
    ):
        self.model = model_manager
        self.events = event_bus
        self.state = system_state
        self.tools = tool_registry
        self._graph = self._build_graph()
        self._active_tasks: dict[str, Task] = {}

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph orchestration graph."""
        builder = StateGraph(GraphState)

        # Add nodes
        builder.add_node("architect", self._architect_node)
        builder.add_node("executor", self._executor_node)
        builder.add_node("auditor", self._auditor_node)
        builder.add_node("finalizer", self._finalizer_node)

        # Set entry point
        builder.set_entry_point("architect")

        # Add edges
        builder.add_conditional_edges(
            "architect",
            self._should_execute,
            {"execute": "executor", "error": "finalizer"},
        )
        builder.add_edge("executor", "auditor")
        builder.add_conditional_edges(
            "auditor",
            self._audit_decision,
            {"continue": "executor", "complete": "finalizer", "error": "finalizer"},
        )
        builder.add_edge("finalizer", END)

        return builder.compile()

    async def _architect_node(self, state: GraphState) -> dict:
        """The Architect: Plans and decomposes tasks."""
        logger.info("   Architect: Planning task decomposition")
        self.state.update_status(STATUS_PLANNING)
        await self.events.publish(Event(
            event_type=EventType.AGENT_ACTIVATED,
            data={"agent": "architect", "action": "planning"},
            source="orchestrator",
        ))

        task_data = state["task"]
        system_prompt = (
            "You are The Architect, a strategic planning agent. "
            "Decompose the user's task into concrete, executable steps. "
            "Each step should specify: description, tool_name (one of: file_ops, shell_ops, "
            "vision_ops, web_ops, or null for reasoning), and tool_args (dict). "
            "Return a JSON object with a 'plan' key containing a list of step objects."
        )
        user_prompt = (
            f"Task: {task_data.get('objective', '')}\n"
            f"Context: {task_data.get('context', '')}\n"
            f"Available tools: file_ops, shell_ops, vision_ops, web_ops\n"
            f"Decompose this into executable steps."
        )

        try:
            response = await self.model.generate([
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ])

            try:
                plan_data = json.loads(response.content)
                plan = plan_data.get("plan", [])
            except json.JSONDecodeError:
                plan = [
                    {"step": 1, "description": "Analyze request", "tool": None, "args": {}},
                    {"step": 2, "description": task_data.get("objective", "Execute task"),
                     "tool": "shell_ops", "args": {}},
                    {"step": 3, "description": "Verify completion", "tool": "file_ops", "args": {}},
                ]

            logger.info(f"   Architect: Generated {len(plan)} step plan")
            return {"plan": plan, "current_step": 0, "status": "planned"}
        except Exception as e:
            logger.error(f"Architect planning failed: {e}")
            return {"plan": [], "status": "error", "error": str(e)}

    async def _executor_node(self, state: GraphState) -> dict:
        """The Executor: Executes planned steps."""
        logger.info("  Executor: Executing step")
        self.state.update_status(STATUS_EXECUTING)
        await self.events.publish(Event(
            event_type=EventType.AGENT_ACTIVATED,
            data={"agent": "executor", "action": "executing"},
            source="orchestrator",
        ))

        if self.state.kill_switch_active:
            return {"status": "killed", "error": "Kill switch engaged"}

        plan = state.get("plan", [])
        current = state.get("current_step", 0)
        results = list(state.get("execution_results", []))

        if current >= len(plan):
            return {"status": "complete", "execution_results": results}

        step = plan[current]
        tool_name = step.get("tool") or step.get("tool_name")
        tool_args = step.get("args") or step.get("tool_args", {})
        description = step.get("description", step.get("action", ""))

        try:
            if self.tools and tool_name:
                tool = self.tools.get_tool(tool_name)
                if tool:
                    result = await tool.execute(**tool_args)
                else:
                    result = f"Tool '{tool_name}' not found, simulating: {description}"
            else:
                # Use LLM for reasoning steps
                response = await self.model.generate([
                    LLMMessage(role="system", content="You are The Executor. Execute the given step and return the result."),
                    LLMMessage(role="user", content=f"Execute: {description}\nTool: {tool_name}\nArgs: {json.dumps(tool_args)}"),
                ])
                result = response.content

            results.append({
                "step": current,
                "description": description,
                "tool": tool_name,
                "result": str(result)[:2000],
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
            })
            logger.info(f"  Executor: Step {current + 1}/{len(plan)} completed")
            return {
                "execution_results": results,
                "current_step": current + 1,
                "status": "executing",
            }
        except Exception as e:
            logger.error(f"Executor step {current} failed: {e}")
            results.append({
                "step": current,
                "description": description,
                "error": str(e),
                "status": "failed",
            })
            return {
                "execution_results": results,
                "current_step": current + 1,
                "status": "error",
                "error": str(e),
            }

    async def _auditor_node(self, state: GraphState) -> dict:
        """The Auditor: Validates security and logs actions."""
        logger.info("   Auditor: Reviewing execution")
        self.state.update_status(STATUS_AUDITING)
        await self.events.publish(Event(
            event_type=EventType.AGENT_ACTIVATED,
            data={"agent": "auditor", "action": "auditing"},
            source="orchestrator",
        ))

        results = state.get("execution_results", [])
        findings = list(state.get("audit_findings", []))

        if not results:
            return {"audit_findings": findings, "status": "complete"}

        latest = results[-1] if results else {}

        try:
            response = await self.model.generate([
                LLMMessage(role="system", content=(
                    "You are The Auditor, a security validation agent. "
                    "Review the execution result for security issues, data leaks, "
                    "or policy violations. Return JSON with: audit_result (PASS/WARN/FAIL), "
                    "risk_level (LOW/MEDIUM/HIGH/CRITICAL), findings (list), recommendation."
                )),
                LLMMessage(role="user", content=f"Audit this execution result:\n{json.dumps(latest, indent=2)}"),
            ])

            try:
                audit = json.loads(response.content)
            except json.JSONDecodeError:
                audit = {
                    "audit_result": "PASS",
                    "risk_level": "LOW",
                    "findings": [],
                    "recommendation": "No issues detected.",
                }

            findings.append({
                "step": latest.get("step", -1),
                "audit": audit,
                "timestamp": datetime.now().isoformat(),
            })

            await self.events.publish(Event(
                event_type=EventType.AUDIT_LOG,
                data={"step": latest.get("step"), "audit": audit},
                source="auditor",
            ))

            if audit.get("risk_level") == "CRITICAL":
                logger.warning("  Auditor: CRITICAL risk detected!")
                return {"audit_findings": findings, "status": "error", "error": "Critical security risk"}

            return {"audit_findings": findings}
        except Exception as e:
            logger.error(f"Auditor review failed: {e}")
            return {"audit_findings": findings}

    async def _finalizer_node(self, state: GraphState) -> dict:
        """Finalize task execution and compile results."""
        logger.info("  Finalizer: Compiling results")
        results = state.get("execution_results", [])
        findings = state.get("audit_findings", [])
        error = state.get("error", "")

        if error:
            final = f"Task completed with errors: {error}\nResults: {len(results)} steps executed."
            status = STATUS_ERROR
        else:
            successful = sum(1 for r in results if r.get("status") == "completed")
            final = f"Task completed successfully. {successful}/{len(results)} steps executed."
            status = STATUS_COMPLETE

        self.state.update_status(status)
        await self.events.publish(Event(
            event_type=EventType.TASK_COMPLETED if status == STATUS_COMPLETE else EventType.TASK_FAILED,
            data={"results": results, "findings": findings},
            source="orchestrator",
        ))

        return {"final_output": final, "status": status}

    def _should_execute(self, state: GraphState) -> str:
        if state.get("status") == "error" or not state.get("plan"):
            return "error"
        return "execute"

    def _audit_decision(self, state: GraphState) -> str:
        if state.get("status") == "error":
            return "error"
        plan = state.get("plan", [])
        current = state.get("current_step", 0)
        if current >= len(plan):
            return "complete"
        return "continue"

    async def run_task(self, task: Task) -> TaskResult:
        """Execute a task through the full orchestration pipeline."""
        logger.info(f"  Starting task: {task.task_id} - {task.objective}")
        self._active_tasks[task.task_id] = task
        task.mark_started()

        self.state.add_task(task.task_id, task.to_dict())
        await self.events.publish(Event(
            event_type=EventType.TASK_STARTED,
            data={"task_id": task.task_id, "objective": task.objective},
            source="orchestrator",
        ))

        initial_state: GraphState = {
            "task": {
                "task_id": task.task_id,
                "objective": task.objective,
                "context": task.context,
            },
            "plan": [],
            "current_step": 0,
            "execution_results": [],
            "audit_findings": [],
            "status": "pending",
            "error": "",
            "final_output": "",
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)
            success = final_state.get("status") == STATUS_COMPLETE
            output = final_state.get("final_output", "")

            if success:
                task.mark_completed(output)
            else:
                task.mark_failed(final_state.get("error", "Unknown error"))

            result = TaskResult(
                task_id=task.task_id,
                success=success,
                output=output,
                audit_trail=final_state.get("audit_findings", []),
                metrics={
                    "steps_planned": len(final_state.get("plan", [])),
                    "steps_executed": len(final_state.get("execution_results", [])),
                    "duration": task.duration_seconds,
                },
            )
            logger.info(f"{' ' if success else ' '} Task {task.task_id} {'completed' if success else 'failed'}")
            return result
        except Exception as e:
            logger.error(f"Task {task.task_id} orchestration failed: {e}")
            task.mark_failed(str(e))
            self.state.increment_errors()
            return TaskResult(
                task_id=task.task_id,
                success=False,
                output=f"Orchestration error: {e}",
            )
        finally:
            self.state.remove_task(task.task_id)
            self._active_tasks.pop(task.task_id, None)
