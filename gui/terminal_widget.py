"""Terminal widget for real-time log display."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

try:
    from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

from gui.theme import AetherTheme

logger = logging.getLogger("aetheros.gui.terminal")


if HAS_PYQT:
    class TerminalWidget(QWidget):
        """Real-time terminal log display widget."""

        log_received = pyqtSignal(dict)

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self._max_lines = 5000
            self._auto_scroll = True
            self._log_level_filter = "ALL"
            self._setup_ui()
            self.log_received.connect(self._append_log)

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            # Toolbar
            toolbar = QHBoxLayout()
            toolbar.setSpacing(8)

            self._title = QLabel("  Terminal Output")
            self._title.setStyleSheet(f"color: {AetherTheme.TEXT_ACCENT}; font-weight: 600; font-size: 14px;")
            toolbar.addWidget(self._title)

            toolbar.addStretch()

            # Log level filter
            self._level_combo = QComboBox()
            self._level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            self._level_combo.setCurrentText("ALL")
            self._level_combo.currentTextChanged.connect(self._on_filter_changed)
            self._level_combo.setFixedWidth(120)
            toolbar.addWidget(QLabel("Filter:"))
            toolbar.addWidget(self._level_combo)

            # Auto-scroll toggle
            self._scroll_btn = QPushButton("  Auto-Scroll")
            self._scroll_btn.setCheckable(True)
            self._scroll_btn.setChecked(True)
            self._scroll_btn.clicked.connect(self._toggle_autoscroll)
            self._scroll_btn.setFixedWidth(120)
            toolbar.addWidget(self._scroll_btn)

            # Clear button
            clear_btn = QPushButton("  Clear")
            clear_btn.clicked.connect(self.clear)
            clear_btn.setFixedWidth(80)
            toolbar.addWidget(clear_btn)

            layout.addLayout(toolbar)

            # Terminal display
            self._terminal = QPlainTextEdit()
            self._terminal.setReadOnly(True)
            self._terminal.setFont(QFont("JetBrains Mono, Consolas, monospace", AetherTheme.FONT_SIZE_TERMINAL))
            self._terminal.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {AetherTheme.TERMINAL_BG};
                    color: {AetherTheme.TERMINAL_FG};
                    border: 1px solid {AetherTheme.BORDER};
                    border-radius: 6px;
                    padding: 8px;
                }}
            """)
            self._terminal.setMaximumBlockCount(self._max_lines)
            layout.addWidget(self._terminal)

            # Line count indicator
            self._status = QLabel("Lines: 0")
            self._status.setStyleSheet(f"color: {AetherTheme.TEXT_MUTED}; font-size: 11px;")
            layout.addWidget(self._status)

        def _on_filter_changed(self, level: str) -> None:
            self._log_level_filter = level

        def _toggle_autoscroll(self, checked: bool) -> None:
            self._auto_scroll = checked

        def _append_log(self, entry: dict) -> None:
            level = entry.get("level", "INFO")
            if self._log_level_filter != "ALL":
                levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
                if levels.index(level) < levels.index(self._log_level_filter):
                    return

            color_map = {
                "DEBUG": AetherTheme.TEXT_MUTED,
                "INFO": AetherTheme.TEXT_PRIMARY,
                "WARNING": AetherTheme.WARNING,
                "ERROR": AetherTheme.ERROR,
                "CRITICAL": AetherTheme.CRITICAL,
            }
            color = color_map.get(level, AetherTheme.TEXT_PRIMARY)
            timestamp = entry.get("timestamp", datetime.now().strftime("%H:%M:%S"))
            message = entry.get("message", "")

            cursor = self._terminal.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)

            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.insertText(f"[{timestamp}] [{level:8s}] {message}\n", fmt)

            if self._auto_scroll:
                self._terminal.setTextCursor(cursor)
                self._terminal.ensureCursorVisible()

            self._status.setText(f"Lines: {self._terminal.blockCount()}")

        def append_text(self, text: str, level: str = "INFO") -> None:
            """Programmatic log append."""
            self.log_received.emit({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": level,
                "message": text,
            })

        def clear(self) -> None:
            self._terminal.clear()
            self._status.setText("Lines: 0")

else:
    class TerminalWidget:
        """Stub when PyQt6 is not available."""
        def __init__(self, *args, **kwargs):
            logger.info("TerminalWidget: PyQt6 not available, running in headless mode")
        def append_text(self, text: str, level: str = "INFO") -> None:
            pass
        def clear(self) -> None:
            pass
