"""Context management for agent conversations."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("aetheros.memory.context")


@dataclass
class ContextMessage:
    """A message in the context window."""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = len(self.content) // 4


@dataclass
class ConversationContext:
    """A conversation context window."""
    context_id: str = ""
    messages: list[ContextMessage] = field(default_factory=list)
    max_tokens: int = 8000
    system_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        base = len(self.system_prompt) // 4
        return base + sum(m.token_estimate for m in self.messages)

    def add_message(self, role: str, content: str, **kwargs) -> None:
        msg = ContextMessage(role=role, content=content, **kwargs)
        self.messages.append(msg)
        self._trim_to_limit()

    def _trim_to_limit(self) -> None:
        while self.total_tokens > self.max_tokens and len(self.messages) > 2:
            removed = self.messages.pop(0)
            logger.debug(f"Trimmed context message: {removed.content[:50]}...")

    def to_messages(self) -> list[dict]:
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        for m in self.messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    def clear(self) -> None:
        self.messages.clear()

    def get_summary(self) -> str:
        return (
            f"Context '{self.context_id}': {len(self.messages)} messages, "
            f"~{self.total_tokens} tokens"
        )


class ContextManager:
    """Manages multiple conversation contexts."""

    def __init__(self, max_contexts: int = 20, default_max_tokens: int = 8000):
        self._contexts: dict[str, ConversationContext] = {}
        self._max_contexts = max_contexts
        self._default_max_tokens = default_max_tokens
        self._active_context: Optional[str] = None

    def create_context(self, context_id: str, system_prompt: str = "",
                       max_tokens: Optional[int] = None) -> ConversationContext:
        if len(self._contexts) >= self._max_contexts:
            oldest = min(self._contexts.keys(), key=lambda k: len(self._contexts[k].messages))
            del self._contexts[oldest]
            logger.debug(f"Evicted context: {oldest}")

        ctx = ConversationContext(
            context_id=context_id,
            system_prompt=system_prompt,
            max_tokens=max_tokens or self._default_max_tokens,
        )
        self._contexts[context_id] = ctx
        self._active_context = context_id
        return ctx

    def get_context(self, context_id: str) -> Optional[ConversationContext]:
        return self._contexts.get(context_id)

    def get_or_create(self, context_id: str, **kwargs) -> ConversationContext:
        ctx = self.get_context(context_id)
        if ctx is None:
            ctx = self.create_context(context_id, **kwargs)
        self._active_context = context_id
        return ctx

    @property
    def active(self) -> Optional[ConversationContext]:
        if self._active_context:
            return self._contexts.get(self._active_context)
        return None

    def delete_context(self, context_id: str) -> bool:
        if context_id in self._contexts:
            del self._contexts[context_id]
            if self._active_context == context_id:
                self._active_context = None
            return True
        return False

    def list_contexts(self) -> list[dict]:
        return [
            {
                "id": cid,
                "messages": len(ctx.messages),
                "tokens": ctx.total_tokens,
                "active": cid == self._active_context,
            }
            for cid, ctx in self._contexts.items()
        ]

    def get_stats(self) -> dict:
        return {
            "total_contexts": len(self._contexts),
            "active": self._active_context,
            "total_messages": sum(len(c.messages) for c in self._contexts.values()),
        }
