"""Self-Evolution Module — Enables AetherOS to analyze execution failures,
generate code patches, and apply them autonomously.

The Architect agent drives a self-refactoring loop:
1. Scan /logs for execution failures and error patterns
2. Diagnose root causes using LLM-backed reasoning
3. Generate code patches for /tools (or any target module)
4. Validate patches in a sandboxed AST check
5. Apply patches atomically with rollback support
6. Re-run the failing task to confirm the fix

This module is the core of AetherOS's self-improvement capability.
"""
from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import importlib
import inspect
import json
import logging
import os
import re
import shutil
import sys
import textwrap
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional, Callable

logger = logging.getLogger("aetheros.core.evolution")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class PatchStatus(Enum):
    PENDING = auto()
    VALIDATED = auto()
    APPLIED = auto()
    ROLLED_BACK = auto()
    FAILED = auto()
    REJECTED = auto()


class FailureSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExecutionFailure:
    """Represents a parsed failure extracted from log files."""
    failure_id: str = field(default_factory=lambda: f"fail-{uuid.uuid4().hex[:8]}")
    timestamp: datetime = field(default_factory=datetime.now)
    source_file: str = ""
    function_name: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback_text: str = ""
    severity: FailureSeverity = FailureSeverity.MEDIUM
    context: dict[str, Any] = field(default_factory=dict)
    log_line: int = 0
    recurrence_count: int = 1

    def to_dict(self) -> dict:
        return {
            "failure_id": self.failure_id,
            "timestamp": self.timestamp.isoformat(),
            "source_file": self.source_file,
            "function_name": self.function_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "severity": self.severity.value,
            "recurrence_count": self.recurrence_count,
        }


@dataclass
class CodePatch:
    """A code patch to be applied to a target file."""
    patch_id: str = field(default_factory=lambda: f"patch-{uuid.uuid4().hex[:8]}")
    target_file: str = ""
    original_content: str = ""
    patched_content: str = ""
    description: str = ""
    failure_ref: str = ""
    status: PatchStatus = PatchStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    applied_at: Optional[datetime] = None
    rollback_content: str = ""
    diff_text: str = ""
    validation_result: dict[str, Any] = field(default_factory=dict)
    author: str = "evolution-engine"

    def compute_diff(self) -> str:
        """Compute a unified diff between original and patched content."""
        original_lines = self.original_content.splitlines(keepends=True)
        patched_lines = self.patched_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines, patched_lines,
            fromfile=f"a/{self.target_file}",
            tofile=f"b/{self.target_file}",
            lineterm="",
        )
        self.diff_text = "\n".join(diff)
        return self.diff_text

    def to_dict(self) -> dict:
        return {
            "patch_id": self.patch_id,
            "target_file": self.target_file,
            "description": self.description,
            "failure_ref": self.failure_ref,
            "status": self.status.name,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "diff_preview": self.diff_text[:500] if self.diff_text else "",
        }


@dataclass
class EvolutionCycle:
    """Tracks a complete evolution cycle: detect → diagnose → patch → verify."""
    cycle_id: str = field(default_factory=lambda: f"evo-{uuid.uuid4().hex[:8]}")
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    failures_detected: list[ExecutionFailure] = field(default_factory=list)
    patches_generated: list[CodePatch] = field(default_factory=list)
    patches_applied: int = 0
    patches_rolled_back: int = 0
    verification_passed: bool = False
    status: str = "running"
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failures_detected": len(self.failures_detected),
            "patches_generated": len(self.patches_generated),
            "patches_applied": self.patches_applied,
            "patches_rolled_back": self.patches_rolled_back,
            "verification_passed": self.verification_passed,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Log Scanner — Parses execution logs for failure patterns
# ---------------------------------------------------------------------------

class LogScanner:
    """Scans log directories for execution failures and error patterns."""

    # Common Python error patterns
    ERROR_PATTERNS = [
        re.compile(r"(?P<etype>\w+Error): (?P<emsg>.+)"),
        re.compile(r"(?P<etype>\w+Exception): (?P<emsg>.+)"),
        re.compile(r"CRITICAL.*?(?P<etype>\w+): (?P<emsg>.+)"),
        re.compile(r"ERROR.*?(?P<etype>\w+): (?P<emsg>.+)"),
    ]

    TRACEBACK_START = re.compile(r"Traceback \(most recent call last\):")
    FILE_LINE = re.compile(r'\s+File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\w+)')

    def __init__(self, log_dir: str, max_age_hours: float = 24.0):
        self.log_dir = log_dir
        self.max_age_hours = max_age_hours
        self._seen_hashes: set[str] = set()

    def scan(self) -> list[ExecutionFailure]:
        """Scan all log files and extract failures."""
        failures: list[ExecutionFailure] = []
        if not os.path.isdir(self.log_dir):
            logger.warning(f"Log directory not found: {self.log_dir}")
            return failures

        cutoff = time.time() - (self.max_age_hours * 3600)
        log_files = sorted(Path(self.log_dir).glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

        for log_path in log_files[:20]:
            if log_path.stat().st_mtime < cutoff:
                continue
            try:
                new_failures = self._parse_log_file(str(log_path))
                failures.extend(new_failures)
            except Exception as e:
                logger.error(f"Error scanning {log_path}: {e}")

        # Deduplicate by error signature
        deduped = self._deduplicate(failures)
        logger.info(f"LogScanner: Found {len(deduped)} unique failures from {len(log_files)} log files")
        return deduped

    def _parse_log_file(self, filepath: str) -> list[ExecutionFailure]:
        """Parse a single log file for failures."""
        failures = []
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for traceback blocks
            if self.TRACEBACK_START.search(line):
                tb_lines = [line]
                i += 1
                source_file = ""
                func_name = ""
                while i < len(lines) and not lines[i].strip().startswith(("Traceback", "ERROR", "CRITICAL")):
                    tb_lines.append(lines[i])
                    file_match = self.FILE_LINE.match(lines[i])
                    if file_match:
                        source_file = file_match.group("file")
                        func_name = file_match.group("func")
                    # Check if this line is the error line
                    for pat in self.ERROR_PATTERNS:
                        m = pat.search(lines[i])
                        if m:
                            failure = ExecutionFailure(
                                source_file=source_file,
                                function_name=func_name,
                                error_type=m.group("etype"),
                                error_message=m.group("emsg"),
                                traceback_text="".join(tb_lines),
                                log_line=i,
                                severity=self._classify_severity(m.group("etype")),
                            )
                            failures.append(failure)
                            break
                    i += 1
                continue

            # Check for standalone error lines
            for pat in self.ERROR_PATTERNS:
                m = pat.search(line)
                if m and "ERROR" in line.upper():
                    failure = ExecutionFailure(
                        error_type=m.group("etype"),
                        error_message=m.group("emsg"),
                        log_line=i,
                        severity=self._classify_severity(m.group("etype")),
                    )
                    failures.append(failure)
                    break
            i += 1

        return failures

    def _classify_severity(self, error_type: str) -> FailureSeverity:
        """Classify failure severity based on error type."""
        critical_types = {"SystemExit", "MemoryError", "RecursionError", "SegmentationFault"}
        high_types = {"RuntimeError", "OSError", "PermissionError", "ConnectionError"}
        medium_types = {"ValueError", "TypeError", "KeyError", "AttributeError", "ImportError"}

        if error_type in critical_types:
            return FailureSeverity.CRITICAL
        if error_type in high_types:
            return FailureSeverity.HIGH
        if error_type in medium_types:
            return FailureSeverity.MEDIUM
        return FailureSeverity.LOW

    def _deduplicate(self, failures: list[ExecutionFailure]) -> list[ExecutionFailure]:
        """Deduplicate failures by error signature."""
        seen: dict[str, ExecutionFailure] = {}
        for f in failures:
            sig = hashlib.md5(
                f"{f.error_type}:{f.error_message}:{f.source_file}".encode()
            ).hexdigest()
            if sig in seen:
                seen[sig].recurrence_count += 1
            else:
                seen[sig] = f
        return list(seen.values())


# ---------------------------------------------------------------------------
# AST Validator — Validates patches at the AST level
# ---------------------------------------------------------------------------

class ASTValidator:
    """Validates Python code patches using AST analysis."""

    FORBIDDEN_NODES = {
        ast.Import: ["os.system", "subprocess.call"],
        ast.Call: [],
    }

    @staticmethod
    def validate_syntax(code: str) -> tuple[bool, str]:
        """Check if code has valid Python syntax."""
        try:
            ast.parse(code)
            return True, "Syntax valid"
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

    @staticmethod
    def validate_safety(code: str, original_code: str) -> tuple[bool, list[str]]:
        """Check patch safety by comparing AST structures."""
        warnings = []
        try:
            new_tree = ast.parse(code)
            old_tree = ast.parse(original_code)
        except SyntaxError as e:
            return False, [f"Syntax error: {e}"]

        # Check for dangerous additions
        new_imports = {
            node.names[0].name if isinstance(node, ast.Import) else node.module
            for node in ast.walk(new_tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        old_imports = {
            node.names[0].name if isinstance(node, ast.Import) else node.module
            for node in ast.walk(old_tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        added_imports = new_imports - old_imports
        dangerous_imports = {"subprocess", "ctypes", "pty", "resource"}
        dangerous_added = added_imports & dangerous_imports
        if dangerous_added:
            warnings.append(f"Dangerous imports added: {dangerous_added}")

        # Check for exec/eval additions
        for node in ast.walk(new_tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("exec", "eval", "compile"):
                    warnings.append(f"Dangerous function call: {node.func.id}")

        # Check function count delta
        new_funcs = sum(1 for n in ast.walk(new_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        old_funcs = sum(1 for n in ast.walk(old_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        if abs(new_funcs - old_funcs) > 5:
            warnings.append(f"Large function count change: {old_funcs} → {new_funcs}")

        is_safe = not any("Dangerous" in w for w in warnings)
        return is_safe, warnings

    @staticmethod
    def extract_functions(code: str) -> dict[str, str]:
        """Extract all function definitions from code."""
        functions = {}
        try:
            tree = ast.parse(code)
            lines = code.splitlines()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno - 1
                    end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start + 1
                    func_code = "\n".join(lines[start:end])
                    functions[node.name] = func_code
        except SyntaxError:
            pass
        return functions

    @staticmethod
    def compute_complexity(code: str) -> dict[str, int]:
        """Compute basic code complexity metrics."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"error": -1}

        metrics = {
            "functions": 0,
            "classes": 0,
            "branches": 0,
            "loops": 0,
            "try_except": 0,
            "lines": len(code.splitlines()),
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                metrics["functions"] += 1
            elif isinstance(node, ast.ClassDef):
                metrics["classes"] += 1
            elif isinstance(node, (ast.If, ast.IfExp)):
                metrics["branches"] += 1
            elif isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                metrics["loops"] += 1
            elif isinstance(node, ast.Try):
                metrics["try_except"] += 1
        return metrics


# ---------------------------------------------------------------------------
# Patch Generator — Creates code patches from failure analysis
# ---------------------------------------------------------------------------

class PatchGenerator:
    """Generates code patches from failure analysis using LLM or heuristics."""

    # Common fix patterns (heuristic-based, no LLM required)
    FIX_PATTERNS = {
        "KeyError": {
            "pattern": r"(\w+)\[(['\"]?\w+['\"]?)\]",
            "fix_template": "{var}.get({key}, {default})",
            "description": "Replace dict key access with .get() for safety",
        },
        "AttributeError": {
            "pattern": r"'(\w+)' object has no attribute '(\w+)'",
            "fix_template": "getattr({obj}, '{attr}', None)",
            "description": "Add getattr fallback for missing attribute",
        },
        "TypeError": {
            "pattern": r"argument.*must be.*not (\w+)",
            "fix_template": "type_cast",
            "description": "Add type casting/validation",
        },
        "IndexError": {
            "pattern": r"(list|tuple) index out of range",
            "fix_template": "bounds_check",
            "description": "Add bounds checking before index access",
        },
        "FileNotFoundError": {
            "pattern": r"No such file or directory: '(.+)'",
            "fix_template": "path_check",
            "description": "Add file existence check before access",
        },
    }

    def __init__(self, project_root: str):
        self.project_root = project_root

    def generate_patch(self, failure: ExecutionFailure,
                       model_generate: Optional[Callable] = None) -> Optional[CodePatch]:
        """Generate a code patch for a given failure."""
        target_file = self._resolve_target_file(failure.source_file)
        if not target_file or not os.path.isfile(target_file):
            logger.warning(f"Cannot locate target file for patching: {failure.source_file}")
            return None

        try:
            with open(target_file, "r") as f:
                original_content = f.read()
        except OSError as e:
            logger.error(f"Cannot read target file {target_file}: {e}")
            return None

        # Try heuristic fix first
        patched = self._apply_heuristic_fix(failure, original_content)

        if patched and patched != original_content:
            patch = CodePatch(
                target_file=target_file,
                original_content=original_content,
                patched_content=patched,
                description=f"Heuristic fix for {failure.error_type}: {failure.error_message[:100]}",
                failure_ref=failure.failure_id,
                author="evolution-engine:heuristic",
            )
            patch.compute_diff()
            return patch

        # If no heuristic fix, generate a descriptive patch suggestion
        patch = CodePatch(
            target_file=target_file,
            original_content=original_content,
            patched_content=original_content,  # No change yet
            description=f"Manual review needed for {failure.error_type}: {failure.error_message[:200]}",
            failure_ref=failure.failure_id,
            status=PatchStatus.PENDING,
            author="evolution-engine:suggestion",
        )
        return patch

    def _resolve_target_file(self, source_path: str) -> Optional[str]:
        """Resolve a source path to an actual file in the project."""
        if not source_path:
            return None

        # Direct path
        if os.path.isfile(source_path):
            return source_path

        # Relative to project root
        candidate = os.path.join(self.project_root, source_path)
        if os.path.isfile(candidate):
            return candidate

        # Search by filename
        basename = os.path.basename(source_path)
        for root, dirs, files in os.walk(self.project_root):
            if basename in files:
                return os.path.join(root, basename)

        return None

    def _apply_heuristic_fix(self, failure: ExecutionFailure, code: str) -> Optional[str]:
        """Apply pattern-based heuristic fixes."""
        error_type = failure.error_type
        fix_info = self.FIX_PATTERNS.get(error_type)
        if not fix_info:
            return None

        lines = code.splitlines()
        modified = False

        if error_type == "KeyError":
            # Replace direct dict access with .get()
            key_match = re.search(r"KeyError: ['\"]?(\w+)['\"]?", failure.error_message)
            if key_match:
                key = key_match.group(1)
                for i, line in enumerate(lines):
                    pattern = re.compile(rf"(\w+)\[(['\"]){key}\2\]")
                    if pattern.search(line):
                        new_line = pattern.sub(rf"\1.get('{key}', None)", line)
                        lines[i] = new_line
                        modified = True

        elif error_type == "FileNotFoundError":
            path_match = re.search(r"No such file or directory: '(.+)'", failure.error_message)
            if path_match and failure.function_name:
                for i, line in enumerate(lines):
                    if f"def {failure.function_name}" in line:
                        indent = len(line) - len(line.lstrip()) + 4
                        check_line = " " * indent + f"os.makedirs(os.path.dirname(path), exist_ok=True)\n"
                        lines.insert(i + 1, check_line)
                        modified = True
                        break

        elif error_type == "AttributeError":
            attr_match = re.search(
                r"'(\w+)' object has no attribute '(\w+)'", failure.error_message
            )
            if attr_match:
                obj_type = attr_match.group(1)
                attr_name = attr_match.group(2)
                for i, line in enumerate(lines):
                    if f".{attr_name}" in line and "getattr" not in line:
                        pattern = re.compile(rf"(\w+)\.{attr_name}")
                        new_line = pattern.sub(rf"getattr(\1, '{attr_name}', None)", line)
                        if new_line != line:
                            lines[i] = new_line
                            modified = True
                            break

        elif error_type == "IndexError":
            for i, line in enumerate(lines):
                idx_match = re.search(r"(\w+)\[(\d+)\]", line)
                if idx_match and failure.function_name and failure.function_name in code[max(0, i - 5):i + 1]:
                    var = idx_match.group(1)
                    idx = idx_match.group(2)
                    indent = " " * (len(line) - len(line.lstrip()))
                    guard = f"{indent}if len({var}) > {idx}:\n"
                    lines[i] = guard + "    " + line
                    modified = True
                    break

        if modified:
            return "\n".join(lines)
        return None


# ---------------------------------------------------------------------------
# Patch Applier — Safely applies and rolls back patches
# ---------------------------------------------------------------------------

class PatchApplier:
    """Atomically applies patches with rollback support."""

    def __init__(self, backup_dir: str):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        self._applied_patches: dict[str, CodePatch] = {}

    def apply(self, patch: CodePatch) -> bool:
        """Apply a patch atomically."""
        if patch.status not in (PatchStatus.PENDING, PatchStatus.VALIDATED):
            logger.warning(f"Cannot apply patch {patch.patch_id}: status={patch.status.name}")
            return False

        target = patch.target_file
        if not os.path.isfile(target):
            logger.error(f"Target file not found: {target}")
            patch.status = PatchStatus.FAILED
            return False

        # Create backup
        backup_path = os.path.join(
            self.backup_dir, f"{patch.patch_id}_{os.path.basename(target)}"
        )
        try:
            shutil.copy2(target, backup_path)
            patch.rollback_content = patch.original_content
        except OSError as e:
            logger.error(f"Backup failed: {e}")
            patch.status = PatchStatus.FAILED
            return False

        # Write patched content
        try:
            with open(target, "w") as f:
                f.write(patch.patched_content)
            patch.status = PatchStatus.APPLIED
            patch.applied_at = datetime.now()
            self._applied_patches[patch.patch_id] = patch
            logger.info(f"Patch {patch.patch_id} applied to {target}")
            return True
        except OSError as e:
            logger.error(f"Patch application failed: {e}")
            # Rollback
            try:
                shutil.copy2(backup_path, target)
            except OSError:
                pass
            patch.status = PatchStatus.FAILED
            return False

    def rollback(self, patch_id: str) -> bool:
        """Rollback an applied patch."""
        patch = self._applied_patches.get(patch_id)
        if not patch:
            logger.warning(f"Patch {patch_id} not found in applied patches")
            return False

        if not patch.rollback_content:
            logger.error(f"No rollback content for patch {patch_id}")
            return False

        try:
            with open(patch.target_file, "w") as f:
                f.write(patch.rollback_content)
            patch.status = PatchStatus.ROLLED_BACK
            logger.info(f"Patch {patch_id} rolled back successfully")
            return True
        except OSError as e:
            logger.error(f"Rollback failed for patch {patch_id}: {e}")
            return False

    def rollback_all(self) -> int:
        """Rollback all applied patches."""
        rolled = 0
        for pid in list(self._applied_patches.keys()):
            if self.rollback(pid):
                rolled += 1
        return rolled


# ---------------------------------------------------------------------------
# Evolution Engine — The main self-evolution controller
# ---------------------------------------------------------------------------

class EvolutionEngine:
    """Main self-evolution engine that orchestrates the refactoring loop.

    Flow: Scan → Diagnose → Generate → Validate → Apply → Verify
    """

    def __init__(
        self,
        project_root: str,
        log_dir: Optional[str] = None,
        backup_dir: Optional[str] = None,
        max_patches_per_cycle: int = 5,
        auto_apply: bool = False,
        safety_checks: bool = True,
    ):
        self.project_root = project_root
        self.log_dir = log_dir or os.path.join(project_root, "logs")
        self.backup_dir = backup_dir or os.path.join(project_root, ".evolution", "backups")

        self.scanner = LogScanner(self.log_dir)
        self.generator = PatchGenerator(project_root)
        self.validator = ASTValidator()
        self.applier = PatchApplier(self.backup_dir)

        self.max_patches_per_cycle = max_patches_per_cycle
        self.auto_apply = auto_apply
        self.safety_checks = safety_checks

        self._cycles: list[EvolutionCycle] = []
        self._total_patches_applied = 0
        self._total_patches_rejected = 0

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(project_root, ".evolution"), exist_ok=True)

        logger.info(
            f"EvolutionEngine initialized: project={project_root}, "
            f"auto_apply={auto_apply}, max_patches={max_patches_per_cycle}"
        )

    async def run_cycle(self, model_generate: Optional[Callable] = None) -> EvolutionCycle:
        """Run a complete evolution cycle."""
        cycle = EvolutionCycle()
        logger.info(f"🧬 Starting evolution cycle {cycle.cycle_id}")

        try:
            # Phase 1: Scan for failures
            failures = self.scanner.scan()
            cycle.failures_detected = failures
            if not failures:
                cycle.status = "no_failures"
                cycle.summary = "No failures detected in logs"
                cycle.completed_at = datetime.now()
                self._cycles.append(cycle)
                return cycle

            logger.info(f"🔍 Found {len(failures)} unique failures")

            # Phase 2: Generate patches
            patches = []
            for failure in failures[:self.max_patches_per_cycle]:
                patch = self.generator.generate_patch(failure, model_generate)
                if patch:
                    patches.append(patch)
            cycle.patches_generated = patches

            if not patches:
                cycle.status = "no_patches"
                cycle.summary = f"Found {len(failures)} failures but no patches could be generated"
                cycle.completed_at = datetime.now()
                self._cycles.append(cycle)
                return cycle

            logger.info(f"🔧 Generated {len(patches)} patches")

            # Phase 3: Validate patches
            validated_patches = []
            for patch in patches:
                if self.safety_checks and patch.patched_content != patch.original_content:
                    syntax_ok, syntax_msg = self.validator.validate_syntax(patch.patched_content)
                    if not syntax_ok:
                        patch.status = PatchStatus.REJECTED
                        patch.validation_result = {"syntax": False, "message": syntax_msg}
                        self._total_patches_rejected += 1
                        continue

                    safe, warnings = self.validator.validate_safety(
                        patch.patched_content, patch.original_content
                    )
                    patch.validation_result = {"safe": safe, "warnings": warnings}
                    if not safe:
                        patch.status = PatchStatus.REJECTED
                        self._total_patches_rejected += 1
                        logger.warning(f"Patch {patch.patch_id} rejected: {warnings}")
                        continue

                    patch.status = PatchStatus.VALIDATED
                    validated_patches.append(patch)
                else:
                    patch.status = PatchStatus.VALIDATED
                    validated_patches.append(patch)

            # Phase 4: Apply patches
            if self.auto_apply:
                for patch in validated_patches:
                    if patch.patched_content != patch.original_content:
                        if self.applier.apply(patch):
                            cycle.patches_applied += 1
                            self._total_patches_applied += 1
                        else:
                            cycle.patches_rolled_back += 1

            cycle.verification_passed = cycle.patches_applied > 0 or not self.auto_apply
            cycle.status = "completed"
            cycle.summary = (
                f"Detected {len(failures)} failures, generated {len(patches)} patches, "
                f"validated {len(validated_patches)}, applied {cycle.patches_applied}"
            )

        except Exception as e:
            cycle.status = "error"
            cycle.summary = f"Evolution cycle failed: {e}"
            logger.error(f"Evolution cycle error: {e}", exc_info=True)

        cycle.completed_at = datetime.now()
        self._cycles.append(cycle)
        self._save_cycle_report(cycle)
        logger.info(f"🧬 Evolution cycle {cycle.cycle_id} complete: {cycle.summary}")
        return cycle

    def _save_cycle_report(self, cycle: EvolutionCycle) -> None:
        """Save cycle report to disk."""
        report_dir = os.path.join(self.project_root, ".evolution", "reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"{cycle.cycle_id}.json")
        report = {
            "cycle": cycle.to_dict(),
            "failures": [f.to_dict() for f in cycle.failures_detected],
            "patches": [p.to_dict() for p in cycle.patches_generated],
        }
        try:
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save cycle report: {e}")

    def rollback_cycle(self, cycle_id: str) -> int:
        """Rollback all patches from a specific cycle."""
        for cycle in self._cycles:
            if cycle.cycle_id == cycle_id:
                rolled = 0
                for patch in cycle.patches_generated:
                    if patch.status == PatchStatus.APPLIED:
                        if self.applier.rollback(patch.patch_id):
                            rolled += 1
                return rolled
        return 0

    def get_status(self) -> dict:
        """Get evolution engine status."""
        return {
            "total_cycles": len(self._cycles),
            "total_patches_applied": self._total_patches_applied,
            "total_patches_rejected": self._total_patches_rejected,
            "auto_apply": self.auto_apply,
            "safety_checks": self.safety_checks,
            "project_root": self.project_root,
            "log_dir": self.log_dir,
            "last_cycle": self._cycles[-1].to_dict() if self._cycles else None,
        }

    def get_cycle_history(self, last_n: int = 10) -> list[dict]:
        """Get recent cycle history."""
        return [c.to_dict() for c in self._cycles[-last_n:]]

    def get_pending_patches(self) -> list[dict]:
        """Get patches awaiting approval."""
        pending = []
        for cycle in self._cycles:
            for patch in cycle.patches_generated:
                if patch.status in (PatchStatus.PENDING, PatchStatus.VALIDATED):
                    pending.append(patch.to_dict())
        return pending

    def approve_patch(self, patch_id: str) -> bool:
        """Manually approve and apply a pending patch."""
        for cycle in self._cycles:
            for patch in cycle.patches_generated:
                if patch.patch_id == patch_id and patch.status == PatchStatus.VALIDATED:
                    return self.applier.apply(patch)
        return False


# ---------------------------------------------------------------------------
# Module-level integration function
# ---------------------------------------------------------------------------

def create_evolution_engine(
    project_root: str,
    log_dir: Optional[str] = None,
    auto_apply: bool = False,
) -> EvolutionEngine:
    """Factory function to create a configured EvolutionEngine."""
    return EvolutionEngine(
        project_root=project_root,
        log_dir=log_dir,
        auto_apply=auto_apply,
        safety_checks=True,
    )
