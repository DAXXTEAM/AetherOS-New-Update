"""Main AetherOS Control Panel GUI."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QTextEdit, QTabWidget,
        QSplitter, QGroupBox, QComboBox, QStatusBar, QMenuBar,
        QMenu, QMessageBox, QFrame, QGridLayout, QCheckBox,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
    from PyQt6.QtGui import QFont, QIcon, QAction
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

from gui.theme import AetherTheme
if HAS_PYQT:
    from gui.terminal_widget import TerminalWidget
    from gui.status_monitor import StatusMonitor

logger = logging.getLogger("aetheros.gui.control_panel")


if HAS_PYQT:
    class ControlPanel(QMainWindow):
        """AetherOS Control Panel - Main GUI Window."""

        task_submitted = pyqtSignal(str)
        kill_switch_triggered = pyqtSignal()
        model_changed = pyqtSignal(str, str)

        def __init__(self, system_state=None):
            super().__init__()
            self._system_state = system_state
            self._setup_window()
            self._setup_menubar()
            self._setup_ui()
            self._setup_statusbar()
            self._setup_refresh_timer()

        def _setup_window(self) -> None:
            self.setWindowTitle("AetherOS Control Panel v1.0")
            self.setMinimumSize(1400, 900)
            self.resize(1600, 1000)
            self.setStyleSheet(AetherTheme.get_stylesheet())

        def _setup_menubar(self) -> None:
            menubar = self.menuBar()

            # File menu
            file_menu = menubar.addMenu("&File")
            new_task = QAction("&New Task", self)
            new_task.setShortcut("Ctrl+N")
            file_menu.addAction(new_task)
            file_menu.addSeparator()
            exit_action = QAction("E&xit", self)
            exit_action.setShortcut("Ctrl+Q")
            exit_action.triggered.connect(self.close)
            file_menu.addAction(exit_action)

            # View menu
            view_menu = menubar.addMenu("&View")
            clear_logs = QAction("&Clear Logs", self)
            clear_logs.setShortcut("Ctrl+L")
            view_menu.addAction(clear_logs)

            # Security menu
            security_menu = menubar.addMenu("&Security")
            kill_action = QAction("🚨 &Kill Switch", self)
            kill_action.setShortcut("Ctrl+Shift+K")
            kill_action.triggered.connect(self._on_kill_switch)
            security_menu.addAction(kill_action)

            # Help menu
            help_menu = menubar.addMenu("&Help")
            about = QAction("&About AetherOS", self)
            about.triggered.connect(self._show_about)
            help_menu.addAction(about)

        def _setup_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(12, 8, 12, 8)
            main_layout.setSpacing(8)

            # Header
            header = self._create_header()
            main_layout.addWidget(header)

            # Main content: splitter with left (controls + status) and right (terminal)
            splitter = QSplitter(Qt.Orientation.Horizontal)

            # Left panel: Task input + Status
            left_panel = QWidget()
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Task input section
            task_group = self._create_task_input()
            left_layout.addWidget(task_group)

            # Model selection
            model_group = self._create_model_selector()
            left_layout.addWidget(model_group)

            # Status monitor
            self._status_monitor = StatusMonitor()
            left_layout.addWidget(self._status_monitor)

            splitter.addWidget(left_panel)

            # Right panel: Terminal + Tabs
            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(0, 0, 0, 0)

            # Tab widget for terminal, audit, memory
            tabs = QTabWidget()

            # Terminal tab
            self._terminal = TerminalWidget()
            tabs.addTab(self._terminal, "📟 Terminal")

            # Audit tab
            audit_widget = QWidget()
            audit_layout = QVBoxLayout(audit_widget)
            self._audit_text = QTextEdit()
            self._audit_text.setReadOnly(True)
            self._audit_text.setFont(QFont("JetBrains Mono", 11))
            self._audit_text.setStyleSheet(f"""
                background-color: {AetherTheme.TERMINAL_BG};
                color: {AetherTheme.TERMINAL_FG};
                border: 1px solid {AetherTheme.BORDER};
                border-radius: 6px;
            """)
            audit_layout.addWidget(self._audit_text)
            tabs.addTab(audit_widget, "🛡️ Audit Log")

            # Memory tab
            memory_widget = QWidget()
            memory_layout = QVBoxLayout(memory_widget)
            search_bar = QHBoxLayout()
            self._memory_search = QLineEdit()
            self._memory_search.setPlaceholderText("Search memories...")
            search_bar.addWidget(self._memory_search)
            search_btn = QPushButton("🔍 Search")
            search_bar.addWidget(search_btn)
            memory_layout.addLayout(search_bar)
            self._memory_text = QTextEdit()
            self._memory_text.setReadOnly(True)
            self._memory_text.setStyleSheet(f"""
                background-color: {AetherTheme.TERMINAL_BG};
                color: {AetherTheme.TERMINAL_FG};
            """)
            memory_layout.addWidget(self._memory_text)
            tabs.addTab(memory_widget, "💾 Memory")

            # Tools tab
            tools_widget = QWidget()
            tools_layout = QVBoxLayout(tools_widget)
            self._tools_text = QTextEdit()
            self._tools_text.setReadOnly(True)
            tools_layout.addWidget(self._tools_text)
            tabs.addTab(tools_widget, "🔧 Tools")

            right_layout.addWidget(tabs)
            splitter.addWidget(right_panel)

            splitter.setSizes([500, 900])
            main_layout.addWidget(splitter)

        def _create_header(self) -> QFrame:
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {AetherTheme.BG_SECONDARY};
                    border: 1px solid {AetherTheme.BORDER};
                    border-radius: 8px;
                    padding: 8px;
                }}
            """)
            layout = QHBoxLayout(frame)

            logo = QLabel("⚡ AetherOS")
            logo.setStyleSheet(f"color: {AetherTheme.TEXT_ACCENT}; font-size: 22px; font-weight: 700; background: transparent;")
            layout.addWidget(logo)

            version = QLabel("v1.0.0 Prometheus")
            version.setStyleSheet(f"color: {AetherTheme.TEXT_MUTED}; font-size: 12px; background: transparent;")
            layout.addWidget(version)

            layout.addStretch()

            # Kill Switch button
            kill_btn = QPushButton("🚨 KILL SWITCH")
            kill_btn.setObjectName("dangerBtn")
            kill_btn.setFixedWidth(150)
            kill_btn.clicked.connect(self._on_kill_switch)
            layout.addWidget(kill_btn)

            return frame

        def _create_task_input(self) -> QGroupBox:
            group = QGroupBox("🎯 Task Input")
            layout = QVBoxLayout(group)

            self._task_input = QTextEdit()
            self._task_input.setPlaceholderText(
                "Describe your task here...\n\n"
                "Examples:\n"
                "• Find all Python files larger than 1MB\n"
                "• Create a new project structure for a Flask app\n"
                "• Search the web for latest Python security advisories"
            )
            self._task_input.setMaximumHeight(150)
            layout.addWidget(self._task_input)

            btn_layout = QHBoxLayout()

            submit_btn = QPushButton("▶ Execute Task")
            submit_btn.setObjectName("primaryBtn")
            submit_btn.clicked.connect(self._on_submit)
            btn_layout.addWidget(submit_btn)

            plan_btn = QPushButton("📋 Plan Only")
            plan_btn.clicked.connect(self._on_plan)
            btn_layout.addWidget(plan_btn)

            clear_btn = QPushButton("🗑 Clear")
            clear_btn.clicked.connect(lambda: self._task_input.clear())
            btn_layout.addWidget(clear_btn)

            layout.addLayout(btn_layout)
            return group

        def _create_model_selector(self) -> QGroupBox:
            group = QGroupBox("🧠 Model Configuration")
            layout = QGridLayout(group)

            layout.addWidget(QLabel("Provider:"), 0, 0)
            self._provider_combo = QComboBox()
            self._provider_combo.addItems(["OpenAI", "Anthropic", "Google", "Ollama"])
            self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
            layout.addWidget(self._provider_combo, 0, 1)

            layout.addWidget(QLabel("Model:"), 1, 0)
            self._model_combo = QComboBox()
            self._model_combo.addItems(["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"])
            layout.addWidget(self._model_combo, 1, 1)

            layout.addWidget(QLabel("Sandbox:"), 2, 0)
            self._sandbox_check = QCheckBox("Enable sandbox mode")
            self._sandbox_check.setChecked(True)
            layout.addWidget(self._sandbox_check, 2, 1)

            return group

        def _setup_statusbar(self) -> None:
            status = self.statusBar()
            self._status_label = QLabel("Ready")
            status.addPermanentWidget(self._status_label)

        def _setup_refresh_timer(self) -> None:
            self._timer = QTimer()
            self._timer.timeout.connect(self._refresh_status)
            self._timer.start(2000)

        def _on_submit(self) -> None:
            task = self._task_input.toPlainText().strip()
            if task:
                self._terminal.append_text(f"Task submitted: {task}", "INFO")
                self.task_submitted.emit(task)
                self._status_label.setText("Task executing...")

        def _on_plan(self) -> None:
            task = self._task_input.toPlainText().strip()
            if task:
                self._terminal.append_text(f"Planning: {task}", "INFO")

        def _on_kill_switch(self) -> None:
            reply = QMessageBox.warning(
                self,
                "⚠️ Kill Switch",
                "This will immediately stop all agent operations.\n\nAre you sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._terminal.append_text("🚨 KILL SWITCH ENGAGED", "CRITICAL")
                self.kill_switch_triggered.emit()

        def _on_provider_changed(self, provider: str) -> None:
            models = {
                "OpenAI": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                "Anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus", "claude-3-haiku"],
                "Google": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
                "Ollama": ["llama3:latest", "mistral:latest", "codellama:latest"],
            }
            self._model_combo.clear()
            self._model_combo.addItems(models.get(provider, []))
            self.model_changed.emit(provider.lower(), self._model_combo.currentText())

        def _refresh_status(self) -> None:
            if self._system_state:
                state_dict = self._system_state.to_dict()
                self._status_monitor.status_updated.emit(state_dict)
                self._status_label.setText(f"Status: {state_dict.get('status', 'idle').upper()}")

        def _show_about(self) -> None:
            QMessageBox.about(
                self,
                "About AetherOS",
                "AetherOS v1.0.0 — Prometheus\n\n"
                "Autonomous AI Agent System\n"
                "Multi-agent orchestration with LangGraph\n"
                "Quantum-safe cryptography\n"
                "Real-time monitoring and control\n\n"
                "© 2024 AetherOS Project",
            )

        def log(self, message: str, level: str = "INFO") -> None:
            """External log interface."""
            self._terminal.append_text(message, level)

        def update_audit(self, entries: list[dict]) -> None:
            text = "\n".join(
                f"[{e.get('timestamp', '')}] [{e.get('severity', '')}] "
                f"{e.get('action', '')} → {e.get('target', '')}"
                for e in entries
            )
            self._audit_text.setPlainText(text)

else:
    class ControlPanel:
        """Stub when PyQt6 not available."""
        def __init__(self, *args, **kwargs):
            logger.info("ControlPanel: PyQt6 not available, running headless")
        def log(self, message: str, level: str = "INFO") -> None:
            logger.log(getattr(logging, level, logging.INFO), message)
        def show(self) -> None:
            logger.info("GUI show() called but PyQt6 not available")
