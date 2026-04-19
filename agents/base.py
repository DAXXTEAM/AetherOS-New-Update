"""Base agent class for all AetherOS agents."""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager, LLMMessage, LLMResponse
from core.state import SystemState


@dataclass
class AgentMessage:
    """Message passed between agents."""
    sender: str
    recipient: str
    content: str
    message_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    requires_response: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content[:500],
            "type": self.message_type,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseAgent(ABC):
    """Abstract base class for all AetherOS agents."""

    def __init__(self, name: str, role: str, model_manager: ModelManager,
                 event_bus: EventBus, system_state: SystemState):
        self.name = name
        self.role = role
        self.model = model_manager
        self.events = event_bus
        self.state = system_state
        self.logger = logging.getLogger(f"aetheros.agents.{name}")
        self._message_history: list[AgentMessage] = []
        self._active = False
        self._system_prompt = self._build_system_prompt()

        # Register with system state
        self.state.register_agent(name, role)

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Build the agent's system prompt."""
        ...

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process an incoming message and return a response."""
        ...

    async def activate(self) -> None:
        """Activate the agent."""
        self._active = True
        self.state.update_agent(self.name, status="active", last_active=datetime.now())
        await self.events.publish(Event(
            event_type=EventType.AGENT_ACTIVATED,
            data={"agent": self.name, "role": self.role},
            source=self.name,
        ))
        self.logger.info(f"Agent {self.name} activated")

    async def deactivate(self) -> None:
        """Deactivate the agent."""
        self._active = False
        self.state.update_agent(self.name, status="idle")
        await self.events.publish(Event(
            event_type=EventType.AGENT_DEACTIVATED,
            data={"agent": self.name},
            source=self.name,
        ))

    async def _call_model(self, user_message: str,
                          additional_context: str = "") -> LLMResponse:
        """Call the LLM with the agent's system prompt."""
        messages = [LLMMessage(role="system", content=self._system_prompt)]
        if additional_context:
            messages.append(LLMMessage(role="system", content=additional_context))

        # Add relevant history
        for msg in self._message_history[-5:]:
            role = "assistant" if msg.sender == self.name else "user"
            messages.append(LLMMessage(role=role, content=msg.content))

        messages.append(LLMMessage(role="user", content=user_message))
        response = await self.model.generate(messages)
        self.state.update_agent(
            self.name,
            messages_processed=self.state.agents[self.name].messages_processed + 1,
            last_active=datetime.now(),
        )
        return response

    def _record_message(self, message: AgentMessage) -> None:
        self._message_history.append(message)
        if len(self._message_history) > 100:
            self._message_history = self._message_history[-100:]

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "active": self._active,
            "messages_processed": len(self._message_history),
            "state": self.state.agents.get(self.name, {}).to_dict() if self.name in self.state.agents else {},
        }
