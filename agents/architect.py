"""The Architect Agent - Planning and task decomposition."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus
from core.model_manager import ModelManager
from core.state import SystemState

logger = logging.getLogger("aetheros.agents.architect")


class ArchitectAgent(BaseAgent):
    """The Architect: Strategic planning and task decomposition.

    Responsibilities:
    - Analyze user objectives
    - Decompose complex tasks into executable steps
    - Select appropriate tools for each step
    - Handle dependencies between steps
    - Adapt plans based on execution feedback
    """

    def __init__(self, model_manager: ModelManager, event_bus: EventBus,
                 system_state: SystemState, available_tools: Optional[list[str]] = None):
        self.available_tools = available_tools or ["file_ops", "shell_ops", "vision_ops", "web_ops"]
        super().__init__("architect", "planning", model_manager, event_bus, system_state)

    def _build_system_prompt(self) -> str:
        tools_desc = ", ".join(getattr(self, 'available_tools', []))
        return f"""You are The Architect, the strategic planning agent in the AetherOS system.

Your role is to:
1. Analyze user objectives and understand their intent
2. Decompose complex tasks into concrete, executable steps
3. Select the right tool for each step from available tools: {tools_desc}
4. Consider dependencies and ordering between steps
5. Identify potential risks and mitigation strategies

Available Tools:
- file_ops: File/folder operations (read, write, copy, move, search, etc.)
- shell_ops: Terminal command execution (with security validation)
- vision_ops: Screen capture and image analysis
- web_ops: Web search and content scraping

Output Format (JSON):
{{
    "analysis": "Brief analysis of the objective",
    "plan": [
        {{
            "step": 1,
            "description": "What this step does",
            "tool": "tool_name or null for reasoning",
            "args": {{}},
            "depends_on": [],
            "risk_level": "LOW|MEDIUM|HIGH",
            "requires_approval": false
        }}
    ],
    "estimated_steps": N,
    "risk_assessment": "Overall risk assessment",
    "alternative_approaches": ["Alternative if primary fails"]
}}

Always respond with valid JSON. Be thorough but efficient."""

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process a planning request and return a plan."""
        self._record_message(message)
        await self.activate()

        try:
            response = await self._call_model(
                f"Create an execution plan for: {message.content}",
                additional_context=f"Message metadata: {json.dumps(message.metadata)}",
            )

            # Validate JSON response
            try:
                plan = json.loads(response.content)
            except json.JSONDecodeError:
                plan = {
                    "analysis": "Task received for planning",
                    "plan": [
                        {"step": 1, "description": "Analyze the request", "tool": None, "args": {}},
                        {"step": 2, "description": message.content, "tool": "shell_ops", "args": {}},
                        {"step": 3, "description": "Verify results", "tool": "file_ops", "args": {}},
                    ],
                    "estimated_steps": 3,
                    "risk_assessment": "LOW",
                }

            result = AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps(plan, indent=2),
                message_type="plan",
                metadata={"original_task": message.content, "steps": len(plan.get("plan", []))},
            )
            self._record_message(result)
            return result

        except Exception as e:
            logger.error(f"Architect planning failed: {e}")
            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps({"error": str(e), "plan": []}),
                message_type="error",
            )
        finally:
            await self.deactivate()

    async def revise_plan(self, original_plan: dict, feedback: str) -> dict:
        """Revise a plan based on execution feedback."""
        response = await self._call_model(
            f"Revise this plan based on feedback:\n"
            f"Original plan: {json.dumps(original_plan)}\n"
            f"Feedback: {feedback}\n"
            f"Return updated plan in the same JSON format."
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return original_plan
