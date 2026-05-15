# ~/Desktop/acropdf/ui/dialogs/dependency_dialog.py
"""
啟動時自動顯示的依賴檢查對話框。
只有在有缺少的依賴時才會跳出來。
提供三種行動：自動安裝、開瀏覽器下載、略過。
"""
import sys
import webbrowser
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QProgressBar, QMessageBox, QCheckBox, QScrollArea,
    QWidget, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from core.dependency_manager import DependencyManager, Dependency, DepStatus

class InstallThread(QThread):
    """背景執行安裝，不阻塞 UI"""
    finished = pyqtSignal(str, bool, str)  # dep_name, success, message

    def __init__(self, dep: Dependency, manager: DependencyManager):
        super().__init__()
        self._dep = dep
        self._mgr = manager

    def run(self):
        success, msg = self._mgr.auto_install(self._dep)
        self.finished.emit(self._dep.name, success, msg)


class DependencyDialog(QDialog):
    """
    缺少依賴時自動彈出的對話框。
    列出所有缺少的項目，每項提供「自動安裝」和「手動下載」按鈕。
    """

    def __init__(self, missing_deps: list[Dependency], manager: DependencyManager,
                 parent=None):
        super().__init__(parent)
        self._missing = missing_deps
        self._mgr = manager
        self._install_threads: list[InstallThread] = []
        self.setWindowTitle("AcroPDF — 外部程式檢查")
        self.setMinimumWidth(550)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 標題
        title = QLabel("AcroPDF 偵測到以下程式尚未安裝：")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("安裝這些程式可以解鎖更多功能。標記「選用」的項目可以略過。")
        subtitle.setStyleSheet("color: #8e8e93;")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # 每個缺失依賴一個區塊
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self._dep_widgets: dict[str, dict] = {}

        for dep in self._missing:
            group = QGroupBox()
            group_layout = QVBoxLayout(group)

            # 名稱 + 狀態
            header = QHBoxLayout()
            name_label = QLabel(f"<b>{dep.name}</b>")
            name_label.setStyleSheet("font-size: 12pt;")
            status_label = QLabel(dep.status.value)
            if dep.required:
                status_label.setStyleSheet(
                    "color: white; background: #e74c3c; padding: 2px 8px; border-radius: 4px;")
            else:
                status_label.setStyleSheet(
                    "color: white; background: #f39c12; padding: 2px 8px; border-radius: 4px;")
            header.addWidget(name_label)
            header.addStretch()
            header.addWidget(status_label)
            group_layout.addLayout(header)

            # 用途說明
            purpose_label = QLabel(dep.purpose)
            purpose_label.setWordWrap(True)
            purpose_label.setStyleSheet("color: #8e8e93; margin-bottom: 4px;")
            group_layout.addWidget(purpose_label)

            # 安裝備註
            if dep.install_note:
                note_label = QLabel(f"💡 {dep.install_note}")
                note_label.setWordWrap(True)
                note_label.setStyleSheet("color: #007AFF; font-size: 10pt;")
                group_layout.addWidget(note_label)

            # 進度條
            progress = QProgressBar()
            progress.setRange(0, 0)  # indeterminate
            progress.hide()
            group_layout.addWidget(progress)

            # 結果訊息
            result_label = QLabel("")
            result_label.hide()
            group_layout.addWidget(result_label)

            # 按鈕列
            btn_row = QHBoxLayout()

            auto_btn = QPushButton("⚡ 自動安裝")
            auto_btn.setStyleSheet(
                "background: #27ae60; color: white; padding: 6px 16px; border-radius: 4px;")
            auto_btn.setToolTip(
                f"macOS: {dep.install_cmd_mac}\nWindows: {dep.install_cmd_win}")
            auto_btn.clicked.connect(
                lambda checked, d=dep: self._auto_install(d))

            download_btn = QPushButton("📥 手動下載")
            download_btn.setStyleSheet("padding: 6px 16px;")
            download_btn.clicked.connect(
                lambda checked, url=dep.download_url: webbrowser.open(url))

            skip_btn = QPushButton("略過")
            skip_btn.setStyleSheet("padding: 6px 16px; color: #8e8e93;")
            skip_btn.clicked.connect(lambda checked, g=group: g.hide())

            btn_row.addWidget(auto_btn)
            btn_row.addWidget(download_btn)
            if not dep.required:
                btn_row.addWidget(skip_btn)
            btn_row.addStretch()
            group_layout.addLayout(btn_row)

            scroll_layout.addWidget(group)

            self._dep_widgets[dep.name] = {
                "group": group,
                "auto_btn": auto_btn,
                "download_btn": download_btn,
                "progress": progress,
                "result_label": result_label,
                "status_label": status_label,
            }

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # 底部按鈕
        bottom = QHBoxLayout()

        self._dont_show = QCheckBox("不再提醒（下次啟動不檢查）")
        bottom.addWidget(self._dont_show)

        bottom.addStretch()

        close_btn = QPushButton("繼續使用 AcroPDF")
        close_btn.setStyleSheet(
            "background: #3498db; color: white; padding: 8px 24px; "
            "border-radius: 4px; font-size: 11pt;")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _auto_install(self, dep: Dependency):
        widgets = self._dep_widgets[dep.name]
        widgets["auto_btn"].setEnabled(False)
        widgets["auto_btn"].setText("安裝中...")
        widgets["progress"].show()
        widgets["result_label"].hide()

        thread = InstallThread(dep, self._mgr)
        thread.finished.connect(self._on_install_finished)
        self._install_threads.append(thread)
        thread.start()

    def _on_install_finished(self, dep_name: str, success: bool, message: str):
        widgets = self._dep_widgets.get(dep_name)
        if not widgets:
            return

        widgets["progress"].hide()

        if success:
            widgets["result_label"].setText(f"✅ {message}")
            widgets["result_label"].setStyleSheet("color: #27ae60; font-weight: bold;")
            widgets["auto_btn"].setText("✅ 已安裝")
            widgets["auto_btn"].setEnabled(False)
            widgets["status_label"].setText("已安裝")
            widgets["status_label"].setStyleSheet(
                "color: white; background: #27ae60; padding: 2px 8px; border-radius: 4px;")
        else:
            widgets["result_label"].setText(f"❌ {message}")
            widgets["result_label"].setStyleSheet("color: #e74c3c;")
            widgets["auto_btn"].setText("重試自動安裝")
            widgets["auto_btn"].setEnabled(True)

        widgets["result_label"].show()

    @property
    def dont_show_again(self) -> bool:
        return self._dont_show.isChecked()
