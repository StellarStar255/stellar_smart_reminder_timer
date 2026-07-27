"""Dialog offering a one-click upgrade to a newer release."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QApplication, QMessageBox
)

from src.core.update_checker import UpdateDownloader, launch_installer
from src.version import __version__


class UpdateDialog(QDialog):
    """Shows the new version + notes; 立即升级 downloads and installs."""

    def __init__(self, version: str, notes: str, asset_name: str,
                 asset_url: str, dark_mode: bool = False, parent=None):
        super().__init__(parent)
        self._asset_name = asset_name
        self._asset_url = asset_url
        self._downloader = None

        self.setWindowTitle("发现新版本")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel(f"🚀 新版本 v{version} 已发布")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(title)

        current = QLabel(f"当前版本 v{__version__} → 最新版本 v{version}")
        current.setStyleSheet("font-size: 13px; color: #6e6e73;")
        layout.addWidget(current)

        if notes.strip():
            notes_view = QTextEdit()
            notes_view.setReadOnly(True)
            notes_view.setPlainText(notes.strip())
            notes_view.setFixedHeight(140)
            layout.addWidget(notes_view)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #6e6e73;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.later_btn = QPushButton("稍后再说")
        self.later_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.later_btn)

        self.update_btn = QPushButton("立即升级")
        self.update_btn.setDefault(True)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #0066d6; }
            QPushButton:disabled { background-color: #9bbef5; }
        """)
        self.update_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.update_btn)

        layout.addLayout(btn_row)

    def _start_download(self):
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText(f"正在下载 {self._asset_name}…")
        self.status_label.show()

        self._downloader = UpdateDownloader(self._asset_url, self._asset_name, self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.finished_ok.connect(self._on_downloaded)
        self._downloader.failed.connect(self._on_failed)
        self._downloader.start()

    def _on_progress(self, percent: int):
        if percent < 0:
            self.progress_bar.setRange(0, 0)  # size unknown -> busy bar
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)

    def _on_downloaded(self, path: str):
        self.status_label.setText("下载完成，正在安装并重启…")
        error = launch_installer(path)
        if error:
            self._on_failed(error)
            return
        QApplication.quit()

    def _on_failed(self, message: str):
        self.progress_bar.hide()
        self.status_label.hide()
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        QMessageBox.warning(self, "升级失败", f"自动升级失败：{message}\n\n"
                            "可以稍后重试，或到 GitHub Releases 页面手动下载。")
