"""Tests for the Self-Evolution Module."""
import json
import os
import tempfile
import pytest
from core.evolution import (
    EvolutionEngine, LogScanner, PatchGenerator, ASTValidator,
    PatchApplier, CodePatch, ExecutionFailure, FailureSeverity, PatchStatus,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def log_dir(temp_dir):
    logdir = os.path.join(temp_dir, "logs")
    os.makedirs(logdir)
    return logdir


@pytest.fixture
def project_dir(temp_dir):
    pdir = os.path.join(temp_dir, "project")
    os.makedirs(pdir)
    os.makedirs(os.path.join(pdir, "tools"))
    # Create a sample file
    with open(os.path.join(pdir, "tools", "sample.py"), "w") as f:
        f.write('def get_value(data):\n    return data["key"]\n')
    return pdir


class TestASTValidator:
    def test_valid_syntax(self):
        ok, msg = ASTValidator.validate_syntax("def foo(): pass")
        assert ok
        assert "valid" in msg.lower()

    def test_invalid_syntax(self):
        ok, msg = ASTValidator.validate_syntax("def foo(")
        assert not ok
        assert "Syntax error" in msg

    def test_safety_clean(self):
        original = "import os\ndef foo(): pass"
        patched = "import os\ndef foo(): return 42"
        safe, warnings = ASTValidator.validate_safety(patched, original)
        assert safe
        assert not any("Dangerous" in w for w in warnings)

    def test_safety_dangerous_import(self):
        original = "def foo(): pass"
        patched = "import subprocess\ndef foo(): subprocess.call('ls')"
        safe, warnings = ASTValidator.validate_safety(patched, original)
        assert not safe

    def test_extract_functions(self):
        code = "def foo():\n    pass\ndef bar():\n    return 1"
        funcs = ASTValidator.extract_functions(code)
        assert "foo" in funcs
        assert "bar" in funcs

    def test_compute_complexity(self):
        code = "def foo():\n    if True:\n        for i in range(10):\n            pass"
        metrics = ASTValidator.compute_complexity(code)
        assert metrics["functions"] == 1
        assert metrics["branches"] == 1
        assert metrics["loops"] == 1


class TestLogScanner:
    def test_scan_empty_dir(self, log_dir):
        scanner = LogScanner(log_dir)
        failures = scanner.scan()
        assert failures == []

    def test_scan_with_errors(self, log_dir):
        log_file = os.path.join(log_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-01 ERROR ValueError: invalid literal\n")
            f.write("2024-01-01 ERROR KeyError: 'missing_key'\n")
        scanner = LogScanner(log_dir)
        failures = scanner.scan()
        assert len(failures) >= 1

    def test_scan_traceback(self, log_dir):
        log_file = os.path.join(log_dir, "trace.log")
        with open(log_file, "w") as f:
            f.write("Traceback (most recent call last):\n")
            f.write('  File "test.py", line 10, in main\n')
            f.write("    x = data['key']\n")
            f.write("KeyError: 'key'\n")
        scanner = LogScanner(log_dir)
        failures = scanner.scan()
        assert len(failures) >= 1
        assert failures[0].error_type == "KeyError"

    def test_severity_classification(self, log_dir):
        scanner = LogScanner(log_dir)
        assert scanner._classify_severity("MemoryError") == FailureSeverity.CRITICAL
        assert scanner._classify_severity("RuntimeError") == FailureSeverity.HIGH
        assert scanner._classify_severity("ValueError") == FailureSeverity.MEDIUM
        assert scanner._classify_severity("SomeCustomError") == FailureSeverity.LOW


class TestPatchGenerator:
    def test_generate_keyerror_patch(self, project_dir):
        gen = PatchGenerator(project_dir)
        failure = ExecutionFailure(
            source_file=os.path.join(project_dir, "tools", "sample.py"),
            function_name="get_value",
            error_type="KeyError",
            error_message="KeyError: 'key'",
        )
        patch = gen.generate_patch(failure)
        assert patch is not None
        assert patch.target_file.endswith("sample.py")

    def test_resolve_target_file(self, project_dir):
        gen = PatchGenerator(project_dir)
        resolved = gen._resolve_target_file("tools/sample.py")
        assert resolved is not None
        assert resolved.endswith("sample.py")

    def test_resolve_missing_file(self, project_dir):
        gen = PatchGenerator(project_dir)
        resolved = gen._resolve_target_file("nonexistent.py")
        assert resolved is None


class TestPatchApplier:
    def test_apply_and_rollback(self, temp_dir):
        backup_dir = os.path.join(temp_dir, "backups")
        target = os.path.join(temp_dir, "target.py")
        with open(target, "w") as f:
            f.write("original content")

        applier = PatchApplier(backup_dir)
        patch = CodePatch(
            target_file=target,
            original_content="original content",
            patched_content="patched content",
            status=PatchStatus.VALIDATED,
        )
        assert applier.apply(patch)
        with open(target) as f:
            assert f.read() == "patched content"

        assert applier.rollback(patch.patch_id)
        with open(target) as f:
            assert f.read() == "original content"


class TestEvolutionEngine:
    @pytest.mark.asyncio
    async def test_no_failures_cycle(self, temp_dir):
        engine = EvolutionEngine(
            project_root=temp_dir,
            log_dir=os.path.join(temp_dir, "logs"),
        )
        cycle = await engine.run_cycle()
        assert cycle.status == "no_failures"

    def test_get_status(self, temp_dir):
        engine = EvolutionEngine(project_root=temp_dir)
        status = engine.get_status()
        assert "total_cycles" in status
        assert status["project_root"] == temp_dir

    def test_cycle_history(self, temp_dir):
        engine = EvolutionEngine(project_root=temp_dir)
        history = engine.get_cycle_history()
        assert isinstance(history, list)
