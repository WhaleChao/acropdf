# ~/Desktop/acropdf/ui/dialogs/custom_stamp/custom_stamp_dialog.py
"""
自訂圖章管理對話框。

功能：
  - 以格狀檢視顯示使用者自訂圖章
  - 新增圖章（PNG / JPG / SVG）
  - 刪除已選圖章
  - 預覽已選圖章
  - 確認後回傳所選圖章路徑
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QDialogButtonBox, QFileDialog, QMessageBox,
    QGroupBox, QSplitter,
)
from PyQt6.QtCore import Qt, QSize, QSettings
from PyQt6.QtGui import QPixmap, QIcon, QImage


_SETTINGS_KEY = "custom_stamps/paths"
_ICON_SIZE = 96
_SUPPORTED_FORMATS = "圖片檔 (*.png *.jpg *.jpeg *.svg *.bmp *.tiff)"


class CustomStampDialog(QDialog):
    """自訂圖章管理對話框。選取圖章後以 get_stamp_path() 取得路徑。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_path: str | None = None
        self._settings = QSettings()

        self.setWindowTitle("自訂圖章管理")
        self.resize(660, 480)
        self._setup_ui()
        self._load_stamps()

    # ── UI 建構 ───────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左側：圖章清單 ───────────────────────────────────────
        left = QGroupBox("圖章集合")
        left_layout = QVBoxLayout(left)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setSpacing(8)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._list, 1)

        # 新增 / 刪除按鈕
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("新增圖章")
        self._btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton("刪除圖章")
        self._btn_remove.setEnabled(False)
        self._btn_remove.clicked.connect(self._on_remove)
        btn_row.addWidget(self._btn_remove)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # ── 右側：預覽 ───────────────────────────────────────────
        right = QGroupBox("預覽")
        right_layout = QVBoxLayout(right)

        self._preview = QLabel("尚未選取圖章")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(200, 200)
        self._preview.setStyleSheet(
            "QLabel { background: palette(base); border: 1px solid #8e8e93; border-radius: 4px; }"
        )
        right_layout.addWidget(self._preview, 1)

        self._path_label = QLabel("")
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("color: #8e8e93; font-size: 11px;")
        right_layout.addWidget(self._path_label)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        # ── 底部按鈕 ─────────────────────────────────────────────
        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="確定", cancel_text="取消")
        ok_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

    # ── 載入 / 儲存設定 ──────────────────────────────────────────
    def _saved_paths(self) -> list[str]:
        raw = self._settings.value(_SETTINGS_KEY, [])
        if isinstance(raw, str):
            return [raw] if raw else []
        return list(raw) if raw else []

    def _persist_paths(self, paths: list[str]):
        self._settings.setValue(_SETTINGS_KEY, paths)

    def _load_stamps(self):
        self._list.clear()
        for p in self._saved_paths():
            if os.path.isfile(p):
                self._add_item(p)

    def _add_item(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            icon = QIcon()
        else:
            icon = QIcon(pixmap.scaled(
                _ICON_SIZE, _ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        item = QListWidgetItem(icon, Path(path).stem)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        item.setSizeHint(QSize(_ICON_SIZE + 20, _ICON_SIZE + 30))
        self._list.addItem(item)

    # ── 事件處理 ─────────────────────────────────────────────────
    def _on_selection_changed(self, current: QListWidgetItem | None, _prev):
        has_sel = current is not None
        self._btn_remove.setEnabled(has_sel)

        if not has_sel:
            self._preview.setText("尚未選取圖章")
            self._path_label.setText("")
            return

        path = current.data(Qt.ItemDataRole.UserRole)
        self._path_label.setText(path)

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._preview.setText("無法載入預覽")
        else:
            scaled = pixmap.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview.setPixmap(scaled)

    def _on_add(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇圖章圖片", "", _SUPPORTED_FORMATS,
        )
        if not paths:
            return

        existing = self._saved_paths()
        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p not in existing:
                existing.append(abs_p)
                self._add_item(abs_p)
        self._persist_paths(existing)

    def _on_remove(self):
        item = self._list.currentItem()
        if item is None:
            return

        path = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "刪除圖章",
            f"確定要從集合中移除此圖章嗎？\n{Path(path).name}\n\n（不會刪除原始檔案）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        row = self._list.row(item)
        self._list.takeItem(row)

        existing = self._saved_paths()
        if path in existing:
            existing.remove(path)
        self._persist_paths(existing)

    def _on_accept(self):
        item = self._list.currentItem()
        if item is not None:
            self._selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    # ── 公開介面 ─────────────────────────────────────────────────
    def get_stamp_path(self) -> str | None:
        """取得使用者選取的圖章路徑，若未選取或取消則回傳 None。"""
        return self._selected_path
