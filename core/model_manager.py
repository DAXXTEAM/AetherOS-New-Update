"""Model Manager - Unified interface for multiple LLM providers."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from config.settings import ModelConfig, ModelProvider

logger = logging.getLogger("aetheros.core.model_manager")


@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # system, user, assistant
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    """Response from an LLM."""
    content: str
    model: str
    provider: str
    usage: dict[str, int] = None
    finish_reason: str = "stop"
    raw: Any = None

    def __post_init__(self):
        if self.usage is None:
            self.usage = {}


class BaseModelAdapter(ABC):
    """Abstract adapter for LLM providers."""

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class OpenAIAdapter(BaseModelAdapter):
    """Adapter for OpenAI GPT models."""

    def is_available(self) -> bool:
        return bool(self.config.api_key)

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        try:
            import openai
            client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
            response = await client.chat.completions.create(
                model=self.config.model_name,
                messages=[m.to_dict() for m in messages],
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            )
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=self.config.model_name,
                provider="openai",
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                raw=response,
            )
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        import openai
        client = openai.AsyncOpenAI(api_key=self.config.api_key)
        stream = await client.chat.completions.create(
            model=self.config.model_name,
            messages=[m.to_dict() for m in messages],
            temperature=kwargs.get("temperature", self.config.temperature),
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class AnthropicAdapter(BaseModelAdapter):
    """Adapter for Anthropic Claude models."""

    def is_available(self) -> bool:
        return bool(self.config.api_key)

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
            system_msg = ""
            filtered = []
            for m in messages:
                if m.role == "system":
                    system_msg = m.content
                else:
                    filtered.append(m.to_dict())

            response = await client.messages.create(
                model=self.config.model_name,
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                system=system_msg,
                messages=filtered,
            )
            return LLMResponse(
                content=response.content[0].text,
                model=self.config.model_name,
                provider="anthropic",
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                },
                finish_reason=response.stop_reason,
                raw=response,
            )
        except Exception as e:
            logger.error(f"Anthropic generation failed: {e}")
            raise

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
        system_msg = ""
        filtered = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                filtered.append(m.to_dict())

        async with client.messages.stream(
            model=self.config.model_name,
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            system=system_msg,
            messages=filtered,
        ) as stream:
            async for text in stream.text_stream:
                yield text


class GoogleAdapter(BaseModelAdapter):
    """Adapter for Google Gemini models."""

    def is_available(self) -> bool:
        return bool(self.config.api_key)

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.config.api_key)
            model = genai.GenerativeModel(self.config.model_name)
            combined = "\n".join(f"{m.role}: {m.content}" for m in messages)
            response = await model.generate_content_async(combined)
            return LLMResponse(
                content=response.text,
                model=self.config.model_name,
                provider="google",
                usage={},
                raw=response,
            )
        except Exception as e:
            logger.error(f"Google generation failed: {e}")
            raise

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        import google.generativeai as genai
        genai.configure(api_key=self.config.api_key)
        model = genai.GenerativeModel(self.config.model_name)
        combined = "\n".join(f"{m.role}: {m.content}" for m in messages)
        response = await model.generate_content_async(combined, stream=True)
        async for chunk in response:
            yield chunk.text


class OllamaAdapter(BaseModelAdapter):
    """Adapter for local Ollama models."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:11434"

    def is_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.config.model_name,
                "messages": [m.to_dict() for m in messages],
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
            }
            async with session.post(
                f"{self.base_url}/api/chat", json=payload
            ) as resp:
                data = await resp.json()
                return LLMResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=self.config.model_name,
                    provider="ollama",
                    usage={
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                    },
                    raw=data,
                )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.config.model_name,
                "messages": [m.to_dict() for m in messages],
                "stream": True,
            }
            async with session.post(
                f"{self.base_url}/api/chat", json=payload
            ) as resp:
                async for line in resp.content:
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content


class SimulatedAdapter(BaseModelAdapter):
    """Simulated adapter for testing without real API keys."""

    def is_available(self) -> bool:
        return True

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user = m.content
                break

        # Intelligent simulation based on context
        if "plan" in last_user.lower() or "decompose" in last_user.lower():
            content = json.dumps({
                "plan": [
                    {"step": 1, "action": "Analyze the request", "tool": None},
                    {"step": 2, "action": "Execute primary operation", "tool": "shell_ops"},
                    {"step": 3, "action": "Verify results", "tool": "file_ops"},
                ],
                "reasoning": "Task decomposed into analysis, execution, and verification phases.",
            })
        elif "audit" in last_user.lower() or "security" in last_user.lower():
            content = json.dumps({
                "audit_result": "PASS",
                "risk_level": "LOW",
                "findings": [],
                "recommendation": "Operation is safe to proceed.",
            })
        elif "execute" in last_user.lower():
            content = json.dumps({
                "status": "completed",
                "output": "Operation executed successfully in simulation mode.",
                "artifacts": [],
            })
        else:
            content = (
                f"[Simulated Response] Processed request regarding: "
                f"{last_user[:100]}... "
                f"In production, this would use the configured LLM provider."
            )

        return LLMResponse(
            content=content,
            model="simulated",
            provider="simulated",
            usage={"prompt_tokens": len(last_user) // 4, "completion_tokens": len(content) // 4},
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        response = await self.generate(messages, **kwargs)
        for word in response.content.split():
            yield word + " "


class ModelManager:
    """Manages model selection and switching between providers."""

    ADAPTER_MAP = {
        ModelProvider.OPENAI: OpenAIAdapter,
        ModelProvider.ANTHROPIC: AnthropicAdapter,
        ModelProvider.GOOGLE: GoogleAdapter,
        ModelProvider.OLLAMA: OllamaAdapter,
    }

    def __init__(self, config: ModelConfig):
        self.config = config
        self._adapter: Optional[BaseModelAdapter] = None
        self._fallback = SimulatedAdapter(config)
        self._initialize()

    def _initialize(self) -> None:
        adapter_cls = self.ADAPTER_MAP.get(self.config.provider)
        if adapter_cls:
            adapter = adapter_cls(self.config)
            if adapter.is_available():
                self._adapter = adapter
                logger.info(f"Initialized {self.config.provider.value} adapter: {self.config.model_name}")
            else:
                logger.warning(
                    f"{self.config.provider.value} adapter not available, using simulated mode"
                )
                self._adapter = self._fallback
        else:
            self._adapter = self._fallback

    @property
    def active_adapter(self) -> BaseModelAdapter:
        return self._adapter or self._fallback

    @property
    def is_simulated(self) -> bool:
        return isinstance(self._adapter, SimulatedAdapter)

    def switch_provider(self, provider: ModelProvider, model_name: Optional[str] = None,
                        api_key: Optional[str] = None) -> bool:
        new_config = ModelConfig(
            provider=provider,
            model_name=model_name,
            api_key=api_key or self.config.api_key,
            base_url=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        adapter_cls = self.ADAPTER_MAP.get(provider)
        if adapter_cls:
            adapter = adapter_cls(new_config)
            if adapter.is_available():
                self._adapter = adapter
                self.config = new_config
                logger.info(f"Switched to {provider.value}: {new_config.model_name}")
                return True
        logger.warning(f"Cannot switch to {provider.value}")
        return False

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        return await self.active_adapter.generate(messages, **kwargs)

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        async for chunk in self.active_adapter.stream(messages, **kwargs):
            yield chunk

    def get_status(self) -> dict:
        return {
            "provider": self.config.provider.value,
            "model": self.config.model_name,
            "simulated": self.is_simulated,
            "available": self.active_adapter.is_available(),
        }
