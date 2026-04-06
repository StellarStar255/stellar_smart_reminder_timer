"""Application theme and styles."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Theme:
    """Application color theme."""

    # Primary colors
    primary: str
    primary_hover: str
    primary_pressed: str

    # Background colors
    background: str
    surface: str
    card: str

    # Text colors
    text_primary: str
    text_secondary: str
    text_muted: str

    # Status colors
    success: str
    warning: str
    error: str

    # Border colors
    border: str
    border_light: str

    # Accent colors
    accent_work: str
    accent_study: str
    accent_rest: str
    accent_exercise: str

    def get_stylesheet(self) -> str:
        """Generate Qt stylesheet from theme."""
        return f"""
            QMainWindow, QWidget {{
                background-color: {self.background};
                color: {self.text_primary};
            }}

            QLabel {{
                color: {self.text_primary};
            }}

            QPushButton {{
                background-color: {self.primary};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }}

            QPushButton:hover {{
                background-color: {self.primary_hover};
            }}

            QPushButton:pressed {{
                background-color: {self.primary_pressed};
            }}

            QPushButton:disabled {{
                background-color: {self.border};
                color: {self.text_muted};
            }}

            QPushButton[class="secondary"] {{
                background-color: {self.surface};
                color: {self.text_primary};
                border: 1px solid {self.border};
            }}

            QPushButton[class="secondary"]:hover {{
                background-color: {self.border_light};
            }}

            QPushButton[class="danger"] {{
                background-color: {self.error};
            }}

            QPushButton[class="danger"]:hover {{
                background-color: #c0392b;
            }}

            QLineEdit, QTextEdit, QSpinBox {{
                background-color: {self.surface};
                border: 1px solid {self.border};
                border-radius: 6px;
                padding: 8px;
                color: {self.text_primary};
            }}

            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{
                border-color: {self.primary};
            }}

            QComboBox {{
                background-color: {self.surface};
                border: 1px solid {self.border};
                border-radius: 6px;
                padding: 8px;
                color: {self.text_primary};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {self.surface};
                border: 1px solid {self.border};
                selection-background-color: {self.primary};
            }}

            QScrollArea {{
                border: none;
                background-color: transparent;
            }}

            QScrollBar:vertical {{
                background-color: {self.background};
                width: 8px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical {{
                background-color: {self.border};
                border-radius: 4px;
                min-height: 20px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {self.text_muted};
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QMenu {{
                background-color: {self.surface};
                border: 1px solid {self.border};
                border-radius: 8px;
                padding: 4px;
            }}

            QMenu::item {{
                padding: 2px 8px;
                border-radius: 4px;
            }}

            QMenu::item:selected {{
                background-color: {self.primary};
                color: white;
            }}

            QToolTip {{
                background-color: {self.card};
                color: {self.text_primary};
                border: 1px solid {self.border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """


# Light theme
LIGHT_THEME = Theme(
    # Primary colors
    primary="#007AFF",
    primary_hover="#0056b3",
    primary_pressed="#004085",

    # Background colors
    background="#f5f5f7",
    surface="#ffffff",
    card="#ffffff",

    # Text colors
    text_primary="#1d1d1f",
    text_secondary="#6e6e73",
    text_muted="#aeaeb2",

    # Status colors
    success="#34c759",
    warning="#ff9f0a",
    error="#ff3b30",

    # Border colors
    border="#d2d2d7",
    border_light="#e5e5ea",

    # Accent colors
    accent_work="#FF6B6B",
    accent_study="#4ECDC4",
    accent_rest="#45B7D1",
    accent_exercise="#96CEB4",
)


# Dark theme
DARK_THEME = Theme(
    # Primary colors
    primary="#0a84ff",
    primary_hover="#409cff",
    primary_pressed="#0066cc",

    # Background colors
    background="#1c1c1e",
    surface="#2c2c2e",
    card="#3a3a3c",

    # Text colors
    text_primary="#ffffff",
    text_secondary="#ebebf5",
    text_muted="#8e8e93",

    # Status colors
    success="#30d158",
    warning="#ffd60a",
    error="#ff453a",

    # Border colors
    border="#48484a",
    border_light="#3a3a3c",

    # Accent colors
    accent_work="#FF6B6B",
    accent_study="#4ECDC4",
    accent_rest="#45B7D1",
    accent_exercise="#96CEB4",
)
