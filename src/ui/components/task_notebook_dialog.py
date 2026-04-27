"""Per-task notebook dialog for taking notes."""

import re
from datetime import datetime

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt, QEvent, QTimer, QUrl
from PyQt6.QtGui import (
    QKeySequence, QShortcut, QDesktopServices,
    QTextCursor, QTextCharFormat, QColor,
)

from src.data.database import Database


URL_PATTERN = re.compile(
    r'(?:https?://|ftp://|www\.)[^\s<>"\'　、。，；：！？]+',
    re.IGNORECASE,
)


class _NotebookTextEdit(QTextEdit):
    """QTextEdit that auto-highlights URLs and opens them on Alt(Option)+click."""

    LINK_COLOR = "#0a84ff"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._default_color = QColor("#1d1d1f")
        self._current_cursor_shape = Qt.CursorShape.IBeamCursor
        self._highlighting = False

        self.setMouseTracking(True)
        self.setAcceptRichText(False)

        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.setInterval(150)
        self._highlight_timer.timeout.connect(self._highlight_links)
        self.textChanged.connect(self._on_text_changed)

    def set_default_text_color(self, color: QColor):
        self._default_color = color
        self._highlight_links()

    def _on_text_changed(self):
        if self._highlighting:
            return
        self._highlight_timer.start()

    def _highlight_links(self):
        """Apply blue/underlined formatting to all URLs in the document."""
        if self._highlighting:
            return
        self._highlighting = True

        doc = self.document()
        plain = self.toPlainText()
        text_len = len(plain)

        saved = self.textCursor()
        saved_anchor = saved.anchor()
        saved_pos = saved.position()

        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()

            cursor.select(QTextCursor.SelectionType.Document)
            base_fmt = QTextCharFormat()
            base_fmt.setForeground(self._default_color)
            base_fmt.setFontUnderline(False)
            cursor.setCharFormat(base_fmt)

            link_color = QColor(self.LINK_COLOR)
            for m in URL_PATTERN.finditer(plain):
                c = QTextCursor(doc)
                c.setPosition(m.start())
                c.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(link_color)
                fmt.setFontUnderline(True)
                c.setCharFormat(fmt)

            cursor.endEditBlock()

            new_cursor = self.textCursor()
            new_cursor.setPosition(min(saved_anchor, text_len))
            new_cursor.setPosition(
                min(saved_pos, text_len),
                QTextCursor.MoveMode.KeepAnchor,
            )
            self.setTextCursor(new_cursor)
        finally:
            self._highlighting = False

    def _url_at_position(self, pos):
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        offset = cursor.position() - block.position()
        for m in URL_PATTERN.finditer(block_text):
            if m.start() <= offset <= m.end():
                url = m.group(0)
                if url.lower().startswith("www."):
                    url = "http://" + url
                return url
        return None

    def mouseMoveEvent(self, event):
        desired = Qt.CursorShape.IBeamCursor
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            if self._url_at_position(event.pos()):
                desired = Qt.CursorShape.PointingHandCursor
        if desired != self._current_cursor_shape:
            self.viewport().setCursor(desired)
            self._current_cursor_shape = desired
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if (event.modifiers() & Qt.KeyboardModifier.AltModifier
                and event.button() == Qt.MouseButton.LeftButton):
            url = self._url_at_position(event.pos())
            if url:
                QDesktopServices.openUrl(QUrl(url))
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        if self._current_cursor_shape != Qt.CursorShape.IBeamCursor:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            self._current_cursor_shape = Qt.CursorShape.IBeamCursor
        super().leaveEvent(event)


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
        self._editor = _NotebookTextEdit()
        self._editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(self._show_editor_context_menu)
        self._editor.setPlaceholderText("在此输入笔记...(按住 Option/Alt 点击链接以打开)")
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
        self._editor._highlight_links()

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
            self._editor.set_default_text_color(QColor("#ffffff"))
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
            self._editor.set_default_text_color(QColor("#1d1d1f"))

    def _show_editor_context_menu(self, pos):
        """Show custom context menu with timestamp option."""
        menu = self._editor.createStandardContextMenu()
        menu.addSeparator()
        timestamp_action = menu.addAction("插入时间戳")

        url = self._editor._url_at_position(pos)
        open_link_action = None
        if url:
            menu.addSeparator()
            open_link_action = menu.addAction("在浏览器中打开链接")

        action = menu.exec(self._editor.mapToGlobal(pos))
        if action == timestamp_action:
            stamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
            self._editor.textCursor().insertText(stamp)
        elif open_link_action is not None and action == open_link_action:
            QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        """Auto-save content on close."""
        content = self._editor.toPlainText()
        self._db.save_notebook(self._task_name, content)
        super().closeEvent(event)
