"""Tests for AetherOS Sandbox Module."""
import pytest
from sandbox.executor import SandboxExecutor, SandboxConfig, ExecutionStatus
from sandbox.validator import CodeValidator, RiskLevel


class TestCodeValidator:
    def test_safe_code(self):
        validator = CodeValidator()
        result = validator.validate("x = 1 + 2\nprint(x)")
        assert result.ast_valid
        # print is checked but at LOW level
        assert result.risk_level.value <= RiskLevel.MEDIUM.value

    def test_blocked_import(self):
        validator = CodeValidator()
        result = validator.validate("import subprocess")
        assert not result.is_safe
        assert "subprocess" in result.blocked_imports

    def test_eval_detection(self):
        validator = CodeValidator()
        result = validator.validate("eval('1+1')")
        assert result.risk_level.value >= RiskLevel.HIGH.value

    def test_syntax_error(self):
        validator = CodeValidator()
        result = validator.validate("def foo(:\n  pass")
        assert not result.ast_valid


class TestSandboxExecutor:
    def test_simple_execution(self):
        sandbox = SandboxExecutor()
        result = sandbox.execute_python("print('hello')")
        assert result.status == ExecutionStatus.COMPLETED
        assert "hello" in result.stdout

    def test_error_execution(self):
        sandbox = SandboxExecutor()
        result = sandbox.execute_python("raise ValueError('test')")
        assert result.status == ExecutionStatus.ERROR
        assert result.exit_code != 0

    def test_stats(self):
        sandbox = SandboxExecutor()
        stats = sandbox.stats
        assert "total_executions" in stats
