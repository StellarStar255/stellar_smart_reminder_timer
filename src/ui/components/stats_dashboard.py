"""Statistics dashboard widget."""

import math
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QPushButton, QMenu, QStackedWidget, QApplication
)
from PyQt6.QtCore import Qt, QRectF, QPropertyAnimation, pyqtProperty, QEasingCurve, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFont, QPen, QPainterPath, QAction, QConicalGradient

import json
from typing import List, Optional
from src.core.statistics_engine import DailyStats, CategoryStats, TaskTimeStats
from src.data.database import Database
from src.ui.components.calendar_picker import CalendarPopup


class StatCard(QFrame):
    """A card showing a single statistic."""

    def __init__(self, title: str, value: str, subtitle: str = "", parent=None):
        super().__init__(parent)

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e5ea;
                border-radius: 10px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #6e6e73;
                text-transform: uppercase;
            }
        """)
        layout.addWidget(self.title_label)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: 600;
                color: #1d1d1f;
            }
        """)
        layout.addWidget(self.value_label)

        # Subtitle
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #6e6e73;
                }
            """)
            layout.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None

    def set_value(self, value: str):
        """Update the value."""
        self.value_label.setText(value)

    def set_subtitle(self, subtitle: str):
        """Update the subtitle."""
        if self.subtitle_label:
            self.subtitle_label.setText(subtitle)


class CategoryBar(QWidget):
    """A horizontal bar showing category distribution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[CategoryStats] = []
        self._dark_mode = False
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self.update()

    def set_data(self, data: List[CategoryStats]):
        """Set the category distribution data."""
        self._data = data
        self.update()

    def paintEvent(self, event):
        """Paint the category distribution bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(stat.total_seconds for stat in self._data)
        if total == 0:
            # Draw empty bar
            painter.setBrush(QColor("#48484a") if self._dark_mode else QColor("#e5e5ea"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 6, 6)
            return

        x = 0
        width = self.width()

        for i, stat in enumerate(self._data):
            if stat.total_seconds == 0:
                continue

            segment_width = int((stat.total_seconds / total) * width)
            if i == len(self._data) - 1:
                # Last segment takes remaining width
                segment_width = width - x

            painter.setBrush(QColor(stat.category_color))
            painter.setPen(Qt.PenStyle.NoPen)

            # Round corners for first and last segments
            if x == 0 and segment_width == width:
                painter.drawRoundedRect(x, 0, segment_width, self.height(), 6, 6)
            elif x == 0:
                painter.drawRoundedRect(x, 0, segment_width + 6, self.height(), 6, 6)
                painter.drawRect(x + segment_width, 0, 6, self.height())
            elif x + segment_width == width:
                painter.drawRoundedRect(x - 6, 0, segment_width + 6, self.height(), 6, 6)
                painter.drawRect(x - 6, 0, 6, self.height())
            else:
                painter.drawRect(x, 0, segment_width, self.height())

            x += segment_width


class CategoryLegend(QWidget):
    """Legend showing category colors and names."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[CategoryStats] = []
        self._dark_mode = False
        self._setup_ui()

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self._rebuild()

    def _setup_ui(self):
        """Set up the legend UI."""
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(16)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addStretch()

    def set_data(self, data: List[CategoryStats]):
        """Set the category data."""
        self._data = data
        self._rebuild()

    def _rebuild(self):
        """Rebuild the legend."""
        # Clear existing items
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = sum(stat.total_seconds for stat in self._data)

        for stat in self._data:
            if stat.total_seconds == 0:
                continue

            percentage = (stat.total_seconds / total * 100) if total > 0 else 0

            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setSpacing(4)
            item_layout.setContentsMargins(0, 0, 0, 0)

            # Color dot
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {stat.category_color}; font-size: 10px;")
            item_layout.addWidget(dot)

            # Name and percentage
            label = QLabel(f"{stat.category_name} {percentage:.0f}%")
            label_color = "#e5e5ea" if self._dark_mode else "#6e6e73"
            label.setStyleSheet(f"font-size: 13px; color: {label_color};")
            item_layout.addWidget(label)

            self.layout.insertWidget(self.layout.count() - 1, item)


class TaskBarChart(QWidget):
    """Beautiful animated bar chart showing time per task."""

    hidden_tasks_changed = pyqtSignal(set)  # emitted when hidden tasks change
    notebook_requested = pyqtSignal(str)  # task_name, emitted on double-click
    continue_task_requested = pyqtSignal(str)  # task_name, emitted from context menu

    # Gradient color palette for bars
    BAR_COLORS = [
        ("#007AFF", "#5AC8FA"),  # Blue
        ("#FF6B6B", "#FF9A9E"),  # Coral
        ("#34C759", "#A8E6CF"),  # Green
        ("#FF9500", "#FFCC02"),  # Orange
        ("#AF52DE", "#DA8FFF"),  # Purple
        ("#FF2D55", "#FF6B8A"),  # Pink
        ("#5856D6", "#8B85F7"),  # Indigo
        ("#00C7BE", "#64DFDF"),  # Teal
        ("#FF6F00", "#FFB74D"),  # Amber
        ("#30B0C7", "#81D4FA"),  # Cyan
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data: List[TaskTimeStats] = []  # unfiltered data
        self._data: List[TaskTimeStats] = []       # filtered for display
        self._hidden_tasks: set = set()            # hidden task names
        self._bar_rects: list = []                 # (QRectF, task_name) for hit-testing
        self._dark_mode = False
        self._anim_progress = 0.0
        self.setMinimumHeight(200)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Animation
        self._animation = QPropertyAnimation(self, b"animProgress")
        self._animation.setDuration(600)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_anim_progress(self):
        return self._anim_progress

    def _set_anim_progress(self, val):
        self._anim_progress = val
        self.update()

    animProgress = pyqtProperty(float, _get_anim_progress, _set_anim_progress)

    def _apply_filter(self):
        """Filter out hidden tasks from display data."""
        self._data = [s for s in self._all_data if s.task_name not in self._hidden_tasks]

    def set_data(self, data: List[TaskTimeStats]):
        """Set chart data and trigger animation only on change."""
        # Check if data actually changed to avoid re-animating on every stats refresh
        new_key = [(s.task_name, s.total_seconds, s.task_count) for s in data]
        old_key = [(s.task_name, s.total_seconds, s.task_count) for s in self._all_data]
        if new_key == old_key:
            return
        self._all_data = data
        self._apply_filter()
        self._anim_progress = 0.0
        self._animation.start()

    def _hit_test_bar(self, pos) -> str | None:
        """Return the task name of the bar at pos, or None."""
        for rect, name in self._bar_rects:
            # Extend hit area a bit below for the label area
            hit_rect = QRectF(rect.x() - 4, rect.y() - 22, rect.width() + 8, rect.height() + 60)
            if hit_rect.contains(QPointF(pos)):
                return name
        return None

    def _show_context_menu(self, pos):
        """Show right-click context menu for hiding/showing tasks."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 20px;
                font-size: 12px;
                color: #1d1d1f;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #e5e5ea;
                margin: 4px 8px;
            }
        """)

        # Check if right-clicked on a bar
        task_name = self._hit_test_bar(pos)
        if task_name:
            continue_action = menu.addAction("▶ 继续")
            continue_action.setData(("continue", task_name))
            menu.addSeparator()
            copy_action = menu.addAction("复制项目名")
            copy_action.setData(("copy_name", task_name))
            hide_action = menu.addAction("隐藏")
            hide_action.setData(("hide", task_name))

        # Show hidden tasks restore options
        if self._hidden_tasks:
            if task_name:
                menu.addSeparator()
            restore_menu = menu.addMenu(f"已隐藏 ({len(self._hidden_tasks)})")
            restore_menu.setStyleSheet(menu.styleSheet())
            for name in sorted(self._hidden_tasks):
                action = restore_menu.addAction(f"显示「{name}」")
                action.setData(("show", name))
            restore_menu.addSeparator()
            show_all = restore_menu.addAction("显示全部")
            show_all.setData(("show_all", None))

        if menu.isEmpty():
            return

        action = menu.exec(self.mapToGlobal(pos))
        if action and action.data():
            cmd, name = action.data()
            if cmd == "continue":
                self.continue_task_requested.emit(name)
                return
            elif cmd == "copy_name":
                QApplication.clipboard().setText(name)
                return
            elif cmd == "hide":
                self._hidden_tasks.add(name)
            elif cmd == "show":
                self._hidden_tasks.discard(name)
            elif cmd == "show_all":
                self._hidden_tasks.clear()
            self._apply_filter()
            self._anim_progress = 0.0
            self._animation.start()
            self.hidden_tasks_changed.emit(self._hidden_tasks)

    def mouseDoubleClickEvent(self, event):
        """Open notebook on double-click on a bar."""
        task_name = self._hit_test_bar(event.pos())
        if task_name:
            self.notebook_requested.emit(task_name)
        else:
            super().mouseDoubleClickEvent(event)

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self.update()

    def paintEvent(self, event):
        """Paint the bar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._data:
            # Empty state
            text_color = QColor("#8e8e93") if not self._dark_mode else QColor("#98989d")
            painter.setPen(text_color)
            painter.setFont(QFont(".AppleSystemUIFont", 13))
            if self._hidden_tasks:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 f"已隐藏 {len(self._hidden_tasks)} 个任务（右键显示）")
            else:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无任务数据")
            self._bar_rects = []
            return

        w = self.width()
        h = self.height()

        # Layout constants
        top_margin = 30      # Space for time labels above bars
        bottom_margin = 50   # Space for task names + count
        left_margin = 10
        right_margin = 10
        bar_spacing = 12
        max_bar_count = min(len(self._data), 8)

        chart_width = w - left_margin - right_margin
        chart_height = h - top_margin - bottom_margin

        bar_width = max(30, min(60, (chart_width - bar_spacing * (max_bar_count + 1)) / max_bar_count))
        total_bars_width = max_bar_count * bar_width + (max_bar_count - 1) * bar_spacing
        start_x = left_margin + (chart_width - total_bars_width) / 2

        # Find max value for scaling
        max_seconds = max(stat.total_seconds for stat in self._data[:max_bar_count])
        if max_seconds == 0:
            max_seconds = 1

        # Draw baseline
        baseline_y = h - bottom_margin
        line_color = QColor("#e5e5ea") if not self._dark_mode else QColor("#48484a")
        painter.setPen(QPen(line_color, 1))
        painter.drawLine(int(left_margin), int(baseline_y), int(w - right_margin), int(baseline_y))

        # Draw bars
        self._bar_rects = []
        for i, stat in enumerate(self._data[:max_bar_count]):
            x = start_x + i * (bar_width + bar_spacing)
            raw_height = (stat.total_seconds / max_seconds) * chart_height * 0.85
            bar_h = max(4, raw_height * self._anim_progress)
            bar_y = baseline_y - bar_h

            # Record bar rect for hit-testing
            self._bar_rects.append((QRectF(x, bar_y, bar_width, bar_h), stat.task_name))

            # Bar gradient
            color_idx = i % len(self.BAR_COLORS)
            c1, c2 = self.BAR_COLORS[color_idx]
            gradient = QLinearGradient(x, bar_y, x, baseline_y)
            gradient.setColorAt(0.0, QColor(c1))
            gradient.setColorAt(1.0, QColor(c2))

            # Draw rounded bar
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            radius = min(6, bar_width / 3)
            bar_rect = QRectF(x, bar_y, bar_width, bar_h)
            path = QPainterPath()
            path.addRoundedRect(bar_rect, radius, radius)
            painter.drawPath(path)

            # Draw glow/shadow effect
            glow_color = QColor(c1)
            glow_color.setAlpha(30)
            painter.setBrush(glow_color)
            glow_rect = QRectF(x - 2, bar_y + bar_h * 0.3, bar_width + 4, bar_h * 0.7 + 4)
            painter.drawRoundedRect(glow_rect, radius + 2, radius + 2)

            # Redraw bar on top of glow
            painter.setBrush(gradient)
            painter.drawPath(path)

            # Time label above bar
            if self._anim_progress > 0.5:
                label_alpha = min(255, int((self._anim_progress - 0.5) * 2 * 255))
                time_color = QColor("#1d1d1f") if not self._dark_mode else QColor("#ffffff")
                time_color.setAlpha(label_alpha)
                painter.setPen(time_color)
                painter.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.DemiBold))
                time_text = stat.format_time()
                time_rect = QRectF(x - 10, bar_y - 22, bar_width + 20, 20)
                painter.drawText(time_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, time_text)

            # Task name below baseline
            name_color = QColor("#6e6e73") if not self._dark_mode else QColor("#98989d")
            painter.setPen(name_color)
            painter.setFont(QFont(".AppleSystemUIFont", 12))
            name_rect = QRectF(x - 8, baseline_y + 4, bar_width + 16, 20)
            # Truncate long names
            display_name = stat.task_name if len(stat.task_name) <= 6 else stat.task_name[:5] + "…"
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, display_name)

            # Task count
            count_color = QColor("#aeaeb2") if not self._dark_mode else QColor("#636366")
            painter.setPen(count_color)
            painter.setFont(QFont(".AppleSystemUIFont", 11))
            count_rect = QRectF(x - 8, baseline_y + 22, bar_width + 16, 18)
            painter.drawText(count_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             f"{stat.task_count}次")


class TaskTreeMap(QWidget):
    """Animated treemap chart showing task time percentage distribution.

    Fills the entire available area with colored rectangles proportional to
    each task's time, with task name, time and percentage labels inside.
    """

    hidden_tasks_changed = pyqtSignal(set)
    notebook_requested = pyqtSignal(str)  # task_name, emitted on double-click
    continue_task_requested = pyqtSignal(str)  # task_name, emitted from context menu
    star_rating_changed = pyqtSignal(str, int)  # task_name, rating (0-5)

    BLOCK_COLORS = TaskBarChart.BAR_COLORS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data: List[TaskTimeStats] = []
        self._data: List[TaskTimeStats] = []
        self._hidden_tasks: set = set()
        self._block_rects: list = []  # (QRectF, task_name) for hit-testing
        self._star_ratings: dict = {}  # task_name -> 0..5
        self._dark_mode = False
        self._anim_progress = 0.0
        self.setMinimumHeight(200)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._animation = QPropertyAnimation(self, b"animProgress")
        self._animation.setDuration(600)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_anim_progress(self):
        return self._anim_progress

    def _set_anim_progress(self, val):
        self._anim_progress = val
        self.update()

    animProgress = pyqtProperty(float, _get_anim_progress, _set_anim_progress)

    def _apply_filter(self):
        self._data = [s for s in self._all_data if s.task_name not in self._hidden_tasks]

    def set_data(self, data: List[TaskTimeStats]):
        new_key = [(s.task_name, s.total_seconds, s.task_count) for s in data]
        old_key = [(s.task_name, s.total_seconds, s.task_count) for s in self._all_data]
        if new_key == old_key:
            return
        self._all_data = data
        self._apply_filter()
        self._anim_progress = 0.0
        self._animation.start()

    def set_dark_mode(self, enabled: bool):
        self._dark_mode = enabled
        self.update()

    def set_star_ratings(self, ratings: dict):
        """Set the task-name -> star rating mapping."""
        self._star_ratings = dict(ratings) if ratings else {}
        self.update()

    # ---- squarified treemap layout ----

    @staticmethod
    def _squarify(values: list, rect: QRectF) -> list:
        """Compute squarified treemap rectangles.

        values: list of (index, value) sorted descending by value.
        rect: available QRectF.
        Returns: list of (index, QRectF).
        """
        if not values:
            return []

        total = sum(v for _, v in values)
        if total <= 0 or rect.width() <= 0 or rect.height() <= 0:
            return []

        results = []
        remaining = list(values)
        r = QRectF(rect)

        while remaining:
            # Normalize values so they sum to the area of the current rect
            area = r.width() * r.height()
            rem_total = sum(v for _, v in remaining)

            # Decide split direction: lay strips along the shorter side
            if r.width() >= r.height():
                # vertical strip on the left
                results += TaskTreeMap._layout_strip(remaining, r, rem_total, area, 'vertical')
            else:
                results += TaskTreeMap._layout_strip(remaining, r, rem_total, area, 'horizontal')

            # _layout_strip consumes items from `remaining` and shrinks `r` in place
            # It modifies remaining and r directly — see implementation below
            # Actually we need a different approach: return new remaining and new rect.
            break  # handled inside _layout_strip via recursion

        return results

    @staticmethod
    def _layout_strip(values, rect, total, area, direction):
        """Lay out values in strips recursively."""
        if not values or area <= 0:
            return []

        results = []
        remaining = list(values)
        r = QRectF(rect)

        while remaining:
            rem_total = sum(v for _, v in remaining)
            if rem_total <= 0:
                break

            short_side = min(r.width(), r.height())
            if short_side <= 0:
                break

            # Greedily add items to current row while aspect ratio improves
            row = [remaining[0]]
            row_sum = remaining[0][1]
            best_worst_ratio = float('inf')

            for k in range(1, len(remaining)):
                test_row = row + [remaining[k]]
                test_sum = row_sum + remaining[k][1]
                # Compute worst aspect ratio in this test row
                strip_len = (test_sum / rem_total) * (r.width() if r.width() >= r.height() else r.height())
                if strip_len <= 0:
                    break
                worst = 0
                for _, v in test_row:
                    item_other = (v / test_sum) * short_side if test_sum > 0 else 0
                    if item_other <= 0 or strip_len <= 0:
                        continue
                    ratio = max(strip_len / item_other, item_other / strip_len)
                    worst = max(worst, ratio)

                if worst <= best_worst_ratio:
                    best_worst_ratio = worst
                    row = test_row
                    row_sum = test_sum
                else:
                    break

            # Lay out the row
            strip_frac = row_sum / rem_total if rem_total > 0 else 1
            if r.width() >= r.height():
                strip_w = r.width() * strip_frac
                y = r.y()
                for idx, v in row:
                    item_h = (v / row_sum) * r.height() if row_sum > 0 else 0
                    results.append((idx, QRectF(r.x(), y, strip_w, item_h)))
                    y += item_h
                r = QRectF(r.x() + strip_w, r.y(), r.width() - strip_w, r.height())
            else:
                strip_h = r.height() * strip_frac
                x = r.x()
                for idx, v in row:
                    item_w = (v / row_sum) * r.width() if row_sum > 0 else 0
                    results.append((idx, QRectF(x, r.y(), item_w, strip_h)))
                    x += item_w
                r = QRectF(r.x(), r.y() + strip_h, r.width(), r.height() - strip_h)

            remaining = remaining[len(row):]

        return results

    # ---- hit testing ----

    def _hit_test_block(self, pos) -> str | None:
        for rect, name in self._block_rects:
            if rect.contains(QPointF(pos)):
                return name
        return None

    def mouseDoubleClickEvent(self, event):
        """Open notebook on double-click on a block."""
        task_name = self._hit_test_block(event.pos())
        if task_name:
            self.notebook_requested.emit(task_name)
        else:
            super().mouseDoubleClickEvent(event)

    # ---- context menu (same pattern as bar chart) ----

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 20px;
                font-size: 12px;
                color: #1d1d1f;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #e5e5ea;
                margin: 4px 8px;
            }
        """)

        task_name = self._hit_test_block(pos)
        if task_name:
            continue_action = menu.addAction("▶ 继续")
            continue_action.setData(("continue", task_name))
            menu.addSeparator()
            current_rating = int(self._star_ratings.get(task_name, 0) or 0)
            star_menu = menu.addMenu(f"重要性 ({'★' * current_rating}{'☆' * (5 - current_rating)})")
            star_menu.setStyleSheet(menu.styleSheet())
            for r in range(0, 6):
                label = "无" if r == 0 else "★" * r
                act = star_menu.addAction(label)
                act.setData(("rate", task_name, r))
            menu.addSeparator()
            copy_action = menu.addAction("复制项目名")
            copy_action.setData(("copy_name", task_name))
            hide_action = menu.addAction("隐藏")
            hide_action.setData(("hide", task_name))

        if self._hidden_tasks:
            if task_name:
                menu.addSeparator()
            restore_menu = menu.addMenu(f"已隐藏 ({len(self._hidden_tasks)})")
            restore_menu.setStyleSheet(menu.styleSheet())
            for name in sorted(self._hidden_tasks):
                action = restore_menu.addAction(f"显示「{name}」")
                action.setData(("show", name))
            restore_menu.addSeparator()
            show_all = restore_menu.addAction("显示全部")
            show_all.setData(("show_all", None))

        if menu.isEmpty():
            return

        action = menu.exec(self.mapToGlobal(pos))
        if action and action.data():
            data = action.data()
            cmd = data[0]
            if cmd == "rate":
                _, name, rating = data
                if rating <= 0:
                    self._star_ratings.pop(name, None)
                else:
                    self._star_ratings[name] = rating
                self.star_rating_changed.emit(name, rating)
                self.update()
                return
            name = data[1]
            if cmd == "continue":
                self.continue_task_requested.emit(name)
                return
            elif cmd == "copy_name":
                QApplication.clipboard().setText(name)
                return
            elif cmd == "hide":
                self._hidden_tasks.add(name)
            elif cmd == "show":
                self._hidden_tasks.discard(name)
            elif cmd == "show_all":
                self._hidden_tasks.clear()
            self._apply_filter()
            self._anim_progress = 0.0
            self._animation.start()
            self.hidden_tasks_changed.emit(self._hidden_tasks)

    # ---- painting ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._data:
            text_color = QColor("#8e8e93") if not self._dark_mode else QColor("#98989d")
            painter.setPen(text_color)
            painter.setFont(QFont(".AppleSystemUIFont", 13))
            if self._hidden_tasks:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 f"已隐藏 {len(self._hidden_tasks)} 个任务（右键显示）")
            else:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无任务数据")
            self._block_rects = []
            return

        w = self.width()
        h = self.height()
        margin = 6
        chart_rect = QRectF(margin, margin, w - margin * 2, h - margin * 2)

        total = sum(s.total_seconds for s in self._data)
        if total == 0:
            return

        # Build values list sorted descending
        values = [(i, s.total_seconds) for i, s in enumerate(self._data)]
        values.sort(key=lambda x: x[1], reverse=True)

        layout = self._layout_strip(values, chart_rect, total,
                                     chart_rect.width() * chart_rect.height(), 'vertical')

        gap = 2  # gap between blocks
        self._block_rects = []

        for idx, block_rect in layout:
            stat = self._data[idx]
            pct = (stat.total_seconds / total) * 100

            # Animate: blocks grow from left/top
            anim = self._anim_progress
            animated_rect = QRectF(
                block_rect.x(),
                block_rect.y(),
                block_rect.width() * anim,
                block_rect.height() * anim
            )
            # Inset for gap
            inset = QRectF(
                animated_rect.x() + gap / 2,
                animated_rect.y() + gap / 2,
                max(0, animated_rect.width() - gap),
                max(0, animated_rect.height() - gap)
            )
            if inset.width() <= 0 or inset.height() <= 0:
                continue

            self._block_rects.append((block_rect, stat.task_name))

            # Draw block with gradient
            color_idx = idx % len(self.BLOCK_COLORS)
            c1, c2 = self.BLOCK_COLORS[color_idx]
            gradient = QLinearGradient(inset.topLeft(), inset.bottomRight())
            gradient.setColorAt(0.0, QColor(c1))
            gradient.setColorAt(1.0, QColor(c2))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            radius = min(8, inset.width() / 4, inset.height() / 4)
            painter.drawRoundedRect(inset, radius, radius)

            # Draw labels inside the block (only if block is large enough)
            if anim < 0.5:
                continue

            # Draw star rating in top-right corner
            rating = int(self._star_ratings.get(stat.task_name, 0) or 0)
            if rating > 0 and inset.width() > 40 and inset.height() > 22:
                star_size = max(9, min(13, int(min(inset.width(), inset.height()) * 0.16)))
                star_text = "★" * rating
                painter.setFont(QFont(".AppleSystemUIFont", star_size, QFont.Weight.Bold))
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(star_text)
                th = fm.height()
                sx = inset.right() - tw - 6
                sy = inset.top() + 4
                star_rect = QRectF(sx, sy, tw, th)
                # shadow
                painter.setPen(QColor(0, 0, 0, 120))
                painter.drawText(star_rect.translated(1, 1), Qt.AlignmentFlag.AlignCenter, star_text)
                painter.setPen(QColor("#FFD700"))
                painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, star_text)

            label_alpha = min(255, int((anim - 0.5) * 2 * 255))
            text_color = QColor("#ffffff")
            text_color.setAlpha(label_alpha)
            shadow_color = QColor(0, 0, 0, int(80 * label_alpha / 255))

            bw = inset.width()
            bh = inset.height()
            pad = 6

            # Decide what to show based on block size
            show_name = bw > 40 and bh > 20
            show_pct = bw > 30 and bh > 16
            show_time = bw > 50 and bh > 36

            if not show_pct:
                continue

            # Calculate font sizes based on block area
            area_factor = min(bw, bh)
            name_size = max(9, min(13, int(area_factor * 0.18)))
            pct_size = max(8, min(11, int(area_factor * 0.14)))

            text_rect = QRectF(inset.x() + pad, inset.y() + pad,
                               bw - pad * 2, bh - pad * 2)

            if show_name and show_time:
                # 3-line layout: name / time / pct
                line_h = text_rect.height() / 3
                display_name = stat.task_name
                max_chars = max(2, int(text_rect.width() / (name_size * 0.65)))
                if len(display_name) > max_chars:
                    display_name = display_name[:max_chars - 1] + "…"

                # Name
                painter.setFont(QFont(".AppleSystemUIFont", name_size, QFont.Weight.DemiBold))
                painter.setPen(shadow_color)
                name_rect = QRectF(text_rect.x() + 1, text_rect.y() + 1, text_rect.width(), line_h)
                painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 display_name)
                painter.setPen(text_color)
                name_rect = QRectF(text_rect.x(), text_rect.y(), text_rect.width(), line_h)
                painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 display_name)

                # Time
                painter.setFont(QFont(".AppleSystemUIFont", pct_size))
                time_text = stat.format_time()
                time_rect = QRectF(text_rect.x(), text_rect.y() + line_h, text_rect.width(), line_h)
                time_color = QColor(255, 255, 255, int(200 * label_alpha / 255))
                painter.setPen(time_color)
                painter.drawText(time_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 time_text)

                # Percentage
                pct_rect = QRectF(text_rect.x(), text_rect.y() + line_h * 2, text_rect.width(), line_h)
                painter.drawText(pct_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 f"{pct:.1f}%")

            elif show_name:
                # 2-line: name / pct
                line_h = text_rect.height() / 2
                display_name = stat.task_name
                max_chars = max(2, int(text_rect.width() / (name_size * 0.65)))
                if len(display_name) > max_chars:
                    display_name = display_name[:max_chars - 1] + "…"

                painter.setFont(QFont(".AppleSystemUIFont", name_size, QFont.Weight.DemiBold))
                painter.setPen(text_color)
                name_rect = QRectF(text_rect.x(), text_rect.y(), text_rect.width(), line_h)
                painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 display_name)

                painter.setFont(QFont(".AppleSystemUIFont", pct_size))
                pct_color = QColor(255, 255, 255, int(200 * label_alpha / 255))
                painter.setPen(pct_color)
                pct_rect = QRectF(text_rect.x(), text_rect.y() + line_h, text_rect.width(), line_h)
                painter.drawText(pct_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 f"{pct:.1f}%")
            else:
                # Just pct
                painter.setFont(QFont(".AppleSystemUIFont", pct_size, QFont.Weight.DemiBold))
                painter.setPen(text_color)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{pct:.0f}%")


class StatsDashboard(QWidget):
    """Dashboard showing statistics overview."""

    period_changed = pyqtSignal(int)  # days: 3, 7, 30, 365
    custom_range_selected = pyqtSignal(date, date)
    notebook_requested = pyqtSignal(str)  # task_name, bubbled from charts
    continue_task_requested = pyqtSignal(str)  # task_name, bubbled from charts

    PERIODS = [
        ("今天", 1),
        ("近三天", 3),
        ("近一周", 7),
        ("近一月", 30),
        ("近一年", 365),
    ]

    SETTINGS_KEY = "hidden_chart_tasks"
    STAR_RATINGS_KEY = "task_star_ratings"

    def __init__(self, db: Optional[Database] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._dark_mode = False
        self._period_buttons: list[QPushButton] = []
        self._calendar_popup = None
        self._custom_range_active = False
        self._active_period_days = 7
        self._chart_mode = "bar"  # "bar" or "pie"
        self._setup_ui()
        self._load_hidden_tasks()
        self._load_star_ratings()

    def _setup_ui(self):
        """Set up the dashboard UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        # Stats cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.running_card = StatCard("当前运行", "0个")
        self.focus_card = StatCard("今日专注", "0分钟")
        self.streak_card = StatCard("连续天数", "0天")

        cards_layout.addWidget(self.running_card)
        cards_layout.addWidget(self.focus_card)
        cards_layout.addWidget(self.streak_card)

        layout.addLayout(cards_layout)

        # Category distribution
        self.dist_frame = QFrame()
        self.dist_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e5ea;
                border-radius: 10px;
                padding: 12px;
            }
        """)

        dist_layout = QVBoxLayout(self.dist_frame)
        dist_layout.setSpacing(8)
        dist_layout.setContentsMargins(12, 12, 12, 12)

        self.dist_title = QLabel("本周时间分布")
        self.dist_title.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: 500;
                color: #1d1d1f;
            }
        """)
        dist_layout.addWidget(self.dist_title)

        self.category_bar = CategoryBar()
        dist_layout.addWidget(self.category_bar)

        self.category_legend = CategoryLegend()
        dist_layout.addWidget(self.category_legend)

        layout.addWidget(self.dist_frame)

        # Task time bar chart
        self.chart_frame = chart_frame = QFrame()
        chart_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e5ea;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setSpacing(8)
        chart_layout.setContentsMargins(12, 12, 12, 12)

        # Header row: title + chart toggle + period selector
        chart_header = QHBoxLayout()

        chart_title = QLabel("任务时间统计")
        chart_title.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: 500;
                color: #1d1d1f;
            }
        """)
        self._chart_title = chart_title
        chart_header.addWidget(chart_title)

        # Chart type toggle button
        self._chart_toggle_btn = QPushButton("占比")
        self._chart_toggle_btn.setFixedHeight(26)
        self._chart_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chart_toggle_btn.setToolTip("切换图表类型")
        self._chart_toggle_btn.clicked.connect(self._on_chart_toggle)
        chart_header.addWidget(self._chart_toggle_btn)
        self._apply_chart_toggle_style()

        chart_header.addStretch()

        # Period selector buttons
        for label, days in self.PERIODS:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("days", days)
            btn.clicked.connect(lambda checked, d=days: self._on_period_clicked(d))
            self._period_buttons.append(btn)
            chart_header.addWidget(btn)

        # Calendar button for custom date range
        self._calendar_btn = QPushButton("📅 日期")
        self._calendar_btn.setFixedHeight(26)
        self._calendar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calendar_btn.setToolTip("自定义日期范围")
        self._calendar_btn.clicked.connect(self._on_calendar_clicked)
        chart_header.addWidget(self._calendar_btn)

        self._apply_period_button_styles(7)  # default: 近一周
        chart_layout.addLayout(chart_header)

        # Stacked widget for bar chart / pie chart
        self._chart_stack = QStackedWidget()
        self.task_bar_chart = TaskBarChart()
        self.task_treemap = TaskTreeMap()
        self.task_bar_chart.hidden_tasks_changed.connect(self._on_hidden_tasks_changed)
        self.task_treemap.hidden_tasks_changed.connect(self._on_hidden_tasks_changed)
        self.task_bar_chart.notebook_requested.connect(self.notebook_requested)
        self.task_treemap.notebook_requested.connect(self.notebook_requested)
        self.task_bar_chart.continue_task_requested.connect(self.continue_task_requested)
        self.task_treemap.continue_task_requested.connect(self.continue_task_requested)
        self.task_treemap.star_rating_changed.connect(self._on_star_rating_changed)
        self._chart_stack.addWidget(self.task_bar_chart)   # index 0
        self._chart_stack.addWidget(self.task_treemap)   # index 1
        self._chart_stack.setCurrentIndex(0)
        chart_layout.addWidget(self._chart_stack)

        layout.addWidget(chart_frame)

    def update_running_count(self, count: int):
        """Update running tasks count."""
        self.running_card.set_value(f"{count}个")

    def update_today_focus(self, seconds: int):
        """Update today's focus time."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            self.focus_card.set_value(f"{hours}小时{minutes}分钟")
        else:
            self.focus_card.set_value(f"{minutes}分钟")

    def update_streak(self, days: int):
        """Update streak count."""
        self.streak_card.set_value(f"{days}天")

    def update_category_distribution(self, stats: List[CategoryStats]):
        """Update category distribution."""
        self.category_bar.set_data(stats)
        self.category_legend.set_data(stats)

    def update_task_distribution(self, stats: List[TaskTimeStats]):
        """Update task time charts (bar and pie)."""
        self.task_bar_chart.set_data(stats)
        self.task_treemap.set_data(stats)

    def _load_hidden_tasks(self):
        """Load hidden tasks from database."""
        if not self._db:
            return
        raw = self._db.get_setting(self.SETTINGS_KEY, "[]")
        try:
            names = set(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            names = set()
        if names:
            self.task_bar_chart._hidden_tasks = set(names)
            self.task_bar_chart._apply_filter()
            self.task_treemap._hidden_tasks = set(names)
            self.task_treemap._apply_filter()

    def _save_hidden_tasks(self, hidden: set):
        """Persist hidden tasks to database."""
        if not self._db:
            return
        self._db.set_setting(self.SETTINGS_KEY, json.dumps(sorted(hidden)))

    def _load_star_ratings(self):
        """Load task star ratings from database."""
        if not self._db:
            return
        raw = self._db.get_setting(self.STAR_RATINGS_KEY, "{}")
        try:
            ratings = {k: int(v) for k, v in json.loads(raw).items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            ratings = {}
        self.task_treemap.set_star_ratings(ratings)

    def _on_star_rating_changed(self, task_name: str, rating: int):
        """Persist star rating change."""
        if not self._db:
            return
        raw = self._db.get_setting(self.STAR_RATINGS_KEY, "{}")
        try:
            ratings = {k: int(v) for k, v in json.loads(raw).items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            ratings = {}
        if rating <= 0:
            ratings.pop(task_name, None)
        else:
            ratings[task_name] = rating
        self._db.set_setting(self.STAR_RATINGS_KEY, json.dumps(ratings, ensure_ascii=False))

    def _on_hidden_tasks_changed(self, hidden: set):
        """Handle hidden tasks change from either chart. Sync and persist."""
        # Sync to the other chart
        self.task_bar_chart._hidden_tasks = set(hidden)
        self.task_bar_chart._apply_filter()
        self.task_bar_chart.update()
        self.task_treemap._hidden_tasks = set(hidden)
        self.task_treemap._apply_filter()
        self.task_treemap.update()
        self._save_hidden_tasks(hidden)

    def _on_period_clicked(self, days: int):
        """Handle period button click."""
        self._custom_range_active = False
        self._active_period_days = days
        self._apply_period_button_styles(days)
        self._apply_calendar_button_style()
        self._chart_title.setText("任务时间统计")
        self.period_changed.emit(days)

    def _on_chart_toggle(self):
        """Toggle between bar chart and pie chart."""
        if self._chart_mode == "bar":
            self._chart_mode = "pie"
            self._chart_toggle_btn.setText("柱状")
            self._chart_stack.setCurrentIndex(1)
        else:
            self._chart_mode = "bar"
            self._chart_toggle_btn.setText("占比")
            self._chart_stack.setCurrentIndex(0)
        self._apply_chart_toggle_style()

    def _apply_chart_toggle_style(self):
        """Apply style to the chart type toggle button."""
        if self._dark_mode:
            self._chart_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3c;
                    color: #e5e5ea;
                    border: 1px solid #48484a;
                    border-radius: 6px;
                    font-size: 13px;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background-color: #48484a;
                    color: #ffffff;
                }
            """)
        else:
            self._chart_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                    border-radius: 6px;
                    font-size: 13px;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background-color: #e5e5ea;
                    color: #1d1d1f;
                }
            """)

    def _on_calendar_clicked(self):
        """Show the calendar popup for custom date range selection."""
        if self._calendar_popup:
            self._calendar_popup.close()
        self._calendar_popup = CalendarPopup(self)
        self._calendar_popup.set_dark_mode(self._dark_mode)
        self._calendar_popup.date_range_confirmed.connect(self._on_custom_range_confirmed)
        # Position below the calendar button
        btn_pos = self._calendar_btn.mapToGlobal(self._calendar_btn.rect().bottomLeft())
        self._calendar_popup.move(btn_pos.x() - 200, btn_pos.y() + 4)
        self._calendar_popup.show()

    def _on_custom_range_confirmed(self, start: date, end: date):
        """Handle confirmed custom date range."""
        self._custom_range_active = True
        # Deselect all period buttons
        self._apply_period_button_styles(None)
        self._apply_calendar_button_style()
        # Update title to show selected range
        self._chart_title.setText(f"任务时间统计  {start.month}/{start.day} - {end.month}/{end.day}")
        self.custom_range_selected.emit(start, end)

    def _apply_period_button_styles(self, active_days: int):
        """Apply styles to period buttons, highlighting the active one."""
        for btn in self._period_buttons:
            if btn.property("days") == active_days:
                if self._dark_mode:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #0a84ff;
                            color: #ffffff;
                            border: none;
                            border-radius: 6px;
                            font-size: 13px;
                            padding: 0 10px;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #007AFF;
                            color: #ffffff;
                            border: none;
                            border-radius: 6px;
                            font-size: 13px;
                            padding: 0 10px;
                        }
                    """)
            else:
                if self._dark_mode:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #3a3a3c;
                            color: #e5e5ea;
                            border: 1px solid #48484a;
                            border-radius: 6px;
                            font-size: 13px;
                            padding: 0 10px;
                        }
                        QPushButton:hover {
                            background-color: #48484a;
                            color: #ffffff;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f5f5f7;
                            color: #1d1d1f;
                            border: 1px solid #d2d2d7;
                            border-radius: 6px;
                            font-size: 13px;
                            padding: 0 10px;
                        }
                        QPushButton:hover {
                            background-color: #e5e5ea;
                            color: #1d1d1f;
                        }
                    """)

    def _apply_calendar_button_style(self):
        """Apply style to the calendar button based on active state."""
        if self._custom_range_active:
            if self._dark_mode:
                self._calendar_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0a84ff;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 13px;
                        padding: 0 10px;
                    }
                """)
            else:
                self._calendar_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #007AFF;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 13px;
                        padding: 0 10px;
                    }
                """)
        else:
            if self._dark_mode:
                self._calendar_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3a3a3c;
                        color: #e5e5ea;
                        border: 1px solid #48484a;
                        border-radius: 6px;
                        font-size: 13px;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background-color: #48484a;
                        color: #ffffff;
                    }
                """)
            else:
                self._calendar_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f5f5f7;
                        color: #1d1d1f;
                        border: 1px solid #d2d2d7;
                        border-radius: 6px;
                        font-size: 13px;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background-color: #e5e5ea;
                        color: #1d1d1f;
                    }
                """)

    def set_dark_mode(self, enabled: bool):
        """Toggle dark mode styling."""
        self._dark_mode = enabled
        self.task_bar_chart.set_dark_mode(enabled)
        self.task_treemap.set_dark_mode(enabled)
        self.category_bar.set_dark_mode(enabled)
        self.category_legend.set_dark_mode(enabled)
        self._apply_chart_toggle_style()

        # Re-apply period button styles for theme
        if self._custom_range_active:
            self._apply_period_button_styles(None)
        else:
            self._apply_period_button_styles(self._active_period_days)
        self._apply_calendar_button_style()

        # Frame & title colors
        if enabled:
            frame_style = """
                QFrame {
                    background-color: #2c2c2e;
                    border: 1px solid #48484a;
                    border-radius: 10px;
                    padding: 12px;
                }
            """
            title_style = """
                QLabel {
                    font-size: 13px;
                    font-weight: 500;
                    color: #ffffff;
                }
            """
            card_title_style = """
                QLabel {
                    font-size: 11px;
                    color: #98989d;
                    text-transform: uppercase;
                }
            """
            card_value_style = """
                QLabel {
                    font-size: 24px;
                    font-weight: 600;
                    color: #ffffff;
                }
            """
        else:
            frame_style = """
                QFrame {
                    background-color: #ffffff;
                    border: 1px solid #e5e5ea;
                    border-radius: 10px;
                    padding: 12px;
                }
            """
            title_style = """
                QLabel {
                    font-size: 13px;
                    font-weight: 500;
                    color: #1d1d1f;
                }
            """
            card_title_style = """
                QLabel {
                    font-size: 11px;
                    color: #6e6e73;
                    text-transform: uppercase;
                }
            """
            card_value_style = """
                QLabel {
                    font-size: 24px;
                    font-weight: 600;
                    color: #1d1d1f;
                }
            """

        # Distribution frame
        self.dist_frame.setStyleSheet(frame_style)
        self.dist_title.setStyleSheet(title_style)

        # Chart frame
        self.chart_frame.setStyleSheet(frame_style)
        self._chart_title.setStyleSheet(title_style)

        # Stat cards
        for card in [self.running_card, self.focus_card, self.streak_card]:
            card.setStyleSheet(frame_style)
            card.title_label.setStyleSheet(card_title_style)
            card.value_label.setStyleSheet(card_value_style)
