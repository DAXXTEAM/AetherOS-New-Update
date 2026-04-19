"""Status monitoring widget."""
from __future__ import annotations

import logging
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
        QGroupBox, QProgressBar, QFrame,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

from gui.theme import AetherTheme

logger = logging.getLogger("aetheros.gui.status")


if HAS_PYQT:
    class StatusCard(QFrame):
        """Individual status metric card."""

        def __init__(self, title: str, icon: str = "📊", parent=None):
            super().__init__(parent)
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {AetherTheme.BG_SECONDARY};
                    border: 1px solid {AetherTheme.BORDER};
                    border-radius: 8px;
                    padding: 12px;
                }}
            """)
            layout = QVBoxLayout(self)
            layout.setSpacing(4)

            header = QHBoxLayout()
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 20px; background: transparent;")
            header.addWidget(icon_label)
            title_label = QLabel(title)
            title_label.setStyleSheet(
                f"color: {AetherTheme.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            header.addWidget(title_label)
            header.addStretch()
            layout.addLayout(header)

            self._value_label = QLabel("--")
            self._value_label.setStyleSheet(
                f"color: {AetherTheme.TEXT_PRIMARY}; font-size: 24px; font-weight: 700; background: transparent;"
            )
            layout.addWidget(self._value_label)

            self._subtitle = QLabel("")
            self._subtitle.setStyleSheet(
                f"color: {AetherTheme.TEXT_MUTED}; font-size: 10px; background: transparent;"
            )
            layout.addWidget(self._subtitle)

        def set_value(self, value: str, subtitle: str = "", color: str = "") -> None:
            self._value_label.setText(value)
            if color:
                self._value_label.setStyleSheet(
                    f"color: {color}; font-size: 24px; font-weight: 700; background: transparent;"
                )
            if subtitle:
                self._subtitle.setText(subtitle)

    class StatusMonitor(QWidget):
        """System status monitoring panel."""

        status_updated = pyqtSignal(dict)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._setup_ui()
            self.status_updated.connect(self._update_display)

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            # Title
            title = QLabel("📡 System Status")
            title.setStyleSheet(
                f"color: {AetherTheme.TEXT_ACCENT}; font-weight: 600; font-size: 14px;"
            )
            layout.addWidget(title)

            # Status cards grid
            cards_layout = QGridLayout()
            cards_layout.setSpacing(8)

            self._status_card = StatusCard("System Status", "🔵")
            self._tasks_card = StatusCard("Active Tasks", "📋")
            self._completed_card = StatusCard("Completed", "✅")
            self._errors_card = StatusCard("Errors", "❌")
            self._model_card = StatusCard("Active Model", "🧠")
            self._uptime_card = StatusCard("Uptime", "⏱️")
            self._memory_card = StatusCard("Memory Entries", "💾")
            self._security_card = StatusCard("Security", "🛡️")

            cards_layout.addWidget(self._status_card, 0, 0)
            cards_layout.addWidget(self._tasks_card, 0, 1)
            cards_layout.addWidget(self._completed_card, 0, 2)
            cards_layout.addWidget(self._errors_card, 0, 3)
            cards_layout.addWidget(self._model_card, 1, 0)
            cards_layout.addWidget(self._uptime_card, 1, 1)
            cards_layout.addWidget(self._memory_card, 1, 2)
            cards_layout.addWidget(self._security_card, 1, 3)

            layout.addLayout(cards_layout)

            # Agent status section
            agents_group = QGroupBox("🤖 Agent Status")
            self._agents_layout = QVBoxLayout(agents_group)
            self._agent_labels: dict[str, QLabel] = {}
            layout.addWidget(agents_group)

            # Task progress
            progress_group = QGroupBox("📊 Current Task Progress")
            progress_layout = QVBoxLayout(progress_group)

            self._task_label = QLabel("No active task")
            self._task_label.setStyleSheet(f"color: {AetherTheme.TEXT_SECONDARY};")
            progress_layout.addWidget(self._task_label)

            self._progress_bar = QProgressBar()
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(0)
            progress_layout.addWidget(self._progress_bar)

            layout.addWidget(progress_group)
            layout.addStretch()

        def _update_display(self, state: dict) -> None:
            """Update all status displays."""
            status = state.get("status", "idle")
            color_map = {
                "idle": AetherTheme.TEXT_MUTED,
                "planning": AetherTheme.INFO,
                "executing": AetherTheme.SUCCESS,
                "auditing": AetherTheme.WARNING,
                "complete": AetherTheme.SUCCESS,
                "error": AetherTheme.ERROR,
                "killed": AetherTheme.CRITICAL,
            }
            self._status_card.set_value(
                status.upper(),
                color=color_map.get(status, AetherTheme.TEXT_PRIMARY),
            )
            self._tasks_card.set_value(str(state.get("active_tasks", 0)))
            self._completed_card.set_value(str(state.get("tasks_completed", 0)))
            err_count = state.get("total_errors", 0)
            self._errors_card.set_value(
                str(err_count),
                color=AetherTheme.ERROR if err_count > 0 else AetherTheme.SUCCESS,
            )
            self._model_card.set_value(
                state.get("model", "N/A"),
                subtitle="Active LLM Provider",
            )

            uptime = state.get("uptime_seconds", 0)
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            self._uptime_card.set_value(f"{hours}h {minutes}m")

            kill_switch = state.get("kill_switch", False)
            self._security_card.set_value(
                "🔴 KILLED" if kill_switch else "🟢 ARMED",
                color=AetherTheme.CRITICAL if kill_switch else AetherTheme.SUCCESS,
            )

            # Update agent statuses
            agents = state.get("agents", {})
            for name, agent_data in agents.items():
                if name not in self._agent_labels:
                    label = QLabel()
                    self._agent_labels[name] = label
                    self._agents_layout.addWidget(label)
                a_status = agent_data.get("status", "idle")
                role = agent_data.get("role", "")
                msgs = agent_data.get("messages_processed", 0)
                self._agent_labels[name].setText(
                    f"{'🟢' if a_status == 'active' else '⚪'} "
                    f"{name.title()} ({role}) — {a_status} | {msgs} msgs"
                )

        def update_progress(self, task_name: str, progress: float) -> None:
            self._task_label.setText(f"Task: {task_name}")
            self._progress_bar.setValue(int(progress * 100))

else:
    class StatusMonitor:
        """Stub when PyQt6 not available."""
        def __init__(self, *args, **kwargs):
            logger.info("StatusMonitor: PyQt6 not available")
        def update_progress(self, *args, **kwargs):
            pass
