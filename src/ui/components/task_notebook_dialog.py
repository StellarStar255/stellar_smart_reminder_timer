"""Per-task notebook dialog for taking notes."""

from datetime import datetime

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeySequence, QShortcut

from src.data.database import Database


class TaskNotebookDialog(QDialog):
    """Modal dialog for viewing/editing per-task-name notes."""

    def __init__(self, db: Database, task_name: str, dark_mode: bool = False, parent=None):
        super().__init__(parent)

        self._db = db
        self._task_name = task_name
        self._dark_mode = dark_mode

        self._setup_ui()
        self.set_dark_mode(dark_mode)
        self._load_content()

        # Cmd+W to close (auto-saves via closeEvent)
        close_shortcut = QShortcut(QKeySequence.StandardKey.Close, self)
        close_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        close_shortcut.activated.connect(self.close)

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle(f"{self._task_name} - 笔记本")
        self.resize(500, 400)
        self.setMinimumSize(350, 250)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 20)

        # Title label
        self._title_label = QLabel(f"{self._task_name}")
        self._title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #1d1d1f;
            }
        """)
        layout.addWidget(self._title_label)

        # Text editor with custom context menu
        self._editor = QTextEdit()
        self._editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(self._show_editor_context_menu)
        self._editor.setPlaceholderText("在此输入笔记...")
        self._editor.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                color: #1d1d1f;
                background-color: #ffffff;
            }
            QTextEdit:focus {
                border-color: #007AFF;
            }
        """)
        layout.addWidget(self._editor, 1)

    def _load_content(self):
        """Load notebook content from database."""
        content = self._db.get_notebook(self._task_name)
        self._editor.setPlainText(content)

    def set_dark_mode(self, enabled: bool):
        """Apply dark or light mode styling."""
        self._dark_mode = enabled
        if enabled:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1c1c1e;
                }
            """)
            self._title_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: 600;
                    color: #ffffff;
                }
            """)
            self._editor.setStyleSheet("""
                QTextEdit {
                    border: 1px solid #48484a;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                    color: #ffffff;
                    background-color: #2c2c2e;
                }
                QTextEdit:focus {
                    border-color: #0a84ff;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #ffffff;
                }
            """)
            self._title_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: 600;
                    color: #1d1d1f;
                }
            """)
            self._editor.setStyleSheet("""
                QTextEdit {
                    border: 1px solid #d2d2d7;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                    color: #1d1d1f;
                    background-color: #ffffff;
                }
                QTextEdit:focus {
                    border-color: #007AFF;
                }
            """)

    def _show_editor_context_menu(self, pos):
        """Show custom context menu with timestamp option."""
        menu = self._editor.createStandardContextMenu()
        menu.addSeparator()
        timestamp_action = menu.addAction("插入时间戳")
        action = menu.exec(self._editor.mapToGlobal(pos))
        if action == timestamp_action:
            stamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
            self._editor.textCursor().insertText(stamp)

    def closeEvent(self, event):
        """Auto-save content on close."""
        content = self._editor.toPlainText()
        self._db.save_notebook(self._task_name, content)
        super().closeEvent(event)
