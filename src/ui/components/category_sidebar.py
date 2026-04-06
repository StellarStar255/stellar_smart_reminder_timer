"""Category sidebar widget."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.models import Category
from typing import List, Optional


class CategoryButton(QPushButton):
    """A styled button for category selection."""

    def __init__(self, category: Optional[Category] = None, is_all: bool = False, parent=None):
        super().__init__(parent)

        self.category = category
        self.is_all = is_all
        self._selected = False
        self._dark_mode = False

        if is_all:
            self.setText("全部")
        elif category:
            self.setText(f"{category.icon} {category.name}")

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._update_style()

    def setSelected(self, selected: bool):
        """Set selection state."""
        self._selected = selected
        self.setChecked(selected)
        self._update_style()

    def _update_style(self):
        """Update button style based on state and dark mode."""
        if self._selected:
            bg = "#0a84ff" if self._dark_mode else "#007AFF"
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-size: 13px;
                    text-align: left;
                }}
            """)
        else:
            if self._dark_mode:
                self.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #ffffff;
                        border: none;
                        border-radius: 8px;
                        padding: 10px 16px;
                        font-size: 13px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #2c2c2e;
                    }
                """)
            else:
                self.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #1d1d1f;
                        border: none;
                        border-radius: 8px;
                        padding: 10px 16px;
                        font-size: 13px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #f5f5f7;
                    }
                """)


class CategorySidebar(QWidget):
    """Sidebar showing categories and quick stats."""

    # Signals
    category_selected = pyqtSignal(object)  # Category or None for "all"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._categories: List[Category] = []
        self._selected_category: Optional[Category] = None
        self._buttons: List[CategoryButton] = []

        self._today_completed = 0
        self._today_duration = 0

        self._setup_ui()

    def _setup_ui(self):
        """Set up the sidebar UI."""
        self.setFixedWidth(160)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        # Title
        title = QLabel("分类")
        title.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: 600;
                color: #6e6e73;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        layout.addWidget(title)
        layout.addSpacing(8)

        # Category buttons container
        self.buttons_layout = QVBoxLayout()
        self.buttons_layout.setSpacing(2)
        layout.addLayout(self.buttons_layout)

        # Add "All" button
        all_btn = CategoryButton(is_all=True)
        all_btn.setSelected(True)
        all_btn.clicked.connect(lambda: self._on_category_clicked(None))
        self.buttons_layout.addWidget(all_btn)
        self._buttons.append(all_btn)

        layout.addStretch()

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("QFrame { background-color: #e5e5ea; }")
        separator.setFixedHeight(1)
        layout.addWidget(separator)
        layout.addSpacing(12)

        # Today's stats
        stats_title = QLabel("今日统计")
        stats_title.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: 600;
                color: #6e6e73;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        layout.addWidget(stats_title)
        layout.addSpacing(8)

        # Completed count
        completed_layout = QHBoxLayout()
        completed_label = QLabel("完成")
        completed_label.setStyleSheet("font-size: 13px; color: #6e6e73;")
        self.completed_value = QLabel("0")
        self.completed_value.setStyleSheet("font-size: 13px; font-weight: 600; color: #1d1d1f;")
        completed_layout.addWidget(completed_label)
        completed_layout.addStretch()
        completed_layout.addWidget(self.completed_value)
        layout.addLayout(completed_layout)

        # Duration
        duration_layout = QHBoxLayout()
        duration_label = QLabel("时长")
        duration_label.setStyleSheet("font-size: 13px; color: #6e6e73;")
        self.duration_value = QLabel("0分钟")
        self.duration_value.setStyleSheet("font-size: 13px; font-weight: 600; color: #1d1d1f;")
        duration_layout.addWidget(duration_label)
        duration_layout.addStretch()
        duration_layout.addWidget(self.duration_value)
        layout.addLayout(duration_layout)

    def set_categories(self, categories: List[Category]):
        """Set the categories to display."""
        self._categories = categories

        # Remove existing category buttons (keep "All" button)
        while len(self._buttons) > 1:
            btn = self._buttons.pop()
            self.buttons_layout.removeWidget(btn)
            btn.deleteLater()

        # Add category buttons
        for category in categories:
            btn = CategoryButton(category=category)
            btn.clicked.connect(lambda checked, c=category: self._on_category_clicked(c))
            self.buttons_layout.addWidget(btn)
            self._buttons.append(btn)

    def _on_category_clicked(self, category: Optional[Category]):
        """Handle category button click."""
        self._selected_category = category

        # Update button states
        for btn in self._buttons:
            if btn.is_all:
                btn.setSelected(category is None)
            else:
                btn.setSelected(btn.category == category)

        self.category_selected.emit(category)

    def update_stats(self, completed: int, duration_seconds: int):
        """Update today's statistics."""
        self._today_completed = completed
        self._today_duration = duration_seconds

        self.completed_value.setText(str(completed))

        # Format duration
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        if hours > 0:
            self.duration_value.setText(f"{hours}小时{minutes}分钟")
        else:
            self.duration_value.setText(f"{minutes}分钟")

    def get_selected_category(self) -> Optional[Category]:
        """Get the currently selected category."""
        return self._selected_category

    def set_dark_mode(self, enabled: bool):
        """Toggle dark mode styling."""
        if enabled:
            self.setStyleSheet("""
                QWidget {
                    background-color: #1c1c1e;
                }
            """)
        else:
            self.setStyleSheet("")

        for btn in self._buttons:
            btn._dark_mode = enabled
            btn._update_style()
