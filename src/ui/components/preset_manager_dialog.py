"""Preset management dialog: browse, search, edit and batch-manage all presets."""

import json
from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.models import Preset, Category
from src.ui.components.preset_bar import EditPresetDialog
from src.ui.components.stats_dashboard import StatsDashboard
from src.ui.components.task_notebook_dialog import TaskNotebookDialog

# Item data roles
_ID_ROLE = Qt.ItemDataRole.UserRole          # preset id, stored on column 0
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1    # numeric sort key for formatted columns


class _SortItem(QTableWidgetItem):
    """Table item that sorts by a numeric key while displaying formatted text."""

    def __lt__(self, other):
        return (self.data(_SORT_ROLE) or 0) < (other.data(_SORT_ROLE) or 0)


class PresetManagerDialog(QDialog):
    """List view over all presets with search, sort, edit and batch delete."""

    presets_changed = pyqtSignal()

    COL_NAME = 0
    COL_CATEGORY = 1
    COL_DURATION = 2
    COL_STARS = 3
    COL_USE_COUNT = 4
    COL_LAST_USED = 5

    def __init__(self, preset_manager, categories: List[Category],
                 parent=None, dark_mode: bool = False):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.categories = categories
        self._categories_by_id: Dict[int, Category] = {c.id: c for c in categories}
        self._presets_by_id: Dict[int, Preset] = {}
        self._dark_mode = dark_mode

        self._setup_ui()
        self._apply_theme()
        self._reload()

    def _setup_ui(self):
        self.setWindowTitle("预设管理")
        self.setMinimumSize(780, 520)
        self.resize(860, 560)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Toolbar: search + category filter
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索预设名称...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self.search_input, 1)

        self.category_filter = QComboBox()
        self.category_filter.setFixedHeight(32)
        self.category_filter.addItem("全部分类", None)
        for cat in self.categories:
            self.category_filter.addItem(f"{cat.icon} {cat.name}", cat.id)
        self.category_filter.currentIndexChanged.connect(self._apply_filters)
        toolbar.addWidget(self.category_filter)

        layout.addLayout(toolbar)

        # Preset table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["名称", "分类", "时长", "重要性", "使用次数", "最近使用"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.cellDoubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (self.COL_CATEGORY, self.COL_DURATION, self.COL_STARS,
                    self.COL_USE_COUNT, self.COL_LAST_USED):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        # Bottom bar: count + actions
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.count_label = QLabel()
        bottom.addWidget(self.count_label)
        bottom.addStretch()

        hint = QLabel("双击编辑笔记本 · 右键更多操作")
        hint.setObjectName("hintLabel")
        bottom.addWidget(hint)

        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setFixedHeight(32)
        self.edit_btn.clicked.connect(self._edit_current)
        bottom.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setFixedHeight(32)
        self.delete_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(self.delete_btn)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setFixedHeight(32)
        self.close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.close_btn)

        layout.addLayout(bottom)

    # --- Data loading & filtering ---

    def _load_task_star_ratings(self) -> Dict[str, int]:
        """Load the task-name -> star rating map set via the stats chart."""
        db = getattr(self.preset_manager, 'db', None)
        if db is None:
            return {}
        try:
            raw = db.get_setting(StatsDashboard.STAR_RATINGS_KEY, "{}")
            data = json.loads(raw) if raw else {}
            return {str(name): int(rating) for name, rating in data.items()}
        except (ValueError, TypeError):
            return {}

    def _reload(self):
        """Reload all presets from the manager into the table."""
        presets = self.preset_manager.get_all()
        self._presets_by_id = {p.id: p for p in presets}
        # Stars can come from the preset itself or from chart task ratings,
        # which are keyed by task name; show whichever is higher.
        task_ratings = self._load_task_star_ratings()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(presets))

        for row, preset in enumerate(presets):
            cat = self._categories_by_id.get(preset.category_id)

            name_text = preset.name + ("　🔒" if preset.is_default else "")
            name_item = QTableWidgetItem(name_text)
            name_item.setData(_ID_ROLE, preset.id)
            name_item.setToolTip(
                preset.name + ("（默认预设，不可删除）" if preset.is_default else "")
            )
            self.table.setItem(row, self.COL_NAME, name_item)

            cat_item = QTableWidgetItem(f"{cat.icon} {cat.name}" if cat else "—")
            self.table.setItem(row, self.COL_CATEGORY, cat_item)

            dur_item = _SortItem(preset.format_duration())
            dur_item.setData(_SORT_ROLE, preset.duration_seconds)
            self.table.setItem(row, self.COL_DURATION, dur_item)

            rating = max(preset.star_rating or 0, task_ratings.get(preset.name, 0))
            rating = max(0, min(5, rating))
            star_item = _SortItem("★" * rating if rating else "—")
            star_item.setData(_SORT_ROLE, rating)
            if rating:
                star_item.setForeground(QColor("#FFB800"))
            self.table.setItem(row, self.COL_STARS, star_item)

            count_item = _SortItem(f"{preset.use_count}次" if preset.use_count else "—")
            count_item.setData(_SORT_ROLE, preset.use_count)
            self.table.setItem(row, self.COL_USE_COUNT, count_item)

            last_text, last_key = self._format_last_used(preset.last_used_at)
            last_item = _SortItem(last_text)
            last_item.setData(_SORT_ROLE, last_key)
            self.table.setItem(row, self.COL_LAST_USED, last_item)

        self.table.setSortingEnabled(True)
        self._apply_filters()

    @staticmethod
    def _format_last_used(last_used_at: Optional[str]):
        """Return (display text, numeric sort key) for a last-used timestamp."""
        if not last_used_at:
            return "—", 0
        try:
            dt = datetime.fromisoformat(last_used_at)
            return dt.strftime("%Y-%m-%d %H:%M"), dt.timestamp()
        except (ValueError, TypeError):
            return "—", 0

    def _apply_filters(self):
        """Hide rows that don't match the search keywords / category filter."""
        keywords = self.search_input.text().strip().lower().split()
        cat_id = self.category_filter.currentData()

        visible = 0
        for row in range(self.table.rowCount()):
            preset = self._preset_at_row(row)
            if preset is None:
                continue
            name_lower = preset.name.lower()
            match = all(kw in name_lower for kw in keywords)
            if match and cat_id is not None:
                match = preset.category_id == cat_id
            self.table.setRowHidden(row, not match)
            if match:
                visible += 1

        total = self.table.rowCount()
        if visible == total:
            self.count_label.setText(f"共 {total} 个预设")
        else:
            self.count_label.setText(f"显示 {visible} / {total} 个预设")

    def _preset_at_row(self, row: int) -> Optional[Preset]:
        item = self.table.item(row, self.COL_NAME)
        if item is None:
            return None
        return self._presets_by_id.get(item.data(_ID_ROLE))

    def _selected_presets(self) -> List[Preset]:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        return [p for p in (self._preset_at_row(r) for r in rows) if p is not None]

    # --- Actions ---

    def _on_double_clicked(self, row: int, _column: int):
        preset = self._preset_at_row(row)
        if preset:
            self._edit_notebook(preset)

    def _edit_notebook(self, preset: Preset):
        """Open the rich-text notebook editor for this preset's task name."""
        db = getattr(self.preset_manager, 'db', None)
        if db is None:
            return
        dialog = TaskNotebookDialog(db, preset.name, self._dark_mode, self)
        dialog.exec()

    def _edit_current(self):
        selected = self._selected_presets()
        if not selected:
            QMessageBox.information(self, "编辑预设", "请先选择一个预设。")
            return
        self._edit_preset(selected[0])

    def _edit_preset(self, preset: Preset):
        dialog = EditPresetDialog(preset, self.categories, self, dark_mode=self._dark_mode)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                preset.name = result['name']
                preset.duration_seconds = result['duration_seconds']
                preset.category_id = result['category_id']
                preset.star_rating = result.get('star_rating', 0)
                self.preset_manager.update(preset)
                self._reload()
                self.presets_changed.emit()

    def _delete_selected(self):
        selected = self._selected_presets()
        if not selected:
            QMessageBox.information(self, "删除预设", "请先选择要删除的预设。")
            return

        deletable = [p for p in selected if not p.is_default]
        locked = len(selected) - len(deletable)
        if not deletable:
            QMessageBox.warning(self, "删除预设", "默认预设不可删除。")
            return

        msg = f"确定删除选中的 {len(deletable)} 个预设吗？"
        if locked:
            msg += f"\n（{locked} 个默认预设将被跳过）"
        confirm = QMessageBox.question(
            self, "删除预设", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for preset in deletable:
            self.preset_manager.delete(preset.id)
        self._reload()
        self.presets_changed.emit()

    def _set_category_for_selected(self, category: Category):
        selected = self._selected_presets()
        if not selected:
            return
        for preset in selected:
            preset.category_id = category.id
            self.preset_manager.update(preset)
        self._reload()
        self.presets_changed.emit()

    def _show_context_menu(self, pos):
        selected = self._selected_presets()
        if not selected:
            return

        menu = QMenu(self)
        edit_action = menu.addAction("编辑预设")
        edit_action.setEnabled(len(selected) == 1)
        notebook_action = menu.addAction("编辑笔记本")
        notebook_action.setEnabled(len(selected) == 1)

        cat_menu = menu.addMenu(f"设置分类（{len(selected)} 项）")
        for cat in self.categories:
            action = cat_menu.addAction(f"{cat.icon} {cat.name}")
            action.triggered.connect(lambda _=False, c=cat: self._set_category_for_selected(c))

        menu.addSeparator()
        delete_action = menu.addAction(f"删除选中（{len(selected)} 项）")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == edit_action:
            self._edit_preset(selected[0])
        elif action == notebook_action:
            self._edit_notebook(selected[0])
        elif action == delete_action:
            self._delete_selected()

    # --- Theme ---

    def _apply_theme(self):
        if self._dark_mode:
            bg = "#2c2c2e"
            text = "#ffffff"
            secondary = "#98989d"
            input_bg = "#3a3a3c"
            border = "#48484a"
            focus = "#0a84ff"
            row_alt = "#333335"
            header_bg = "#3a3a3c"
            selection_bg = "#0a84ff"
            btn_bg = "#3a3a3c"
            btn_hover = "#48484a"
        else:
            bg = "#ffffff"
            text = "#1d1d1f"
            secondary = "#6e6e73"
            input_bg = "#f5f5f7"
            border = "#d2d2d7"
            focus = "#007AFF"
            row_alt = "#f5f5f7"
            header_bg = "#f5f5f7"
            selection_bg = "#007AFF"
            btn_bg = "#f5f5f7"
            btn_hover = "#e5e5ea"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
            }}
            QLabel {{
                color: {text};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#hintLabel {{
                color: {secondary};
                font-size: 12px;
            }}
            QLineEdit {{
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
                background-color: {input_bg};
                color: {text};
            }}
            QLineEdit:focus {{
                border-color: {focus};
            }}
            QComboBox {{
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
                background-color: {input_bg};
                color: {text};
            }}
            QTableWidget {{
                border: 1px solid {border};
                border-radius: 8px;
                background-color: {bg};
                alternate-background-color: {row_alt};
                color: {text};
                font-size: 13px;
                selection-background-color: {selection_bg};
                selection-color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {text};
                border: none;
                border-bottom: 1px solid {border};
                padding: 6px 8px;
                font-size: 12px;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 13px;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#dangerButton {{
                color: #ff3b30;
            }}
        """)
