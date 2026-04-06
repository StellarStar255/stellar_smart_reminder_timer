"""Main application window."""

from datetime import date, datetime
from typing import Dict, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSystemTrayIcon, QMenu,
    QApplication, QMessageBox, QSizePolicy, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QIcon, QAction, QFont, QPixmap, QPainter, QColor, QBrush

from src.data.database import Database
from src.data.repositories import CategoryRepository, PresetRepository, TaskRepository
from src.core.timer_engine import TimerEngine
from src.core.task_manager import TaskManager
from src.core.preset_manager import PresetManager
from src.core.statistics_engine import StatisticsEngine
from src.core.notification_service import NotificationService, InAppNotificationDialog
from src.models import Task, TaskStatus, Category, Preset
from src.ui.components.timer_card import TimerCard, EditTimerDialog
from src.ui.components.preset_bar import PresetBar, CustomTimerDialog, EditPresetDialog
from src.ui.components.category_sidebar import CategorySidebar
from src.ui.components.stats_dashboard import StatsDashboard
from src.ui.components.task_notebook_dialog import TaskNotebookDialog
from src.ui.styles import LIGHT_THEME, DARK_THEME


def _create_objc_delegate_class():
    """Create ObjC delegate class once at module level."""
    import objc
    from Foundation import NSObject

    class _TrayMenuDelegate(NSObject):
        _main_window = None

        def showWindow_(self, sender):
            if self._main_window:
                self._main_window._show_window()

        def quitApp_(self, sender):
            QApplication.quit()

    return _TrayMenuDelegate

_TrayMenuDelegate = _create_objc_delegate_class()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)

        self.db = db
        self._dark_mode = db.get_setting("dark_mode", "0") == "1"

        # Initialize repositories
        self.category_repo = CategoryRepository(db)
        self.preset_repo = PresetRepository(db)
        self.task_repo = TaskRepository(db)

        # Initialize engines
        self.timer_engine = TimerEngine(self)
        self.task_manager = TaskManager(db, self.timer_engine, self)
        self.preset_manager = PresetManager(db)
        self.stats_engine = StatisticsEngine(db)
        self.notification_service = NotificationService(self)

        # Timer cards mapping
        self._timer_cards: Dict[int, TimerCard] = {}

        # Category cache
        self._categories: Dict[int, Category] = {}

        # Current task distribution period (days)
        self._task_dist_days: int = 7

        # Current category filter (None = all)
        self._selected_category_id: Optional[int] = None

        self._setup_ui()
        self._setup_tray()
        self._connect_signals()
        self._load_data()

        # Restore saved preferences
        self._restore_preferences()

        # Start stats update timer
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(5000)  # Update every 5 seconds

    def _setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("星际脉动")
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)

        # Set window icon
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                  "assets", "stellar_pulse_smart_reminder_timer.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left sidebar
        self.sidebar = CategorySidebar()
        main_layout.addWidget(self.sidebar)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("QFrame { background-color: #e5e5ea; }")
        separator.setFixedWidth(1)
        main_layout.addWidget(separator)

        # Main content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(20, 16, 20, 16)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("星际脉动")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        header_layout.addWidget(title)

        # Current time display
        self._clock_label = QLabel()
        self._clock_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                color: #6e6e73;
                padding-left: 8px;
            }
        """)
        header_layout.addWidget(self._clock_label)
        self._update_clock()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Preset search input
        self.preset_search_input = QLineEdit()
        self.preset_search_input.setPlaceholderText("🔍 搜索预设...")
        self.preset_search_input.setClearButtonEnabled(True)
        self.preset_search_input.setFixedWidth(160)
        self.preset_search_input.setFixedHeight(32)
        self.preset_search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 12px;
                background-color: #f5f5f7;
                color: #1d1d1f;
            }
            QLineEdit:focus {
                border-color: #007AFF;
                background-color: #ffffff;
            }
        """)
        header_layout.addWidget(self.preset_search_input)

        header_layout.addStretch()

        # Alarm mode toggle button
        self.alarm_btn = QPushButton("🔔 一直响")
        self.alarm_btn.setFixedHeight(36)
        self.alarm_btn.setToolTip("切换闹钟模式：一直响 / 响三下")
        self.alarm_btn.clicked.connect(self._toggle_alarm_mode)
        self.alarm_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                font-size: 14px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #e5e5ea;
                color: #1d1d1f;
            }
        """)
        header_layout.addWidget(self.alarm_btn)

        # Theme toggle button
        self.theme_btn = QPushButton("🌙 深色")
        self.theme_btn.setFixedHeight(36)
        self.theme_btn.setToolTip("切换深色模式")
        self.theme_btn.clicked.connect(self._toggle_theme)
        self.theme_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                font-size: 14px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #e5e5ea;
                color: #1d1d1f;
            }
        """)
        header_layout.addWidget(self.theme_btn)

        content_layout.addLayout(header_layout)

        # Preset bar
        self.preset_bar = PresetBar()
        content_layout.addWidget(self.preset_bar)

        # Main scrollable content area (timer cards at top, stats below)
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # Timer cards area (always at the top, visible first)
        self.timer_container = QWidget()
        self.timer_container.setAcceptDrops(True)
        self.timer_container.installEventFilter(self)
        self.timer_layout = QHBoxLayout(self.timer_container)
        self.timer_layout.setSpacing(16)
        self.timer_layout.setContentsMargins(0, 0, 0, 0)
        self.timer_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Drop indicator for drag-reorder
        self._card_drop_indicator = QWidget(self.timer_container)
        self._card_drop_indicator.setFixedWidth(3)
        self._card_drop_indicator.setStyleSheet("background-color: #007AFF; border-radius: 1px;")
        self._card_drop_indicator.hide()

        # Placeholder when no timers
        self.empty_label = QLabel("点击上方预设或自定义按钮开始计时")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("""
            QLabel {
                color: #6e6e73;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.timer_layout.addWidget(self.empty_label)
        self.timer_layout.addStretch()

        scroll_layout.addWidget(self.timer_container)

        # Stats dashboard (below timer cards, scrollable)
        self.stats_dashboard = StatsDashboard(db=self.db)
        scroll_layout.addWidget(self.stats_dashboard)

        scroll_layout.addStretch()

        main_scroll.setWidget(scroll_content)
        content_layout.addWidget(main_scroll, 1)

        main_layout.addWidget(content, 1)

        # Apply initial theme
        self._apply_theme()

    def _setup_tray(self):
        """Set up macOS native status bar item via pyobjc."""
        from AppKit import (
            NSStatusBar, NSImage, NSVariableStatusItemLength,
            NSMenu, NSMenuItem, NSApplication, NSData
        )
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

        # Keep a QSystemTrayIcon reference for closeEvent compatibility
        self.tray_icon = QSystemTrayIcon(self)

        # Create native macOS status bar item
        self._status_bar = NSStatusBar.systemStatusBar()
        self._status_item = self._status_bar.statusItemWithLength_(NSVariableStatusItemLength)

        # Create 22x22 clock icon
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(0, 0, 0, 255)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(3, 3, 16, 16)
        painter.setPen(QColor(255, 255, 255))
        painter.drawLine(11, 11, 11, 6)
        painter.drawLine(11, 11, 15, 11)
        painter.end()

        # Convert QPixmap to NSImage
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        ns_data = NSData.dataWithBytes_length_(bytes(byte_array), len(byte_array))
        ns_image = NSImage.alloc().initWithData_(ns_data)
        ns_image.setTemplate_(True)  # Adapts to light/dark menu bar
        self._status_item.button().setImage_(ns_image)

        # Create native menu
        ns_menu = NSMenu.alloc().init()

        self._menu_delegate = _TrayMenuDelegate.alloc().init()
        self._menu_delegate._main_window = self

        show_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("显示窗口", "showWindow:", "")
        show_item.setTarget_(self._menu_delegate)
        ns_menu.addItem_(show_item)

        ns_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quitApp:", "")
        quit_item.setTarget_(self._menu_delegate)
        ns_menu.addItem_(quit_item)

        self._status_item.setMenu_(ns_menu)

    def _connect_signals(self):
        """Connect all signals."""
        # Preset bar
        self.preset_bar.preset_selected.connect(self._on_preset_selected)
        self.preset_bar.custom_requested.connect(self._on_custom_requested)
        self.preset_bar.preset_deleted.connect(self._on_preset_deleted)
        self.preset_bar.preset_edit_requested.connect(self._on_preset_edit_requested)
        self.preset_search_input.textChanged.connect(self.preset_bar._on_search_changed)

        # Stats dashboard
        self.stats_dashboard.period_changed.connect(self._on_period_changed)
        self.stats_dashboard.custom_range_selected.connect(self._on_custom_range_selected)
        self.stats_dashboard.notebook_requested.connect(self._on_notebook_requested)
        self.stats_dashboard.continue_task_requested.connect(self._on_continue_task_from_chart)

        # Sidebar
        self.sidebar.category_selected.connect(self._on_category_selected)

        # Task manager
        self.task_manager.task_created.connect(self._on_task_created)
        self.task_manager.task_completed.connect(self._on_task_completed)

        # Timer engine
        self.timer_engine.tick.connect(self._on_timer_tick)

        # Notification service
        self.notification_service.show_popup.connect(self._show_popup)

    def _load_data(self):
        """Load initial data."""
        # Load categories
        categories = self.category_repo.get_all()
        for cat in categories:
            self._categories[cat.id] = cat
        self.sidebar.set_categories(categories)

        # Load presets (default + custom)
        self._refresh_presets()

        # Load active tasks
        self.task_manager.load_active_tasks()
        for task in self.timer_engine.active_tasks:
            self._create_timer_card(task)

        # Update stats
        self._update_stats()

    def _refresh_presets(self):
        """Refresh preset bar with all presets."""
        self.preset_search_input.clear()
        presets = self.preset_manager.get_all()
        self.preset_bar.set_presets(presets)

    def _refresh_presets_filtered(self):
        """Refresh preset bar respecting the current category filter."""
        self.preset_search_input.clear()
        if self._selected_category_id is None:
            presets = self.preset_manager.get_all()
        else:
            presets = [p for p in self.preset_manager.get_all()
                       if p.category_id == self._selected_category_id]
        self.preset_bar.set_presets(presets)

    def _create_timer_card(self, task: Task):
        """Create a timer card for a task."""
        category = self._categories.get(task.category_id)
        card = TimerCard(task, category)
        card.toggle_clicked.connect(self._on_card_toggle)
        card.stop_clicked.connect(self._on_card_stop)
        card.edit_requested.connect(self._on_card_edit)
        card.notebook_requested.connect(self._on_notebook_requested)
        card.set_dark_mode(self._dark_mode)

        # Add to layout before stretch
        self.timer_layout.insertWidget(self.timer_layout.count() - 1, card)
        self._timer_cards[task.id] = card

        # Hide empty label
        self.empty_label.hide()

    def _remove_timer_card(self, task_id: int):
        """Remove a timer card."""
        if task_id in self._timer_cards:
            card = self._timer_cards.pop(task_id)
            self.timer_layout.removeWidget(card)
            card.deleteLater()

        # Show empty label if no cards
        if not self._timer_cards:
            self.empty_label.show()

    def _update_stats(self):
        """Update statistics display."""
        # Running count
        running = self.timer_engine.running_count
        self.stats_dashboard.update_running_count(running)

        # Today's stats
        today_stats = self.stats_engine.get_today_stats()
        self.stats_dashboard.update_today_focus(today_stats.total_focus_seconds)
        self.sidebar.update_stats(
            today_stats.completed_tasks,
            today_stats.total_focus_seconds
        )

        # Streak
        streak = self.stats_engine.get_streak()
        self.stats_dashboard.update_streak(streak)

        # Category distribution
        cat_stats = self.stats_engine.get_category_distribution()
        self.stats_dashboard.update_category_distribution(cat_stats)

        # Task time distribution bar chart
        task_stats = self.stats_engine.get_task_time_distribution(days=self._task_dist_days)
        self.stats_dashboard.update_task_distribution(task_stats)

    # Event handlers

    def _on_preset_selected(self, preset: Preset):
        """Handle preset selection."""
        task = self.task_manager.create_from_preset(preset)
        self._create_timer_card(task)
        self.task_manager.start_task(task.id)
        # Refresh presets so ordering reflects updated use_count
        self._refresh_presets_filtered()

    def _on_custom_requested(self):
        """Handle custom timer request."""
        categories = list(self._categories.values())
        dialog = CustomTimerDialog(categories, self, dark_mode=self._dark_mode)

        if dialog.exec():
            result = dialog.get_result()
            if result:
                task = self.task_manager.create_task(
                    name=result['name'],
                    duration_seconds=result['duration_seconds'],
                    category_id=result['category_id'],
                )
                self._create_timer_card(task)
                self.task_manager.start_task(task.id)

                # Auto-save as preset for future reuse (dedup by name+duration)
                existing = self.preset_repo.find_by_name_and_duration(
                    result['name'], result['duration_seconds']
                )
                if existing:
                    self.preset_manager.record_usage(existing.id)
                else:
                    self.preset_manager.create(
                        name=result['name'],
                        duration_seconds=result['duration_seconds'],
                        category_id=result['category_id'],
                    )
                self._refresh_presets()

    def _on_preset_deleted(self, preset_id: int):
        """Handle custom preset deletion."""
        self.preset_manager.delete(preset_id)
        self._refresh_presets()

    def _on_preset_edit_requested(self, preset: Preset):
        """Handle preset edit request via right-click menu."""
        categories = list(self._categories.values())
        dialog = EditPresetDialog(preset, categories, self, dark_mode=self._dark_mode)

        if dialog.exec():
            result = dialog.get_result()
            if result:
                preset.name = result['name']
                preset.duration_seconds = result['duration_seconds']
                preset.category_id = result['category_id']
                self.preset_manager.update(preset)
                self._refresh_presets()

    def _on_card_edit(self, task_id: int):
        """Handle timer card edit request via right-click menu."""
        task = self.timer_engine.get_task(task_id)
        if not task:
            return

        categories = list(self._categories.values())
        dialog = EditTimerDialog(task, categories, self)

        if dialog.exec():
            result = dialog.get_result()
            if result:
                task.name = result['name']
                new_duration = result['duration_seconds']
                if new_duration != task.duration_seconds:
                    # Adjust duration, keep elapsed intact
                    task.duration_seconds = new_duration
                task.category_id = result['category_id']
                self.task_repo.update(task)

                # Update the card display
                if task_id in self._timer_cards:
                    category = self._categories.get(task.category_id)
                    self._timer_cards[task_id].set_category(category)
                    self._timer_cards[task_id].update_task(task)

    def _on_period_changed(self, days: int):
        """Handle task distribution period change."""
        self._task_dist_days = days
        task_stats = self.stats_engine.get_task_time_distribution(days=days)
        self.stats_dashboard.update_task_distribution(task_stats)
        # Also update category distribution with the same period
        cat_stats = self.stats_engine.get_category_distribution(days=days)
        self.stats_dashboard.update_category_distribution(cat_stats)

    def _on_custom_range_selected(self, start_date: date, end_date: date):
        """Handle custom date range selection from calendar."""
        cat_stats = self.stats_engine.get_category_distribution_range(start_date, end_date)
        self.stats_dashboard.update_category_distribution(cat_stats)
        task_stats = self.stats_engine.get_task_time_distribution_range(start_date, end_date)
        self.stats_dashboard.update_task_distribution(task_stats)

    def _on_category_selected(self, category: Optional[Category]):
        """Handle category filter selection."""
        self._selected_category_id = category.id if category else None

        # Filter timer cards
        for task_id, card in self._timer_cards.items():
            if self._selected_category_id is None:
                card.show()
            else:
                task = self.timer_engine.get_task(task_id)
                card.setVisible(task is not None and task.category_id == self._selected_category_id)

        # Filter presets
        if self._selected_category_id is None:
            presets = self.preset_manager.get_all()
        else:
            presets = [p for p in self.preset_manager.get_all()
                       if p.category_id == self._selected_category_id]
        self.preset_bar.set_presets(presets)

    def _on_task_created(self, task: Task):
        """Handle task creation."""
        pass  # Card is created in _on_preset_selected

    def _on_task_completed(self, task: Task):
        """Handle task completion."""
        self.notification_service.notify_task_completed(task, self)
        self._update_stats()

    def _on_timer_tick(self, task_id: int):
        """Handle timer tick."""
        task = self.timer_engine.get_task(task_id)
        if task and task_id in self._timer_cards:
            self._timer_cards[task_id].update_task(task)

    def _on_card_toggle(self, task_id: int):
        """Handle card toggle button."""
        self.task_manager.toggle_task(task_id)
        task = self.timer_engine.get_task(task_id)
        if task and task_id in self._timer_cards:
            self._timer_cards[task_id].update_task(task)

    def _on_card_stop(self, task_id: int):
        """Handle card stop button."""
        self.task_manager.stop_task(task_id)
        self._remove_timer_card(task_id)
        self._update_stats()

    def _on_notebook_requested(self, task_name: str):
        """Open notebook dialog for a task name."""
        dialog = TaskNotebookDialog(self.db, task_name, self._dark_mode, self)
        dialog.exec()

    def _on_continue_task_from_chart(self, task_name: str):
        """Continue a task from the stats chart right-click menu."""
        preset = self.preset_repo.find_by_name(task_name)
        if preset:
            task = self.task_manager.create_from_preset(preset)
            self._create_timer_card(task)
            self.task_manager.start_task(task.id)
            self._refresh_presets_filtered()

    def _show_popup(self, title: str, message: str, task: Task):
        """Show in-app notification popup."""
        # Pass callback to stop alarm when dialog closes
        dialog = InAppNotificationDialog(
            title, message, task, self,
            on_close_callback=self.notification_service.stop_alarm,
            db=self.db
        )
        dialog.exec()

        # Stop alarm when dialog closes (backup)
        self.notification_service.stop_alarm()

        if dialog.should_restart() and task:
            # Create new task with same settings
            new_task = self.task_manager.create_task(
                name=task.name,
                duration_seconds=task.duration_seconds,
                category_id=task.category_id,
            )
            self._remove_timer_card(task.id)
            self._create_timer_card(new_task)
            self.task_manager.start_task(new_task.id)
        else:
            # Remove completed card
            self._remove_timer_card(task.id)

    def _show_window(self):
        """Show and activate the main window."""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    def _update_clock(self):
        """Update the clock label with current time."""
        now = datetime.now()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[now.weekday()]
        self._clock_label.setText(now.strftime(f"%m月%d日 {weekday} %H:%M:%S"))

    def _restore_preferences(self):
        """Restore saved alarm mode and theme from database."""
        from src.core.notification_service import NotificationService
        saved_alarm = self.db.get_setting("alarm_mode", "continuous")
        if saved_alarm == "three_times":
            self.notification_service.alarm_mode = NotificationService.ALARM_THREE_TIMES
            self.alarm_btn.setText("🔔 响三下")

        if self._dark_mode:
            self._apply_theme()

    def _toggle_alarm_mode(self):
        """Toggle between alarm modes."""
        from src.core.notification_service import NotificationService
        if self.notification_service.alarm_mode == NotificationService.ALARM_CONTINUOUS:
            self.notification_service.alarm_mode = NotificationService.ALARM_THREE_TIMES
            self.alarm_btn.setText("🔔 响三下")
            self.db.set_setting("alarm_mode", "three_times")
        else:
            self.notification_service.alarm_mode = NotificationService.ALARM_CONTINUOUS
            self.alarm_btn.setText("🔔 一直响")
            self.db.set_setting("alarm_mode", "continuous")

    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        self._dark_mode = not self._dark_mode
        self.db.set_setting("dark_mode", "1" if self._dark_mode else "0")
        self._apply_theme()

    def _apply_theme(self):
        """Apply current theme."""
        theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self.setStyleSheet(theme.get_stylesheet())

        # Update theme button
        self.theme_btn.setText("☀️ 浅色" if self._dark_mode else "🌙 深色")

        # Update clock label color
        clock_color = "#98989d" if self._dark_mode else "#6e6e73"
        self._clock_label.setStyleSheet(f"""
            QLabel {{
                font-size: 15px;
                color: {clock_color};
                padding-left: 8px;
            }}
        """)

        # Update alarm & theme button styles for current theme
        if self._dark_mode:
            self.alarm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2e;
                    color: #ffffff;
                    border: 1px solid #48484a;
                    border-radius: 8px;
                    font-size: 14px;
                    padding: 0 14px;
                }
                QPushButton:hover {
                    background-color: #3a3a3c;
                    color: #ffffff;
                }
            """)
            self.theme_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2e;
                    color: #ffffff;
                    border: 1px solid #48484a;
                    border-radius: 8px;
                    font-size: 14px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #3a3a3c;
                    color: #ffffff;
                }
            """)
        else:
            self.alarm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                    border-radius: 8px;
                    font-size: 14px;
                    padding: 0 14px;
                }
                QPushButton:hover {
                    background-color: #e5e5ea;
                    color: #1d1d1f;
                }
            """)
            self.theme_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                    border-radius: 8px;
                    font-size: 14px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #e5e5ea;
                    color: #1d1d1f;
                }
            """)

        # Update components
        self.sidebar.set_dark_mode(self._dark_mode)
        self.stats_dashboard.set_dark_mode(self._dark_mode)
        self.preset_bar.set_dark_mode(self._dark_mode)
        if self._dark_mode:
            self.preset_search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #48484a;
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 12px;
                    background-color: #2c2c2e;
                    color: #ffffff;
                }
                QLineEdit:focus {
                    border-color: #0a84ff;
                    background-color: #3a3a3c;
                }
            """)
        else:
            self.preset_search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #d2d2d7;
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 12px;
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                }
                QLineEdit:focus {
                    border-color: #007AFF;
                    background-color: #ffffff;
                }
            """)

        for card in self._timer_cards.values():
            card.set_dark_mode(self._dark_mode)

    # --- Timer card drag-reorder ---

    def eventFilter(self, obj, event):
        """Handle drag/drop events on timer_container."""
        if obj is not self.timer_container:
            return super().eventFilter(obj, event)

        etype = event.type()

        if etype == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                return True

        elif etype == QEvent.Type.DragMove:
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                drop_idx = self._calc_card_drop_index(event.position().x())
                self._show_card_drop_indicator(drop_idx)
                return True

        elif etype == QEvent.Type.Drop:
            self._card_drop_indicator.hide()
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                task_id = int(event.mimeData().data("application/x-timer-card-id").data().decode())
                drop_idx = self._calc_card_drop_index(event.position().x())
                self._handle_card_drop(task_id, drop_idx)
                return True

        elif etype == QEvent.Type.DragLeave:
            self._card_drop_indicator.hide()
            return True

        return super().eventFilter(obj, event)

    def _calc_card_drop_index(self, local_x: float) -> int:
        """Calculate card insertion index from x position."""
        count = self.timer_layout.count()
        for i in range(count):
            item = self.timer_layout.itemAt(i)
            w = item.widget()
            if w is None or not isinstance(w, TimerCard):
                continue
            center = w.x() + w.width() / 2
            if local_x < center:
                return i
        # Count only TimerCard widgets for the "after last" index
        last_card_idx = 0
        for i in range(count):
            item = self.timer_layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), TimerCard):
                last_card_idx = i + 1
        return last_card_idx

    def _show_card_drop_indicator(self, drop_idx: int):
        """Show drop indicator at the given position."""
        count = self.timer_layout.count()
        # Find the widget at drop_idx or the last card
        if drop_idx < count:
            item = self.timer_layout.itemAt(drop_idx)
            if item and item.widget():
                x = item.widget().x() - 4
            else:
                x = 0
        else:
            # After last card
            for i in range(count - 1, -1, -1):
                item = self.timer_layout.itemAt(i)
                w = item.widget()
                if w and isinstance(w, TimerCard):
                    x = w.x() + w.width() + 4
                    break
            else:
                x = 0

        self._card_drop_indicator.setFixedHeight(self.timer_container.height())
        self._card_drop_indicator.move(int(x), 0)
        self._card_drop_indicator.show()
        self._card_drop_indicator.raise_()

    def _handle_card_drop(self, task_id: int, drop_idx: int):
        """Move the timer card to the new position and persist order."""
        if task_id not in self._timer_cards:
            return

        # Find source index
        src_idx = None
        for i in range(self.timer_layout.count()):
            item = self.timer_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TimerCard) and w.task.id == task_id:
                src_idx = i
                break

        if src_idx is None or src_idx == drop_idx:
            return

        # Remove from layout and re-insert
        item = self.timer_layout.takeAt(src_idx)
        widget = item.widget()

        # Adjust index after removal
        if src_idx < drop_idx:
            drop_idx -= 1

        self.timer_layout.insertWidget(drop_idx, widget)

        # Persist new order to database
        order_mapping = []
        for i in range(self.timer_layout.count()):
            item = self.timer_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TimerCard):
                order_mapping.append((i, w.task.id))
        self.task_repo.update_display_orders(order_mapping)

    def closeEvent(self, event):
        """Handle window close - minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
