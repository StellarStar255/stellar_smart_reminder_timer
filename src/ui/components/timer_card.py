"""Timer card widget for displaying individual task timers."""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QMenu,
    QDialog, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPointF
from PyQt6.QtGui import QDrag, QFont, QPainter, QColor
from typing import List

from src.models import Task, TaskStatus, Category
from src.ui.components.circular_progress import CircularProgress


class _ElidedLabel(QLabel):
    """Center-aligned label that wraps text across at most two lines and appends
    a single ellipsis to the last line when the full text doesn't fit.

    Wrapping is computed from the widget's *real* width during painting, so the
    front of the name stays continuous and text is never clipped mid-character
    (the failure mode of guessing the available width up front)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._text_color = QColor("#1d1d1f")
        self._max_lines = 2

    def setFullText(self, text: str):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self.update()

    def fullText(self) -> str:
        return self._full_text

    def setTextColor(self, color):
        self._text_color = QColor(color)
        self.update()

    def _wrap_lines(self, width: int) -> List[str]:
        """Greedily pack the text into up to ``_max_lines`` lines that each fit
        ``width``; the last line is elided with '…' if text remains."""
        fm = self.fontMetrics()
        lines: List[str] = []
        remaining = self._full_text
        for idx in range(self._max_lines):
            if not remaining:
                break
            is_last = idx == self._max_lines - 1
            # Largest prefix of ``remaining`` that fits the line width.
            fit = 1
            for j in range(1, len(remaining) + 1):
                if fm.horizontalAdvance(remaining[:j]) <= width:
                    fit = j
                else:
                    break
            if fit >= len(remaining):
                lines.append(remaining)
                remaining = ""
            elif is_last:
                lines.append(fm.elidedText(remaining, Qt.TextElideMode.ElideRight, width))
                remaining = ""
            else:
                lines.append(remaining[:fit])
                remaining = remaining[fit:]
        return lines

    def paintEvent(self, event):
        if not self._full_text:
            return
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self._text_color)
        fm = self.fontMetrics()
        width = self.width()
        lines = self._wrap_lines(width)

        line_height = fm.lineSpacing()
        total_h = len(lines) * line_height
        y = (self.height() - total_h) / 2 + fm.ascent()
        for line in lines:
            x = (width - fm.horizontalAdvance(line)) / 2
            painter.drawText(QPointF(x, y), line)
            y += line_height


class TimerCard(QFrame):
    """A card widget displaying a single task timer."""

    # Signals
    toggle_clicked = pyqtSignal(int)  # task_id
    stop_clicked = pyqtSignal(int)  # task_id
    delete_clicked = pyqtSignal(int)  # task_id
    edit_requested = pyqtSignal(int)  # task_id
    notebook_requested = pyqtSignal(str)  # task_name
    name_edited = pyqtSignal(int, str)  # task_id, new_name

    def __init__(self, task: Task, category: Category = None, parent=None):
        super().__init__(parent)

        self.task = task
        self.category = category
        self._dark_mode = False

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
                background: transparent;
            }
        """)
        layout.addWidget(self.category_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Circular progress - clickable to toggle timer
        self.progress = CircularProgress()
        self.progress.setMinimumSize(140, 140)
        self.progress.clicked.connect(self._on_toggle)
        self.progress.setToolTip("点击暂停/继续")
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignCenter)

        # Task name (custom label: wraps to two lines, ellipsis only at the end)
        self.name_label = _ElidedLabel()
        name_font = QFont()
        name_font.setPixelSize(15)
        name_font.setWeight(QFont.Weight.Medium)
        self.name_label.setFont(name_font)
        # Reserve room for two lines so cards with short and long names keep
        # their buttons aligned at the same height.
        self.name_label.setFixedHeight(44)
        self.name_label.setStyleSheet("QLabel { background: transparent; }")
        layout.addWidget(self.name_label)

        # Inline name editor (hidden until the name is double-clicked)
        self.name_edit = QLineEdit()
        self.name_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_edit.setFixedHeight(44)
        self.name_edit.hide()
        self.name_edit.returnPressed.connect(self._commit_name_edit)
        self.name_edit.editingFinished.connect(self._commit_name_edit)
        self.name_edit.installEventFilter(self)
        layout.addWidget(self.name_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.toggle_btn = QPushButton("开始")
        self.toggle_btn.setMinimumWidth(70)
        self.toggle_btn.setFixedHeight(34)
        self.toggle_btn.clicked.connect(self._on_toggle)
        # Transparent border keeps the box model identical to the stop
        # button (which has a real 1px border), so both render the same size.
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: 1px solid transparent;
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
        self.stop_btn.setFixedHeight(34)
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

        # Equal stretch makes the layout give both buttons exactly the same
        # width, so they always render identical in size.
        btn_layout.addWidget(self.toggle_btn, 1)
        btn_layout.addWidget(self.stop_btn, 1)

        layout.addLayout(btn_layout)

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(200)

    def _update_display(self):
        """Update the display based on current task state."""
        # Update name (the label clamps it to two lines with a trailing
        # ellipsis; the full name is shown as a tooltip).
        self.name_label.setFullText(self.task.name)

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
        """Double-click the name to rename inline; elsewhere opens the notebook."""
        child = self.childAt(event.pos())
        # Double-clicking the name (label or its reserved area) edits it inline.
        if child is self.name_label or self._is_in_name_area(event.pos()):
            self._start_name_edit()
            return
        if child in (self.toggle_btn, self.stop_btn, self.progress):
            super().mouseDoubleClickEvent(event)
            return
        self.notebook_requested.emit(self.task.name)

    def _is_in_name_area(self, pos):
        """Whether a point falls within the name label's row."""
        geo = self.name_label.geometry()
        return geo.top() <= pos.y() <= geo.bottom()

    def _start_name_edit(self):
        """Switch the name label to an editable line edit."""
        self.name_edit.setText(self.task.name)
        self._apply_name_edit_style()
        self.name_label.hide()
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _commit_name_edit(self):
        """Persist the inline-edited name and restore the label."""
        if not self.name_edit.isVisible():
            return
        # Block re-entrancy: editingFinished fires again when we hide the editor.
        self.name_edit.blockSignals(True)
        new_name = self.name_edit.text().strip()
        self.name_edit.hide()
        self.name_label.show()
        self.name_edit.blockSignals(False)

        if new_name and new_name != self.task.name:
            self.task.name = new_name
            self.name_label.setFullText(new_name)
            self.name_edited.emit(self.task.id, new_name)

    def eventFilter(self, obj, event):
        """Cancel an in-progress inline rename when Escape is pressed."""
        from PyQt6.QtCore import QEvent
        if obj is self.name_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.name_edit.blockSignals(True)
                self.name_edit.hide()
                self.name_label.show()
                self.name_edit.blockSignals(False)
                return True
        return super().eventFilter(obj, event)

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

    def _apply_name_edit_style(self):
        """Style the inline name editor to match the current theme."""
        if self._dark_mode:
            text, bg, border = "#ffffff", "#3a3a3c", "#0a84ff"
        else:
            text, bg, border = "#1d1d1f", "#ffffff", "#007AFF"
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                font-size: 15px;
                font-weight: 500;
                color: {text};
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
            }}
        """)

    def set_dark_mode(self, enabled: bool):
        """Toggle dark mode styling."""
        self._dark_mode = enabled
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
            self.name_label.setTextColor("#ffffff")
            self.category_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #8e8e93;
                    background: transparent;
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
            self.name_label.setTextColor("#1d1d1f")
            self.category_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #6e6e73;
                    background: transparent;
                }
            """)
            self.progress.setTrackColor("#e5e5ea")
            self.progress.setTextColor("#1d1d1f")
            self.progress.setStatusColor("#6e6e73")


class EditTimerDialog(QDialog):
    """Dialog for editing a running/paused timer."""

    def __init__(self, task: Task, categories: List[Category], parent=None, dark_mode: bool = False):
        super().__init__(parent)

        self.task = task
        self.categories = categories
        self.result_data = None

        self._setup_ui()
        # Reuse the shared theme-aware dialog styling so this matches the other
        # dialogs and stays readable in dark mode.
        from src.ui.components.preset_bar import _apply_dialog_theme
        _apply_dialog_theme(self, dark_mode)
        # Re-apply the secondary tint to the elapsed-time hint after theming.
        hint_color = "#98989d" if dark_mode else "#6e6e73"
        self.info_label.setStyleSheet(
            f"QLabel {{ font-size: 12px; color: {hint_color}; background: transparent; }}"
        )

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
        self.info_label = QLabel(f"已计时: {elapsed_mins}分{elapsed_secs}秒")
        self.info_label.setStyleSheet("QLabel { font-size: 12px; color: #6e6e73; }")
        layout.addWidget(self.info_label)

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
