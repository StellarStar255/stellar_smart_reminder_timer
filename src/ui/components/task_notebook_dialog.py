"""Per-task notebook dialog for taking notes."""

import re
from datetime import datetime

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import (
    QKeySequence, QShortcut, QDesktopServices,
    QTextCursor, QTextCharFormat, QColor, QFont, QSyntaxHighlighter,
)

from src.data.database import Database


URL_PATTERN = re.compile(
    r'(?:https?://|ftp://|www\.)[^\s<>"\'　、。，；：！？]+',
    re.IGNORECASE,
)

# Highlight (highlighter-pen) background colors. Paired with a fixed dark
# foreground so highlighted text stays readable in both light and dark mode.
HIGHLIGHT_FG = "#1d1d1f"
HIGHLIGHT_COLORS = [
    ("黄色", "#fff3a0"),
    ("绿色", "#c2f0c2"),
    ("蓝色", "#bfe3ff"),
    ("粉色", "#ffc9d6"),
    ("橙色", "#ffd9a8"),
    ("紫色", "#e3ccff"),
]


class _LinkHighlighter(QSyntaxHighlighter):
    """Overlays blue/underlined formatting on URLs for display only.

    Because this is a syntax highlighter, the formatting is applied at render
    time and is *not* stored in the document's character formats. That means it
    never clobbers user formatting (bold/strikethrough/highlight) and is never
    written out by ``toHtml()``.
    """

    LINK_COLOR = "#0a84ff"

    def highlightBlock(self, text: str):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.LINK_COLOR))
        fmt.setFontUnderline(True)
        for m in URL_PATTERN.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), fmt)


class _NotebookTextEdit(QTextEdit):
    """Rich-text QTextEdit that auto-highlights URLs and opens them on
    Alt(Option)+click, and supports bold / strikethrough / color highlight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_cursor_shape = Qt.CursorShape.IBeamCursor

        self.setMouseTracking(True)
        self.setAcceptRichText(True)

        self._link_highlighter = _LinkHighlighter(self.document())

    # ----- URL handling -------------------------------------------------

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

    # ----- Rich-text formatting ----------------------------------------

    def _merge_format(self, fmt: QTextCharFormat):
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            # No selection: apply to the format used for subsequent typing.
            self.mergeCurrentCharFormat(fmt)

    def toggle_bold(self):
        is_bold = self.textCursor().charFormat().fontWeight() >= QFont.Weight.Bold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self._merge_format(fmt)

    def toggle_strikethrough(self):
        is_struck = self.textCursor().charFormat().fontStrikeOut()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not is_struck)
        self._merge_format(fmt)

    def apply_highlight(self, color_hex: str):
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(color_hex))
        fmt.setForeground(QColor(HIGHLIGHT_FG))
        self._merge_format(fmt)

    def clear_highlight(self):
        self._clear_selection_format(clear_bg=True, clear_fg=True)

    def clear_all_formatting(self):
        self._clear_selection_format(
            clear_bg=True, clear_fg=True, clear_bold=True, clear_strike=True,
        )

    def _clear_selection_format(self, clear_bg=False, clear_fg=False,
                                clear_bold=False, clear_strike=False):
        """Remove formatting properties across the selection while preserving
        the ones not being cleared (works per-fragment so mixed runs survive)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        doc = self.document()

        editor_cursor = QTextCursor(doc)
        editor_cursor.beginEditBlock()
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fs = frag.position()
                fe = fs + frag.length()
                if fe > start and fs < end:
                    fmt = QTextCharFormat(frag.charFormat())
                    if clear_bg:
                        fmt.clearBackground()
                    if clear_fg:
                        fmt.clearForeground()
                    if clear_bold:
                        fmt.setFontWeight(QFont.Weight.Normal)
                    if clear_strike:
                        fmt.setFontStrikeOut(False)
                    seg = QTextCursor(doc)
                    seg.setPosition(max(fs, start))
                    seg.setPosition(min(fe, end), QTextCursor.MoveMode.KeepAnchor)
                    seg.setCharFormat(fmt)
                it += 1
            block = block.next()
        editor_cursor.endEditBlock()


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
        self._editor.setPlaceholderText(
            "在此输入笔记...(选中文字后右键可设置格式;按住 Option/Alt 点击链接以打开)"
        )
        layout.addWidget(self._editor, 1)

    def _load_content(self):
        """Load notebook content from database (HTML or legacy plain text)."""
        content = self._db.get_notebook(self._task_name)
        stripped = content.lstrip()
        if stripped.startswith("<!DOCTYPE") or stripped.lower().startswith("<html"):
            self._editor.setHtml(content)
        else:
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
        """Show custom context menu with formatting and timestamp options."""
        menu = self._editor.createStandardContextMenu()

        # --- Formatting -------------------------------------------------
        menu.addSeparator()

        cur_fmt = self._editor.textCursor().charFormat()

        bold_action = menu.addAction("加粗")
        bold_action.setCheckable(True)
        bold_action.setChecked(cur_fmt.fontWeight() >= QFont.Weight.Bold)

        strike_action = menu.addAction("删除线")
        strike_action.setCheckable(True)
        strike_action.setChecked(cur_fmt.fontStrikeOut())

        highlight_menu = menu.addMenu("高亮颜色")
        color_actions = {}
        for label, hex_color in HIGHLIGHT_COLORS:
            act = highlight_menu.addAction(label)
            color_actions[act] = hex_color
        highlight_menu.addSeparator()
        clear_highlight_action = highlight_menu.addAction("清除高亮")

        clear_all_action = menu.addAction("清除所有格式")

        # --- Timestamp / link ------------------------------------------
        menu.addSeparator()
        timestamp_action = menu.addAction("插入时间戳")

        url = self._editor._url_at_position(pos)
        open_link_action = None
        if url:
            menu.addSeparator()
            open_link_action = menu.addAction("在浏览器中打开链接")

        action = menu.exec(self._editor.mapToGlobal(pos))
        if action is None:
            return

        if action == bold_action:
            self._editor.toggle_bold()
        elif action == strike_action:
            self._editor.toggle_strikethrough()
        elif action in color_actions:
            self._editor.apply_highlight(color_actions[action])
        elif action == clear_highlight_action:
            self._editor.clear_highlight()
        elif action == clear_all_action:
            self._editor.clear_all_formatting()
        elif action == timestamp_action:
            stamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
            self._editor.textCursor().insertText(stamp)
        elif open_link_action is not None and action == open_link_action:
            QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        """Auto-save content on close (as HTML to preserve formatting)."""
        if self._editor.toPlainText().strip():
            content = self._editor.toHtml()
        else:
            content = ""  # keep empty notes empty rather than storing boilerplate HTML
        self._db.save_notebook(self._task_name, content)
        super().closeEvent(event)
