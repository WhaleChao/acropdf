# ~/Desktop/acropdf/ui/dialogs/text_box/text_box_dialog.py
"""
文字框插入對話框。
- 顯示從 PDF 偵測到的字體大小（可手動調整）
- 多行文字輸入
- 顯示選取範圍尺寸資訊
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QSpinBox, QPushButton,
    QDialogButtonBox, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class TextBoxDialog(QDialog):
    def __init__(self, font_size: float = 12,
                 rect_info: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("插入文字框")
        self.resize(420, 300)
        self._font_size = max(4, min(200, int(round(font_size))))
        self._rect_info = rect_info
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── 尺寸資訊提示 ─────────────────────────────────────────────
        if self._rect_info:
            info_lbl = QLabel(self._rect_info)
            info_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(info_lbl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #ddd;")
            layout.addWidget(sep)

        # ── 字體大小 row ──────────────────────────────────────────────
        size_row = QHBoxLayout()
        size_lbl = QLabel("字體大小：")
        size_row.addWidget(size_lbl)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(4, 200)
        self._size_spin.setValue(self._font_size)
        self._size_spin.setSuffix(" pt")
        self._size_spin.setFixedWidth(90)
        self._size_spin.valueChanged.connect(self._update_preview_font)
        size_row.addWidget(self._size_spin)

        detected_lbl = QLabel(f"（由頁面文字自動偵測：{self._font_size} pt）")
        detected_lbl.setStyleSheet("color: #888; font-size: 11px;")
        size_row.addWidget(detected_lbl)
        size_row.addStretch()
        layout.addLayout(size_row)

        # ── 文字輸入區 ───────────────────────────────────────────────
        layout.addWidget(QLabel("文字內容："))
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("請輸入要插入的文字…")
        self._text_edit.setMinimumHeight(120)
        self._update_preview_font(self._font_size)
        layout.addWidget(self._text_edit)

        # ── 按鈕 ─────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("插入")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._text_edit.setFocus()

    def _update_preview_font(self, size: int):
        """即時更新輸入區字體大小，讓使用者預覽效果。"""
        f = QFont()
        f.setPointSize(max(6, min(size, 36)))   # UI 內最大顯示 36pt
        self._text_edit.setFont(f)

    def get_result(self) -> tuple[str, int]:
        """回傳 (文字內容, 字體大小 pt)"""
        return self._text_edit.toPlainText(), self._size_spin.value()
