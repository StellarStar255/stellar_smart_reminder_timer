#!/usr/bin/env python3
"""
StellarPulse - Smart Reminder Application
A better task timer and reminder app for macOS.
"""

import sys
import os
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

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("星际脉冲")
    app.setOrganizationName("StellarPulse")
    app.setOrganizationDomain("stellarpulse.app")

    # Set application icon
    icon_path = os.path.join(BASE_DIR, "assets", "stellar_pulse_smart_reminder_timer.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Set default font
    font = QFont(".AppleSystemUIFont", 13)
    app.setFont(font)

    # Initialize database
    db = Database()
    db.initialize()

    # Create and show main window
    window = MainWindow(db)
    window.show()

    # Handle macOS Dock icon click to reshow window
    dock_filter = DockClickFilter(window)
    app.installEventFilter(dock_filter)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
