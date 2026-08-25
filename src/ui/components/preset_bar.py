"""Preset bar widget for quick timer starts."""
import random

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QDialog, QVBoxLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox,
    QScrollArea, QMenu, QApplication, QDateTimeEdit, QTextEdit,
    QCalendarWidget
)
from PyQt6.QtCore import pyqtSignal, Qt, QMimeData, QEvent
from PyQt6.QtGui import QDrag

from src.models import Preset, Category
from typing import List


# Extended duration options (label, minutes) for the custom timer dropdown.
LONG_DURATION_OPTIONS = [
    ("1 小时", 60),
    ("2 小时", 120),
    ("3 小时", 180),
    ("5 小时", 300),
    ("8 小时", 480),
    ("12 小时", 720),
    ("24 小时", 24 * 60),
    ("2 天", 2 * 24 * 60),
    ("3 天", 3 * 24 * 60),
    ("5 天", 5 * 24 * 60),
    ("1 周", 7 * 24 * 60),
    ("2 周", 14 * 24 * 60),
    ("1 个月", 30 * 24 * 60),
]


class PresetButton(QPushButton):
    """A styled button for preset quick-start."""

    delete_requested = pyqtSignal(object)  # Preset
    edit_requested = pyqtSignal(object)  # Preset

    def __init__(self, preset: Preset, parent=None):
        super().__init__(parent)
        self.preset = preset
        self._dark_mode = False
        self._draggable = False  # enabled only in manual sort mode
        self._drag_start_pos = None
        self.drag_started = False  # suppress the click that follows a drag

        # Fixed size so every preset box lines up uniformly; long names are
        # elided with an ellipsis instead of overflowing into the next box.
        self.setFixedWidth(120)
        self.setFixedHeight(58)

        # Use a layout with QLabel for rich text (styled count)
        btn_layout = QVBoxLayout(self)
        btn_layout.setSpacing(0)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setStyleSheet("background: transparent; border: none;")
        self._update_label_text()
        btn_layout.addWidget(self._label)

        # Full name on hover, since long names get elided in the box.
        self.setToolTip(preset.name)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        base_border = "#007AFF" if not preset.is_default else "#d2d2d7"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid {base_border};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #e5e5ea;
                border-color: #007AFF;
            }}
            QPushButton:pressed {{
                background-color: #d2d2d7;
            }}
        """)

    def _elide_name(self, name: str) -> str:
        """Truncate an overly long preset name to fit the fixed button width."""
        from PyQt6.QtGui import QFontMetrics, QFont
        font = QFont(self.font())
        font.setPixelSize(14)
        # Available text width = fixed width minus horizontal padding & border.
        avail = self.width() - 28 if self.width() > 40 else 92
        return QFontMetrics(font).elidedText(name, Qt.TextElideMode.ElideRight, avail)

    def _update_label_text(self):
        """Update label with rich text, count in small gray."""
        import html
        name_color = "#ffffff" if self._dark_mode else "#1d1d1f"
        count_color = "#888888" if self._dark_mode else "#b0b0b0"
        star_color = "#FFB800"
        name = html.escape(self._elide_name(self.preset.name))
        duration = html.escape(self.preset.format_duration())

        rating = max(0, min(5, getattr(self.preset, 'star_rating', 0) or 0))
        stars_html = ""
        if rating > 0:
            stars_html = (
                f'<div style="text-align:center; line-height:10px; margin-bottom:1px;">'
                f'<span style="color:{star_color}; font-size:10px;">{"★" * rating}</span>'
                f'</div>'
            )

        if self.preset.use_count > 0:
            html = (
                f'{stars_html}'
                f'<div style="text-align:center;">'
                f'<span style="color:{name_color}; font-size:14px;">{name}</span><br/>'
                f'<span style="color:{name_color}; font-size:13px;">{duration}</span>'
                f'&nbsp;&nbsp;<span style="color:{count_color}; font-size:11px;">{self.preset.use_count}次</span>'
                f'</div>'
            )
        else:
            html = (
                f'{stars_html}'
                f'<div style="text-align:center;">'
                f'<span style="color:{name_color}; font-size:14px;">{name}</span><br/>'
                f'<span style="color:{name_color}; font-size:13px;">{duration}</span>'
                f'</div>'
            )
        self._label.setText(html)

    def _show_context_menu(self, pos):
        """Show right-click context menu for presets."""
        menu = QMenu(self)
        edit_action = menu.addAction("编辑预设")
        delete_action = None
        if not self.preset.is_default:
            menu.addSeparator()
            delete_action = menu.addAction("删除此预设")
        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit(self.preset)
        elif action and action == delete_action:
            self.delete_requested.emit(self.preset)

    def set_draggable(self, enabled: bool):
        """Enable/disable drag-to-reorder (manual sort mode only)."""
        self._draggable = enabled
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if enabled
            else Qt.CursorShape.PointingHandCursor
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (not self._draggable or self._drag_start_pos is None
                or not (event.buttons() & Qt.MouseButton.LeftButton)):
            super().mouseMoveEvent(event)
            return
        moved = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if moved < QApplication.startDragDistance():
            return

        self.drag_started = True
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(PresetBar.MIME_TYPE.format(self.preset.id))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._drag_start_pos)
        drag.exec(Qt.DropAction.MoveAction)


class PresetBar(QWidget):
    """Bar containing preset quick-start buttons."""

    # Drag-and-drop payload format; the preset id is interpolated in.
    MIME_TYPE = "application/x-stellar-preset:{}"

    # Signals
    preset_selected = pyqtSignal(object)  # Preset
    custom_requested = pyqtSignal()
    preset_deleted = pyqtSignal(int)  # preset_id
    preset_edit_requested = pyqtSignal(object)  # Preset
    presets_reordered = pyqtSignal(list)  # ordered list of preset ids

    def __init__(self, parent=None):
        super().__init__(parent)

        self._presets: List[Preset] = []
        self._manual_mode = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the preset bar UI."""
        outer_layout = QHBoxLayout(self)
        outer_layout.setSpacing(0)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Scrollable area for preset buttons
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFixedHeight(72)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:horizontal {
                height: 4px;
                background: transparent;
            }
            QScrollBar::handle:horizontal {
                background: #c0c0c0;
                border-radius: 2px;
            }
        """)

        self.scroll_widget = QWidget()
        self.layout = QHBoxLayout(self.scroll_widget)
        self.layout.setSpacing(8)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Add stretch at the end
        self.layout.addStretch()

        # Accept preset drops on the content widget for drag-reorder.
        self.scroll_widget.setAcceptDrops(True)
        self.scroll_widget.installEventFilter(self)

        # Thin vertical line showing where a dragged preset will land.
        self._drop_indicator = QWidget(self.scroll_widget)
        self._drop_indicator.setFixedWidth(3)
        self._drop_indicator.setStyleSheet(
            "background-color: #007AFF; border-radius: 1px;"
        )
        self._drop_indicator.hide()

        self.scroll_area.setWidget(self.scroll_widget)
        outer_layout.addWidget(self.scroll_area)

    def set_presets(self, presets: List[Preset]):
        """Set the presets to display."""
        self._presets = presets
        self._rebuild_buttons()

    def _rebuild_buttons(self):
        """Rebuild all preset buttons."""
        # Clear existing buttons (except stretch)
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add custom button first (always at the front)
        custom_btn = QPushButton("+ 自定义")
        custom_btn.setMinimumWidth(90)
        custom_btn.setMinimumHeight(56)
        custom_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        custom_btn.clicked.connect(self.custom_requested.emit)
        self.layout.insertWidget(self.layout.count() - 1, custom_btn)

        # Add preset buttons after custom button
        for preset in self._presets:
            btn = PresetButton(preset)
            btn.set_draggable(self._manual_mode)
            btn.clicked.connect(lambda checked, b=btn: self._on_preset_clicked(b))
            btn.delete_requested.connect(self._on_preset_delete)
            btn.edit_requested.connect(self._on_preset_edit)
            self.layout.insertWidget(self.layout.count() - 1, btn)

    def _on_preset_clicked(self, button: 'PresetButton'):
        """Handle preset button click (ignored if the click ended a drag)."""
        if button.drag_started:
            button.drag_started = False
            return
        self.preset_selected.emit(button.preset)

    def set_manual_mode(self, enabled: bool):
        """Toggle manual drag-reorder mode for the preset buttons."""
        self._manual_mode = enabled
        for btn in self._preset_buttons():
            btn.set_draggable(enabled)

    def _preset_buttons(self) -> List['PresetButton']:
        """Return the preset buttons in current visual (layout) order."""
        buttons = []
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if isinstance(w, PresetButton):
                buttons.append(w)
        return buttons

    def _drop_index_among(self, buttons: List['PresetButton'], x: int) -> int:
        """Index (within `buttons`) at which a drop at scroll-widget x lands."""
        for idx, btn in enumerate(buttons):
            if x < btn.x() + btn.width() / 2:
                return idx
        return len(buttons)

    def eventFilter(self, obj, event):
        """Handle drag-reorder events on the scrollable content widget."""
        if obj is not self.scroll_widget or not self._manual_mode:
            return super().eventFilter(obj, event)

        etype = event.type()
        if etype == QEvent.Type.DragEnter:
            if event.mimeData().hasText() and event.mimeData().text().startswith(
                    self.MIME_TYPE.format("")[:-1]):
                event.acceptProposedAction()
                return True
        elif etype == QEvent.Type.DragMove:
            buttons = self._preset_buttons()
            index = self._drop_index_among(buttons, int(event.position().x()))
            self._show_drop_indicator(buttons, index)
            event.acceptProposedAction()
            return True
        elif etype == QEvent.Type.DragLeave:
            self._drop_indicator.hide()
            return True
        elif etype == QEvent.Type.Drop:
            self._drop_indicator.hide()
            self._handle_drop(event)
            event.acceptProposedAction()
            return True
        return super().eventFilter(obj, event)

    def _show_drop_indicator(self, buttons: List['PresetButton'], index: int):
        """Position the vertical drop indicator before button `index`."""
        if not buttons:
            self._drop_indicator.hide()
            return
        if index < len(buttons):
            x = buttons[index].x() - 6
            top = buttons[index].y()
            height = buttons[index].height()
        else:
            last = buttons[-1]
            x = last.x() + last.width() + 3
            top = last.y()
            height = last.height()
        self._drop_indicator.setGeometry(x, top, 3, height)
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _handle_drop(self, event):
        """Reorder presets after a drop and emit the new id ordering."""
        text = event.mimeData().text()
        prefix = self.MIME_TYPE.format("")
        try:
            source_id = int(text[len(prefix):])
        except (ValueError, TypeError):
            return

        buttons = self._preset_buttons()
        ids = [b.preset.id for b in buttons]
        if source_id not in ids:
            return

        target = self._drop_index_among(buttons, int(event.position().x()))
        old = ids.index(source_id)
        ids.pop(old)
        # Account for the removed item shifting indices to its right.
        if target > old:
            target -= 1
        ids.insert(target, source_id)

        if ids != [b.preset.id for b in buttons]:
            self.presets_reordered.emit(ids)

    def _on_search_changed(self, text: str):
        """Filter preset buttons based on search keywords (space-separated, all must match)."""
        keywords = text.strip().lower().split()
        for i in range(self.layout.count() - 1):  # skip trailing stretch
            item = self.layout.itemAt(i)
            widget = item.widget()
            if widget and isinstance(widget, PresetButton):
                if not keywords:
                    widget.setVisible(True)
                else:
                    name_lower = widget.preset.name.lower()
                    widget.setVisible(all(kw in name_lower for kw in keywords))

    def _on_preset_edit(self, preset: Preset):
        """Handle preset edit request."""
        self.preset_edit_requested.emit(preset)

    def _on_preset_delete(self, preset: Preset):
        """Handle preset delete request."""
        if not preset.is_default:
            self.preset_deleted.emit(preset.id)

    def set_dark_mode(self, enabled: bool):
        """Toggle dark mode styling."""
        # Update button styles based on dark mode
        for i in range(self.layout.count() - 1):
            item = self.layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), PresetButton):
                btn = item.widget()
                btn._dark_mode = enabled
                btn._update_label_text()
                is_custom = not btn.preset.is_default
                if enabled:
                    border = "#0a84ff" if is_custom else "#48484a"
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: #2c2c2e;
                            color: #ffffff;
                            border: 1px solid {border};
                            border-radius: 8px;
                            padding: 8px 12px;
                            font-size: 12px;
                            text-align: center;
                        }}
                        QPushButton:hover {{
                            background-color: #3a3a3c;
                            border-color: #0a84ff;
                        }}
                        QPushButton:pressed {{
                            background-color: #48484a;
                        }}
                    """)
                else:
                    border = "#007AFF" if is_custom else "#d2d2d7"
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: #f5f5f7;
                            color: #1d1d1f;
                            border: 1px solid {border};
                            border-radius: 8px;
                            padding: 8px 12px;
                            font-size: 12px;
                            text-align: center;
                        }}
                        QPushButton:hover {{
                            background-color: #e5e5ea;
                            border-color: #007AFF;
                        }}
                        QPushButton:pressed {{
                            background-color: #d2d2d7;
                        }}
                    """)


def _style_calendar_popup(calendar: QCalendarWidget, dark_mode: bool):
    """Theme a QDateTimeEdit's calendar popup, which renders in its own window."""
    if dark_mode:
        bg, text, header, disabled, sel = "#2c2c2e", "#ffffff", "#3a3a3c", "#636366", "#0a84ff"
    else:
        bg, text, header, disabled, sel = "#ffffff", "#1d1d1f", "#f5f5f7", "#c7c7cc", "#007AFF"
    calendar.setStyleSheet(f"""
        QCalendarWidget QWidget {{ alternate-background-color: {bg}; }}
        QCalendarWidget QAbstractItemView:enabled {{
            background-color: {bg};
            color: {text};
            selection-background-color: {sel};
            selection-color: #ffffff;
        }}
        QCalendarWidget QAbstractItemView:disabled {{ color: {disabled}; }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{ background-color: {header}; }}
        QCalendarWidget QToolButton {{
            color: {text};
            background-color: transparent;
            border: none;
            padding: 4px 8px;
        }}
        QCalendarWidget QToolButton:hover {{ background-color: {sel}; color: #ffffff; }}
        QCalendarWidget QSpinBox {{ color: {text}; background-color: {bg}; }}
    """)


def _apply_dialog_theme(dialog: QDialog, dark_mode: bool):
    """Apply theme-aware styling to a dialog, overriding global theme."""
    from PyQt6.QtGui import QColor

    if dark_mode:
        bg = "#2c2c2e"
        text = "#ffffff"
        input_bg = "#3a3a3c"
        border = "#636366"
        focus_border = "#0a84ff"
        btn_bg = "#3a3a3c"
        label_secondary = "#ebebf5"
    else:
        bg = "#ffffff"
        text = "#1d1d1f"
        input_bg = "#ffffff"
        border = "#d2d2d7"
        focus_border = "#007AFF"
        btn_bg = "#f5f5f7"
        label_secondary = "#1d1d1f"

    label_style = f"font-size: 13px; color: {label_secondary}; background-color: {bg};"
    input_style = f"""
        padding: 8px;
        border: 1px solid {border};
        border-radius: 6px;
        font-size: 13px;
        color: {text};
        background-color: {input_bg};
    """
    for w in dialog.findChildren(QLabel):
        w.setStyleSheet(label_style)
    # Collect QLineEdits that belong to a spin box so we skip them below
    spinbox_line_edits = set()
    # QDateTimeEdit is a QAbstractSpinBox, not a QSpinBox, so findChildren
    # misses it — but it needs the very same palette-only treatment: a
    # stylesheet with padding shifts its internal line edit and clips the
    # digits. The calendar popup is a separate top-level window that inherits
    # nothing from the dialog, so it is styled explicitly.
    def _style_spin_like(w):
        """Palette-only theming for spin boxes and date edits.

        Stylesheets fight with their internal QLineEdit — padding shifts the
        editor inside the frame and clips the digits — so only the palette is
        touched. The inner editor is reached via findChildren instead of the
        protected lineEdit(), which sip refuses on widgets that were created
        in C++ (the calendar popup's year spin box, for one).
        """
        w.setStyleSheet("")
        pal = w.palette()
        pal.setColor(pal.ColorRole.Text, QColor(text))
        pal.setColor(pal.ColorRole.Base, QColor(input_bg))
        pal.setColor(pal.ColorRole.WindowText, QColor(text))
        w.setPalette(pal)
        for le in w.findChildren(QLineEdit):
            spinbox_line_edits.add(le)
            le.setStyleSheet("")
            le_pal = le.palette()
            le_pal.setColor(le_pal.ColorRole.Text, QColor(text))
            le_pal.setColor(le_pal.ColorRole.Base, QColor(input_bg))
            le.setPalette(le_pal)

    # QDateTimeEdit is a QAbstractSpinBox, not a QSpinBox, so findChildren
    # misses it and it has to be handled alongside. Its calendar popup is a
    # separate top-level window that inherits nothing from the dialog.
    for w in dialog.findChildren(QDateTimeEdit):
        _style_spin_like(w)
        calendar = w.calendarWidget()
        if calendar is not None:
            _style_calendar_popup(calendar, dark_mode)
    for w in dialog.findChildren(QSpinBox):
        _style_spin_like(w)
    for w in dialog.findChildren(QLineEdit):
        if w in spinbox_line_edits:
            continue
        w.setStyleSheet(f"QLineEdit {{ {input_style} }} QLineEdit:focus {{ border-color: {focus_border}; }}")
    for w in dialog.findChildren(QComboBox):
        w.setStyleSheet(f"QComboBox {{ {input_style} }} QComboBox:focus {{ border-color: {focus_border}; }}")
    for w in dialog.findChildren(QTextEdit):
        w.setStyleSheet(f"QTextEdit {{ {input_style} }} QTextEdit:focus {{ border-color: {focus_border}; }}")
    palette = dialog.palette()
    palette.setColor(palette.ColorRole.Window, QColor(bg))
    palette.setColor(palette.ColorRole.WindowText, QColor(text))
    palette.setColor(palette.ColorRole.Base, QColor(input_bg))
    palette.setColor(palette.ColorRole.Text, QColor(text))
    palette.setColor(palette.ColorRole.Button, QColor(btn_bg))
    palette.setColor(palette.ColorRole.ButtonText, QColor(text))
    dialog.setPalette(palette)
    dialog.setAutoFillBackground(True)


class CustomTimerDialog(QDialog):
    """Dialog for creating a custom timer."""

    def __init__(self, categories: List[Category], parent=None, dark_mode: bool = False):
        super().__init__(parent)

        self.categories = categories
        self.result_data = None

        self._setup_ui()
        _apply_dialog_theme(self, dark_mode)

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("自定义计时器")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Task name
        name_label = QLabel("任务名称")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入任务名称...")
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)

        # Duration
        quick_options = (10, 20, 30)
        duration_label = QLabel("时长（分钟）")
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 43200)  # 1 min to 1 month (30 days)
        # Randomly pre-fill from the quick options so different timers stagger
        # by default; the user can still tweak the value before confirming.
        self.duration_input.setValue(random.choice(quick_options))
        self.duration_input.setSuffix("")
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_input)

        # Quick-fill duration buttons
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        for mins in quick_options:
            btn = QPushButton(f"{mins} 分钟")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mins: self.duration_input.setValue(m))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

        # Extended-duration dropdown for longer timers
        self.duration_preset_combo = QComboBox()
        self.duration_preset_combo.addItem("更多时长...", None)
        for label, mins in LONG_DURATION_OPTIONS:
            self.duration_preset_combo.addItem(label, mins)
        self.duration_preset_combo.currentIndexChanged.connect(
            self._on_duration_preset_changed
        )
        layout.addWidget(self.duration_preset_combo)

        # Category
        category_label = QLabel("分类")
        self.category_combo = QComboBox()
        for cat in self.categories:
            self.category_combo.addItem(f"{cat.icon} {cat.name}", cat.id)
        layout.addWidget(category_label)
        layout.addWidget(self.category_combo)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_duration_preset_changed(self, index: int):
        """Apply a selected extended-duration option to the spinbox."""
        mins = self.duration_preset_combo.itemData(index)
        if mins is not None:
            self.duration_input.setValue(mins)
        # Reset back to the placeholder so the same option can be picked again.
        self.duration_preset_combo.blockSignals(True)
        self.duration_preset_combo.setCurrentIndex(0)
        self.duration_preset_combo.blockSignals(False)

    def _on_accept(self):
        """Handle dialog acceptance."""
        name = self.name_input.text().strip()
        if not name:
            name = "自定义任务"

        self.result_data = {
            'name': name,
            'duration_seconds': self.duration_input.value() * 60,
            'category_id': self.category_combo.currentData(),
        }
        self.accept()

    def get_result(self):
        """Get the dialog result."""
        return self.result_data


class EditPresetDialog(QDialog):
    """Dialog for editing an existing preset."""

    def __init__(self, preset: Preset, categories: List[Category], parent=None, dark_mode: bool = False):
        super().__init__(parent)

        self.preset = preset
        self.categories = categories
        self.result_data = None

        self._setup_ui()
        _apply_dialog_theme(self, dark_mode)

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("编辑预设")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Task name
        name_label = QLabel("预设名称")
        self.name_input = QLineEdit()
        self.name_input.setText(self.preset.name)
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)

        # Duration
        duration_label = QLabel("时长（分钟）")
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 43200)  # 1 min to 1 month, same as custom dialog
        self.duration_input.setValue(self.preset.duration_seconds // 60)
        self.duration_input.setSuffix("")
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_input)

        # Category
        category_label = QLabel("分类")
        self.category_combo = QComboBox()
        current_index = 0
        for i, cat in enumerate(self.categories):
            self.category_combo.addItem(f"{cat.icon} {cat.name}", cat.id)
            if cat.id == self.preset.category_id:
                current_index = i
        self.category_combo.setCurrentIndex(current_index)
        layout.addWidget(category_label)
        layout.addWidget(self.category_combo)

        # Star rating (importance)
        star_label = QLabel("重要性 (0-5 星)")
        self.star_input = QSpinBox()
        self.star_input.setRange(0, 5)
        self.star_input.setValue(getattr(self.preset, 'star_rating', 0) or 0)
        layout.addWidget(star_label)
        layout.addWidget(self.star_input)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        """Handle dialog acceptance."""
        name = self.name_input.text().strip()
        if not name:
            name = self.preset.name

        self.result_data = {
            'name': name,
            'duration_seconds': self.duration_input.value() * 60,
            'category_id': self.category_combo.currentData(),
            'star_rating': self.star_input.value(),
        }
        self.accept()

    def get_result(self):
        """Get the dialog result."""
        return self.result_data
