"""Dark theme definition for AetherOS Control Panel."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AetherTheme:
    """Professional dark theme colors and styles."""

    # Primary palette
    BG_PRIMARY = "#0d1117"
    BG_SECONDARY = "#161b22"
    BG_TERTIARY = "#21262d"
    BG_HOVER = "#30363d"
    BG_ACTIVE = "#388bfd26"

    # Text colors
    TEXT_PRIMARY = "#e6edf3"
    TEXT_SECONDARY = "#8b949e"
    TEXT_MUTED = "#6e7681"
    TEXT_ACCENT = "#58a6ff"

    # Semantic colors
    SUCCESS = "#3fb950"
    WARNING = "#d29922"
    ERROR = "#f85149"
    INFO = "#58a6ff"
    CRITICAL = "#ff6b6b"

    # Borders
    BORDER = "#30363d"
    BORDER_ACTIVE = "#58a6ff"

    # Specific elements
    TERMINAL_BG = "#010409"
    TERMINAL_FG = "#c9d1d9"
    TERMINAL_CURSOR = "#58a6ff"

    # Font
    FONT_MONO = "JetBrains Mono, Consolas, Monaco, Courier New, monospace"
    FONT_UI = "Inter, Segoe UI, system-ui, sans-serif"
    FONT_SIZE = 13
    FONT_SIZE_SMALL = 11
    FONT_SIZE_TERMINAL = 12

    @classmethod
    def get_stylesheet(cls) -> str:
        """Generate the complete Qt stylesheet."""
        return f"""
        /* Main Window */
        QMainWindow {{
            background-color: {cls.BG_PRIMARY};
            color: {cls.TEXT_PRIMARY};
        }}

        /* Central Widget */
        QWidget {{
            background-color: {cls.BG_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-family: {cls.FONT_UI};
            font-size: {cls.FONT_SIZE}px;
        }}

        /* Group Boxes */
        QGroupBox {{
            background-color: {cls.BG_SECONDARY};
            border: 1px solid {cls.BORDER};
            border-radius: 8px;
            margin-top: 12px;
            padding: 16px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: {cls.TEXT_ACCENT};
        }}

        /* Labels */
        QLabel {{
            color: {cls.TEXT_PRIMARY};
            background: transparent;
        }}

        /* Buttons */
        QPushButton {{
            background-color: {cls.BG_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 500;
            min-height: 28px;
        }}
        QPushButton:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.TEXT_SECONDARY};
        }}
        QPushButton:pressed {{
            background-color: {cls.BG_ACTIVE};
            border-color: {cls.BORDER_ACTIVE};
        }}
        QPushButton:disabled {{
            color: {cls.TEXT_MUTED};
            background-color: {cls.BG_SECONDARY};
        }}

        /* Primary Button */
        QPushButton#primaryBtn {{
            background-color: #238636;
            border-color: #2ea043;
            color: white;
        }}
        QPushButton#primaryBtn:hover {{
            background-color: #2ea043;
        }}

        /* Danger Button */
        QPushButton#dangerBtn {{
            background-color: #da3633;
            border-color: {cls.ERROR};
            color: white;
        }}
        QPushButton#dangerBtn:hover {{
            background-color: {cls.ERROR};
        }}

        /* Line Edits */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {cls.BG_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 8px;
            selection-background-color: {cls.BG_ACTIVE};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {cls.BORDER_ACTIVE};
        }}

        /* Combo Boxes */
        QComboBox {{
            background-color: {cls.BG_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 6px 12px;
            min-height: 28px;
        }}
        QComboBox:hover {{
            border-color: {cls.TEXT_SECONDARY};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 30px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            selection-background-color: {cls.BG_HOVER};
        }}

        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {cls.BORDER};
            border-radius: 4px;
            background-color: {cls.BG_SECONDARY};
        }}
        QTabBar::tab {{
            background-color: {cls.BG_TERTIARY};
            color: {cls.TEXT_SECONDARY};
            border: 1px solid {cls.BORDER};
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}
        QTabBar::tab:selected {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border-bottom: 2px solid {cls.BORDER_ACTIVE};
        }}
        QTabBar::tab:hover {{
            color: {cls.TEXT_PRIMARY};
            background-color: {cls.BG_HOVER};
        }}

        /* Progress Bar */
        QProgressBar {{
            background-color: {cls.BG_TERTIARY};
            border: 1px solid {cls.BORDER};
            border-radius: 4px;
            height: 20px;
            text-align: center;
            color: {cls.TEXT_PRIMARY};
        }}
        QProgressBar::chunk {{
            background-color: {cls.SUCCESS};
            border-radius: 3px;
        }}

        /* Scroll Bar */
        QScrollBar:vertical {{
            background: {cls.BG_PRIMARY};
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {cls.BG_HOVER};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {cls.TEXT_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {cls.BG_PRIMARY};
            height: 10px;
        }}
        QScrollBar::handle:horizontal {{
            background: {cls.BG_HOVER};
            border-radius: 5px;
            min-width: 30px;
        }}

        /* Status Bar */
        QStatusBar {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_SECONDARY};
            border-top: 1px solid {cls.BORDER};
        }}

        /* Menu Bar */
        QMenuBar {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border-bottom: 1px solid {cls.BORDER};
        }}
        QMenuBar::item:selected {{
            background-color: {cls.BG_HOVER};
        }}
        QMenu {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
        }}
        QMenu::item:selected {{
            background-color: {cls.BG_HOVER};
        }}

        /* Splitter */
        QSplitter::handle {{
            background-color: {cls.BORDER};
            height: 2px;
            width: 2px;
        }}

        /* Tool Tip */
        QToolTip {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            padding: 4px 8px;
            border-radius: 4px;
        }}

        /* List Widget */
        QListWidget {{
            background-color: {cls.BG_TERTIARY};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
        }}
        QListWidget::item {{
            padding: 4px 8px;
            border-bottom: 1px solid {cls.BORDER};
        }}
        QListWidget::item:selected {{
            background-color: {cls.BG_ACTIVE};
            color: {cls.TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: {cls.BG_HOVER};
        }}

        /* Table Widget */
        QTableWidget, QTableView {{
            background-color: {cls.BG_TERTIARY};
            border: 1px solid {cls.BORDER};
            gridline-color: {cls.BORDER};
            border-radius: 6px;
        }}
        QHeaderView::section {{
            background-color: {cls.BG_SECONDARY};
            color: {cls.TEXT_PRIMARY};
            padding: 6px;
            border: 1px solid {cls.BORDER};
            font-weight: 600;
        }}

        /* Check Box */
        QCheckBox {{
            color: {cls.TEXT_PRIMARY};
            spacing: 8px;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {cls.BORDER};
            border-radius: 4px;
            background: {cls.BG_TERTIARY};
        }}
        QCheckBox::indicator:checked {{
            background: {cls.INFO};
            border-color: {cls.INFO};
        }}

        /* Spin Box */
        QSpinBox, QDoubleSpinBox {{
            background-color: {cls.BG_TERTIARY};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        """
