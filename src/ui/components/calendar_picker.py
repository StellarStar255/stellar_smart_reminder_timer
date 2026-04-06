"""Calendar date range picker popup."""

import calendar
from datetime import date, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGridLayout,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush


class CalendarGrid(QWidget):
    """Custom-painted month calendar grid supporting date range selection."""

    date_clicked = pyqtSignal(date)

    CELL_SIZE = 36
    HEADER_HEIGHT = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = date.today().year
        self._month = date.today().month
        self._start_date = None
        self._end_date = None
        self._hover_date = None
        self._dark_mode = False

        self.setMouseTracking(True)
        self.setFixedSize(self.CELL_SIZE * 7, self.HEADER_HEIGHT + self.CELL_SIZE * 6)

    def set_month(self, year: int, month: int):
        self._year = year
        self._month = month
        self.update()

    def set_range(self, start: date = None, end: date = None):
        self._start_date = start
        self._end_date = end
        self.update()

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self.update()

    def _date_at_pos(self, pos: QPoint):
        """Return the date at a given pixel position, or None."""
        col = pos.x() // self.CELL_SIZE
        row = (pos.y() - self.HEADER_HEIGHT) // self.CELL_SIZE
        if row < 0 or col < 0 or col >= 7 or row >= 6:
            return None

        cal = calendar.Calendar(firstweekday=0)  # Monday first
        weeks = cal.monthdayscalendar(self._year, self._month)
        if row >= len(weeks):
            return None
        day = weeks[row][col]
        if day == 0:
            return None
        return date(self._year, self._month, day)

    def mousePressEvent(self, event):
        d = self._date_at_pos(event.pos())
        if d:
            self.date_clicked.emit(d)

    def mouseMoveEvent(self, event):
        d = self._date_at_pos(event.pos())
        if d != self._hover_date:
            self._hover_date = d
            self.update()

    def leaveEvent(self, event):
        self._hover_date = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cs = self.CELL_SIZE
        today = date.today()

        # Colors
        if self._dark_mode:
            bg_color = QColor("#2c2c2e")
            text_color = QColor("#ffffff")
            dim_text = QColor("#636366")
            header_color = QColor("#98989d")
            highlight = QColor("#0a84ff")
            range_bg = QColor(10, 132, 255, 40)
            hover_bg = QColor(255, 255, 255, 20)
        else:
            bg_color = QColor("#ffffff")
            text_color = QColor("#1d1d1f")
            dim_text = QColor("#aeaeb2")
            header_color = QColor("#6e6e73")
            highlight = QColor("#007AFF")
            range_bg = QColor(0, 122, 255, 30)
            hover_bg = QColor(0, 0, 0, 10)

        # Background
        painter.fillRect(self.rect(), bg_color)

        # Weekday headers
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        painter.setFont(QFont(".AppleSystemUIFont", 11))
        painter.setPen(header_color)
        for i, wd in enumerate(weekdays):
            x = i * cs
            painter.drawText(x, 0, cs, self.HEADER_HEIGHT,
                             Qt.AlignmentFlag.AlignCenter, wd)

        # Day cells
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(self._year, self._month)

        painter.setFont(QFont(".AppleSystemUIFont", 12))

        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                if day == 0:
                    continue

                x = col * cs
                y = self.HEADER_HEIGHT + row * cs
                d = date(self._year, self._month, day)

                # Determine if this date is in selected range
                in_range = False
                is_endpoint = False
                if self._start_date and self._end_date:
                    s, e = sorted([self._start_date, self._end_date])
                    in_range = s <= d <= e
                    is_endpoint = d == s or d == e
                elif self._start_date:
                    is_endpoint = d == self._start_date
                    # Show preview range while hovering
                    if self._hover_date:
                        s, e = sorted([self._start_date, self._hover_date])
                        in_range = s <= d <= e

                # Draw range background
                if in_range and not is_endpoint:
                    painter.fillRect(x, y, cs, cs, range_bg)

                # Draw endpoint circle
                if is_endpoint:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(highlight)
                    cx = x + cs // 2
                    cy = y + cs // 2
                    painter.drawEllipse(cx - 14, cy - 14, 28, 28)

                # Draw hover highlight
                elif d == self._hover_date and not in_range:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(hover_bg)
                    cx = x + cs // 2
                    cy = y + cs // 2
                    painter.drawEllipse(cx - 14, cy - 14, 28, 28)

                # Draw today circle outline
                if d == today and not is_endpoint:
                    painter.setPen(QPen(highlight, 1.5))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    cx = x + cs // 2
                    cy = y + cs // 2
                    painter.drawEllipse(cx - 14, cy - 14, 28, 28)

                # Draw day text
                if is_endpoint:
                    painter.setPen(QColor("#ffffff"))
                elif d == today:
                    painter.setPen(highlight)
                else:
                    painter.setPen(text_color)

                painter.drawText(x, y, cs, cs,
                                 Qt.AlignmentFlag.AlignCenter, str(day))

        painter.end()


class CalendarPopup(QWidget):
    """Popup widget for selecting a date range via calendar."""

    date_range_confirmed = pyqtSignal(date, date)

    QUICK_PRESETS = [
        ("本周", "_this_week"),
        ("上周", "_last_week"),
        ("本月", "_this_month"),
        ("上月", "_last_month"),
        ("近3个月", "_last_3_months"),
        ("今年", "_this_year"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._dark_mode = False
        self._start_date = None
        self._end_date = None
        self._selection_step = 0  # 0 = pick start, 1 = pick end
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Month navigation header
        nav = QHBoxLayout()
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(28, 28)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev_month)

        self._month_label = QLabel()
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_label.setFont(QFont(".AppleSystemUIFont", 13, QFont.Weight.DemiBold))

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(28, 28)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._next_month)

        nav.addWidget(self._prev_btn)
        nav.addStretch()
        nav.addWidget(self._month_label)
        nav.addStretch()
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        # Calendar grid
        self._grid = CalendarGrid()
        self._grid.date_clicked.connect(self._on_date_clicked)
        layout.addWidget(self._grid)

        # Range info label
        self._range_label = QLabel("请点击选择起始日期")
        self._range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._range_label.setFont(QFont(".AppleSystemUIFont", 11))
        layout.addWidget(self._range_label)

        # Quick preset buttons
        preset_layout = QGridLayout()
        preset_layout.setSpacing(6)
        for i, (label, method_name) in enumerate(self.QUICK_PRESETS):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(getattr(self, method_name))
            row, col = divmod(i, 3)
            preset_layout.addWidget(btn, row, col)
        layout.addLayout(preset_layout)

        # Confirm / Cancel
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(30)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.close)

        self._confirm_btn = QPushButton("确认")
        self._confirm_btn.setFixedHeight(30)
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._confirm)

        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._confirm_btn)
        layout.addLayout(btn_layout)

        # Init month display
        today = date.today()
        self._view_year = today.year
        self._view_month = today.month
        self._update_month_display()
        self._apply_styles()

    def _update_month_display(self):
        self._month_label.setText(f"{self._view_year}年{self._view_month}月")
        self._grid.set_month(self._view_year, self._view_month)

    def _prev_month(self):
        if self._view_month == 1:
            self._view_month = 12
            self._view_year -= 1
        else:
            self._view_month -= 1
        self._update_month_display()

    def _next_month(self):
        if self._view_month == 12:
            self._view_month = 1
            self._view_year += 1
        else:
            self._view_month += 1
        self._update_month_display()

    def _on_date_clicked(self, d: date):
        if self._selection_step == 0:
            self._start_date = d
            self._end_date = None
            self._selection_step = 1
            self._grid.set_range(d)
            self._range_label.setText(f"起始: {d.month}/{d.day}  请选择结束日期")
            self._confirm_btn.setEnabled(False)
        else:
            self._end_date = d
            self._selection_step = 0
            s, e = sorted([self._start_date, self._end_date])
            self._start_date, self._end_date = s, e
            self._grid.set_range(s, e)
            self._range_label.setText(f"{s.month}/{s.day} - {e.month}/{e.day}")
            self._confirm_btn.setEnabled(True)

    def _set_quick_range(self, start: date, end: date):
        self._start_date = start
        self._end_date = end
        self._selection_step = 0
        self._grid.set_range(start, end)
        self._range_label.setText(f"{start.month}/{start.day} - {end.month}/{end.day}")
        self._confirm_btn.setEnabled(True)
        # Navigate view to show the start month
        self._view_year = start.year
        self._view_month = start.month
        self._update_month_display()

    def _this_week(self):
        today = date.today()
        start = today - timedelta(days=today.weekday())  # Monday
        end = start + timedelta(days=6)
        self._set_quick_range(start, end)

    def _last_week(self):
        today = date.today()
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        self._set_quick_range(start, end)

    def _this_month(self):
        today = date.today()
        start = today.replace(day=1)
        end = today
        self._set_quick_range(start, end)

    def _last_month(self):
        today = date.today()
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        self._set_quick_range(start, end)

    def _last_3_months(self):
        today = date.today()
        end = today
        # Go back ~3 months
        month = today.month - 3
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        start = date(year, month, 1)
        self._set_quick_range(start, end)

    def _this_year(self):
        today = date.today()
        start = date(today.year, 1, 1)
        self._set_quick_range(start, today)

    def _confirm(self):
        if self._start_date and self._end_date:
            self.date_range_confirmed.emit(self._start_date, self._end_date)
            self.close()

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self._grid.set_dark_mode(enabled)
        self._apply_styles()

    def _apply_styles(self):
        if self._dark_mode:
            self.setStyleSheet("""
                CalendarPopup {
                    background-color: #2c2c2e;
                    border: 1px solid #48484a;
                    border-radius: 12px;
                }
                QLabel {
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #3a3a3c;
                    color: #ffffff;
                    border: 1px solid #48484a;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 0 8px;
                }
                QPushButton:hover {
                    background-color: #48484a;
                }
                QPushButton#confirmBtn {
                    background-color: #0a84ff;
                    border: none;
                }
                QPushButton#confirmBtn:hover {
                    background-color: #409cff;
                }
                QPushButton#confirmBtn:disabled {
                    background-color: #3a3a3c;
                    color: #636366;
                }
            """)
        else:
            self.setStyleSheet("""
                CalendarPopup {
                    background-color: #ffffff;
                    border: 1px solid #d2d2d7;
                    border-radius: 12px;
                }
                QLabel {
                    color: #1d1d1f;
                }
                QPushButton {
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 0 8px;
                }
                QPushButton:hover {
                    background-color: #e5e5ea;
                }
                QPushButton#confirmBtn {
                    background-color: #007AFF;
                    color: #ffffff;
                    border: none;
                }
                QPushButton#confirmBtn:hover {
                    background-color: #0066d6;
                }
                QPushButton#confirmBtn:disabled {
                    background-color: #e5e5ea;
                    color: #aeaeb2;
                }
            """)
        self._confirm_btn.setObjectName("confirmBtn")
