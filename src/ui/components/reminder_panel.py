"""Scheduled-reminder panel: the list, the editor dialog and the alarm popup.

Countdown timers answer "在多久之后"; reminders answer "在什么时候" — a wall
clock date and time, optionally repeating.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox, QDateTimeEdit,
    QTextEdit, QMessageBox, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, QDateTime, QTime, pyqtSignal
from PyQt6.QtGui import QFont

from src.models import Reminder, RepeatMode, REPEAT_LABELS, Category
from src.ui.components.preset_bar import _apply_dialog_theme


# (label, minutes from now) shortcuts offered in the editor dialog
QUICK_OFFSETS = [("10 分钟后", 10), ("30 分钟后", 30), ("1 小时后", 60), ("3 小时后", 180)]

# (label, hour) shortcuts that land on a fixed clock time
QUICK_CLOCK_TIMES = [("今天 18:00", 0, 18), ("明天 09:00", 1, 9), ("明天 20:00", 1, 20)]

SNOOZE_OPTIONS = [5, 10, 30, 60]


def _palette(dark_mode: bool) -> dict:
    """Theme colors shared by every widget in this module."""
    if dark_mode:
        return {
            'bg': "#2c2c2e", 'border': "#48484a", 'hover': "#636366",
            'text': "#ffffff", 'secondary': "#98989d", 'accent': "#0a84ff",
            'chip': "#3a3a3c", 'danger': "#ff453a",
        }
    return {
        'bg': "#ffffff", 'border': "#e5e5ea", 'hover': "#d2d2d7",
        'text': "#1d1d1f", 'secondary': "#6e6e73", 'accent': "#007AFF",
        'chip': "#f5f5f7", 'danger': "#ff3b30",
    }


class ReminderDialog(QDialog):
    """Create or edit a date/time reminder."""

    def __init__(self, categories: List[Category], reminder: Optional[Reminder] = None,
                 parent=None, dark_mode: bool = False):
        super().__init__(parent)
        self.categories = categories
        self.reminder = reminder
        self.result_data = None

        self._setup_ui()
        _apply_dialog_theme(self, dark_mode)

    def _setup_ui(self):
        editing = self.reminder is not None
        self.setWindowTitle("编辑定时提醒" if editing else "新建定时提醒")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        layout.addWidget(QLabel("提醒内容"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例如：给妈妈打电话")
        if editing:
            self.title_input.setText(self.reminder.title)
        layout.addWidget(self.title_input)

        # Date + time
        layout.addWidget(QLabel("提醒时间"))
        self.datetime_input = QDateTimeEdit()
        self.datetime_input.setCalendarPopup(True)
        self.datetime_input.setDisplayFormat("yyyy年MM月dd日  HH:mm")
        if editing:
            self.datetime_input.setDateTime(QDateTime(self.reminder.remind_at))
        else:
            # Default to the next round 5 minutes, at least 5 minutes out, so
            # the prefilled value is always usable as-is.
            target = datetime.now() + timedelta(minutes=5)
            target = target.replace(second=0, microsecond=0)
            target += timedelta(minutes=(5 - target.minute % 5) % 5)
            self.datetime_input.setDateTime(QDateTime(target))
        layout.addWidget(self.datetime_input)

        # Relative shortcuts
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        for label, minutes in QUICK_OFFSETS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=minutes: self._set_offset(m))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

        # Fixed clock-time shortcuts
        clock_row = QHBoxLayout()
        clock_row.setSpacing(6)
        for label, day_offset, hour in QUICK_CLOCK_TIMES:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, d=day_offset, h=hour: self._set_clock_time(d, h))
            clock_row.addWidget(btn)
        layout.addLayout(clock_row)

        # Repeat
        layout.addWidget(QLabel("重复"))
        self.repeat_combo = QComboBox()
        for mode in RepeatMode:
            self.repeat_combo.addItem(REPEAT_LABELS[mode], mode.value)
        if editing:
            index = self.repeat_combo.findData(self.reminder.repeat.value)
            self.repeat_combo.setCurrentIndex(max(0, index))
        layout.addWidget(self.repeat_combo)

        # Optional auto-started timer — the bridge back to the countdown side
        layout.addWidget(QLabel("到点后自动开始计时"))
        self.auto_start_input = QSpinBox()
        self.auto_start_input.setRange(0, 1440)
        self.auto_start_input.setSpecialValueText("不自动开始")
        self.auto_start_input.setSuffix(" 分钟")
        if editing:
            self.auto_start_input.setValue(self.reminder.auto_start_minutes)
        self.auto_start_input.valueChanged.connect(self._sync_category_enabled)
        layout.addWidget(self.auto_start_input)

        self.category_combo = QComboBox()
        for cat in self.categories:
            self.category_combo.addItem(f"{cat.icon} {cat.name}", cat.id)
        if editing and self.reminder.category_id is not None:
            index = self.category_combo.findData(self.reminder.category_id)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        self.category_combo.setToolTip("自动开始的计时任务归入哪个分类")
        layout.addWidget(self.category_combo)
        self._sync_category_enabled()

        # Notes
        layout.addWidget(QLabel("备注（可选）"))
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(60)
        self.notes_input.setPlaceholderText("提醒弹窗里会一起显示…")
        if editing:
            self.notes_input.setPlainText(self.reminder.notes)
        layout.addWidget(self.notes_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _set_offset(self, minutes: int):
        target = (datetime.now() + timedelta(minutes=minutes)).replace(
            second=0, microsecond=0)
        self.datetime_input.setDateTime(QDateTime(target))

    def _set_clock_time(self, day_offset: int, hour: int):
        target = (datetime.now() + timedelta(days=day_offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0)
        self.datetime_input.setDateTime(QDateTime(target))

    def _sync_category_enabled(self):
        self.category_combo.setEnabled(self.auto_start_input.value() > 0)

    def _on_accept(self):
        title = self.title_input.text().strip() or "定时提醒"
        value = self.datetime_input.dateTime()
        # Seconds aren't editable in this dialog; zero them so a reminder set
        # for 09:00 fires at 09:00:00 rather than at whatever second it was created.
        value.setTime(QTime(value.time().hour(), value.time().minute(), 0))
        remind_at = value.toPyDateTime()
        repeat = RepeatMode(self.repeat_combo.currentData())

        if repeat == RepeatMode.NONE and remind_at <= datetime.now():
            QMessageBox.warning(
                self, "时间已过",
                f"{remind_at.strftime('%Y年%m月%d日 %H:%M')} 已经过去了，"
                "请选择一个将来的时间。")
            return

        auto_start = self.auto_start_input.value()
        self.result_data = {
            'title': title,
            'remind_at': remind_at,
            'repeat': repeat,
            'auto_start_minutes': auto_start,
            'category_id': self.category_combo.currentData() if auto_start else None,
            'notes': self.notes_input.toPlainText().strip(),
        }
        self.accept()

    def get_result(self) -> Optional[dict]:
        return self.result_data


class ReminderPopupDialog(QDialog):
    """The alarm popup shown when a reminder comes due."""

    def __init__(self, reminder: Reminder, parent=None, dark_mode: bool = False,
                 on_close_callback=None):
        super().__init__(parent)
        self.reminder = reminder
        self._on_close_callback = on_close_callback
        self._snooze_minutes: Optional[int] = None
        self._dark_mode = dark_mode

        self.setWindowTitle("定时提醒")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self):
        colors = _palette(self._dark_mode)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QDialog {{ background-color: {colors['bg']}; }}")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        header = QLabel(f"⏰ {self.reminder.title}")
        header.setWordWrap(True)
        header.setFont(QFont(".AppleSystemUIFont", 17, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {colors['text']}; background: transparent;")
        layout.addWidget(header)

        scheduled = self.reminder.remind_at.strftime("%Y年%m月%d日 %H:%M")
        subtitle = f"提醒时间：{scheduled}"
        if self.reminder.repeat != RepeatMode.NONE:
            subtitle += f" · {self.reminder.describe_repeat()}"
        time_label = QLabel(subtitle)
        time_label.setStyleSheet(
            f"color: {colors['secondary']}; font-size: 13px; background: transparent;")
        layout.addWidget(time_label)

        if self.reminder.notes:
            notes = QLabel(self.reminder.notes)
            notes.setWordWrap(True)
            notes.setStyleSheet(f"""
                color: {colors['text']};
                font-size: 13px;
                background-color: {colors['chip']};
                border-radius: 8px;
                padding: 10px;
            """)
            layout.addWidget(notes)

        if self.reminder.auto_start_minutes > 0:
            auto = QLabel(f"已自动开始 {self.reminder.auto_start_minutes} 分钟计时")
            auto.setStyleSheet(
                f"color: {colors['accent']}; font-size: 13px; background: transparent;")
            layout.addWidget(auto)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        snooze_btn = QPushButton("稍后提醒 ▾")
        snooze_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['chip']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background-color: {colors['hover']}; }}
        """)
        snooze_menu = QMenu(self)
        for minutes in SNOOZE_OPTIONS:
            action = snooze_menu.addAction(f"{minutes} 分钟后")
            action.triggered.connect(lambda _=False, m=minutes: self._on_snooze(m))
        snooze_btn.setMenu(snooze_menu)
        btn_row.addWidget(snooze_btn)

        ok_btn = QPushButton("知道了")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background-color: #0056b3; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def _on_snooze(self, minutes: int):
        self._snooze_minutes = minutes
        self.accept()

    def snooze_minutes(self) -> Optional[int]:
        """Minutes the user chose to postpone by, or None if dismissed."""
        return self._snooze_minutes

    def done(self, result):
        if self._on_close_callback:
            self._on_close_callback()
        super().done(result)


class ReminderRow(QFrame):
    """One reminder in the list."""

    toggle_requested = pyqtSignal(int, bool)  # reminder_id, enabled
    edit_requested = pyqtSignal(object)       # Reminder
    delete_requested = pyqtSignal(int)        # reminder_id

    def __init__(self, reminder: Reminder, category: Optional[Category] = None,
                 parent=None, dark_mode: bool = False):
        super().__init__(parent)
        self.reminder = reminder
        self.category = category
        self._dark_mode = dark_mode
        self.setObjectName("reminderRow")
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 8, 12, 8)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedSize(30, 30)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)

        self.time_label = QLabel()
        self.time_label.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.DemiBold))
        self.time_label.setMinimumWidth(120)
        layout.addWidget(self.time_label)

        self.title_label = QLabel()
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title_label, 1)

        self.repeat_label = QLabel()
        layout.addWidget(self.repeat_label)

        self.status_label = QLabel()
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setMinimumWidth(130)
        layout.addWidget(self.status_label)

        self.edit_btn = QPushButton("✎")
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.setToolTip("编辑提醒")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.reminder))
        layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedSize(28, 28)
        self.delete_btn.setToolTip("删除提醒")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(
            lambda: self.delete_requested.emit(self.reminder.id))
        layout.addWidget(self.delete_btn)

    def _on_toggle(self):
        self.toggle_requested.emit(self.reminder.id, self.toggle_btn.isChecked())

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self.refresh()

    def refresh(self):
        """Redraw everything that depends on the reminder or the clock."""
        colors = _palette(self._dark_mode)
        reminder = self.reminder
        due = reminder.next_due()
        pending = due is not None

        self.setStyleSheet(f"""
            QFrame#reminderRow {{
                background-color: {colors['bg']};
                border: 1px solid {colors['border']};
                border-radius: 10px;
            }}
            QFrame#reminderRow:hover {{ border-color: {colors['hover']}; }}
        """)

        self.toggle_btn.blockSignals(True)
        self.toggle_btn.setChecked(reminder.enabled)
        self.toggle_btn.blockSignals(False)
        self.toggle_btn.setText("🔔" if reminder.enabled else "🔕")
        self.toggle_btn.setToolTip("已开启，点击关闭" if reminder.enabled else "已关闭，点击开启")
        # color and padding must be spelled out: the window-wide theme styles
        # every QPushButton white with 8px/16px padding, which would leave
        # these icon-only buttons blank and clipped.
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {colors['text']};
                padding: 0;
                font-size: 15px;
            }}
            QPushButton:hover {{
                background-color: {colors['chip']};
                border-radius: 8px;
            }}
        """)

        time_text = Reminder.format_datetime(due or reminder.remind_at)
        self.time_label.setText(time_text)
        time_color = colors['text'] if pending else colors['secondary']
        self.time_label.setStyleSheet(f"color: {time_color}; background: transparent;")

        title = reminder.title
        if reminder.auto_start_minutes > 0:
            icon = f"{self.category.icon} " if self.category else ""
            title += f"  ⏱ {icon}{reminder.auto_start_minutes} 分钟"
        self.title_label.setText(title)
        self.title_label.setToolTip(reminder.notes or reminder.title)
        title_color = colors['text'] if pending else colors['secondary']
        self.title_label.setStyleSheet(
            f"color: {title_color}; font-size: 13px; background: transparent;")

        if reminder.repeat == RepeatMode.NONE:
            self.repeat_label.setText("")
            self.repeat_label.setVisible(False)
        else:
            self.repeat_label.setVisible(True)
            self.repeat_label.setText(f" {reminder.describe_repeat()} ")
            self.repeat_label.setStyleSheet(f"""
                color: {colors['accent']};
                background-color: {colors['chip']};
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 12px;
            """)

        status = reminder.status_text()
        self.status_label.setText(status)
        if reminder.was_missed:
            status_color = colors['danger']
        elif pending:
            status_color = colors['accent'] if reminder.snoozed_until else colors['secondary']
        else:
            status_color = colors['secondary']
        self.status_label.setStyleSheet(
            f"color: {status_color}; font-size: 12px; background: transparent;")

        icon_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {colors['secondary']};
                padding: 0;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {colors['chip']};
                border-radius: 6px;
                color: {colors['text']};
            }}
        """
        self.edit_btn.setStyleSheet(icon_style)
        self.delete_btn.setStyleSheet(icon_style)


class ReminderPanel(QWidget):
    """Collapsible list of scheduled reminders with an add button."""

    create_requested = pyqtSignal()
    edit_requested = pyqtSignal(object)       # Reminder
    delete_requested = pyqtSignal(int)        # reminder_id
    toggle_requested = pyqtSignal(int, bool)  # reminder_id, enabled
    clear_finished_requested = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_mode = False
        self._collapsed = False
        self._rows: List[ReminderRow] = []
        self._categories = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.collapse_btn = QPushButton("▾")
        self.collapse_btn.setFixedSize(24, 24)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.clicked.connect(self._toggle_collapsed)
        header.addWidget(self.collapse_btn)

        self.title_label = QLabel("⏰ 定时提醒")
        self.title_label.setFont(QFont(".AppleSystemUIFont", 15, QFont.Weight.Bold))
        header.addWidget(self.title_label)

        self.count_label = QLabel("")
        header.addWidget(self.count_label)
        header.addStretch()

        self.clear_btn = QPushButton("清除已完成")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("删除已经响过的一次性提醒")
        self.clear_btn.clicked.connect(self.clear_finished_requested.emit)
        header.addWidget(self.clear_btn)

        self.add_btn = QPushButton("+ 新建提醒")
        self.add_btn.setFixedHeight(28)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setToolTip("在指定的日期和时间提醒你")
        self.add_btn.clicked.connect(self.create_requested.emit)
        header.addWidget(self.add_btn)

        layout.addLayout(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setSpacing(6)
        self.body_layout.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("还没有定时提醒 — 点击「+ 新建提醒」按日期和时间安排一条")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self.empty_label)

        layout.addWidget(self.body)

        self._apply_styles()

    # --- Content ---

    def set_categories(self, categories):
        self._categories = {c.id: c for c in categories}

    def set_reminders(self, reminders: List[Reminder]):
        """Rebuild the list; ``reminders`` is expected pre-sorted."""
        for row in self._rows:
            self.body_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []

        for reminder in reminders:
            row = ReminderRow(
                reminder, self._categories.get(reminder.category_id),
                dark_mode=self._dark_mode)
            row.toggle_requested.connect(self.toggle_requested.emit)
            row.edit_requested.connect(self.edit_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            self.body_layout.addWidget(row)
            self._rows.append(row)

        self.empty_label.setVisible(not reminders)

        pending = sum(1 for r in reminders if r.next_due() is not None)
        finished = len(reminders) - pending
        self.count_label.setText(f"{pending} 条待提醒" if reminders else "")
        self.clear_btn.setVisible(finished > 0)

    def refresh_countdowns(self):
        """Re-render the per-row countdown text (called once a second)."""
        if self._collapsed:
            return
        for row in self._rows:
            row.refresh()

    # --- Appearance ---

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self.body.setVisible(not collapsed)
        self.collapse_btn.setText("▸" if collapsed else "▾")

    def _toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)
        self.collapsed_changed.emit(self._collapsed)

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self._apply_styles()
        for row in self._rows:
            row.set_dark_mode(enabled)

    def _apply_styles(self):
        colors = _palette(self._dark_mode)
        self.title_label.setStyleSheet(
            f"color: {colors['text']}; background: transparent;")
        self.count_label.setStyleSheet(
            f"color: {colors['secondary']}; font-size: 12px; background: transparent;")
        self.empty_label.setStyleSheet(f"""
            QLabel {{
                color: {colors['secondary']};
                font-size: 13px;
                padding: 18px;
                border: 1px dashed {colors['border']};
                border-radius: 10px;
            }}
        """)
        button_style = f"""
            QPushButton {{
                background-color: {colors['chip']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                font-size: 13px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {colors['hover']};
                color: {colors['text']};
            }}
        """
        self.add_btn.setStyleSheet(button_style)
        self.clear_btn.setStyleSheet(button_style)
        self.collapse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {colors['secondary']};
                padding: 0;
                font-size: 13px;
            }}
            QPushButton:hover {{ color: {colors['text']}; }}
        """)
