"""Pipeline utilities for chaining tool operations."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from core.task import TaskStep, TaskStatus
from tools.base import ToolRegistry, ToolResult

logger = logging.getLogger("aetheros.core.pipeline")


@dataclass
class PipelineStep:
    """A step in a processing pipeline."""
    name: str
    tool_name: str
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    condition: Optional[Callable[[dict], bool]] = None
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    timeout: int = 60
    retries: int = 0
    result: Optional[ToolResult] = None

    def should_run(self, context: dict) -> bool:
        if self.condition:
            return self.condition(context)
        return True


class Pipeline:
    """Composable tool execution pipeline."""

    def __init__(self, name: str, tool_registry: ToolRegistry):
        self.name = name
        self.tools = tool_registry
        self._steps: list[PipelineStep] = []
        self._context: dict[str, Any] = {}
        self._results: list[dict] = []

    def add_step(self, step: PipelineStep) -> "Pipeline":
        self._steps.append(step)
        return self

    def add(self, name: str, tool_name: str, action: str, **kwargs) -> "Pipeline":
        self._steps.append(PipelineStep(
            name=name, tool_name=tool_name, action=action, args=kwargs
        ))
        return self

    async def execute(self, initial_context: Optional[dict] = None) -> dict:
        self._context = initial_context or {}
        self._results.clear()
        start = datetime.now()

        logger.info(f"Pipeline '{self.name}' starting with {len(self._steps)} steps")

        for i, step in enumerate(self._steps):
            if not step.should_run(self._context):
                logger.info(f"  Step '{step.name}' skipped (condition not met)")
                continue

            logger.info(f"  [{i+1}/{len(self._steps)}] Executing '{step.name}'")
            merged_args = {**step.args, "action": step.action}
            merged_args.update(self._context.get("override_args", {}))

            result = None
            for attempt in range(step.retries + 1):
                try:
                    result = await self.tools.execute_tool(step.tool_name, **merged_args)
                    if result.success:
                        break
                    if attempt < step.retries:
                        logger.warning(f"  Step '{step.name}' failed, retrying ({attempt+1}/{step.retries})")
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"  Step '{step.name}' error: {e}")
                    result = ToolResult(success=False, error=str(e))

            step.result = result
            self._results.append({
                "step": step.name,
                "success": result.success if result else False,
                "output": result.output[:1000] if result else "",
                "error": result.error if result else "No result",
            })

            self._context[f"step_{step.name}_result"] = result
            self._context[f"step_{step.name}_output"] = result.output if result else ""

            if result and not result.success:
                if step.on_failure == "abort":
                    logger.warning(f"  Pipeline '{self.name}' aborted at step '{step.name}'")
                    break

        duration = (datetime.now() - start).total_seconds()
        success_count = sum(1 for r in self._results if r["success"])

        return {
            "pipeline": self.name,
            "total_steps": len(self._steps),
            "executed": len(self._results),
            "succeeded": success_count,
            "failed": len(self._results) - success_count,
            "duration": duration,
            "results": self._results,
        }


class PipelineBuilder:
    """Fluent builder for common pipeline patterns."""

    def __init__(self, tool_registry: ToolRegistry):
        self.tools = tool_registry

    def file_processing(self, name: str, input_path: str, output_path: str,
                        transform: str = "") -> Pipeline:
        """Create a file processing pipeline."""
        pipe = Pipeline(name, self.tools)
        pipe.add("read_input", "file_ops", "read", path=input_path)
        if transform:
            pipe.add("transform", "shell_ops", "run", command=transform)
        pipe.add("write_output", "file_ops", "write", path=output_path, content="")
        return pipe

    def system_check(self, name: str = "system_health") -> Pipeline:
        """Create a system health check pipeline."""
        pipe = Pipeline(name, self.tools)
        pipe.add("disk_usage", "shell_ops", "run", command="df -h")
        pipe.add("memory_usage", "shell_ops", "run", command="free -m")
        pipe.add("process_list", "shell_ops", "run", command="ps aux --sort=-%mem | head -10")
        pipe.add("uptime", "shell_ops", "run", command="uptime")
        return pipe

    def backup(self, source: str, destination: str) -> Pipeline:
        """Create a backup pipeline."""
        pipe = Pipeline("backup", self.tools)
        pipe.add("verify_source", "file_ops", "info", path=source)
        pipe.add("create_backup", "file_ops", "copy", path=source, destination=destination)
        pipe.add("verify_backup", "file_ops", "hash", path=destination)
        return pipe
