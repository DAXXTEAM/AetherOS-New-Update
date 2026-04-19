"""Agent team coordination and communication."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus, Event, EventType

logger = logging.getLogger("aetheros.agents.team")


@dataclass
class TeamMetrics:
    """Metrics for team performance."""
    messages_exchanged: int = 0
    tasks_delegated: int = 0
    consensus_rounds: int = 0
    avg_response_time: float = 0.0
    _response_times: list[float] = field(default_factory=list, repr=False)

    def record_response(self, duration: float) -> None:
        self._response_times.append(duration)
        self.avg_response_time = sum(self._response_times) / len(self._response_times)

    def to_dict(self) -> dict:
        return {
            "messages_exchanged": self.messages_exchanged,
            "tasks_delegated": self.tasks_delegated,
            "consensus_rounds": self.consensus_rounds,
            "avg_response_time_ms": round(self.avg_response_time * 1000, 2),
        }


class AgentTeam:
    """Coordinated team of agents with communication protocols."""

    def __init__(self, name: str, event_bus: EventBus):
        self.name = name
        self.event_bus = event_bus
        self._agents: dict[str, BaseAgent] = {}
        self._message_queue: dict[str, list[AgentMessage]] = defaultdict(list)
        self._metrics = TeamMetrics()
        self._conversation_log: list[AgentMessage] = []

    def add_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent
        logger.info(f"Team '{self.name}': Added agent '{agent.name}' ({agent.role})")

    def remove_agent(self, name: str) -> None:
        self._agents.pop(name, None)

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    async def send_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Send a message to an agent and optionally get a response."""
        recipient = self._agents.get(message.recipient)
        if not recipient:
            logger.error(f"Agent '{message.recipient}' not found in team")
            return None

        self._metrics.messages_exchanged += 1
        self._conversation_log.append(message)

        start = datetime.now()
        response = await recipient.process(message)
        duration = (datetime.now() - start).total_seconds()
        self._metrics.record_response(duration)

        if response:
            self._conversation_log.append(response)

        return response

    async def broadcast(self, message: AgentMessage) -> list[AgentMessage]:
        """Broadcast a message to all agents except sender."""
        responses = []
        for name, agent in self._agents.items():
            if name != message.sender:
                msg = AgentMessage(
                    sender=message.sender,
                    recipient=name,
                    content=message.content,
                    message_type=message.message_type,
                    metadata=message.metadata,
                )
                response = await self.send_message(msg)
                if response:
                    responses.append(response)
        return responses

    async def delegate_task(self, task_description: str,
                            from_agent: str, to_agent: str) -> Optional[AgentMessage]:
        """Delegate a task from one agent to another."""
        self._metrics.tasks_delegated += 1
        message = AgentMessage(
            sender=from_agent,
            recipient=to_agent,
            content=task_description,
            message_type="delegation",
            metadata={"delegated": True},
            requires_response=True,
        )
        return await self.send_message(message)

    async def consensus(self, topic: str, agents: Optional[list[str]] = None) -> dict:
        """Gather input from agents to reach consensus."""
        self._metrics.consensus_rounds += 1
        target_agents = agents or list(self._agents.keys())
        responses = {}

        for name in target_agents:
            if name in self._agents:
                msg = AgentMessage(
                    sender="team_coordinator",
                    recipient=name,
                    content=f"Provide your assessment on: {topic}",
                    message_type="consensus_request",
                )
                response = await self.send_message(msg)
                if response:
                    responses[name] = response.content

        return {
            "topic": topic,
            "participants": target_agents,
            "responses": responses,
            "timestamp": datetime.now().isoformat(),
        }

    def get_conversation_log(self, last_n: int = 50) -> list[dict]:
        return [m.to_dict() for m in self._conversation_log[-last_n:]]

    def get_metrics(self) -> dict:
        return {
            "team_name": self.name,
            "agents": list(self._agents.keys()),
            "metrics": self._metrics.to_dict(),
        }

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "agents": {
                name: agent.get_status()
                for name, agent in self._agents.items()
            },
            "metrics": self._metrics.to_dict(),
            "conversation_length": len(self._conversation_log),
        }
