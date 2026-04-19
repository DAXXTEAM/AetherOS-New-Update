"""Secure shell execution operations."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import signal
import time
from datetime import datetime
from typing import Optional

from config.constants import ALLOWED_SHELL_COMMANDS, BLOCKED_SHELL_PATTERNS, MAX_SHELL_TIMEOUT
from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.shell_ops")


class CommandValidator:
    """Validates shell commands for safety."""

    def __init__(self, whitelist: Optional[list[str]] = None,
                 blocked_patterns: Optional[list[str]] = None,
                 whitelist_enabled: bool = False):
        self.whitelist = whitelist or ALLOWED_SHELL_COMMANDS
        self.blocked_patterns = blocked_patterns or BLOCKED_SHELL_PATTERNS
        self.whitelist_enabled = whitelist_enabled
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.blocked_patterns]

    def validate(self, command: str) -> tuple[bool, str]:
        """Returns (is_safe, reason)."""
        if not command or not command.strip():
            return False, "Empty command"

        # Check blocked patterns
        for pattern in self._compiled_patterns:
            if pattern.search(command):
                return False, f"Command matches blocked pattern: {pattern.pattern}"

        # Check whitelist if enabled
        if self.whitelist_enabled:
            try:
                parts = shlex.split(command)
                base_cmd = os.path.basename(parts[0]) if parts else ""
                if base_cmd not in self.whitelist:
                    return False, f"Command '{base_cmd}' not in whitelist"
            except ValueError:
                return False, "Could not parse command"

        # Check for obvious shell injection
        dangerous_chars = ["$(", "`", "&&", "||", ";", "|"]
        if any(dc in command for dc in dangerous_chars):
            # Allow pipes and chains but warn
            logger.warning(f"Command contains shell operators: {command[:80]}")

        return True, "Command approved"


class ShellOps(BaseTool):
    """Secure terminal command execution."""

    def __init__(self, sandbox: bool = True, whitelist_enabled: bool = False,
                 working_dir: Optional[str] = None):
        super().__init__("shell_ops", "Secure terminal command execution")
        self.validator = CommandValidator(whitelist_enabled=whitelist_enabled)
        self.sandbox = sandbox
        self.working_dir = working_dir or os.path.expanduser("~")
        self._execution_log: list[dict] = []

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "run")
        dispatch = {
            "run": self._run_command,
            "run_background": self._run_background,
            "run_script": self._run_script,
            "env": self._get_env,
            "which": self._which,
            "processes": self._list_processes,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "shell_ops",
            "description": "Secure terminal command execution",
            "parameters": {
                "action": {"type": "string", "enum": ["run", "run_background", "run_script", "env", "which", "processes"]},
                "command": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
                "working_dir": {"type": "string"},
                "env": {"type": "object"},
            },
        }

    async def _run_command(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        timeout = min(args.get("timeout", 30), MAX_SHELL_TIMEOUT)
        cwd = args.get("working_dir", self.working_dir)

        is_safe, reason = self.validator.validate(command)
        if not is_safe:
            self._log_execution(command, "BLOCKED", reason)
            return ToolResult(success=False, error=f"Command blocked: {reason}")

        self._log_execution(command, "STARTED", "")
        try:
            env = os.environ.copy()
            custom_env = args.get("env", {})
            env.update(custom_env)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                self._log_execution(command, "TIMEOUT", f"Killed after {timeout}s")
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    metadata={"exit_code": -1, "timeout": True},
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            exit_code = proc.returncode

            output = stdout_str
            if stderr_str:
                output += f"\n[STDERR]\n{stderr_str}"

            # Truncate very long output
            max_output = args.get("max_output", 50000)
            if len(output) > max_output:
                output = output[:max_output] + f"\n... [truncated, {len(output)} total chars]"

            success = exit_code == 0
            self._log_execution(command, "COMPLETED" if success else "FAILED", f"exit={exit_code}")

            return ToolResult(
                success=success,
                output=output,
                error=stderr_str if not success else None,
                metadata={"exit_code": exit_code, "command": command},
            )
        except Exception as e:
            self._log_execution(command, "ERROR", str(e))
            return ToolResult(success=False, error=str(e))

    async def _run_background(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        is_safe, reason = self.validator.validate(command)
        if not is_safe:
            return ToolResult(success=False, error=f"Command blocked: {reason}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=args.get("working_dir", self.working_dir),
            )
            self._log_execution(command, "BACKGROUND", f"pid={proc.pid}")
            return ToolResult(
                success=True,
                output=f"Background process started: PID {proc.pid}",
                metadata={"pid": proc.pid},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_script(self, args: dict) -> ToolResult:
        script = args.get("script", "")
        interpreter = args.get("interpreter", "bash")
        if not script:
            return ToolResult(success=False, error="No script provided")

        import tempfile
        suffix = ".sh" if interpreter == "bash" else ".py"
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="aether_script_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script)
            os.chmod(path, 0o755)
            return await self._run_command({
                "command": f"{interpreter} {path}",
                "timeout": args.get("timeout", 60),
                "working_dir": args.get("working_dir", self.working_dir),
            })
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    async def _get_env(self, args: dict) -> ToolResult:
        var = args.get("variable", "")
        if var:
            val = os.environ.get(var, "[not set]")
            return ToolResult(success=True, output=f"{var}={val}")
        safe_vars = {k: v for k, v in os.environ.items()
                     if not any(s in k.lower() for s in ["key", "secret", "token", "password"])}
        output = "\n".join(f"{k}={v[:100]}" for k, v in sorted(safe_vars.items()))
        return ToolResult(success=True, output=output)

    async def _which(self, args: dict) -> ToolResult:
        program = args.get("program", "")
        result = await self._run_command({"command": f"which {shlex.quote(program)}", "timeout": 5})
        return result

    async def _list_processes(self, args: dict) -> ToolResult:
        return await self._run_command({"command": "ps aux --sort=-%mem | head -20", "timeout": 5})

    def _log_execution(self, command: str, status: str, detail: str) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command[:200],
            "status": status,
            "detail": detail,
        }
        self._execution_log.append(entry)
        if len(self._execution_log) > 1000:
            self._execution_log = self._execution_log[-1000:]
        logger.info(f"Shell [{status}]: {command[:80]} {detail}")

    def get_execution_log(self, last_n: int = 50) -> list[dict]:
        return self._execution_log[-last_n:]
