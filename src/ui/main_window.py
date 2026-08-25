"""Main application window."""

import sys
from datetime import date, datetime
from typing import Dict, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSystemTrayIcon, QMenu,
    QApplication, QMessageBox, QSizePolicy, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QObject
from PyQt6.QtGui import QIcon, QAction, QFont, QPixmap, QPainter, QColor, QBrush

from src.data.database import Database
from src.data.repositories import (
    CategoryRepository, PresetRepository, TaskRepository, ReminderRepository
)
from src.core.timer_engine import TimerEngine
from src.core.task_manager import TaskManager
from src.core.preset_manager import PresetManager
from src.core.statistics_engine import StatisticsEngine
from src.core.notification_service import NotificationService, InAppNotificationDialog
from src.core.reminder_scheduler import ReminderScheduler
from src.models import Task, TaskStatus, Category, Preset, Reminder
from src.ui.components.timer_card import TimerCard, EditTimerDialog
from src.ui.components.preset_bar import PresetBar, CustomTimerDialog, EditPresetDialog
from src.ui.components.preset_manager_dialog import PresetManagerDialog
from src.ui.components.category_sidebar import CategorySidebar
from src.ui.components.flow_layout import FlowLayout
from src.ui.components.stats_dashboard import StatsDashboard
from src.ui.components.task_notebook_dialog import TaskNotebookDialog
from src.ui.components.reminder_panel import (
    ReminderPanel, ReminderDialog, ReminderPopupDialog
)
from src.ui.styles import LIGHT_THEME, DARK_THEME


IS_MACOS = sys.platform == "darwin"


def _create_objc_delegate_class():
    """Create ObjC delegate class once at module level (macOS only)."""
    import objc
    from Foundation import NSObject

    class _TrayMenuDelegate(NSObject):
        _main_window = None

        def showWindow_(self, sender):
            if self._main_window:
                self._main_window._show_window()

        def checkUpdates_(self, sender):
            if self._main_window:
                self._main_window._manual_update_check()

        def quitApp_(self, sender):
            QApplication.quit()

    return _TrayMenuDelegate

_TrayMenuDelegate = _create_objc_delegate_class() if IS_MACOS else None


class _AppActivateFilter(QObject):
    """Runs a callback whenever the app is brought to the front.

    Used to re-read the notification permission, so granting it in System
    Settings takes effect on the very next timer instead of after a restart.
    """

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ApplicationActivate:
            try:
                self._callback()
            except Exception:
                pass  # an exception through a Qt virtual would take the app down
        return super().eventFilter(obj, event)


class _CardsScrollArea(QScrollArea):
    """Horizontal-only scroll area whose height always fits its content,
    so only the timer-card row scrolls sideways while everything below it
    stays pinned to the window width."""

    _SCROLLBAR_ALLOWANCE = 14  # styled bar height (10px) + margins

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def setWidget(self, widget):
        super().setWidget(widget)
        widget.installEventFilter(self)
        self._sync_height()

    def eventFilter(self, obj, event):
        # Track content size changes so the row never collapses or clips.
        if obj is self.widget() and event.type() in (
            QEvent.Type.Resize, QEvent.Type.LayoutRequest
        ):
            self._sync_height()
        return super().eventFilter(obj, event)

    def _sync_height(self):
        widget = self.widget()
        height = widget.sizeHint().height() if widget else 0
        self.setFixedHeight(height + self._SCROLLBAR_ALLOWANCE)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)

        self.db = db
        self._dark_mode = db.get_setting("dark_mode", "0") == "1"
        # Timer area view mode: "card" (horizontal grid) or "list" (rows)
        self._view_mode = db.get_setting("timer_view_mode", "card")
        if self._view_mode not in ("card", "list"):
            self._view_mode = "card"

        # Initialize repositories
        self.category_repo = CategoryRepository(db)
        self.preset_repo = PresetRepository(db)
        self.task_repo = TaskRepository(db)
        self.reminder_repo = ReminderRepository(db)

        # Initialize engines
        self.timer_engine = TimerEngine(self)
        self.task_manager = TaskManager(db, self.timer_engine, self)
        self.preset_manager = PresetManager(db)
        self.stats_engine = StatisticsEngine(db)
        self.notification_service = NotificationService(self)
        self.reminder_scheduler = ReminderScheduler(self.reminder_repo, self)

        # Reminder popups are modal, so a second reminder coming due while one
        # is on screen waits here instead of stacking nested event loops.
        self._reminder_popup_open = False
        self._pending_reminder_popups = []

        # Timer cards mapping
        self._timer_cards: Dict[int, TimerCard] = {}

        # Built before the layout so the clock tick can always refresh it
        self.reminder_panel = ReminderPanel()

        # Category cache
        self._categories: Dict[int, Category] = {}

        # Current task distribution period (days)
        self._task_dist_days: int = 7

        # Current category filter (None = all)
        self._selected_category_id: Optional[int] = None

        self._setup_ui()
        self._setup_tray()
        self._setup_system_notifications()
        self._connect_signals()
        self._load_data()

        # Restore saved preferences
        self._restore_preferences()

        # Start the wall-clock reminder scheduler. Anything that came due while
        # the app was closed is picked up on its first check.
        self.reminder_scheduler.start()

        # Start stats update timer
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(5000)  # Update every 5 seconds

        # Check GitHub Releases for a newer version shortly after startup
        self._update_checker = None
        QTimer.singleShot(3000, self._check_for_updates)

    def _check_for_updates(self, manual: bool = False):
        """Check GitHub Releases; manual checks also report "no update"."""
        from src.core.update_checker import UpdateChecker
        self._update_checker = UpdateChecker(self)
        self._update_checker.update_available.connect(self._on_update_available)
        if manual:
            self._update_checker.up_to_date.connect(self._on_up_to_date)
            self._update_checker.check_failed.connect(self._on_update_check_failed)
        self._update_checker.start()

    def _manual_update_check(self):
        """Tray-menu entry point: bring the window up, then check."""
        self._show_window()
        self._check_for_updates(manual=True)

    def _on_up_to_date(self, remote_tag: str):
        from src.version import __version__
        QMessageBox.information(
            self, "检查更新",
            f"当前已是最新版本 v{__version__}，无需升级。")

    def _on_update_check_failed(self, message: str):
        QMessageBox.warning(
            self, "检查更新",
            f"检查更新失败：{message}\n\n请确认网络后重试。")

    def _on_update_available(self, version: str, notes: str,
                             asset_name: str, asset_url: str):
        """Offer the one-click upgrade dialog."""
        from src.ui.components.update_dialog import UpdateDialog
        dialog = UpdateDialog(version, notes, asset_name, asset_url,
                              dark_mode=self._dark_mode, parent=self)
        dialog.exec()

    def _setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("星际脉动")
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)

        # Set window icon
        import os
        from src.resources import resource_path
        icon_path = resource_path("assets", "stellar_pulse_smart_reminder_timer.png")
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
        # Fix the label width to the widest possible clock string, otherwise
        # the per-second updates resize it and shove the widgets next to it.
        from PyQt6.QtGui import QFontMetrics
        clock_font = QFont(self._clock_label.font())
        clock_font.setPixelSize(15)
        metrics = QFontMetrics(clock_font)
        widest_digit = max("0123456789", key=metrics.horizontalAdvance)
        sample = f"00月00日 周四 00:00:00".replace("0", widest_digit)
        self._clock_label.setFixedWidth(metrics.horizontalAdvance(sample) + 16)
        self._clock_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        header_layout.addWidget(self._clock_label)
        self._update_clock()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Toolbar row below the title: FlowLayout wraps the controls onto
        # extra lines when the window is narrow, instead of letting a
        # QHBoxLayout squeeze them into overlapping slivers.
        toolbar_flow = FlowLayout(hspacing=8, vspacing=8)

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
        toolbar_flow.addWidget(self.preset_search_input)

        # Preset management button (opens list-style manager dialog)
        self.manage_btn = QPushButton("🗂 管理预设")
        self.manage_btn.setFixedHeight(32)
        self.manage_btn.setToolTip("以列表方式整理、修改和管理所有预设")
        self.manage_btn.clicked.connect(self._on_manage_presets)
        self.manage_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                font-size: 13px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #e5e5ea;
                color: #1d1d1f;
            }
        """)
        toolbar_flow.addWidget(self.manage_btn)

        # New scheduled reminder (a date + time, not a countdown)
        self.reminder_btn = QPushButton("⏰ 定时提醒")
        self.reminder_btn.setFixedHeight(32)
        self.reminder_btn.setToolTip("在指定的日期和时间提醒你，可设置每天/工作日/每周重复")
        self.reminder_btn.clicked.connect(self._on_create_reminder)
        self.reminder_btn.setStyleSheet(self.manage_btn.styleSheet())
        toolbar_flow.addWidget(self.reminder_btn)

        # Preset sort-mode toggle (smart auto-sort <-> manual drag order)
        self.sort_mode_btn = QPushButton()
        self.sort_mode_btn.setFixedHeight(32)
        self.sort_mode_btn.clicked.connect(self._toggle_sort_mode)
        self.sort_mode_btn.setStyleSheet(self.manage_btn.styleSheet())
        toolbar_flow.addWidget(self.sort_mode_btn)

        # Timer view-mode toggle (card grid <-> compact list)
        self.view_mode_btn = QPushButton()
        self.view_mode_btn.setFixedHeight(32)
        self.view_mode_btn.clicked.connect(self._toggle_view_mode)
        self.view_mode_btn.setStyleSheet(self.manage_btn.styleSheet())
        toolbar_flow.addWidget(self.view_mode_btn)

        # Save-config button (exports presets/categories/settings to JSON)
        self.save_config_btn = QPushButton("💾 保存配置")
        self.save_config_btn.setFixedHeight(32)
        self.save_config_btn.setToolTip("把所有预设、分类和设置导出为 JSON 备份文件")
        self.save_config_btn.clicked.connect(self._on_save_config)
        self.save_config_btn.setStyleSheet(self.manage_btn.styleSheet())
        toolbar_flow.addWidget(self.save_config_btn)

        # Import/export menu button (file-based config transfer).
        # Shown manually on press (not via setMenu) so it pops immediately;
        # WA_TranslucentBackground lets the rounded QSS corners render in a
        # single pass instead of square-window-then-mask, which flickers.
        self.transfer_btn = QPushButton("📤 导入导出")
        self.transfer_btn.setFixedHeight(32)
        self.transfer_btn.setToolTip("把预设和设置导出为文件，或从文件导入")
        self._transfer_menu = QMenu(self)
        self._transfer_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        export_action = self._transfer_menu.addAction("导出配置到文件…")
        export_action.triggered.connect(self._on_export_config)
        import_action = self._transfer_menu.addAction("从文件导入配置…")
        import_action.triggered.connect(self._on_import_config)
        self._transfer_menu_hidden_at = 0.0
        self._transfer_menu.aboutToHide.connect(self._on_transfer_menu_hidden)
        self.transfer_btn.pressed.connect(self._show_transfer_menu)
        self.transfer_btn.setStyleSheet(self.manage_btn.styleSheet())
        # Pre-polish so the first open doesn't pay style computation cost
        self._transfer_menu.ensurePolished()
        self._transfer_menu.sizeHint()
        toolbar_flow.addWidget(self.transfer_btn)

        # UI scale menu — applied via QT_SCALE_FACTOR, so it needs a restart
        self.font_btn = QPushButton("Aa 字号")
        self.font_btn.setFixedHeight(32)
        self.font_btn.setToolTip("调整字体和界面整体显示大小")
        self.font_btn.clicked.connect(self._show_font_menu)
        self.font_btn.setStyleSheet(self.manage_btn.styleSheet())
        toolbar_flow.addWidget(self.font_btn)

        header_layout.addStretch()

        # One-click update check button
        self.update_btn = QPushButton("🔄 检查更新")
        self.update_btn.setFixedHeight(36)
        self.update_btn.setToolTip("检查新版本，一键升级")
        self.update_btn.clicked.connect(
            lambda: self._check_for_updates(manual=True))
        self.update_btn.setStyleSheet("""
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
        header_layout.addWidget(self.update_btn)

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
        content_layout.addLayout(toolbar_flow)

        # Preset bar
        self.preset_bar = PresetBar()
        content_layout.addWidget(self.preset_bar)

        # Task search row (filters the timer cards below by name)
        task_search_row = QHBoxLayout()
        task_search_row.setSpacing(10)

        self.task_search_input = QLineEdit()
        self.task_search_input.setPlaceholderText("🔍 搜索任务，空格分隔多个关键词…")
        self.task_search_input.setToolTip("空格分隔多个关键词，任务名需同时包含所有关键词")
        self.task_search_input.setClearButtonEnabled(True)
        self.task_search_input.setFixedHeight(34)
        self.task_search_input.setFixedWidth(300)
        self.task_search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d2d2d7;
                border-radius: 17px;
                padding: 0 14px;
                font-size: 13px;
                background-color: #f5f5f7;
                color: #1d1d1f;
            }
            QLineEdit:focus {
                border-color: #007AFF;
                background-color: #ffffff;
            }
        """)
        task_search_row.addWidget(self.task_search_input)

        # Live match count shown only while a query is active
        self.task_search_count = QLabel("")
        self.task_search_count.setStyleSheet(
            "QLabel { color: #6e6e73; font-size: 12px; }"
        )
        task_search_row.addWidget(self.task_search_count)
        task_search_row.addStretch()

        content_layout.addLayout(task_search_row)

        # Main scrollable content area (timer cards at top, stats below);
        # scrolls vertically only — horizontal overflow is handled by the
        # dedicated timer-card scroll area so the stats stay fully visible.
        main_scroll = QScrollArea()
        self._main_scroll = main_scroll
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

        # Only the timer-card row scrolls horizontally, with a visible
        # scroll bar hinting at off-screen cards.
        self.cards_scroll = _CardsScrollArea()
        self.cards_scroll.setWidget(self.timer_container)
        scroll_layout.addWidget(self.cards_scroll)

        # List-view container: vertical stack of compact full-width rows,
        # shown instead of the horizontal card row in list mode.
        self.list_container = QWidget()
        self.list_container.setAcceptDrops(True)
        self.list_container.installEventFilter(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(self.list_container)

        # Drop indicator for list-mode drag-reorder (horizontal line)
        self._list_drop_indicator = QWidget(self.list_container)
        self._list_drop_indicator.setFixedHeight(3)
        self._list_drop_indicator.setStyleSheet("background-color: #007AFF; border-radius: 1px;")
        self._list_drop_indicator.hide()

        # Scheduled reminders (date + time), between the timers and the stats
        self.reminder_panel.set_collapsed(
            self.db.get_setting("reminders_collapsed", "0") == "1")
        scroll_layout.addWidget(self.reminder_panel)

        # Stats dashboard (below timer cards, scrollable)
        self.stats_dashboard = StatsDashboard(db=self.db)
        scroll_layout.addWidget(self.stats_dashboard)

        scroll_layout.addStretch()

        main_scroll.setWidget(scroll_content)
        content_layout.addWidget(main_scroll, 1)

        main_layout.addWidget(content, 1)

        # Show the container matching the saved view mode
        self._apply_view_mode()

        # Apply initial theme
        self._apply_theme()

    def _setup_tray(self):
        """Set up the tray icon: native status bar on macOS, Qt elsewhere."""
        if not IS_MACOS:
            self._setup_tray_qt()
            return
        self._setup_tray_macos()

    def _setup_tray_qt(self):
        """Cross-platform QSystemTrayIcon fallback (Windows/Linux)."""
        from src.resources import resource_path

        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path("assets", "stellar_pulse_smart_reminder_timer.png")
        if QIcon(icon_path).isNull():
            self.tray_icon.setIcon(self.windowIcon())
        else:
            self.tray_icon.setIcon(QIcon(icon_path))

        menu = QMenu()
        show_action = QAction("显示窗口", menu)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)
        from src.version import __version__
        update_action = QAction(f"检查更新…（当前 v{__version__}）", menu)
        update_action.triggered.connect(self._manual_update_check)
        menu.addAction(update_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        self._tray_menu = menu  # keep alive; setContextMenu doesn't take ownership
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray_icon.show()
        self.notification_service.set_tray_icon(self.tray_icon)

    def _setup_tray_macos(self):
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

        # Create a clock icon as outline strokes. macOS template images only
        # use the alpha channel, so a filled face would render as a solid
        # blob — keep the face transparent and draw ring + hands as strokes.
        # Rendered at 44x44 (2x) for Retina sharpness, displayed at 22x22.
        from PyQt6.QtGui import QPen
        pixmap = QPixmap(44, 44)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(0, 0, 0))
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 4, 36, 36)   # clock ring
        painter.drawLine(22, 22, 22, 11)    # minute hand (12 o'clock)
        painter.drawLine(22, 22, 30, 26)    # hour hand (~4 o'clock)
        painter.end()

        # Convert QPixmap to NSImage
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        from Foundation import NSMakeSize
        ns_data = NSData.dataWithBytes_length_(bytes(byte_array), len(byte_array))
        ns_image = NSImage.alloc().initWithData_(ns_data)
        ns_image.setSize_(NSMakeSize(22, 22))  # 44px bitmap at 22pt = Retina 2x
        ns_image.setTemplate_(True)  # Adapts to light/dark menu bar
        self._status_item.button().setImage_(ns_image)

        # Create native menu
        ns_menu = NSMenu.alloc().init()

        self._menu_delegate = _TrayMenuDelegate.alloc().init()
        self._menu_delegate._main_window = self

        show_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("显示窗口", "showWindow:", "")
        show_item.setTarget_(self._menu_delegate)
        ns_menu.addItem_(show_item)

        from src.version import __version__
        update_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"检查更新…（当前 v{__version__}）", "checkUpdates:", "")
        update_item.setTarget_(self._menu_delegate)
        ns_menu.addItem_(update_item)

        ns_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quitApp:", "")
        quit_item.setTarget_(self._menu_delegate)
        ns_menu.addItem_(quit_item)

        self._status_item.setMenu_(ns_menu)

    def _setup_system_notifications(self):
        """Register for macOS notifications posted as the app itself."""
        if not IS_MACOS:
            return
        from src.core import macos_notifier
        if not macos_notifier.is_available():
            return  # source checkout / no bundle — osascript fallback is used
        macos_notifier.set_click_handler(self._show_window)
        # Prompts on a first-ever launch; a no-op once the user has answered.
        macos_notifier.request_authorization()

        # Pick up a switch flipped in System Settings without a restart.
        self._notify_activate_filter = _AppActivateFilter(
            macos_notifier.refresh_authorization)
        QApplication.instance().installEventFilter(self._notify_activate_filter)

        # The status query is async, so give it a moment before judging it.
        QTimer.singleShot(3000, self._offer_notification_permission_help)

    def _offer_notification_permission_help(self):
        """Guide the user to the settings pane when permission was denied.

        macOS only ever shows its own prompt once per bundle id, so an app
        that was denied — including by a version that never asked properly —
        can never ask again; the switch has to be flipped by hand.
        """
        from src.core import macos_notifier
        if macos_notifier.authorization_status() != macos_notifier.STATUS_DENIED:
            return
        if self.db.get_setting("notify_permission_hint", "1") != "1":
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("系统通知未开启")
        box.setText("「星际脉动」的通知权限是关闭的，计时结束时不会弹出提醒。")
        box.setInformativeText(
            "macOS 只会在首次安装时询问一次，之后只能手动开启：\n"
            "系统设置 → 通知 → 星际脉动 → 打开「允许通知」\n"
            "建议提醒样式选「提醒」，横幅几秒就自动消失，容易错过。")
        open_btn = box.addButton("打开系统设置", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("以后再说", QMessageBox.ButtonRole.RejectRole)
        never_btn = box.addButton("不再提示", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(open_btn)
        box.exec()

        if box.clickedButton() is open_btn:
            macos_notifier.open_notification_settings()
        elif box.clickedButton() is never_btn:
            self.db.set_setting("notify_permission_hint", "0")

    def _connect_signals(self):
        """Connect all signals."""
        # Preset bar
        self.preset_bar.preset_selected.connect(self._on_preset_selected)
        self.preset_bar.custom_requested.connect(self._on_custom_requested)
        self.preset_bar.preset_deleted.connect(self._on_preset_deleted)
        self.preset_bar.preset_edit_requested.connect(self._on_preset_edit_requested)
        self.preset_bar.presets_reordered.connect(self._on_presets_reordered)
        self.preset_search_input.textChanged.connect(self.preset_bar._on_search_changed)
        self.task_search_input.textChanged.connect(self._apply_task_filters)

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

        # Reminder panel + scheduler
        self.reminder_panel.create_requested.connect(self._on_create_reminder)
        self.reminder_panel.edit_requested.connect(self._on_edit_reminder)
        self.reminder_panel.delete_requested.connect(self._on_delete_reminder)
        self.reminder_panel.toggle_requested.connect(
            self.reminder_scheduler.set_enabled)
        self.reminder_panel.clear_finished_requested.connect(
            self._on_clear_finished_reminders)
        self.reminder_panel.collapsed_changed.connect(
            lambda collapsed: self.db.set_setting(
                "reminders_collapsed", "1" if collapsed else "0"))
        self.reminder_scheduler.reminders_changed.connect(self._refresh_reminders)
        self.reminder_scheduler.reminder_due.connect(self._on_reminder_due)
        self.reminder_scheduler.reminder_missed.connect(self._on_reminder_missed)

    def _load_data(self):
        """Load initial data."""
        # Load categories
        categories = self.category_repo.get_all()
        for cat in categories:
            self._categories[cat.id] = cat
        self.sidebar.set_categories(categories)
        self.reminder_panel.set_categories(categories)

        # Load presets (default + custom), applying the saved sort mode
        self._update_sort_mode_ui()
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

    def _update_sort_mode_ui(self):
        """Sync the sort-mode button label and the preset bar's drag state."""
        mode = self.preset_manager.get_sort_mode()
        if mode == "manual":
            self.sort_mode_btn.setText("✋ 手动排序")
            self.sort_mode_btn.setToolTip("当前为手动排序，可拖拽调整预设顺序；点击切换为智能排序")
        elif mode == "recent":
            self.sort_mode_btn.setText("🕒 最近使用")
            self.sort_mode_btn.setToolTip("当前按最近使用时间排序；点击切换为手动拖拽排序")
        else:
            self.sort_mode_btn.setText("🔀 智能排序")
            self.sort_mode_btn.setToolTip("当前按使用频率和最近使用智能排序；点击切换为最近使用排序")
        self.preset_bar.set_manual_mode(mode == "manual")

    def _toggle_sort_mode(self):
        """Cycle preset ordering: smart -> recent -> manual -> smart."""
        mode = self.preset_manager.get_sort_mode()
        if mode == "smart":
            self.preset_manager.set_sort_mode("recent")
        elif mode == "recent":
            # Snapshot the current (recent) order so manual mode starts from
            # exactly what's on screen instead of stale sort_order values.
            current = self.preset_manager.get_all()
            self.preset_manager.reorder([p.id for p in current])
            self.preset_manager.set_sort_mode("manual")
        else:
            self.preset_manager.set_sort_mode("smart")
        self._update_sort_mode_ui()
        self._refresh_presets_filtered()

    def _on_presets_reordered(self, ordered_ids):
        """Persist a manual drag-reorder of presets."""
        self.preset_manager.reorder(ordered_ids)
        self._refresh_presets_filtered()

    def _active_cards_layout(self):
        """The layout currently holding the timer cards."""
        return self.list_layout if self._view_mode == "list" else self.timer_layout

    def _apply_view_mode(self):
        """Sync container visibility, empty-label parent and button label."""
        is_list = self._view_mode == "list"
        self.cards_scroll.setVisible(not is_list)
        self.list_container.setVisible(is_list)

        # Keep the empty placeholder inside whichever container is visible
        if is_list:
            self.timer_layout.removeWidget(self.empty_label)
            self.list_layout.insertWidget(0, self.empty_label)
        else:
            self.list_layout.removeWidget(self.empty_label)
            self.timer_layout.insertWidget(0, self.empty_label)

        if is_list:
            self.view_mode_btn.setText("▦ 卡片视图")
            self.view_mode_btn.setToolTip("当前为列表视图；点击切换为卡片视图")
        else:
            self.view_mode_btn.setText("☰ 列表视图")
            self.view_mode_btn.setToolTip("当前为卡片视图；点击切换为列表视图，方便整体浏览")

    def _toggle_view_mode(self):
        """Switch the timer area between card grid and compact list."""
        self._view_mode = "list" if self._view_mode == "card" else "card"
        self.db.set_setting("timer_view_mode", self._view_mode)
        self._apply_view_mode()
        self._rebuild_timer_cards()

    def _rebuild_timer_cards(self):
        """Recreate all timer cards in the current view mode, keeping order."""
        old_cards = []
        for layout in (self.timer_layout, self.list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if isinstance(w, TimerCard):
                    old_cards.append(w)

        tasks = [card.task for card in old_cards]
        self._timer_cards.clear()
        for card in old_cards:
            card.setParent(None)
            card.deleteLater()

        for task in tasks:
            self._create_timer_card(task)

        # Re-apply the current category/search filters to the fresh cards
        self._apply_task_filters()

    def _apply_task_filters(self, *_):
        """Show/hide timer cards by the category filter and search query.

        The query is split on whitespace into keywords combined with AND:
        a card matches only if its name contains every keyword.
        """
        keywords = self.task_search_input.text().lower().split()
        visible = 0
        for task_id, card in self._timer_cards.items():
            task = self.timer_engine.get_task(task_id)
            matches = True
            if self._selected_category_id is not None:
                matches = (
                    task is not None
                    and task.category_id == self._selected_category_id
                )
            if matches and keywords:
                name = ((task.name if task else card.task.name) or "").lower()
                matches = all(kw in name for kw in keywords)
            card.setVisible(matches)
            if matches:
                visible += 1

        self.task_search_count.setText(f"{visible} 个匹配" if keywords else "")

        # Placeholder: no timers at all vs. everything filtered out
        if not self._timer_cards:
            self.empty_label.setText("点击上方预设或自定义按钮开始计时")
            self.empty_label.show()
        elif visible == 0:
            self.empty_label.setText("没有匹配的任务")
            self.empty_label.show()
        else:
            self.empty_label.hide()

    def _create_timer_card(self, task: Task):
        """Create a timer card for a task."""
        category = self._categories.get(task.category_id)
        card = TimerCard(task, category, view_mode=self._view_mode)
        card.toggle_clicked.connect(self._on_card_toggle)
        card.stop_clicked.connect(self._on_card_stop)
        card.edit_requested.connect(self._on_card_edit)
        card.notebook_requested.connect(self._on_notebook_requested)
        card.name_edited.connect(self._on_card_name_edited)
        card.set_dark_mode(self._dark_mode)

        if self._view_mode == "list":
            self.list_layout.addWidget(card)
        else:
            # Add to layout before stretch
            self.timer_layout.insertWidget(self.timer_layout.count() - 1, card)
        self._timer_cards[task.id] = card

        # Sync visibility (empty label, active search/category filters)
        self._apply_task_filters()
        self.cards_scroll.updateGeometry()

    def _remove_timer_card(self, task_id: int):
        """Remove a timer card."""
        if task_id in self._timer_cards:
            card = self._timer_cards.pop(task_id)
            self._active_cards_layout().removeWidget(card)
            card.deleteLater()

        self._apply_task_filters()
        self.cards_scroll.updateGeometry()

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
        self._move_card_to_front(task.id)
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
                self._move_card_to_front(task.id)

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

    def _collect_config_data(self) -> dict:
        """Flush on-screen preferences and assemble the full config snapshot."""
        self.db.set_setting("dark_mode", "1" if self._dark_mode else "0")
        alarm = ("three_times"
                 if self.notification_service.alarm_mode == NotificationService.ALARM_THREE_TIMES
                 else "continuous")
        self.db.set_setting("alarm_mode", alarm)
        self.db.set_setting("task_dist_days", str(self._task_dist_days))
        self.db.set_setting(
            StatsDashboard.CHART_MODE_KEY, self.stats_dashboard._chart_mode
        )

        cursor = self.db.execute("SELECT key, value FROM app_settings")
        settings = {row['key']: row['value'] for row in cursor.fetchall()}

        cursor = self.db.execute(
            "SELECT task_name, content FROM task_notebooks WHERE content != ''"
        )
        notebooks = {row['task_name']: row['content'] for row in cursor.fetchall()}

        return {
            'app': 'stellarpulse',
            'version': 1,
            'exported_at': datetime.now().isoformat(),
            'categories': [c.to_dict() for c in self.category_repo.get_all()],
            'presets': [p.to_dict() for p in self.preset_repo.get_all()],
            'reminders': [r.to_dict() for r in self.reminder_repo.get_all()],
            'settings': settings,
            'notebooks': notebooks,
        }

    def _on_save_config(self):
        """Silently save all settings and write a JSON backup to the app dir."""
        import json
        from pathlib import Path

        data = self._collect_config_data()
        try:
            backup_path = Path.home() / ".stellarpulse" / "config_backup.json"
            backup_path.parent.mkdir(exist_ok=True)
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "保存配置", f"保存失败：{e}")
            return

        # Brief inline feedback on the button itself, no popup
        self.save_config_btn.setText("✅ 已保存")
        self.save_config_btn.setEnabled(False)
        QTimer.singleShot(1500, self._reset_save_config_btn)

    def _reset_save_config_btn(self):
        self.save_config_btn.setText("💾 保存配置")
        self.save_config_btn.setEnabled(True)

    def _on_export_config(self):
        """Export presets, categories and settings to a user-chosen file."""
        import json
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog

        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()
        default_name = f"stellarpulse_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", str(default_dir / default_name), "JSON 文件 (*.json)"
        )
        if not path:
            return

        data = self._collect_config_data()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "导出配置", f"导出失败：{e}")
            return

        QMessageBox.information(
            self, "导出配置",
            f"已导出 {len(data['presets'])} 个预设、{len(data['categories'])} 个分类、"
            f"{len(data['reminders'])} 条定时提醒、{len(data['notebooks'])} 篇笔记"
            f"和全部设置到：\n{path}"
        )

    def _on_import_config(self):
        """Import presets, categories and settings from an exported file.

        Merge semantics: nothing local is deleted. Categories match by name,
        presets dedup by name+duration; settings are overwritten.
        """
        import json
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", str(Path.home()), "JSON 文件 (*.json)"
        )
        if not path:
            return

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "导入配置", f"无法读取配置文件：{e}")
            return
        if not isinstance(data, dict) or data.get('app') != 'stellarpulse':
            QMessageBox.warning(self, "导入配置", "这不是星际脉动导出的配置文件。")
            return

        # Merge categories by name; map exported ids to local ids
        local_cats = {c.name: c for c in self.category_repo.get_all()}
        id_map = {}
        new_cats = 0
        for cat_data in data.get('categories', []):
            name = cat_data.get('name')
            if not name:
                continue
            if name in local_cats:
                id_map[cat_data.get('id')] = local_cats[name].id
            else:
                cat = Category.from_dict({**cat_data, 'id': None, 'is_default': False})
                created = self.category_repo.create(cat)
                local_cats[name] = created
                id_map[cat_data.get('id')] = created.id
                new_cats += 1

        # Merge presets (dedup by name + duration)
        fallback_cat_id = next(iter(id_map.values()), None) or next(iter(self._categories), 1)
        added = updated = 0
        for p in data.get('presets', []):
            name = p.get('name')
            duration = p.get('duration_seconds')
            if not name or not isinstance(duration, int) or duration <= 0:
                continue
            cat_id = id_map.get(p.get('category_id'), fallback_cat_id)
            existing = self.preset_repo.find_by_name_and_duration(name, duration)
            if existing:
                changed = False
                if (p.get('star_rating') or 0) > (existing.star_rating or 0):
                    existing.star_rating = p['star_rating']
                    changed = True
                if p.get('category_id') in id_map and existing.category_id != cat_id:
                    existing.category_id = cat_id
                    changed = True
                if changed:
                    self.preset_repo.update(existing)
                    updated += 1
            else:
                self.preset_repo.create(Preset(
                    name=name,
                    duration_seconds=duration,
                    category_id=cat_id,
                    is_default=False,
                    sort_order=p.get('sort_order', 0) or 0,
                    use_count=p.get('use_count', 0) or 0,
                    star_rating=p.get('star_rating', 0) or 0,
                ))
                added += 1

        # Merge reminders, deduped by title + scheduled time so re-importing
        # the same backup doesn't pile up duplicates
        existing_keys = {(r.title, r.remind_at.isoformat())
                         for r in self.reminder_repo.get_all()}
        reminders_added = 0
        for r in data.get('reminders', []):
            if not isinstance(r, dict) or not r.get('title') or not r.get('remind_at'):
                continue
            if (r['title'], r['remind_at']) in existing_keys:
                continue
            try:
                reminder = Reminder.from_dict({**r, 'id': None})
            except (KeyError, ValueError):
                continue
            reminder.category_id = id_map.get(r.get('category_id'), None)
            self.reminder_repo.create(reminder)
            existing_keys.add((r['title'], r['remind_at']))
            reminders_added += 1

        # Merge notebooks: only fill in tasks whose local notebook is empty,
        # so existing local notes are never overwritten
        notebooks_added = 0
        for task_name, content in data.get('notebooks', {}).items():
            if not content:
                continue
            if not self.db.get_notebook(task_name):
                self.db.save_notebook(task_name, content)
                notebooks_added += 1

        # Overwrite settings and re-apply them to the UI
        settings = data.get('settings', {})
        for key, value in settings.items():
            self.db.set_setting(str(key), str(value))
        self._apply_imported_settings(settings)

        # Refresh caches and views
        self._categories.clear()
        categories = self.category_repo.get_all()
        for cat in categories:
            self._categories[cat.id] = cat
        self.sidebar.set_categories(categories)
        self.reminder_panel.set_categories(categories)
        self._refresh_presets()
        self._update_stats()
        self.reminder_scheduler.reload()

        QMessageBox.information(
            self, "导入配置",
            f"导入完成：新增 {added} 个预设、更新 {updated} 个预设、新增 {new_cats} 个分类、"
            f"新增 {reminders_added} 条定时提醒、导入 {notebooks_added} 篇笔记，"
            f"并应用了 {len(settings)} 项设置。"
        )

    def _apply_imported_settings(self, settings: dict):
        """Re-apply imported preference values to the live UI."""
        if 'dark_mode' in settings:
            self._dark_mode = str(settings.get('dark_mode')) == '1'
            self._apply_theme()
        alarm = settings.get('alarm_mode')
        if alarm == 'three_times':
            self.notification_service.alarm_mode = NotificationService.ALARM_THREE_TIMES
            self.alarm_btn.setText("🔔 响三下")
        elif alarm == 'continuous':
            self.notification_service.alarm_mode = NotificationService.ALARM_CONTINUOUS
            self.alarm_btn.setText("🔔 一直响")
        days = str(settings.get('task_dist_days', ''))
        if days.isdigit():
            self.stats_dashboard.set_period(int(days))
        mode = settings.get('chart_mode')
        if mode in ('bar', 'pie'):
            self.stats_dashboard.set_chart_mode(mode)
        view = settings.get('timer_view_mode')
        if view in ('card', 'list') and view != self._view_mode:
            self._view_mode = view
            self._apply_view_mode()
            self._rebuild_timer_cards()
        # Chart star ratings / hidden tasks were written to settings above
        self.stats_dashboard._load_star_ratings()
        self.stats_dashboard._load_hidden_tasks()

    def _on_manage_presets(self):
        """Open the list-style preset manager dialog."""
        categories = list(self._categories.values())
        dialog = PresetManagerDialog(
            self.preset_manager, categories, self, dark_mode=self._dark_mode
        )
        # Keep the preset bar in sync while the dialog stays open
        dialog.presets_changed.connect(self._refresh_presets_filtered)
        dialog.exec()
        self._refresh_presets_filtered()

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
                preset.star_rating = result.get('star_rating', 0)
                self.preset_manager.update(preset)
                self._refresh_presets()

    def _on_card_edit(self, task_id: int):
        """Handle timer card edit request via right-click menu."""
        task = self.timer_engine.get_task(task_id)
        if not task:
            return

        categories = list(self._categories.values())
        dialog = EditTimerDialog(task, categories, self, dark_mode=self._dark_mode)

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

    def _on_card_name_edited(self, task_id: int, new_name: str):
        """Persist an inline rename from a timer card."""
        task = self.timer_engine.get_task(task_id)
        if not task:
            return
        task.name = new_name
        self.task_repo.update(task)
        # A rename can change whether the card matches the search query
        self._apply_task_filters()

    def _on_period_changed(self, days: int):
        """Handle task distribution period change."""
        self._task_dist_days = days
        self.db.set_setting("task_dist_days", str(days))
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

        # Filter timer cards (combined with the search query)
        self._apply_task_filters()

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
        # Resuming a paused timer should bump its preset's recency so
        # "最近使用"/智能排序 surface the just-activated timer, and move the
        # card itself to the front of the row.
        if task and task.status == TaskStatus.RUNNING:
            self._touch_preset_for_task(task)
            self._move_card_to_front(task_id)

    def _touch_preset_for_task(self, task: Task):
        """Refresh the recency of the preset matching a task, then re-sort."""
        preset = (
            self.preset_repo.find_by_name_and_duration(
                task.name, task.duration_seconds)
            or self.preset_repo.find_by_name(task.name)
        )
        if not preset:
            return
        self.preset_manager.touch_last_used(preset.id)
        # Manual order is fixed by the user, so don't disturb it.
        if self.preset_manager.get_sort_mode() != "manual":
            self._refresh_presets_filtered()

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
            self._move_card_to_front(task.id)
            self._refresh_presets_filtered()

    # --- Scheduled reminders ---

    def _refresh_reminders(self):
        """Re-render the reminder list from the scheduler's current state."""
        self.reminder_panel.set_reminders(self.reminder_scheduler.reminders)

    def _on_create_reminder(self):
        """Open the editor for a brand-new reminder."""
        dialog = ReminderDialog(
            list(self._categories.values()), parent=self, dark_mode=self._dark_mode)
        if not dialog.exec():
            return
        result = dialog.get_result()
        if not result:
            return
        self.reminder_scheduler.add(Reminder(
            title=result['title'],
            remind_at=result['remind_at'],
            repeat=result['repeat'],
            auto_start_minutes=result['auto_start_minutes'],
            category_id=result['category_id'],
            notes=result['notes'],
        ).arm())
        # A freshly created reminder is always visible, even if the panel was
        # collapsed when the toolbar button was used.
        self.reminder_panel.set_collapsed(False)
        self.db.set_setting("reminders_collapsed", "0")

    def _on_edit_reminder(self, reminder: Reminder):
        """Edit an existing reminder, re-arming it if its time moved."""
        dialog = ReminderDialog(
            list(self._categories.values()), reminder=reminder,
            parent=self, dark_mode=self._dark_mode)
        if not dialog.exec():
            return
        result = dialog.get_result()
        if not result:
            return

        rescheduled = (result['remind_at'] != reminder.remind_at
                       or result['repeat'] != reminder.repeat)
        reminder.title = result['title']
        reminder.remind_at = result['remind_at']
        reminder.repeat = result['repeat']
        reminder.auto_start_minutes = result['auto_start_minutes']
        reminder.category_id = result['category_id']
        reminder.notes = result['notes']
        if rescheduled:
            # Moving the time means the user wants it to ring again, so drop
            # the fire history that would otherwise mark it as done.
            reminder.last_fired_at = None
            reminder.snoozed_until = None
            reminder.enabled = True
            reminder.arm()
        self.reminder_scheduler.update(reminder)

    def _on_delete_reminder(self, reminder_id: int):
        reminder = self.reminder_scheduler.get(reminder_id)
        if not reminder:
            return
        resp = QMessageBox.question(
            self, "删除提醒", f"确定删除提醒「{reminder.title}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self.reminder_scheduler.delete(reminder_id)

    def _on_clear_finished_reminders(self):
        count = self.reminder_scheduler.delete_finished()
        if count:
            self._refresh_reminders()

    def _on_reminder_due(self, reminder: Reminder):
        """A reminder came due: ring, optionally start its timer, show a popup."""
        message = reminder.notes or reminder.remind_at.strftime("%m月%d日 %H:%M")
        self.notification_service.notify_reminder(f"⏰ {reminder.title}", message)

        if reminder.auto_start_minutes > 0:
            self._start_reminder_timer(reminder)

        self._queue_reminder_popup(reminder)

    def _on_reminder_missed(self, reminder: Reminder):
        """A reminder came due while the app was closed or the Mac asleep.

        Recorded and reported without an alarm — ringing hours late is noise,
        but silently swallowing it would be worse.
        """
        scheduled = reminder.remind_at.strftime("%m月%d日 %H:%M")
        self.notification_service.notify_reminder_missed(
            "错过的提醒", f"「{reminder.title}」原定于 {scheduled}")

    def _start_reminder_timer(self, reminder: Reminder):
        """Start the countdown a reminder is configured to kick off."""
        category_id = reminder.category_id
        if category_id not in self._categories:
            category_id = next(iter(self._categories), 1)
        task = self.task_manager.create_task(
            name=reminder.title,
            duration_seconds=reminder.auto_start_minutes * 60,
            category_id=category_id,
        )
        self._create_timer_card(task)
        self.task_manager.start_task(task.id)
        self._move_card_to_front(task.id)

    def _queue_reminder_popup(self, reminder: Reminder):
        """Show the alarm popup, one at a time."""
        if self._reminder_popup_open:
            self._pending_reminder_popups.append(reminder)
            return

        self._reminder_popup_open = True
        try:
            self._show_window()
            dialog = ReminderPopupDialog(
                reminder, parent=self, dark_mode=self._dark_mode,
                on_close_callback=self.notification_service.stop_alarm)
            dialog.exec()
            self.notification_service.stop_alarm()

            minutes = dialog.snooze_minutes()
            if minutes:
                self.reminder_scheduler.snooze(reminder.id, minutes)
        finally:
            self._reminder_popup_open = False

        if self._pending_reminder_popups:
            self._queue_reminder_popup(self._pending_reminder_popups.pop(0))

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
            self._move_card_to_front(new_task.id)
        else:
            # Remove completed card
            self._remove_timer_card(task.id)

    _UI_SCALES = [("小", "0.9"), ("标准", "1.0"), ("大", "1.15"), ("特大", "1.3")]

    def _show_font_menu(self):
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        current = self.db.get_setting("ui_scale", "1.0") or "1.0"
        for label, value in self._UI_SCALES:
            action = menu.addAction(f"{label}（{round(float(value) * 100)}%）")
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(lambda _, v=value: self._set_ui_scale(v))
        menu.exec(self.font_btn.mapToGlobal(self.font_btn.rect().bottomLeft()))

    def _set_ui_scale(self, value: str):
        if value == (self.db.get_setting("ui_scale", "1.0") or "1.0"):
            return
        self.db.set_setting("ui_scale", value)
        resp = QMessageBox.question(
            self, "调整字号",
            "新的显示大小将在重启应用后生效。\n是否立即重启？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self._restart_app()

    def _restart_app(self):
        """Relaunch this app and quit the current process."""
        import os
        import subprocess
        from src.core.update_checker import _current_mac_app_bundle
        app_path = _current_mac_app_bundle()
        if app_path:
            # A fresh `open` after this process exits avoids two instances
            # racing on the sqlite database.
            subprocess.Popen(["/bin/bash", "-c", f'sleep 1; open "{app_path}"'],
                             start_new_session=True)
        elif getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable], start_new_session=True)
        else:
            subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])],
                             start_new_session=True)
        QApplication.quit()

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
        # Reminder countdowns tick on the same beat as the clock
        self.reminder_panel.refresh_countdowns()

    def _restore_preferences(self):
        """Restore saved alarm mode and theme from database."""
        from src.core.notification_service import NotificationService
        saved_alarm = self.db.get_setting("alarm_mode", "continuous")
        if saved_alarm == "three_times":
            self.notification_service.alarm_mode = NotificationService.ALARM_THREE_TIMES
            self.alarm_btn.setText("🔔 响三下")

        # Restore the task-distribution period (e.g. 近一月) chosen last time
        saved_days = self.db.get_setting("task_dist_days", "")
        if saved_days.isdigit():
            self.stats_dashboard.set_period(int(saved_days))

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

    def _on_transfer_menu_hidden(self):
        import time
        self._transfer_menu_hidden_at = time.monotonic()

    def _show_transfer_menu(self):
        """Pop the import/export menu just below its button (on press)."""
        import time
        from PyQt6.QtCore import QPoint
        # The press that dismisses an open menu also lands on the button;
        # ignore it so the menu doesn't instantly reopen (visible as flicker).
        if time.monotonic() - self._transfer_menu_hidden_at < 0.2:
            return
        pos = self.transfer_btn.mapToGlobal(QPoint(0, self.transfer_btn.height() + 4))
        self._transfer_menu.popup(pos)

    def _style_main_scroll(self):
        """Style the scroll areas; the card row gets a visible horizontal bar."""
        if self._dark_mode:
            handle = "#5a5a5e"
            handle_hover = "#6e6e73"
        else:
            handle = "#c0c0c0"
            handle_hover = "#a0a0a5"
        self._main_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        self.cards_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:horizontal {{
                height: 10px;
                background: transparent;
                margin: 2px 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {handle};
                border-radius: 3px;
                min-width: 40px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
                height: 0;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
        """)

    def _apply_theme(self):
        """Apply current theme."""
        theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self.setStyleSheet(theme.get_stylesheet())
        self._style_main_scroll()

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
            self.update_btn.setStyleSheet(self.theme_btn.styleSheet())
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
            self.update_btn.setStyleSheet(self.theme_btn.styleSheet())

        # Manage-presets button follows the same look as the other header buttons
        if self._dark_mode:
            self.manage_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2e;
                    color: #ffffff;
                    border: 1px solid #48484a;
                    border-radius: 8px;
                    font-size: 13px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #3a3a3c;
                    color: #ffffff;
                }
            """)
        else:
            self.manage_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                    border-radius: 8px;
                    font-size: 13px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #e5e5ea;
                    color: #1d1d1f;
                }
            """)

        self.save_config_btn.setStyleSheet(self.manage_btn.styleSheet())
        self.transfer_btn.setStyleSheet(self.manage_btn.styleSheet())
        self.reminder_btn.setStyleSheet(self.manage_btn.styleSheet())
        self.sort_mode_btn.setStyleSheet(self.manage_btn.styleSheet())
        self.view_mode_btn.setStyleSheet(self.manage_btn.styleSheet())
        self.font_btn.setStyleSheet(self.manage_btn.styleSheet())

        # Update components
        self.sidebar.set_dark_mode(self._dark_mode)
        self.stats_dashboard.set_dark_mode(self._dark_mode)
        self.preset_bar.set_dark_mode(self._dark_mode)
        self.reminder_panel.set_dark_mode(self._dark_mode)
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
            self.task_search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #48484a;
                    border-radius: 17px;
                    padding: 0 14px;
                    font-size: 13px;
                    background-color: #2c2c2e;
                    color: #ffffff;
                }
                QLineEdit:focus {
                    border-color: #0a84ff;
                    background-color: #3a3a3c;
                }
            """)
            self.task_search_count.setStyleSheet(
                "QLabel { color: #98989d; font-size: 12px; }"
            )
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
            self.task_search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #d2d2d7;
                    border-radius: 17px;
                    padding: 0 14px;
                    font-size: 13px;
                    background-color: #f5f5f7;
                    color: #1d1d1f;
                }
                QLineEdit:focus {
                    border-color: #007AFF;
                    background-color: #ffffff;
                }
            """)
            self.task_search_count.setStyleSheet(
                "QLabel { color: #6e6e73; font-size: 12px; }"
            )

        for card in self._timer_cards.values():
            card.set_dark_mode(self._dark_mode)

    # --- Timer card drag-reorder ---

    def eventFilter(self, obj, event):
        """Handle drag/drop events on the timer card containers."""
        if obj is not self.timer_container and obj is not self.list_container:
            return super().eventFilter(obj, event)

        etype = event.type()

        if etype == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                return True

        elif etype == QEvent.Type.DragMove:
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                drop_idx = self._calc_card_drop_index(event.position())
                self._show_card_drop_indicator(drop_idx)
                return True

        elif etype == QEvent.Type.Drop:
            self._card_drop_indicator.hide()
            self._list_drop_indicator.hide()
            if event.mimeData().hasFormat("application/x-timer-card-id"):
                event.acceptProposedAction()
                task_id = int(event.mimeData().data("application/x-timer-card-id").data().decode())
                drop_idx = self._calc_card_drop_index(event.position())
                self._handle_card_drop(task_id, drop_idx)
                return True

        elif etype == QEvent.Type.DragLeave:
            self._card_drop_indicator.hide()
            self._list_drop_indicator.hide()
            return True

        return super().eventFilter(obj, event)

    def _calc_card_drop_index(self, pos) -> int:
        """Calculate card insertion index from the drag position.

        Card mode compares x against card centers; list mode compares y
        against row centers.
        """
        layout = self._active_cards_layout()
        vertical = self._view_mode == "list"
        coord = pos.y() if vertical else pos.x()
        count = layout.count()
        for i in range(count):
            w = layout.itemAt(i).widget()
            if w is None or not isinstance(w, TimerCard):
                continue
            center = (w.y() + w.height() / 2) if vertical else (w.x() + w.width() / 2)
            if coord < center:
                return i
        # Count only TimerCard widgets for the "after last" index
        last_card_idx = 0
        for i in range(count):
            item = layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), TimerCard):
                last_card_idx = i + 1
        return last_card_idx

    def _show_card_drop_indicator(self, drop_idx: int):
        """Show drop indicator at the given position."""
        if self._view_mode == "list":
            self._show_list_drop_indicator(drop_idx)
            return
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

    def _show_list_drop_indicator(self, drop_idx: int):
        """Horizontal drop line between list rows."""
        layout = self.list_layout
        count = layout.count()
        y = 0
        if drop_idx < count:
            item = layout.itemAt(drop_idx)
            if item and item.widget():
                y = item.widget().y() - 5
        else:
            for i in range(count - 1, -1, -1):
                w = layout.itemAt(i).widget()
                if isinstance(w, TimerCard):
                    y = w.y() + w.height() + 2
                    break

        self._list_drop_indicator.setFixedWidth(self.list_container.width())
        self._list_drop_indicator.move(0, max(0, int(y)))
        self._list_drop_indicator.show()
        self._list_drop_indicator.raise_()

    def _handle_card_drop(self, task_id: int, drop_idx: int):
        """Move the timer card to the new position and persist order."""
        if task_id not in self._timer_cards:
            return

        layout = self._active_cards_layout()

        # Find source index
        src_idx = None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TimerCard) and w.task.id == task_id:
                src_idx = i
                break

        if src_idx is None or src_idx == drop_idx:
            return

        # Remove from layout and re-insert
        item = layout.takeAt(src_idx)
        widget = item.widget()

        # Adjust index after removal
        if src_idx < drop_idx:
            drop_idx -= 1

        layout.insertWidget(drop_idx, widget)

        # Persist new order to database
        order_mapping = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TimerCard):
                order_mapping.append((i, w.task.id))
        self.task_repo.update_display_orders(order_mapping)

    def _move_card_to_front(self, task_id: int):
        """Move a timer card to the front of the row and persist the order.

        Called whenever a timer is started or resumed so the most recently
        activated card sits first, mirroring the preset "最近使用" ordering.
        """
        if task_id not in self._timer_cards:
            return

        layout = self._active_cards_layout()
        src_idx = None
        first_card_idx = None
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, TimerCard):
                if first_card_idx is None:
                    first_card_idx = i
                if w.task.id == task_id:
                    src_idx = i

        if src_idx is None or first_card_idx is None or src_idx == first_card_idx:
            return

        # src_idx > first_card_idx here, so removing it doesn't shift the
        # front position; re-insert the card at the front.
        item = layout.takeAt(src_idx)
        layout.insertWidget(first_card_idx, item.widget())

        order_mapping = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, TimerCard):
                order_mapping.append((len(order_mapping), w.task.id))
        self.task_repo.update_display_orders(order_mapping)

        # Scroll back to the start so the just-activated card is visible.
        if self._view_mode == "card":
            self.cards_scroll.horizontalScrollBar().setValue(0)
        else:
            self._main_scroll.verticalScrollBar().setValue(0)

    def closeEvent(self, event):
        """Handle window close - minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
