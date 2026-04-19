"""AetherOS Sandbox   Isolated Code Execution.

Provides sandboxed environments for safe code execution
with resource limits, timeout control, and output capture.
"""
from __future__ import annotations

import enum
import logging
import os
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sandbox.executor")


class ExecutionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"
    KILLED = "killed"


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    max_time_seconds: float = 30.0
    max_memory_mb: int = 256
    max_output_bytes: int = 1_000_000
    allowed_imports: List[str] = field(default_factory=lambda: [
        "math", "json", "re", "datetime", "collections", "itertools",
        "functools", "string", "random", "hashlib", "os.path",
    ])
    blocked_modules: List[str] = field(default_factory=lambda: [
        "subprocess", "shutil", "socket", "http", "urllib",
        "ctypes", "importlib", "pickle",
    ])
    network_access: bool = False
    filesystem_read: bool = True
    filesystem_write: bool = False


@dataclass
class ExecutionResult:
    """Result of sandboxed code execution."""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ExecutionStatus = ExecutionStatus.PENDING
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    exit_code: int = -1
    duration_ms: float = 0.0
    memory_used_mb: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "stdout": self.stdout[:500] + "..." if len(self.stdout) > 500 else self.stdout,
            "stderr": self.stderr[:500] + "..." if len(self.stderr) > 500 else self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


class SandboxExecutor:
    """Executes code in isolated sandbox environments.

    Usage:
        sandbox = SandboxExecutor()
        result = sandbox.execute_python("print('Hello, World!')")
        print(result.stdout)  # "Hello, World!"
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._execution_history: List[ExecutionResult] = []
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        logger.info("SandboxExecutor initialized")

    def execute_python(self, code: str, stdin_data: str = "") -> ExecutionResult:
        """Execute Python code in a sandboxed subprocess."""
        result = ExecutionResult()
        result.started_at = datetime.utcnow()
        result.status = ExecutionStatus.RUNNING

        # Validate code before execution
        from sandbox.validator import CodeValidator
        validator = CodeValidator(
            blocked_modules=self.config.blocked_modules,
            allowed_imports=self.config.allowed_imports,
        )
        validation = validator.validate(code)
        if validation.risk_level.value >= 3:  # HIGH or CRITICAL
            result.status = ExecutionStatus.ERROR
            result.error = f"Code rejected: {validation.summary}"
            result.completed_at = datetime.utcnow()
            self._execution_history.append(result)
            return result

        try:
            # Write code to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, prefix="aetheros_sandbox_"
            ) as f:
                f.write(code)
                temp_path = f.name

            try:
                start_time = time.perf_counter()
                proc = subprocess.Popen(
                    ["python3", temp_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE if stdin_data else None,
                    env={
                        "PATH": os.environ.get("PATH", "/usr/bin"),
                        "HOME": tempfile.gettempdir(),
                    },
                )

                with self._lock:
                    self._active_processes[result.execution_id] = proc

                try:
                    stdout, stderr = proc.communicate(
                        input=stdin_data.encode() if stdin_data else None,
                        timeout=self.config.max_time_seconds,
                    )
                    result.stdout = stdout.decode("utf-8", errors="replace")[:self.config.max_output_bytes]
                    result.stderr = stderr.decode("utf-8", errors="replace")[:self.config.max_output_bytes]
                    result.exit_code = proc.returncode
                    result.status = (
                        ExecutionStatus.COMPLETED if proc.returncode == 0
                        else ExecutionStatus.ERROR
                    )
                except subprocess.TimeoutExpired:
                    proc.kill()
                    result.status = ExecutionStatus.TIMEOUT
                    result.error = f"Execution timed out after {self.config.max_time_seconds}s"

                result.duration_ms = (time.perf_counter() - start_time) * 1000

            finally:
                os.unlink(temp_path)
                with self._lock:
                    self._active_processes.pop(result.execution_id, None)

        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.error = str(e)
            logger.error(f"Sandbox execution error: {e}")

        result.completed_at = datetime.utcnow()
        self._execution_history.append(result)
        return result

    def execute_shell(self, command: str) -> ExecutionResult:
        """Execute a shell command in sandbox (restricted)."""
        from config.constants import BLOCKED_SHELL_PATTERNS, ALLOWED_SHELL_COMMANDS
        import re

        result = ExecutionResult()
        result.started_at = datetime.utcnow()

        # Check command against blocklist
        for pattern in BLOCKED_SHELL_PATTERNS:
            if re.search(pattern, command):
                result.status = ExecutionStatus.ERROR
                result.error = f"Command blocked by security policy: {pattern}"
                return result

        # Check command starts with allowed command
        cmd_base = command.split()[0] if command.split() else ""
        if cmd_base not in ALLOWED_SHELL_COMMANDS:
            result.status = ExecutionStatus.ERROR
            result.error = f"Command '{cmd_base}' not in allowed list"
            return result

        try:
            start_time = time.perf_counter()
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=self.config.max_time_seconds,
                text=True,
            )
            result.stdout = proc.stdout[:self.config.max_output_bytes]
            result.stderr = proc.stderr[:self.config.max_output_bytes]
            result.exit_code = proc.returncode
            result.status = ExecutionStatus.COMPLETED
            result.duration_ms = (time.perf_counter() - start_time) * 1000
        except subprocess.TimeoutExpired:
            result.status = ExecutionStatus.TIMEOUT
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.error = str(e)

        result.completed_at = datetime.utcnow()
        self._execution_history.append(result)
        return result

    def kill(self, execution_id: str) -> bool:
        with self._lock:
            proc = self._active_processes.get(execution_id)
            if proc:
                proc.kill()
                return True
            return False

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._execution_history[-limit:]]

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_processes)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_executions": len(self._execution_history),
            "active": self.active_count,
            "max_time": self.config.max_time_seconds,
        }
