"""Preset bar widget for quick timer starts."""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QDialog, QVBoxLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox,
    QScrollArea, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt

from src.models import Preset, Category
from typing import List


class PresetButton(QPushButton):
    """A styled button for preset quick-start."""

    delete_requested = pyqtSignal(object)  # Preset
    edit_requested = pyqtSignal(object)  # Preset

    def __init__(self, preset: Preset, parent=None):
        super().__init__(parent)
        self.preset = preset
        self._dark_mode = False

        self.setMinimumWidth(110)
        self.setMinimumHeight(56)

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

    def _update_label_text(self):
        """Update label with rich text, count in small gray."""
        name_color = "#ffffff" if self._dark_mode else "#1d1d1f"
        count_color = "#888888" if self._dark_mode else "#b0b0b0"
        star_color = "#FFB800"
        name = self.preset.name
        duration = self.preset.format_duration()

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


class PresetBar(QWidget):
    """Bar containing preset quick-start buttons."""

    # Signals
    preset_selected = pyqtSignal(object)  # Preset
    custom_requested = pyqtSignal()
    preset_deleted = pyqtSignal(int)  # preset_id
    preset_edit_requested = pyqtSignal(object)  # Preset

    def __init__(self, parent=None):
        super().__init__(parent)

        self._presets: List[Preset] = []

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
            btn.clicked.connect(lambda checked, p=preset: self._on_preset_clicked(p))
            btn.delete_requested.connect(self._on_preset_delete)
            btn.edit_requested.connect(self._on_preset_edit)
            self.layout.insertWidget(self.layout.count() - 1, btn)

    def _on_preset_clicked(self, preset: Preset):
        """Handle preset button click."""
        self.preset_selected.emit(preset)

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
    # Collect QLineEdits that belong to QSpinBox so we skip them below
    spinbox_line_edits = set()
    for w in dialog.findChildren(QSpinBox):
        le = w.lineEdit()
        if le:
            spinbox_line_edits.add(le)
        # Use only palette for QSpinBox - stylesheets conflict with internal QLineEdit
        w.setStyleSheet("")
        pal = w.palette()
        pal.setColor(pal.ColorRole.Text, QColor(text))
        pal.setColor(pal.ColorRole.Base, QColor(input_bg))
        pal.setColor(pal.ColorRole.WindowText, QColor(text))
        w.setPalette(pal)
        if le:
            le.setStyleSheet("")
            le_pal = le.palette()
            le_pal.setColor(le_pal.ColorRole.Text, QColor(text))
            le_pal.setColor(le_pal.ColorRole.Base, QColor(input_bg))
            le.setPalette(le_pal)
    for w in dialog.findChildren(QLineEdit):
        if w in spinbox_line_edits:
            continue
        w.setStyleSheet(f"QLineEdit {{ {input_style} }} QLineEdit:focus {{ border-color: {focus_border}; }}")
    for w in dialog.findChildren(QComboBox):
        w.setStyleSheet(f"QComboBox {{ {input_style} }} QComboBox:focus {{ border-color: {focus_border}; }}")

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
        duration_label = QLabel("时长（分钟）")
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 480)  # 1 min to 8 hours
        self.duration_input.setValue(25)
        self.duration_input.setSuffix("")
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_input)

        # Quick-fill duration buttons
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        for mins in (10, 20, 30):
            btn = QPushButton(f"{mins} 分钟")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mins: self.duration_input.setValue(m))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

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
        self.duration_input.setRange(1, 480)
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
