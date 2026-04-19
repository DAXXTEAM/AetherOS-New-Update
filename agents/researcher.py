"""Researcher Agent   Information gathering and analysis."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus
from core.model_manager import ModelManager
from core.state import SystemState

logger = logging.getLogger("aetheros.agents.researcher")


class ResearcherAgent(BaseAgent):
    """The Researcher: Information gathering, web research, and data analysis.

    Responsibilities:
    - Gather information from web sources
    - Analyze and summarize data
    - Cross-reference findings
    - Generate research reports
    - Maintain knowledge base
    """

    def __init__(self, model_manager: ModelManager, event_bus: EventBus,
                 system_state: SystemState):
        super().__init__("researcher", "research", model_manager, event_bus, system_state)
        self._research_cache: dict[str, dict] = {}

    def _build_system_prompt(self) -> str:
        return """You are The Researcher, an information gathering and analysis agent in AetherOS.

Your role is to:
1. Search for relevant information from available sources
2. Analyze and cross-reference data
3. Summarize findings clearly and accurately
4. Identify patterns and insights
5. Maintain a knowledge cache for repeated queries

Output Format (JSON):
{
    "findings": [
        {"source": "source_name", "content": "finding", "confidence": 0.0-1.0}
    ],
    "summary": "Brief summary of research",
    "insights": ["Key insight 1", "Key insight 2"],
    "needs_further_research": false,
    "suggested_queries": []
}"""

    async def process(self, message: AgentMessage) -> AgentMessage:
        self._record_message(message)
        await self.activate()
        try:
            cache_key = message.content[:100]
            if cache_key in self._research_cache:
                result = self._research_cache[cache_key]
            else:
                response = await self._call_model(
                    f"Research the following topic: {message.content}"
                )
                try:
                    result = json.loads(response.content)
                except json.JSONDecodeError:
                    result = {
                        "findings": [{"source": "llm", "content": response.content, "confidence": 0.7}],
                        "summary": response.content[:200],
                        "insights": [],
                    }
                self._research_cache[cache_key] = result

            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps(result, indent=2),
                message_type="research_result",
                metadata={"cached": cache_key in self._research_cache},
            )
        except Exception as e:
            logger.error(f"Researcher failed: {e}")
            return AgentMessage(
                sender=self.name, recipient=message.sender,
                content=json.dumps({"error": str(e)}), message_type="error",
            )
        finally:
            await self.deactivate()
