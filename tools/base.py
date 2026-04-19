"""Base tool infrastructure."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("aetheros.tools.base")


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract base class for all AetherOS tools."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"aetheros.tools.{name}")
        self._execution_count = 0
        self._error_count = 0

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        ...

    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON schema describing the tool's parameters."""
        ...

    async def safe_execute(self, **kwargs) -> ToolResult:
        """Execute with error handling and metrics."""
        start = datetime.now()
        self._execution_count += 1
        try:
            result = await self.execute(**kwargs)
            result.execution_time = (datetime.now() - start).total_seconds()
            return result
        except Exception as e:
            self._error_count += 1
            self.logger.error(f"Tool {self.name} execution failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                execution_time=(datetime.now() - start).total_seconds(),
            )

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "executions": self._execution_count,
            "errors": self._error_count,
            "error_rate": self._error_count / max(self._execution_count, 1),
        }


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "stats": t.get_stats()}
            for t in self._tools.values()
        ]

    def get_schemas(self) -> dict[str, dict]:
        return {name: tool.get_schema() for name, tool in self._tools.items()}

    async def execute_tool(self, name: str, **kwargs) -> ToolResult:
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool '{name}' not found")
        return await tool.safe_execute(**kwargs)
