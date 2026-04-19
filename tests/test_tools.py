"""Tests for tools module."""
import asyncio
import os
import tempfile
import pytest

from tools.base import ToolRegistry, ToolResult
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps, CommandValidator
from tools.web_ops import WebOps, HTMLParser


class TestToolRegistry:
    def test_register_and_get(self, tool_registry):
        tool = tool_registry.get_tool("file_ops")
        assert tool is not None
        assert tool.name == "file_ops"

    def test_list_tools(self, tool_registry):
        tools = tool_registry.list_tools()
        assert len(tools) >= 2
        names = [t["name"] for t in tools]
        assert "file_ops" in names

    def test_get_missing_tool(self, tool_registry):
        assert tool_registry.get_tool("nonexistent") is None

    @pytest.mark.asyncio
    async def test_execute_missing_tool(self, tool_registry):
        result = await tool_registry.execute_tool("nonexistent")
        assert not result.success


class TestFileOps:
    @pytest.fixture
    def file_ops(self, temp_dir):
        return FileOps(allowed_dirs=[temp_dir, "/tmp"], sandbox=True)

    @pytest.mark.asyncio
    async def test_write_and_read(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "test.txt")
        result = await file_ops.execute(action="write", path=path, content="Hello World")
        assert result.success

        result = await file_ops.execute(action="read", path=path)
        assert result.success
        assert "Hello World" in result.output

    @pytest.mark.asyncio
    async def test_mkdir(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "subdir", "nested")
        result = await file_ops.execute(action="mkdir", path=path)
        assert result.success
        assert os.path.isdir(path)

    @pytest.mark.asyncio
    async def test_list_dir(self, file_ops, temp_dir):
        # Create some files
        for name in ["a.txt", "b.txt", "c.py"]:
            with open(os.path.join(temp_dir, name), "w") as f:
                f.write("x")
        result = await file_ops.execute(action="list", path=temp_dir)
        assert result.success
        assert "a.txt" in result.output

    @pytest.mark.asyncio
    async def test_copy(self, file_ops, temp_dir):
        src = os.path.join(temp_dir, "src.txt")
        dst = os.path.join(temp_dir, "dst.txt")
        with open(src, "w") as f:
            f.write("copy me")
        result = await file_ops.execute(action="copy", path=src, destination=dst)
        assert result.success
        assert os.path.exists(dst)

    @pytest.mark.asyncio
    async def test_move(self, file_ops, temp_dir):
        src = os.path.join(temp_dir, "move_src.txt")
        dst = os.path.join(temp_dir, "move_dst.txt")
        with open(src, "w") as f:
            f.write("move me")
        result = await file_ops.execute(action="move", path=src, destination=dst)
        assert result.success
        assert os.path.exists(dst)
        assert not os.path.exists(src)

    @pytest.mark.asyncio
    async def test_delete(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "del.txt")
        with open(path, "w") as f:
            f.write("x")
        result = await file_ops.execute(action="delete", path=path)
        assert result.success
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_file_info(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "info.txt")
        with open(path, "w") as f:
            f.write("info test")
        result = await file_ops.execute(action="info", path=path)
        assert result.success
        assert "size" in result.metadata

    @pytest.mark.asyncio
    async def test_hash(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "hash.txt")
        with open(path, "w") as f:
            f.write("hash me")
        result = await file_ops.execute(action="hash", path=path)
        assert result.success
        assert "sha256:" in result.output

    @pytest.mark.asyncio
    async def test_find_replace(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "fr.txt")
        with open(path, "w") as f:
            f.write("hello world hello")
        result = await file_ops.execute(action="find_replace", path=path, find="hello", replace="hi")
        assert result.success
        assert result.metadata["replacements"] == 2

    @pytest.mark.asyncio
    async def test_tree(self, file_ops, temp_dir):
        os.makedirs(os.path.join(temp_dir, "sub1"))
        os.makedirs(os.path.join(temp_dir, "sub2"))
        with open(os.path.join(temp_dir, "sub1", "f.txt"), "w") as f:
            f.write("x")
        result = await file_ops.execute(action="tree", path=temp_dir)
        assert result.success
        assert "sub1" in result.output

    @pytest.mark.asyncio
    async def test_sandbox_blocks_outside(self, file_ops):
        result = await file_ops.execute(action="read", path="/etc/shadow")
        assert not result.success

    @pytest.mark.asyncio
    async def test_append(self, file_ops, temp_dir):
        path = os.path.join(temp_dir, "append.txt")
        with open(path, "w") as f:
            f.write("line1\n")
        result = await file_ops.execute(action="append", path=path, content="line2\n")
        assert result.success
        with open(path) as f:
            assert "line2" in f.read()

    @pytest.mark.asyncio
    async def test_search(self, file_ops, temp_dir):
        for name in ["a.py", "b.py", "c.txt"]:
            with open(os.path.join(temp_dir, name), "w") as f:
                f.write("x")
        result = await file_ops.execute(action="search", path=temp_dir, pattern="*.py")
        assert result.success
        assert "a.py" in result.output

    @pytest.mark.asyncio
    async def test_unknown_action(self, file_ops):
        result = await file_ops.execute(action="nonexistent")
        assert not result.success


class TestCommandValidator:
    def test_safe_command(self):
        v = CommandValidator(whitelist_enabled=False)
        safe, _ = v.validate("ls -la")
        assert safe

    def test_blocked_command(self):
        v = CommandValidator()
        safe, reason = v.validate("rm -rf /")
        assert not safe

    def test_empty_command(self):
        v = CommandValidator()
        safe, _ = v.validate("")
        assert not safe

    def test_whitelist_mode(self):
        v = CommandValidator(whitelist_enabled=True)
        safe, _ = v.validate("ls -la")
        assert safe

        safe, _ = v.validate("unknown_cmd arg")
        assert not safe


class TestShellOps:
    @pytest.fixture
    def shell_ops(self, temp_dir):
        return ShellOps(sandbox=True, working_dir=temp_dir)

    @pytest.mark.asyncio
    async def test_run_command(self, shell_ops):
        result = await shell_ops.execute(action="run", command="echo hello")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_run_with_timeout(self, shell_ops):
        result = await shell_ops.execute(action="run", command="sleep 0.1 && echo done", timeout=5)
        assert result.success

    @pytest.mark.asyncio
    async def test_command_failure(self, shell_ops):
        result = await shell_ops.execute(action="run", command="false")
        assert not result.success

    @pytest.mark.asyncio
    async def test_blocked_command(self, shell_ops):
        result = await shell_ops.execute(action="run", command="rm -rf /")
        assert not result.success

    @pytest.mark.asyncio
    async def test_env(self, shell_ops):
        result = await shell_ops.execute(action="env", variable="HOME")
        assert result.success
        assert "HOME=" in result.output

    @pytest.mark.asyncio
    async def test_which(self, shell_ops):
        result = await shell_ops.execute(action="which", program="python3")
        assert result.success

    @pytest.mark.asyncio
    async def test_execution_log(self, shell_ops):
        await shell_ops.execute(action="run", command="echo test1")
        await shell_ops.execute(action="run", command="echo test2")
        log = shell_ops.get_execution_log()
        assert len(log) >= 2

    @pytest.mark.asyncio
    async def test_run_script(self, shell_ops):
        result = await shell_ops.execute(
            action="run_script",
            script="echo 'script output'",
            interpreter="bash",
        )
        assert result.success
        assert "script output" in result.output


class TestHTMLParser:
    def test_extract_text(self):
        html = "<html><body><p>Hello <b>World</b></p><script>var x=1;</script></body></html>"
        text = HTMLParser.extract_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "var x" not in text

    def test_extract_links(self):
        html = '<a href="https://example.com">Example</a> <a href="/page">Page</a>'
        links = HTMLParser.extract_links(html, "https://base.com")
        assert len(links) == 2
        assert links[0]["url"] == "https://example.com"

    def test_extract_metadata(self):
        html = '<html><head><title>Test Page</title><meta name="description" content="A test"></head></html>'
        meta = HTMLParser.extract_metadata(html)
        assert meta.get("title") == "Test Page"
        assert meta.get("description") == "A test"
