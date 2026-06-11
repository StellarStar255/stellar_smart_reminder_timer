"""Per-task notebook dialog for taking notes."""

import re
import struct
import zlib
from datetime import datetime

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import (
    QKeySequence, QShortcut, QDesktopServices,
    QTextCursor, QTextCharFormat, QColor, QFont, QSyntaxHighlighter,
    QPixmap, QIcon, QPainter, QImage,
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


def _color_swatch(hex_color: str, size: int = 14) -> QIcon:
    """Build a small rounded color-swatch icon for menu entries."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(hex_color))
    painter.setPen(QColor(0, 0, 0, 60))
    painter.drawRoundedRect(0, 0, size - 1, size - 1, 3, 3)
    painter.end()
    return QIcon(pm)


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

    # ----- Image paste / drop -------------------------------------------

    # Pasted images wider than this are scaled down to keep the stored
    # notebook HTML (base64-embedded) reasonably small.
    MAX_IMAGE_WIDTH = 800

    IMAGE_FILE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff')

    def canInsertFromMimeData(self, source) -> bool:
        # NOTE: any exception escaping these C++ virtual overrides aborts the
        # whole process under PyQt6, so they must never raise.
        try:
            if source.hasImage():
                return True
            return super().canInsertFromMimeData(source)
        except Exception:
            return False

    def insertFromMimeData(self, source):
        """Embed pasted/dropped images as base64 data URIs so they survive
        toHtml() round-trips (database save, export/import)."""
        try:
            image = self._image_from_mime_data(source)
        except Exception:
            image = None
        if image is not None and not image.isNull():
            try:
                self._insert_image(image)
                return
            except Exception:
                pass  # fall through to the default text handler
        super().insertFromMimeData(source)

    def _image_from_mime_data(self, source):
        """Extract a QImage from mime data, tolerating the many shapes the
        macOS clipboard can deliver (QImage, QPixmap, raw bytes, file URLs)."""
        if source.hasImage():
            raw = source.imageData()
            if isinstance(raw, QImage) and not raw.isNull():
                return QImage(raw)  # detached copy
            if isinstance(raw, QPixmap) and not raw.isNull():
                return raw.toImage()
        # Fall back to decoding the raw clipboard bytes (screenshots on
        # macOS are typically provided as TIFF/PNG data)
        for mime_type in ('image/png', 'image/tiff', 'image/jpeg',
                          'image/bmp', 'image/webp'):
            if source.hasFormat(mime_type):
                image = QImage()
                if image.loadFromData(source.data(mime_type)) and not image.isNull():
                    return image
        if source.hasUrls():
            for url in source.urls():
                if (url.isLocalFile()
                        and url.toLocalFile().lower().endswith(self.IMAGE_FILE_SUFFIXES)):
                    image = QImage(url.toLocalFile())
                    if not image.isNull():
                        return image
        return None

    def _insert_image(self, image: QImage):
        # Normalize exotic clipboard pixel formats before scaling/encoding
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        if image.isNull():
            return
        if image.width() > self.MAX_IMAGE_WIDTH:
            image = image.scaledToWidth(
                self.MAX_IMAGE_WIDTH, Qt.TransformationMode.SmoothTransformation
            )
        png_bytes = self._encode_png(image)
        if not png_bytes:
            return
        import base64
        b64 = base64.b64encode(png_bytes).decode('ascii')
        self.textCursor().insertHtml(
            f'<img src="data:image/png;base64,{b64}" width="{image.width()}" />'
        )

    # ----- Image copy (notebook -> other apps) ---------------------------

    def createMimeDataFromSelection(self):
        """Attach real image data when the selection contains an image, so
        Cmd+C can paste into external apps (not just HTML markup).

        Note: the QTextEditMimeData returned by super() generates its format
        list lazily from the document fragment and ignores setImageData, so
        a fresh QMimeData must be built instead."""
        base = super().createMimeDataFromSelection()
        try:
            image = self._first_image_in_selection()
            if image is None or image.isNull():
                return base
            from PyQt6.QtCore import QMimeData
            mime = QMimeData()
            mime.setHtml(base.html())
            mime.setText(base.text())
            mime.setImageData(image)
            return mime
        except Exception:
            return base

    def _first_image_in_selection(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return None
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        doc = self.document()
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.position() < end and frag.position() + frag.length() > start:
                    fmt = frag.charFormat()
                    if fmt.isImageFormat():
                        image = self._resolve_image(fmt.toImageFormat().name())
                        if image is not None:
                            return image
                it += 1
            block = block.next()
        return None

    def image_at_position(self, pos):
        """Return the QImage under the mouse position, if any."""
        cursor = self.cursorForPosition(pos)
        fmt = cursor.charFormat()
        if not fmt.isImageFormat():
            cursor.movePosition(QTextCursor.MoveOperation.Right,
                                QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
        if fmt.isImageFormat():
            return self._resolve_image(fmt.toImageFormat().name())
        return None

    def _resolve_image(self, src: str):
        """Resolve an <img> source (data URI) to a QImage."""
        from PyQt6.QtGui import QTextDocument
        resource = self.document().resource(
            QTextDocument.ResourceType.ImageResource.value, QUrl(src)
        )
        if isinstance(resource, QImage) and not resource.isNull():
            return resource
        if isinstance(resource, QPixmap) and not resource.isNull():
            return resource.toImage()
        if src.startswith('data:image/') and ',' in src:
            import base64
            try:
                image = QImage.fromData(base64.b64decode(src.split(',', 1)[1]))
                if not image.isNull():
                    return image
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _encode_png(image: QImage) -> bytes:
        """Encode a QImage as PNG in pure Python.

        QImage.save(..., "PNG") segfaults under anaconda because conda's
        libz clashes with the libpng bundled inside Qt; encoding with
        Python's own zlib sidesteps Qt's image writer entirely.
        """
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        if image.isNull():
            return b''
        width, height = image.width(), image.height()
        ptr = image.constBits()
        ptr.setsize(image.sizeInBytes())
        data = bytes(ptr)
        stride = image.bytesPerLine()
        # PNG scanlines: filter byte 0 (None) + raw RGBA rows
        raw = b''.join(
            b'\x00' + data[y * stride: y * stride + width * 4]
            for y in range(height)
        )

        def chunk(tag: bytes, payload: bytes) -> bytes:
            return (struct.pack('>I', len(payload)) + tag + payload
                    + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

        ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(raw, 6))
                + chunk(b'IEND', b''))

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
            "在此输入笔记...(选中文字后右键可设置格式;按住 Option/Alt 点击链接以打开;"
            "支持直接粘贴图片)"
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

        menu.addSeparator()
        color_actions = {}
        for label, hex_color in HIGHLIGHT_COLORS:
            act = menu.addAction(_color_swatch(hex_color), f"高亮 · {label}")
            color_actions[act] = hex_color
        clear_highlight_action = menu.addAction("清除高亮")

        menu.addSeparator()
        clear_all_action = menu.addAction("清除所有格式")

        # --- Timestamp / link / image -----------------------------------
        menu.addSeparator()
        timestamp_action = menu.addAction("插入时间戳")

        url = self._editor._url_at_position(pos)
        open_link_action = None
        if url:
            menu.addSeparator()
            open_link_action = menu.addAction("在浏览器中打开链接")

        image_under_cursor = self._editor.image_at_position(pos)
        copy_image_action = None
        if image_under_cursor is not None:
            menu.addSeparator()
            copy_image_action = menu.addAction("复制图片")

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
        elif copy_image_action is not None and action == copy_image_action:
            from PyQt6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setImage(image_under_cursor)

    def closeEvent(self, event):
        """Auto-save content on close (as HTML to preserve formatting)."""
        if self._editor.toPlainText().strip():
            content = self._editor.toHtml()
        else:
            content = ""  # keep empty notes empty rather than storing boilerplate HTML
        self._db.save_notebook(self._task_name, content)
        super().closeEvent(event)
