"""Timer card widget for displaying individual task timers."""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QMenu,
    QDialog, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag
from typing import List

from src.models import Task, TaskStatus, Category
from src.ui.components.circular_progress import CircularProgress


class TimerCard(QFrame):
    """A card widget displaying a single task timer."""

    # Signals
    toggle_clicked = pyqtSignal(int)  # task_id
    stop_clicked = pyqtSignal(int)  # task_id
    delete_clicked = pyqtSignal(int)  # task_id
    edit_requested = pyqtSignal(int)  # task_id
    notebook_requested = pyqtSignal(str)  # task_name

    def __init__(self, task: Task, category: Category = None, parent=None):
        super().__init__(parent)

        self.task = task
        self.category = category

        self._setup_ui()
        self._update_display()

        # Enable right-click context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_ui(self):
        """Set up the card UI."""
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setObjectName("timerCard")

        # Card styling
        self.setStyleSheet("""
            QFrame#timerCard {
                background-color: #ffffff;
                border: 1px solid #e5e5ea;
                border-radius: 12px;
                padding: 16px;
            }
            QFrame#timerCard:hover {
                border-color: #d2d2d7;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Category indicator
        self.category_label = QLabel()
        self.category_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #6e6e73;
            }
        """)
        layout.addWidget(self.category_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Circular progress - clickable to toggle timer
        self.progress = CircularProgress()
        self.progress.setMinimumSize(140, 140)
        self.progress.clicked.connect(self._on_toggle)
        self.progress.setToolTip("点击暂停/继续")
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignCenter)

        # Task name
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: 500;
                color: #1d1d1f;
            }
        """)
        layout.addWidget(self.name_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.toggle_btn = QPushButton("开始")
        self.toggle_btn.setMinimumWidth(70)
        self.toggle_btn.clicked.connect(self._on_toggle)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumWidth(70)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e5e5ea;
            }
        """)

        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(200)

    def _update_display(self):
        """Update the display based on current task state."""
        # Update name
        self.name_label.setText(self.task.name)

        # Update category
        if self.category:
            self.category_label.setText(f"{self.category.icon} {self.category.name}")
            self.progress.setProgressColor(self.category.color)
        else:
            self.category_label.setText("")

        # Update progress
        self.progress.setProgress(self.task.progress)
        self.progress.setTimeText(self.task.format_remaining())

        # Update status and button
        if self.task.status == TaskStatus.RUNNING:
            self.toggle_btn.setText("暂停")
            self.progress.setStatusText("计时中")
            self.stop_btn.setEnabled(True)
        elif self.task.status == TaskStatus.PAUSED:
            self.toggle_btn.setText("继续")
            self.progress.setStatusText("已暂停")
            self.stop_btn.setEnabled(True)
        elif self.task.status == TaskStatus.COMPLETED:
            self.toggle_btn.setText("完成")
            self.toggle_btn.setEnabled(False)
            self.progress.setStatusText("已完成")
            self.stop_btn.setEnabled(False)
        else:
            self.toggle_btn.setText("开始")
            self.progress.setStatusText("")
            self.stop_btn.setEnabled(False)

    def update_task(self, task: Task):
        """Update the task and refresh display."""
        self.task = task
        self._update_display()

    def set_category(self, category: Category):
        """Set the category and update display."""
        self.category = category
        self._update_display()

    def _on_toggle(self):
        """Handle toggle button click."""
        self.toggle_clicked.emit(self.task.id)

    def _on_stop(self):
        """Handle stop button click."""
        self.stop_clicked.emit(self.task.id)

    def mousePressEvent(self, event):
        """Save drag start position on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Start drag if mouse moved far enough from press point."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, '_drag_start_pos') or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 20:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-timer-card-id", str(self.task.id).encode())
        drag.setMimeData(mime)

        # Grab a semi-transparent snapshot as drag pixmap
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        self._drag_start_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event):
        """Reset drag start position."""
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Open notebook on double-click on empty area."""
        child = self.childAt(event.pos())
        if child in (self.toggle_btn, self.stop_btn, self.progress):
            super().mouseDoubleClickEvent(event)
            return
        self.notebook_requested.emit(self.task.name)

    def _show_context_menu(self, pos):
        """Show right-click context menu for the timer card."""
        menu = QMenu(self)
        edit_action = menu.addAction("编辑此计时器")
        copy_name_action = menu.addAction("复制当前名称")
        menu.addSeparator()
        toggle_action = None
        if self.task.status == TaskStatus.RUNNING:
            toggle_action = menu.addAction("暂停")
        elif self.task.status == TaskStatus.PAUSED:
            toggle_action = menu.addAction("继续")
        stop_action = menu.addAction("停止")

        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit(self.task.id)
        elif action == copy_name_action:
            QApplication.clipboard().setText(self.task.name)
        elif action and action == toggle_action:
            self.toggle_clicked.emit(self.task.id)
        elif action == stop_action:
            self.stop_clicked.emit(self.task.id)

    def set_dark_mode(self, enabled: bool):
        """Toggle dark mode styling."""
        if enabled:
            self.setStyleSheet("""
                QFrame#timerCard {
                    background-color: #2c2c2e;
                    border: 1px solid #48484a;
                    border-radius: 12px;
                    padding: 16px;
                }
                QFrame#timerCard:hover {
                    border-color: #636366;
                }
            """)
            self.name_label.setStyleSheet("""
                QLabel {
                    font-size: 15px;
                    font-weight: 500;
                    color: #ffffff;
                }
            """)
            self.category_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #8e8e93;
                }
            """)
            self.progress.setTrackColor("#48484a")
            self.progress.setTextColor("#ffffff")
            self.progress.setStatusColor("#8e8e93")
        else:
            self.setStyleSheet("""
                QFrame#timerCard {
                    background-color: #ffffff;
                    border: 1px solid #e5e5ea;
                    border-radius: 12px;
                    padding: 16px;
                }
                QFrame#timerCard:hover {
                    border-color: #d2d2d7;
                }
            """)
            self.name_label.setStyleSheet("""
                QLabel {
                    font-size: 15px;
                    font-weight: 500;
                    color: #1d1d1f;
                }
            """)
            self.category_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #6e6e73;
                }
            """)
            self.progress.setTrackColor("#e5e5ea")
            self.progress.setTextColor("#1d1d1f")
            self.progress.setStatusColor("#6e6e73")


class EditTimerDialog(QDialog):
    """Dialog for editing a running/paused timer."""

    def __init__(self, task: Task, categories: List[Category], parent=None):
        super().__init__(parent)

        self.task = task
        self.categories = categories
        self.result_data = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("编辑计时器")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Task name
        name_label = QLabel("任务名称")
        self.name_input = QLineEdit()
        self.name_input.setText(self.task.name)
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)

        # Duration (show total duration in minutes)
        duration_label = QLabel("总时长（分钟）")
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 480)
        self.duration_input.setValue(self.task.duration_seconds // 60)
        self.duration_input.setSuffix(" 分钟")
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_input)

        # Info about elapsed time
        elapsed_mins = self.task.elapsed_seconds // 60
        elapsed_secs = self.task.elapsed_seconds % 60
        info_label = QLabel(f"已计时: {elapsed_mins}分{elapsed_secs}秒")
        info_label.setStyleSheet("QLabel { font-size: 12px; color: #6e6e73; }")
        layout.addWidget(info_label)

        # Category
        category_label = QLabel("分类")
        self.category_combo = QComboBox()
        current_index = 0
        for i, cat in enumerate(self.categories):
            self.category_combo.addItem(f"{cat.icon} {cat.name}", cat.id)
            if cat.id == self.task.category_id:
                current_index = i
        self.category_combo.setCurrentIndex(current_index)
        layout.addWidget(category_label)
        layout.addWidget(self.category_combo)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Style
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                font-size: 13px;
                color: #1d1d1f;
            }
            QLineEdit, QSpinBox, QComboBox {
                padding: 8px;
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #007AFF;
            }
        """)

    def _on_accept(self):
        """Handle dialog acceptance."""
        name = self.name_input.text().strip()
        if not name:
            name = self.task.name

        self.result_data = {
            'name': name,
            'duration_seconds': self.duration_input.value() * 60,
            'category_id': self.category_combo.currentData(),
        }
        self.accept()

    def get_result(self):
        """Get the dialog result."""
        return self.result_data
