# ~/Desktop/acropdf/ui/panels/file_browser_panel.py
"""
案件資料夾面板 — 顯示任意根目錄的資料夾樹（預設 Synology Drive），
點擊 PDF / 圖片即可在主視窗開啟。
支援 macOS / Windows。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QLabel,
    QPushButton, QFileDialog, QMenu, QToolButton, QSizePolicy,
    QFrame,
)
from PyQt6.QtCore import (
    Qt, QDir, QModelIndex, pyqtSignal, QSortFilterProxyModel,
)
from PyQt6.QtGui import QFileSystemModel, QAction

# ── 常數 ──────────────────────────────────────────────────────────
_OPENABLE_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".tiff", ".tif"}
_SKIP_DIR_NAMES = {"OCR", "cache", "#recycle", "$RECYCLE.BIN", "System Volume Information"}

_IS_WINDOWS = platform.system() == "Windows"
_IS_MAC     = platform.system() == "Darwin"


def _synology_drive_path() -> str | None:
    """回傳 Synology Drive 本機同步資料夾（跨平台）。"""
    home = Path.home()
    candidates = [
        home / "SynologyDrive",
        # Windows 常見安裝路徑
        home / "Synology Drive",
        Path("C:/Users") / home.name / "SynologyDrive",
    ]
    for p in candidates:
        if p.is_dir():
            return str(p)
    return None


def _default_root() -> str:
    """決定預設根目錄：Synology Drive > home。"""
    synology = _synology_drive_path()
    # 優先用 SynologyDrive/01_案件
    if synology:
        cases = Path(synology) / "01_案件"
        if cases.is_dir():
            return str(cases)
        return synology
    return str(Path.home())


_DEFAULT_ROOT = _default_root()


def _reveal_in_file_manager(path: str):
    """在檔案管理員中顯示檔案（跨平台）。"""
    try:
        if _IS_MAC:
            subprocess.run(["open", "-R", path], check=False)
        elif _IS_WINDOWS:
            subprocess.run(["explorer", "/select,", path], check=False)
        else:
            # Linux：嘗試 xdg-open 開啟父目錄
            parent = str(Path(path).parent)
            subprocess.run(["xdg-open", parent], check=False)
    except Exception:
        pass


# ── 過濾 Proxy ────────────────────────────────────────────────────

class _CaseFilterProxy(QSortFilterProxyModel):
    """只顯示資料夾與可開啟的檔案類型，隱藏系統 / 快取目錄。"""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src  = self.sourceModel()
        idx  = src.index(source_row, 0, source_parent)
        name = src.fileName(idx)

        if src.isDir(idx):
            # 跳過隱藏目錄（. 或 _ 開頭）、系統目錄
            if name.startswith(".") or name.startswith("_"):
                return False
            if name in _SKIP_DIR_NAMES:
                return False
            return True

        # 檔案：只顯示可開啟的副檔名
        ext = Path(name).suffix.lower()
        return ext in _OPENABLE_EXTS


# ── 主面板 ────────────────────────────────────────────────────────

class FileBrowserPanel(QWidget):
    """左側資料夾瀏覽面板。"""

    file_open_requested = pyqtSignal(str)  # 傳出要開啟的完整路徑

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._root   = self._load_root()
        self._setup_ui()
        self._set_root(self._root)

    # ── 根目錄持久化 ──────────────────────────────────────────────

    def _load_root(self) -> str:
        if self._config:
            saved = self._config.get("file_browser_root", "") or ""
            if saved and os.path.isdir(saved):
                return saved
        return _DEFAULT_ROOT

    def _save_root(self, path: str):
        self._root = path
        if self._config:
            self._config.set("file_browser_root", path)

    # ── UI 建置 ──────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        # ── 頂部工具列 ──
        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 4, 0)
        top.setSpacing(2)

        self._root_label = QLabel()
        self._root_label.setWordWrap(False)
        self._root_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._root_label.setProperty("role", "muted")
        top.addWidget(self._root_label)

        btn_refresh = QToolButton()
        btn_refresh.setText("↺")
        btn_refresh.setToolTip("重新整理")
        btn_refresh.setFixedSize(22, 22)
        btn_refresh.clicked.connect(self._refresh)
        top.addWidget(btn_refresh)

        btn_root = QToolButton()
        btn_root.setText("…")
        btn_root.setToolTip("選擇資料夾")
        btn_root.setFixedSize(22, 22)
        btn_root.clicked.connect(self._change_root)
        top.addWidget(btn_root)

        layout.addLayout(top)

        # ── 分隔線 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        # ── 檔案系統 Model + Proxy ──
        self._fs_model = QFileSystemModel()
        self._fs_model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self._fs_model.setReadOnly(True)
        # QFileSystemModel 非同步載入：目錄讀完後重新套 rootIndex
        self._fs_model.directoryLoaded.connect(self._on_directory_loaded)

        self._proxy = _CaseFilterProxy()
        self._proxy.setSourceModel(self._fs_model)
        self._proxy.setRecursiveFilteringEnabled(True)

        # ── TreeView ──
        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(True)
        for col in range(1, 4):
            self._tree.hideColumn(col)
        self._tree.setAnimated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.activated.connect(self._on_double_click)
        layout.addWidget(self._tree)

        # ── 底部快捷按鈕列 ──
        bottom = QVBoxLayout()
        bottom.setContentsMargins(4, 2, 4, 4)
        bottom.setSpacing(2)

        # 「選擇資料夾」永遠顯示
        btn_choose = QPushButton("📂  選擇資料夾…")
        btn_choose.setFlat(True)
        btn_choose.setStyleSheet("text-align: left; padding: 2px 6px; font-size: 11px;")
        btn_choose.setToolTip("選擇任意資料夾作為根目錄")
        btn_choose.clicked.connect(self._change_root)
        bottom.addWidget(btn_choose)

        # 有 Synology Drive 才顯示捷徑
        synology = _synology_drive_path()
        if synology:
            btn_synology = QPushButton("☁  Synology Drive")
            btn_synology.setFlat(True)
            btn_synology.setStyleSheet("text-align: left; padding: 2px 6px; font-size: 11px;")
            btn_synology.setToolTip(synology)
            btn_synology.clicked.connect(lambda: self._jump_to(synology))
            bottom.addWidget(btn_synology)

        layout.addLayout(bottom)

    # ── 根目錄操作 ────────────────────────────────────────────────

    def _set_root(self, path: str):
        self._root = path
        root_src_idx = self._fs_model.setRootPath(path)
        proxy_idx    = self._proxy.mapFromSource(root_src_idx)
        self._tree.setRootIndex(proxy_idx)
        self._update_label(path)

    def _update_label(self, path: str):
        home    = str(Path.home())
        display = path.replace(home, "~") if path.startswith(home) else path
        # Windows：把反斜線換成正斜線顯示
        display = display.replace("\\", "/")
        self._root_label.setText(display)
        self._root_label.setToolTip(path)

    def _change_root(self):
        """開啟資料夾選擇對話框，可選任意根目錄。"""
        start = self._root if os.path.isdir(self._root) else str(Path.home())
        new_dir = QFileDialog.getExistingDirectory(
            self, "選擇資料夾", start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if new_dir:
            self._save_root(new_dir)
            self._set_root(new_dir)

    def _jump_to(self, path: str):
        """跳到指定路徑（不存在則忽略）。"""
        if os.path.isdir(path):
            self._save_root(path)
            self._set_root(path)

    def _go_synology(self):
        synology = _synology_drive_path()
        if synology:
            self._jump_to(synology)

    def _on_directory_loaded(self, path: str):
        """QFileSystemModel 非同步讀完目錄後，重新套 rootIndex 讓樹狀更新。"""
        try:
            if os.path.normpath(path) == os.path.normpath(self._root):
                src_idx   = self._fs_model.index(self._root)
                proxy_idx = self._proxy.mapFromSource(src_idx)
                self._tree.setRootIndex(proxy_idx)
        except Exception:
            pass

    def _refresh(self):
        # 先重設為空路徑再回來，強制 model 重新掃描
        self._fs_model.setRootPath("")
        self._set_root(self._root)

    # ── 事件 ─────────────────────────────────────────────────────

    def _on_double_click(self, proxy_idx: QModelIndex):
        src_idx = self._proxy.mapToSource(proxy_idx)
        if self._fs_model.isDir(src_idx):
            if self._tree.isExpanded(proxy_idx):
                self._tree.collapse(proxy_idx)
            else:
                self._tree.expand(proxy_idx)
            return
        path = self._fs_model.filePath(src_idx)
        if Path(path).suffix.lower() in _OPENABLE_EXTS:
            self.file_open_requested.emit(path)

    def _context_menu(self, pos):
        proxy_idx = self._tree.indexAt(pos)
        src_idx   = self._proxy.mapToSource(proxy_idx) if proxy_idx.isValid() else QModelIndex()
        menu      = QMenu(self)

        if proxy_idx.isValid():
            path = self._fs_model.filePath(src_idx)

            if not self._fs_model.isDir(src_idx):
                act_open = QAction("開啟", self)
                act_open.triggered.connect(lambda: self.file_open_requested.emit(path))
                menu.addAction(act_open)
                menu.addSeparator()

            label = "在 Finder 中顯示" if _IS_MAC else "在檔案總管中顯示"
            act_reveal = QAction(label, self)
            act_reveal.triggered.connect(lambda: _reveal_in_file_manager(path))
            menu.addAction(act_reveal)

            if self._fs_model.isDir(src_idx):
                menu.addSeparator()
                act_set_root = QAction("設為根資料夾", self)
                act_set_root.triggered.connect(
                    lambda: (self._save_root(path), self._set_root(path))
                )
                menu.addAction(act_set_root)

        menu.addSeparator()
        act_change = QAction("選擇資料夾…", self)
        act_change.triggered.connect(self._change_root)
        menu.addAction(act_change)

        act_refresh = QAction("重新整理", self)
        act_refresh.triggered.connect(self._refresh)
        menu.addAction(act_refresh)

        menu.exec(self._tree.viewport().mapToGlobal(pos))
