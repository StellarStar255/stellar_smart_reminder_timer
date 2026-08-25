"""Notification service for system and in-app notifications."""

from typing import Optional
import subprocess
import sys
import os

IS_MACOS = sys.platform == "darwin"

from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QMessageBox, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit
)
from PyQt6.QtGui import QColor, QIcon

from src.models import Task


class NotificationService(QObject):
    """Handles both macOS system notifications and in-app popups."""

    # Signal for showing in-app notification
    show_popup = pyqtSignal(str, str, object)  # title, message, task

    # Alarm modes
    ALARM_THREE_TIMES = "three"
    ALARM_CONTINUOUS = "continuous"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alarm_mode = self.ALARM_CONTINUOUS  # Default: continuous
        self._alarm_timer: Optional[QTimer] = None
        self._alarm_process: Optional[subprocess.Popen] = None
        # Qt tray icon used for system notifications on Windows/Linux,
        # where osascript is unavailable; set by MainWindow after setup.
        self._tray_icon = None

    def set_tray_icon(self, tray_icon):
        """Provide a QSystemTrayIcon for non-macOS system notifications."""
        self._tray_icon = tray_icon

    @property
    def alarm_mode(self) -> str:
        return self._alarm_mode

    @alarm_mode.setter
    def alarm_mode(self, mode: str):
        if mode in (self.ALARM_THREE_TIMES, self.ALARM_CONTINUOUS):
            self._alarm_mode = mode

    def notify_task_completed(self, task: Task, parent_widget: Optional[QWidget] = None):
        """Send notification for completed task."""
        title = "计时完成！"
        message = f"「{task.name}」已完成\n用时: {task.format_elapsed()}"

        # Play alarm sound based on mode
        if self._alarm_mode == self.ALARM_THREE_TIMES:
            self._play_alarm_three_times()
        else:
            self._start_continuous_alarm()

        # Send system notification
        self._send_system_notification(title, message)

        # Emit signal for in-app popup
        self.show_popup.emit(title, message, task)

    def notify_reminder(self, title: str, message: str):
        """Ring for a scheduled reminder; the popup is shown by the caller."""
        if self._alarm_mode == self.ALARM_THREE_TIMES:
            self._play_alarm_three_times()
        else:
            self._start_continuous_alarm()
        self._send_system_notification(title, message)

    def notify_reminder_missed(self, title: str, message: str):
        """Quietly record a reminder that came due while the app was away."""
        self._send_system_notification(title, message)

    def stop_alarm(self):
        """Stop the continuous alarm."""
        if self._alarm_timer:
            self._alarm_timer.stop()
            self._alarm_timer = None
        if self._alarm_process:
            try:
                self._alarm_process.terminate()
            except Exception:
                pass
            self._alarm_process = None

    def _play_alarm_three_times(self):
        """Play alarm sound 3 times."""
        if not IS_MACOS:
            self._beep_n_times(3)
            return
        sound_path = self._get_sound_path()
        if sound_path:
            try:
                subprocess.Popen(
                    ["bash", "-c",
                     f"afplay '{sound_path}' && sleep 0.3 && afplay '{sound_path}' && sleep 0.3 && afplay '{sound_path}'"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def _beep_n_times(self, count: int, interval_ms: int = 700):
        """Cross-platform fallback: system beep repeated a few times."""
        for i in range(count):
            QTimer.singleShot(i * interval_ms, self._system_beep)

    @staticmethod
    def _system_beep():
        """One system alert sound without any external process."""
        if sys.platform == "win32":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return
            except Exception:
                pass
        from PyQt6.QtWidgets import QApplication
        QApplication.beep()

    def _start_continuous_alarm(self):
        """Start continuous alarm that plays until stopped."""
        self.stop_alarm()  # Stop any existing alarm

        if not IS_MACOS:
            self._system_beep()
            self._alarm_timer = QTimer(self)
            self._alarm_timer.timeout.connect(self._system_beep)
            self._alarm_timer.start(1500)
            return

        sound_path = self._get_sound_path()
        if not sound_path:
            return

        # Play first sound immediately
        self._play_single_sound(sound_path)

        # Set up timer to repeat every 1.5 seconds
        self._alarm_timer = QTimer(self)
        self._alarm_timer.timeout.connect(lambda: self._play_single_sound(sound_path))
        self._alarm_timer.start(1500)  # Repeat every 1.5 seconds

    def _play_single_sound(self, sound_path: str):
        """Play a single sound."""
        try:
            self._alarm_process = subprocess.Popen(
                ["afplay", sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    def _get_sound_path(self) -> Optional[str]:
        """Get available sound file path."""
        sound_paths = [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Ping.aiff",
            "/System/Library/Sounds/Hero.aiff",
        ]
        for path in sound_paths:
            if os.path.exists(path):
                return path
        return None

    def notify_task_reminder(self, task: Task, minutes_left: int):
        """Send reminder notification."""
        title = "任务提醒"
        message = f"「{task.name}」还剩 {minutes_left} 分钟"
        self._play_reminder_sound()
        self._send_system_notification(title, message)

    def _play_reminder_sound(self):
        """Play a softer reminder sound."""
        if not IS_MACOS:
            self._system_beep()
            return
        sound_path = "/System/Library/Sounds/Tink.aiff"
        if os.path.exists(sound_path):
            try:
                subprocess.Popen(
                    ["afplay", sound_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def _send_system_notification(self, title: str, message: str):
        """Send a system notification.

        macOS: UNUserNotificationCenter when running from the signed app
        bundle, so the banner is signed \"星际脉动\" and can be managed on its
        own row in 系统设置 → 通知; falls back to osascript (posted as System
        Events) when it is unavailable or unauthorized — a source checkout,
        or the app's notification permission being switched off.
        Windows/Linux: tray icon balloon message.
        """
        if not IS_MACOS:
            if self._tray_icon is not None:
                try:
                    self._tray_icon.showMessage(title, message)
                except Exception:
                    pass
            return

        from src.core import macos_notifier
        if macos_notifier.send(
            title, message,
            on_failure=lambda: self._send_osascript_notification(title, message),
        ):
            return
        self._send_osascript_notification(title, message)

    def _send_osascript_notification(self, title: str, message: str):
        """Fallback banner, posted under System Events' identity."""
        safe_title = title.replace('"', '\\"').replace("'", "\\'")
        safe_message = message.replace('"', '\\"').replace("'", "\\'").replace('\n', ' ')

        script = (
            f'tell application "System Events" to display notification '
            f'"{safe_message}" with title "{safe_title}"'
        )
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


class InAppNotificationDialog(QDialog):
    """In-app notification popup dialog with collapsible notes."""

    def __init__(self, title: str, message: str, task: Optional[Task] = None,
                 parent: Optional[QWidget] = None,
                 on_close_callback=None, db=None):
        super().__init__(parent)

        self.task = task
        self._on_close_callback = on_close_callback
        self._db = db
        self._restart = False

        self.setWindowTitle(title)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(360)

        self._setup_ui(message)

    def _setup_ui(self, message: str):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(palette.ColorRole.Window, QColor("#ffffff"))
        self.setPalette(palette)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setAutoFillBackground(True)
        p = msg_label.palette()
        p.setColor(p.ColorRole.Window, QColor("#ffffff"))
        p.setColor(p.ColorRole.WindowText, QColor("#1d1d1f"))
        msg_label.setPalette(p)
        msg_label.setStyleSheet("font-size: 14px; color: #1d1d1f; background-color: #ffffff; padding: 4px 0;")
        layout.addWidget(msg_label)

        # Collapsible notes toggle
        self._notes_toggle = QPushButton("添加笔记 ▶")
        self._notes_toggle.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #007AFF;
                font-size: 13px;
                text-align: left;
                padding: 2px 0;
            }
            QPushButton:hover {
                color: #0056b3;
            }
        """)
        self._notes_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notes_toggle.clicked.connect(self._toggle_notes)
        layout.addWidget(self._notes_toggle)

        # Notes editor (hidden by default)
        self._notes_editor = QTextEdit()
        self._notes_editor.setPlaceholderText("在此记录笔记...")
        self._notes_editor.setFixedHeight(120)
        self._notes_editor.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                color: #1d1d1f;
                background-color: #f9f9f9;
            }
            QTextEdit:focus {
                border-color: #007AFF;
            }
        """)
        self._notes_editor.hide()
        layout.addWidget(self._notes_editor)

        # Load existing notes
        if self._db and self.task:
            content = self._db.get_notebook(self.task.name)
            if content:
                self._notes_editor.setPlainText(content)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_style = """
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """
        restart_style = """
            QPushButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #e5e5ea;
            }
        """

        btn_layout.addStretch()

        if self.task:
            restart_btn = QPushButton("重新开始")
            restart_btn.setStyleSheet(restart_style)
            restart_btn.clicked.connect(self._on_restart)
            btn_layout.addWidget(restart_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(btn_style)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        self.setStyleSheet("QDialog { background-color: #ffffff; }")

    def _toggle_notes(self):
        """Toggle notes editor visibility."""
        if self._notes_editor.isVisible():
            self._notes_editor.hide()
            self._notes_toggle.setText("添加笔记 ▶")
        else:
            self._notes_editor.show()
            self._notes_editor.setFocus()
            self._notes_toggle.setText("添加笔记 ▼")
        self.adjustSize()

    def _on_restart(self):
        self._restart = True
        self.accept()

    def done(self, result):
        """Save notes and call callback when dialog closes."""
        # Save notes if editor was used
        if self._db and self.task and self._notes_editor.toPlainText().strip():
            self._db.save_notebook(self.task.name, self._notes_editor.toPlainText())

        if self._on_close_callback:
            self._on_close_callback()
        super().done(result)

    def should_restart(self) -> bool:
        """Check if user clicked restart button."""
        return self._restart
