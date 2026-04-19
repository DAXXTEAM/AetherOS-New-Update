"""The Executor Agent - OS-level action execution."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager
from core.state import SystemState
from tools.base import ToolRegistry, ToolResult

logger = logging.getLogger("aetheros.agents.executor")


class ExecutorAgent(BaseAgent):
    """The Executor: OS-level action execution.

    Responsibilities:
    - Execute planned steps using available tools
    - Handle file system operations
    - Run shell commands safely
    - Interact with GUI elements
    - Report execution results
    """

    def __init__(self, model_manager: ModelManager, event_bus: EventBus,
                 system_state: SystemState, tool_registry: Optional[ToolRegistry] = None):
        self.tools = tool_registry or ToolRegistry()
        super().__init__("executor", "execution", model_manager, event_bus, system_state)

    def _build_system_prompt(self) -> str:
        return """You are The Executor, the action execution agent in the AetherOS system.

Your role is to:
1. Execute planned steps using available system tools
2. Handle file operations, shell commands, and web interactions
3. Report results accurately and completely
4. Handle errors gracefully and suggest alternatives
5. Never execute dangerous or unauthorized operations

When executing a step, analyze it and determine:
- Which tool to use
- What arguments to pass
- Whether any safety concerns exist

Output Format (JSON):
{
    "tool": "tool_name",
    "action": "specific_action",
    "args": {},
    "reasoning": "Why this approach",
    "safety_check": "PASS|WARN|FAIL"
}

Always validate before executing. Report results honestly."""

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process an execution request."""
        self._record_message(message)
        await self.activate()

        try:
            # Parse the step to execute
            try:
                step_data = json.loads(message.content)
            except json.JSONDecodeError:
                step_data = {"description": message.content}

            tool_name = step_data.get("tool") or step_data.get("tool_name")
            tool_args = step_data.get("args") or step_data.get("tool_args", {})
            description = step_data.get("description", "")

            # Execute via tool if specified
            if tool_name and self.tools.get_tool(tool_name):
                result = await self.tools.execute_tool(tool_name, **tool_args)
                exec_result = {
                    "status": "completed" if result.success else "failed",
                    "output": result.output[:5000],
                    "error": result.error,
                    "tool": tool_name,
                    "execution_time": result.execution_time,
                }
            else:
                # Use LLM for reasoning/non-tool steps
                response = await self._call_model(
                    f"Execute this step: {description}\n"
                    f"Tool: {tool_name}\nArgs: {json.dumps(tool_args)}\n"
                    f"Determine the best way to accomplish this."
                )
                exec_result = {
                    "status": "completed",
                    "output": response.content[:5000],
                    "tool": tool_name or "reasoning",
                    "execution_time": 0,
                }

            # Emit execution event
            await self.events.publish(Event(
                event_type=EventType.TASK_PROGRESS,
                data={"step": step_data, "result": exec_result},
                source=self.name,
            ))

            result_msg = AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps(exec_result),
                message_type="execution_result",
                metadata={
                    "step": step_data.get("step", 0),
                    "tool": tool_name,
                    "success": exec_result["status"] == "completed",
                },
            )
            self._record_message(result_msg)
            return result_msg

        except Exception as e:
            logger.error(f"Executor failed: {e}")
            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps({"status": "failed", "error": str(e)}),
                message_type="error",
            )
        finally:
            await self.deactivate()

    async def execute_step(self, step: dict) -> dict:
        """Direct step execution interface."""
        msg = AgentMessage(
            sender="orchestrator",
            recipient=self.name,
            content=json.dumps(step),
            message_type="step",
        )
        result = await self.process(msg)
        try:
            return json.loads(result.content)
        except json.JSONDecodeError:
            return {"status": "failed", "error": "Invalid result format"}
