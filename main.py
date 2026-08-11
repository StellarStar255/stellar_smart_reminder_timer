#!/usr/bin/env python3
"""
StellarPulse - Smart Reminder Application
A better task timer and reminder app for macOS.
"""

import sys
import os
import faulthandler

# Write native-crash stack traces to a log so segfaults are diagnosable.
_CRASH_LOG_PATH = os.path.expanduser("~/.stellarpulse/crash.log")
os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
_crash_log_file = open(_CRASH_LOG_PATH, "a")
faulthandler.enable(_crash_log_file)

# Force Qt to load plugins from THIS interpreter's PyQt6 install. If
# QT_PLUGIN_PATH points at another Python's PyQt6 (e.g. /Library/Frameworks
# Python 3.13 while running anaconda's 3.12), the process mixes two Qt
# builds and segfaults deep inside QtGui — seen as a crash in
# QImage::save() when pasting clipboard images.
# Source runs only: PyInstaller bundles resolve plugins themselves, and this
# override would point at a path that doesn't exist inside the app bundle.
if getattr(sys, "frozen", False):
    _qt_plugin_dir = os.path.join(
        getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)),
        "PyQt6", "Qt6", "plugins",
    )
else:
    import PyQt6 as _PyQt6
    _qt_plugin_dir = os.path.join(os.path.dirname(_PyQt6.__file__), "Qt6", "plugins")
if os.path.isdir(_qt_plugin_dir):
    os.environ["QT_PLUGIN_PATH"] = _qt_plugin_dir
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_qt_plugin_dir, "platforms")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent, QObject
from PyQt6.QtGui import QFont, QIcon

from src.ui import MainWindow
from src.data import Database


class DockClickFilter(QObject):
    """Event filter to handle macOS Dock icon click to reshow window."""

    def __init__(self, window):
        super().__init__()
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ApplicationActivate:
            if not self._window.isVisible():
                self._window._show_window()
        return super().eventFilter(obj, event)

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # The user-chosen UI scale (Aa 字号 menu) is applied through
    # QT_SCALE_FACTOR, which Qt only reads before the QApplication is
    # created — so the database must be opened first.
    db = Database()
    db.initialize()
    ui_scale = db.get_setting("ui_scale", "1.0")
    if ui_scale not in ("", "1.0"):
        os.environ["QT_SCALE_FACTOR"] = ui_scale

    from src.version import __version__, APP_DISPLAY_NAME
    from src.resources import resource_path

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("StellarPulse")
    app.setOrganizationDomain("stellarpulse.app")

    # Set application icon
    icon_path = resource_path("assets", "stellar_pulse_smart_reminder_timer.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Set default font (macOS system font; other platforms keep Qt's default)
    if sys.platform == "darwin":
        app.setFont(QFont(".AppleSystemUIFont", 13))

    # Create and show main window
    window = MainWindow(db)
    window.show()

    # Handle macOS Dock icon click to reshow window
    dock_filter = DockClickFilter(window)
    app.installEventFilter(dock_filter)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
