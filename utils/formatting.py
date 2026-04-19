"""AetherOS Utils   Formatting Utilities."""
from datetime import datetime, timedelta
from typing import Union


class FormatUtils:
    """Common formatting operations."""

    @staticmethod
    def human_bytes(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def human_duration(seconds: float) -> str:
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        if seconds < 3600:
            return f"{seconds / 60:.1f}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    @staticmethod
    def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def relative_time(dt: datetime) -> str:
        delta = datetime.utcnow() - dt
        if delta.total_seconds() < 60:
            return "just now"
        if delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)} minutes ago"
        if delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)} hours ago"
        return f"{delta.days} days ago"

    @staticmethod
    def table(headers: list, rows: list, padding: int = 2) -> str:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        sep = "+" + "+".join("-" * (w + padding * 2) for w in widths) + "+"
        def fmt_row(cells):
            return "|" + "|".join(
                f"{' ' * padding}{str(c).ljust(w)}{' ' * padding}"
                for c, w in zip(cells, widths)
            ) + "|"
        lines = [sep, fmt_row(headers), sep]
        for row in rows:
            lines.append(fmt_row(row))
        lines.append(sep)
        return "\n".join(lines)
