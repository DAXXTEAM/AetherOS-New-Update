"""AetherOS Sandbox   Code Validation.

Validates code for security risks before sandbox execution.
"""
from __future__ import annotations

import ast
import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("sandbox.validator")


class RiskLevel(enum.Enum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ValidationIssue:
    """A single validation issue found in code."""
    line: int = 0
    column: int = 0
    message: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "risk": self.risk_level.name,
            "category": self.category,
        }


@dataclass
class ValidationResult:
    """Complete validation result for a code submission."""
    is_safe: bool = True
    risk_level: RiskLevel = RiskLevel.SAFE
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: str = ""
    ast_valid: bool = True
    line_count: int = 0
    import_count: int = 0
    blocked_imports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "risk_level": self.risk_level.name,
            "issues_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "ast_valid": self.ast_valid,
            "line_count": self.line_count,
            "import_count": self.import_count,
            "blocked_imports": self.blocked_imports,
        }


class CodeValidator:
    """Validates Python code for security risks.

    Checks for:
    - Dangerous imports (subprocess, os, sys, etc.)
    - Eval/exec usage
    - File system access
    - Network operations
    - Infinite loops
    - Resource exhaustion patterns
    """

    DANGEROUS_BUILTINS = {
        "eval", "exec", "compile", "__import__",
        "globals", "locals", "vars", "dir",
        "getattr", "setattr", "delattr",
        "open", "input",
    }

    DANGEROUS_PATTERNS = [
        (r"os\.system\s*\(", "os.system call detected", RiskLevel.CRITICAL),
        (r"subprocess\.", "subprocess module usage", RiskLevel.CRITICAL),
        (r"__import__\s*\(", "dynamic import detected", RiskLevel.HIGH),
        (r"eval\s*\(", "eval() usage detected", RiskLevel.HIGH),
        (r"exec\s*\(", "exec() usage detected", RiskLevel.HIGH),
        (r"while\s+True", "infinite loop risk", RiskLevel.MEDIUM),
        (r"open", "file open detected", RiskLevel.HIGH),
        (r"socket\.", "socket usage detected", RiskLevel.CRITICAL),
        (r"rmtree", "directory deletion detected", RiskLevel.CRITICAL),
    ]

    def __init__(
        self,
        blocked_modules: Optional[List[str]] = None,
        allowed_imports: Optional[List[str]] = None,
        max_lines: int = 1000,
    ):
        self.blocked_modules = set(blocked_modules or [
            "subprocess", "shutil", "socket", "http",
            "urllib", "ctypes", "importlib", "pickle",
            "os", "sys", "signal", "multiprocessing",
        ])
        self.allowed_imports = set(allowed_imports or [
            "math", "json", "re", "datetime", "collections",
            "itertools", "functools", "string", "random",
            "hashlib", "typing", "dataclasses", "enum",
            "abc", "copy", "operator", "statistics",
        ])
        self.max_lines = max_lines

    def validate(self, code: str) -> ValidationResult:
        """Validate code for security risks."""
        result = ValidationResult()
        result.line_count = code.count("\n") + 1

        # Check line count
        if result.line_count > self.max_lines:
            result.issues.append(ValidationIssue(
                message=f"Code exceeds max line count ({result.line_count} > {self.max_lines})",
                risk_level=RiskLevel.MEDIUM,
                category="size",
            ))

        # AST validation
        try:
            tree = ast.parse(code)
            result.ast_valid = True
            self._check_ast(tree, result)
        except SyntaxError as e:
            result.ast_valid = False
            result.issues.append(ValidationIssue(
                line=e.lineno or 0,
                message=f"Syntax error: {e.msg}",
                risk_level=RiskLevel.LOW,
                category="syntax",
            ))

        # Pattern-based checks
        self._check_patterns(code, result)

        # Determine overall risk
        if result.issues:
            max_risk = max(i.risk_level.value for i in result.issues)
            result.risk_level = RiskLevel(max_risk)
            result.is_safe = max_risk < RiskLevel.HIGH.value
        else:
            result.risk_level = RiskLevel.SAFE
            result.is_safe = True

        result.summary = (
            f"{len(result.issues)} issues found. "
            f"Risk level: {result.risk_level.name}. "
            f"{'SAFE' if result.is_safe else 'BLOCKED'}"
        )

        return result

    def _check_ast(self, tree: ast.AST, result: ValidationResult) -> None:
        """Check AST nodes for dangerous constructs."""
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    result.import_count += 1
                    if module in self.blocked_modules:
                        result.blocked_imports.append(module)
                        result.issues.append(ValidationIssue(
                            line=node.lineno,
                            message=f"Blocked import: {module}",
                            risk_level=RiskLevel.CRITICAL,
                            category="import",
                        ))
                    elif module not in self.allowed_imports:
                        result.issues.append(ValidationIssue(
                            line=node.lineno,
                            message=f"Unknown import: {module}",
                            risk_level=RiskLevel.MEDIUM,
                            category="import",
                        ))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    result.import_count += 1
                    if module in self.blocked_modules:
                        result.blocked_imports.append(module)
                        result.issues.append(ValidationIssue(
                            line=node.lineno,
                            message=f"Blocked import: from {module}",
                            risk_level=RiskLevel.CRITICAL,
                            category="import",
                        ))

            # Check dangerous function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.DANGEROUS_BUILTINS:
                        result.issues.append(ValidationIssue(
                            line=node.lineno,
                            message=f"Dangerous builtin: {node.func.id}()",
                            risk_level=RiskLevel.HIGH,
                            category="builtin",
                        ))

    def _check_patterns(self, code: str, result: ValidationResult) -> None:
        """Check code against regex patterns."""
        for pattern, message, risk in self.DANGEROUS_PATTERNS:
            matches = re.finditer(pattern, code)
            for match in matches:
                line_num = code[:match.start()].count("\n") + 1
                result.issues.append(ValidationIssue(
                    line=line_num,
                    message=message,
                    risk_level=risk,
                    category="pattern",
                ))
