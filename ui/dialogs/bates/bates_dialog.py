# ~/Desktop/acropdf/ui/dialogs/bates/bates_dialog.py
"""
Bates 編號對話框。

為法律文件批次插入 Bates 編號（頁碼戳記），支援：
  - 自訂前綴 / 後綴
  - 起始編號與位數
  - 六種位置（上左/上中/上右/下左/下中/下右）
  - 字體大小調整
  - 全部頁面或自訂頁碼範圍
  - 即時預覽格式
"""
from __future__ import annotations

from typing import List, Optional

import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox,
    QRadioButton, QButtonGroup, QGroupBox,
    QDialogButtonBox, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# 位置名稱 → (水平對齊, 垂直區域)
_POSITION_MAP = {
    "上左": ("left",   "top"),
    "上中": ("center", "top"),
    "上右": ("right",  "top"),
    "下左": ("left",   "bottom"),
    "下中": ("center", "bottom"),
    "下右": ("right",  "bottom"),
}


class BatesDialog(QDialog):
    """Bates 編號插入對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("Bates 編號")
        self.resize(460, 420)
        self._setup_ui()
        self._update_preview()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 編號格式 ─────────────────────────────────────────────────
        fmt_grp = QGroupBox("編號格式")
        fmt_form = QFormLayout(fmt_grp)

        self._prefix = QLineEdit()
        self._prefix.setPlaceholderText("例如 ABC-")
        self._prefix.textChanged.connect(self._update_preview)
        fmt_form.addRow("前綴：", self._prefix)

        self._start_num = QSpinBox()
        self._start_num.setRange(0, 9_999_999)
        self._start_num.setValue(1)
        self._start_num.valueChanged.connect(self._update_preview)
        fmt_form.addRow("起始編號：", self._start_num)

        self._digits = QSpinBox()
        self._digits.setRange(4, 10)
        self._digits.setValue(6)
        self._digits.valueChanged.connect(self._update_preview)
        fmt_form.addRow("位數：", self._digits)

        self._suffix = QLineEdit()
        self._suffix.setPlaceholderText("（選填）")
        self._suffix.textChanged.connect(self._update_preview)
        fmt_form.addRow("後綴：", self._suffix)

        layout.addWidget(fmt_grp)

        # ── 位置與字體 ───────────────────────────────────────────────
        pos_grp = QGroupBox("位置與字體")
        pos_form = QFormLayout(pos_grp)

        self._position = QComboBox()
        self._position.addItems(list(_POSITION_MAP.keys()))
        self._position.setCurrentIndex(4)  # 預設：下中
        pos_form.addRow("位置：", self._position)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 24)
        self._font_size.setValue(10)
        self._font_size.setSuffix(" pt")
        pos_form.addRow("字體大小：", self._font_size)

        layout.addWidget(pos_grp)

        # ── 頁碼範圍 ─────────────────────────────────────────────────
        range_grp = QGroupBox("頁碼範圍")
        range_lay = QVBoxLayout(range_grp)

        self._range_all = QRadioButton(f"全部頁面（共 {self._doc.page_count} 頁）")
        self._range_custom = QRadioButton("自訂範圍：")
        self._range_all.setChecked(True)

        self._range_group = QButtonGroup(self)
        self._range_group.addButton(self._range_all)
        self._range_group.addButton(self._range_custom)

        range_lay.addWidget(self._range_all)

        custom_row = QHBoxLayout()
        custom_row.addWidget(self._range_custom)
        self._range_input = QLineEdit()
        self._range_input.setPlaceholderText("例如 1-5, 8, 10-12")
        self._range_input.setEnabled(False)
        custom_row.addWidget(self._range_input)
        range_lay.addLayout(custom_row)

        self._range_custom.toggled.connect(self._range_input.setEnabled)

        layout.addWidget(range_grp)

        # ── 預覽 ─────────────────────────────────────────────────────
        self._preview = QLabel()
        self._preview.setStyleSheet(
            "background: palette(base); padding: 8px; border-radius: 4px; "
            "font-family: monospace; font-size: 12px; color: palette(text);"
        )
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._preview)

        # ── 按鈕 ─────────────────────────────────────────────────────
        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="套用", cancel_text="取消")
        ok_btn.clicked.connect(self._apply)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

    # ----------------------------------------------------------- helpers
    def _format_bates(self, number: int) -> str:
        prefix = self._prefix.text()
        suffix = self._suffix.text()
        digits = self._digits.value()
        num_str = str(number).zfill(digits)
        return f"{prefix}{num_str}{suffix}"

    def _update_preview(self):
        start = self._start_num.value()
        example1 = self._format_bates(start)
        example2 = self._format_bates(start + 1)
        self._preview.setText(f"預覽：{example1}    {example2}    ...")

    def _parse_page_range(self) -> Optional[List[int]]:
        """解析頁碼範圍，回傳 0-based 頁碼列表。"""
        total = self._doc.page_count
        if self._range_all.isChecked():
            return list(range(total))

        text = self._range_input.text().strip()
        if not text:
            return None

        pages: list[int] = []
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                tokens = part.split("-", 1)
                try:
                    a, b = int(tokens[0].strip()), int(tokens[1].strip())
                except ValueError:
                    return None
                if a < 1 or b < a or b > total:
                    return None
                pages.extend(range(a - 1, b))
            else:
                try:
                    p = int(part)
                except ValueError:
                    return None
                if p < 1 or p > total:
                    return None
                pages.append(p - 1)
        return sorted(set(pages))

    def _compute_position(self, page: fitz.Page) -> fitz.Point:
        """根據選擇的位置回傳插入座標。"""
        rect = page.rect
        margin = 36  # 0.5 inch
        font_size = self._font_size.value()

        pos_name = self._position.currentText()
        h_align, v_area = _POSITION_MAP.get(pos_name, ("center", "bottom"))

        # 垂直位置
        if v_area == "top":
            y = margin + font_size
        else:
            y = rect.height - margin

        # 水平位置（粗估文字寬度用於置中/靠右）
        bates_text = self._format_bates(self._start_num.value())
        approx_width = len(bates_text) * font_size * 0.5

        if h_align == "left":
            x = margin
        elif h_align == "right":
            x = rect.width - margin - approx_width
        else:  # center
            x = (rect.width - approx_width) / 2

        return fitz.Point(max(margin, x), y)

    # ------------------------------------------------------------- apply
    def _apply(self):
        pages = self._parse_page_range()
        if pages is None:
            QMessageBox.warning(self, "錯誤", "頁碼範圍格式不正確。\n範例：1-5, 8, 10-12")
            return
        if not pages:
            QMessageBox.warning(self, "錯誤", "未選取任何頁面。")
            return

        font_size = self._font_size.value()
        current_num = self._start_num.value()

        try:
            self._doc.begin_op("Bates 編號")

            for page_idx in pages:
                page = self._doc.fitz_doc[page_idx]
                bates_text = self._format_bates(current_num)
                point = self._compute_position(page)

                page.insert_text(
                    point,
                    bates_text,
                    fontname="helv",
                    fontsize=font_size,
                    color=(0, 0, 0),
                )
                current_num += 1

            self._doc.end_op()
            self._doc._mark_modified()

            QMessageBox.information(
                self, "完成",
                f"已在 {len(pages)} 頁插入 Bates 編號。\n"
                f"範圍：{self._format_bates(self._start_num.value())} ~ "
                f"{self._format_bates(current_num - 1)}"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "失敗", f"插入 Bates 編號時發生錯誤：\n{e}")
