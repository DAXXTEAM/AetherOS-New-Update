"""Advanced file and folder management operations."""
from __future__ import annotations

import glob
import hashlib
import logging
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.file_ops")


class FileOps(BaseTool):
    """Advanced file system operations with safety checks."""

    def __init__(self, allowed_dirs: Optional[list[str]] = None, sandbox: bool = True):
        super().__init__("file_ops", "Advanced file and folder management")
        self.allowed_dirs = allowed_dirs or [os.path.expanduser("~"), "/tmp"]
        self.sandbox = sandbox

    def _validate_path(self, path: str) -> tuple[bool, str]:
        """Validate that a path is within allowed directories."""
        resolved = os.path.realpath(os.path.expanduser(path))
        if not self.sandbox:
            return True, resolved
        for allowed in self.allowed_dirs:
            allowed_resolved = os.path.realpath(os.path.expanduser(allowed))
            if resolved.startswith(allowed_resolved):
                return True, resolved
        return False, f"Path '{path}' is outside allowed directories"

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        dispatch = {
            "read": self._read_file,
            "write": self._write_file,
            "append": self._append_file,
            "delete": self._delete,
            "copy": self._copy,
            "move": self._move,
            "mkdir": self._mkdir,
            "list": self._list_dir,
            "search": self._search,
            "info": self._file_info,
            "hash": self._file_hash,
            "tree": self._dir_tree,
            "find_replace": self._find_replace,
            "diff": self._diff_files,
            "temp_file": self._create_temp,
            "set_permissions": self._set_permissions,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "file_ops",
            "description": "Advanced file system operations",
            "parameters": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append", "delete", "copy", "move",
                             "mkdir", "list", "search", "info", "hash", "tree",
                             "find_replace", "diff", "temp_file", "set_permissions"],
                },
                "path": {"type": "string"},
                "content": {"type": "string"},
                "destination": {"type": "string"},
                "pattern": {"type": "string"},
                "recursive": {"type": "boolean", "default": False},
            },
        }

    async def _read_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            encoding = args.get("encoding", "utf-8")
            max_size = args.get("max_size", 10 * 1024 * 1024)  # 10MB
            size = os.path.getsize(resolved)
            if size > max_size:
                return ToolResult(success=False, error=f"File too large: {size} bytes (max: {max_size})")
            with open(resolved, "r", encoding=encoding) as f:
                content = f.read()
            return ToolResult(
                success=True,
                output=content,
                metadata={"path": resolved, "size": size, "lines": content.count("\n") + 1},
            )
        except UnicodeDecodeError:
            with open(resolved, "rb") as f:
                raw = f.read(1000)
            return ToolResult(
                success=True,
                output=f"[Binary file: {os.path.getsize(resolved)} bytes, first 1000: {raw.hex()[:200]}]",
                metadata={"binary": True},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _write_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            backup = None
            if os.path.exists(resolved):
                backup = resolved + ".bak"
                shutil.copy2(resolved, backup)
            with open(resolved, "w", encoding=args.get("encoding", "utf-8")) as f:
                f.write(content)
            return ToolResult(
                success=True,
                output=f"Written {len(content)} bytes to {resolved}",
                metadata={"path": resolved, "size": len(content), "backup": backup},
                artifacts=[resolved],
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _append_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            with open(resolved, "a", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, output=f"Appended {len(content)} bytes to {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _delete(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            if os.path.isfile(resolved):
                os.remove(resolved)
                return ToolResult(success=True, output=f"Deleted file: {resolved}")
            elif os.path.isdir(resolved):
                if args.get("recursive", False):
                    shutil.rmtree(resolved)
                    return ToolResult(success=True, output=f"Deleted directory: {resolved}")
                else:
                    os.rmdir(resolved)
                    return ToolResult(success=True, output=f"Deleted empty directory: {resolved}")
            return ToolResult(success=False, error=f"Path does not exist: {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _copy(self, args: dict) -> ToolResult:
        src = args.get("path", "")
        dst = args.get("destination", "")
        valid_s, resolved_s = self._validate_path(src)
        valid_d, resolved_d = self._validate_path(dst)
        if not valid_s:
            return ToolResult(success=False, error=resolved_s)
        if not valid_d:
            return ToolResult(success=False, error=resolved_d)
        try:
            if os.path.isdir(resolved_s):
                shutil.copytree(resolved_s, resolved_d, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(resolved_d), exist_ok=True)
                shutil.copy2(resolved_s, resolved_d)
            return ToolResult(success=True, output=f"Copied {resolved_s} → {resolved_d}", artifacts=[resolved_d])
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _move(self, args: dict) -> ToolResult:
        src = args.get("path", "")
        dst = args.get("destination", "")
        valid_s, resolved_s = self._validate_path(src)
        valid_d, resolved_d = self._validate_path(dst)
        if not valid_s:
            return ToolResult(success=False, error=resolved_s)
        if not valid_d:
            return ToolResult(success=False, error=resolved_d)
        try:
            os.makedirs(os.path.dirname(resolved_d), exist_ok=True)
            shutil.move(resolved_s, resolved_d)
            return ToolResult(success=True, output=f"Moved {resolved_s} → {resolved_d}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _mkdir(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            os.makedirs(resolved, exist_ok=True)
            return ToolResult(success=True, output=f"Created directory: {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _list_dir(self, args: dict) -> ToolResult:
        path = args.get("path", ".")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            entries = []
            for entry in sorted(os.listdir(resolved)):
                full = os.path.join(resolved, entry)
                st = os.stat(full)
                entries.append({
                    "name": entry,
                    "type": "dir" if os.path.isdir(full) else "file",
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "permissions": oct(st.st_mode)[-3:],
                })
            output = "\n".join(
                f"{'📁' if e['type'] == 'dir' else '📄'} {e['name']:40s} "
                f"{e['size']:>10,} bytes  {e['modified']}"
                for e in entries
            )
            return ToolResult(success=True, output=output, metadata={"count": len(entries), "entries": entries})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _search(self, args: dict) -> ToolResult:
        path = args.get("path", ".")
        pattern = args.get("pattern", "*")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            recursive = args.get("recursive", True)
            if recursive:
                matches = glob.glob(os.path.join(resolved, "**", pattern), recursive=True)
            else:
                matches = glob.glob(os.path.join(resolved, pattern))
            content_search = args.get("content", "")
            if content_search:
                filtered = []
                for m in matches:
                    if os.path.isfile(m):
                        try:
                            with open(m, "r") as f:
                                if content_search in f.read():
                                    filtered.append(m)
                        except (UnicodeDecodeError, PermissionError):
                            pass
                matches = filtered
            output = "\n".join(matches[:100])
            return ToolResult(
                success=True,
                output=output or "No matches found",
                metadata={"total_matches": len(matches), "shown": min(len(matches), 100)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _file_info(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            st = os.stat(resolved)
            info = {
                "path": resolved,
                "type": "directory" if os.path.isdir(resolved) else "file",
                "size": st.st_size,
                "permissions": oct(st.st_mode),
                "owner_uid": st.st_uid,
                "group_gid": st.st_gid,
                "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(st.st_atime).isoformat(),
            }
            if os.path.isfile(resolved):
                ext = os.path.splitext(resolved)[1]
                info["extension"] = ext
            output = "\n".join(f"{k}: {v}" for k, v in info.items())
            return ToolResult(success=True, output=output, metadata=info)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _file_hash(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            algo = args.get("algorithm", "sha256")
            h = hashlib.new(algo)
            with open(resolved, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            digest = h.hexdigest()
            return ToolResult(success=True, output=f"{algo}:{digest}", metadata={"algorithm": algo, "hash": digest})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _dir_tree(self, args: dict) -> ToolResult:
        path = args.get("path", ".")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        max_depth = args.get("max_depth", 4)
        lines = []
        file_count = 0
        dir_count = 0

        def walk(dirpath: str, prefix: str, depth: int):
            nonlocal file_count, dir_count
            if depth > max_depth:
                lines.append(f"{prefix}...")
                return
            try:
                entries = sorted(os.listdir(dirpath))
            except PermissionError:
                lines.append(f"{prefix}[Permission Denied]")
                return
            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                full = os.path.join(dirpath, entry)
                if os.path.isdir(full):
                    dir_count += 1
                    lines.append(f"{prefix}{connector}📁 {entry}/")
                    ext_prefix = prefix + ("    " if is_last else "│   ")
                    walk(full, ext_prefix, depth + 1)
                else:
                    file_count += 1
                    size = os.path.getsize(full)
                    lines.append(f"{prefix}{connector}📄 {entry} ({size:,} bytes)")

        lines.append(f"📁 {os.path.basename(resolved)}/")
        walk(resolved, "", 1)
        lines.append(f"\n{dir_count} directories, {file_count} files")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"dirs": dir_count, "files": file_count},
        )

    async def _find_replace(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        find = args.get("find", "")
        replace = args.get("replace", "")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            with open(resolved, "r") as f:
                content = f.read()
            count = content.count(find)
            if count == 0:
                return ToolResult(success=True, output="No matches found", metadata={"replacements": 0})
            new_content = content.replace(find, replace)
            shutil.copy2(resolved, resolved + ".bak")
            with open(resolved, "w") as f:
                f.write(new_content)
            return ToolResult(
                success=True,
                output=f"Replaced {count} occurrences",
                metadata={"replacements": count},
                artifacts=[resolved],
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _diff_files(self, args: dict) -> ToolResult:
        import difflib
        path_a = args.get("path", "")
        path_b = args.get("destination", "")
        valid_a, resolved_a = self._validate_path(path_a)
        valid_b, resolved_b = self._validate_path(path_b)
        if not valid_a:
            return ToolResult(success=False, error=resolved_a)
        if not valid_b:
            return ToolResult(success=False, error=resolved_b)
        try:
            with open(resolved_a) as f:
                lines_a = f.readlines()
            with open(resolved_b) as f:
                lines_b = f.readlines()
            diff = difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=path_b)
            output = "".join(diff)
            return ToolResult(success=True, output=output or "Files are identical")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _create_temp(self, args: dict) -> ToolResult:
        try:
            suffix = args.get("suffix", ".txt")
            prefix = args.get("prefix", "aether_")
            content = args.get("content", "")
            fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
            with os.fdopen(fd, "w") as f:
                f.write(content)
            return ToolResult(success=True, output=f"Created temp file: {path}", artifacts=[path])
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _set_permissions(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        mode = args.get("mode", "644")
        valid, resolved = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, error=resolved)
        try:
            os.chmod(resolved, int(mode, 8))
            return ToolResult(success=True, output=f"Set permissions {mode} on {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
