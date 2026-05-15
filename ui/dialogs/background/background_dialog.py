# ~/Desktop/acropdf/ui/dialogs/background/background_dialog.py
"""
頁面背景設定對話框。

支援兩種背景模式：
  - 純色背景：透過色彩選擇器設定顏色與透明度
  - 圖片背景：選擇圖片檔案，支援填滿/適合/自訂縮放模式
"""
from __future__ import annotations

import os
from typing import List, Optional

import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton,
    QTabWidget, QWidget, QSlider, QGroupBox,
    QRadioButton, QButtonGroup, QComboBox,
    QDialogButtonBox, QMessageBox, QFileDialog,
    QColorDialog, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette


class BackgroundDialog(QDialog):
    """頁面背景設定對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._chosen_color: QColor = QColor(255, 255, 255)
        self._image_path: str = ""
        self.setWindowTitle("頁面背景")
        self.resize(480, 440)
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 分頁 ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_color_tab(), "純色背景")
        self._tabs.addTab(self._build_image_tab(), "圖片背景")
        layout.addWidget(self._tabs)

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

        # ── 按鈕 ─────────────────────────────────────────────────────
        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="套用", cancel_text="取消")
        ok_btn.clicked.connect(self._apply)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

    # ── 純色分頁 ─────────────────────────────────────────────────────
    def _build_color_tab(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        lay.setSpacing(12)

        # 色彩選擇
        color_row = QHBoxLayout()
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(60, 30)
        self._update_color_preview()
        color_row.addWidget(self._color_preview)

        pick_btn = QPushButton("選擇顏色...")
        pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(pick_btn)
        color_row.addStretch()
        lay.addRow("背景色：", color_row)

        # 透明度
        opacity_row = QHBoxLayout()
        self._color_opacity = QSlider(Qt.Orientation.Horizontal)
        self._color_opacity.setRange(0, 100)
        self._color_opacity.setValue(100)
        self._color_opacity_label = QLabel("100%")
        self._color_opacity.valueChanged.connect(
            lambda v: self._color_opacity_label.setText(f"{v}%")
        )
        opacity_row.addWidget(self._color_opacity)
        opacity_row.addWidget(self._color_opacity_label)
        lay.addRow("不透明度：", opacity_row)

        return w

    # ── 圖片分頁 ─────────────────────────────────────────────────────
    def _build_image_tab(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        lay.setSpacing(12)

        # 檔案選擇
        file_row = QHBoxLayout()
        self._image_label = QLabel("（尚未選擇）")
        self._image_label.setStyleSheet("color: #8e8e93;")
        file_row.addWidget(self._image_label, 1)

        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._pick_image)
        file_row.addWidget(browse_btn)
        lay.addRow("圖片檔案：", file_row)

        # 縮放模式
        self._scale_mode = QComboBox()
        self._scale_mode.addItems(["填滿", "適合", "自訂"])
        self._scale_mode.currentIndexChanged.connect(self._on_scale_mode_changed)
        lay.addRow("縮放模式：", self._scale_mode)

        # 自訂比例
        self._custom_scale = QDoubleSpinBox()
        self._custom_scale.setRange(10.0, 500.0)
        self._custom_scale.setValue(100.0)
        self._custom_scale.setSuffix(" %")
        self._custom_scale.setEnabled(False)
        lay.addRow("自訂比例：", self._custom_scale)

        # 透明度
        opacity_row = QHBoxLayout()
        self._image_opacity = QSlider(Qt.Orientation.Horizontal)
        self._image_opacity.setRange(0, 100)
        self._image_opacity.setValue(100)
        self._image_opacity_label = QLabel("100%")
        self._image_opacity.valueChanged.connect(
            lambda v: self._image_opacity_label.setText(f"{v}%")
        )
        opacity_row.addWidget(self._image_opacity)
        opacity_row.addWidget(self._image_opacity_label)
        lay.addRow("不透明度：", opacity_row)

        return w

    # ----------------------------------------------------------- helpers
    def _update_color_preview(self):
        self._color_preview.setStyleSheet(
            f"background-color: {self._chosen_color.name()}; "
            f"border: 1px solid #999; border-radius: 3px;"
        )

    def _pick_color(self):
        color = QColorDialog.getColor(self._chosen_color, self, "選擇背景色")
        if color.isValid():
            self._chosen_color = color
            self._update_color_preview()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇背景圖片", "",
            "圖片檔案 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif);;所有檔案 (*)",
        )
        if path:
            self._image_path = path
            basename = os.path.basename(path)
            self._image_label.setText(basename)
            self._image_label.setStyleSheet("color: palette(text);")

    def _on_scale_mode_changed(self, index: int):
        self._custom_scale.setEnabled(index == 2)  # 自訂

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

    def _compute_image_rect(self, page: fitz.Page) -> fitz.Rect:
        """根據縮放模式計算圖片目標矩形。"""
        page_rect = page.rect
        mode = self._scale_mode.currentText()

        if mode == "填滿":
            return page_rect

        if mode == "自訂":
            scale = self._custom_scale.value() / 100.0
            w = page_rect.width * scale
            h = page_rect.height * scale
            cx = page_rect.width / 2
            cy = page_rect.height / 2
            return fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

        # 適合：保持圖片原始比例，置中
        try:
            img_doc = fitz.open(self._image_path)
            # 讀取第一頁（圖片）的尺寸
            img_page = img_doc[0]
            img_w, img_h = img_page.rect.width, img_page.rect.height
            img_doc.close()
        except Exception:
            return page_rect

        pw, ph = page_rect.width, page_rect.height
        ratio_w = pw / img_w
        ratio_h = ph / img_h
        ratio = min(ratio_w, ratio_h)

        fit_w = img_w * ratio
        fit_h = img_h * ratio
        cx, cy = pw / 2, ph / 2
        return fitz.Rect(cx - fit_w / 2, cy - fit_h / 2,
                         cx + fit_w / 2, cy + fit_h / 2)

    # ------------------------------------------------------------- apply
    def _apply(self):
        pages = self._parse_page_range()
        if pages is None:
            QMessageBox.warning(self, "錯誤", "頁碼範圍格式不正確。\n範例：1-5, 8, 10-12")
            return
        if not pages:
            QMessageBox.warning(self, "錯誤", "未選取任何頁面。")
            return

        is_color = self._tabs.currentIndex() == 0

        if not is_color and not self._image_path:
            QMessageBox.warning(self, "錯誤", "請先選擇背景圖片。")
            return

        if not is_color and not os.path.isfile(self._image_path):
            QMessageBox.warning(self, "錯誤", f"圖片檔案不存在：\n{self._image_path}")
            return

        try:
            self._doc.begin_op("頁面背景")

            if is_color:
                self._apply_color_bg(pages)
            else:
                self._apply_image_bg(pages)

            self._doc.end_op()
            self._doc._mark_modified()

            mode_name = "純色" if is_color else "圖片"
            QMessageBox.information(
                self, "完成",
                f"已在 {len(pages)} 頁套用{mode_name}背景。"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "失敗", f"套用背景時發生錯誤：\n{e}")

    def _apply_color_bg(self, pages: List[int]):
        """在指定頁面繪製純色背景矩形。"""
        r = self._chosen_color.redF()
        g = self._chosen_color.greenF()
        b = self._chosen_color.blueF()
        opacity = self._color_opacity.value() / 100.0

        for page_idx in pages:
            page = self._doc.fitz_doc[page_idx]
            shape = page.new_shape()
            shape.draw_rect(page.rect)
            shape.finish(
                color=None,
                fill=(r, g, b),
                fill_opacity=opacity,
            )
            shape.insert_text(fitz.Point(0, 0), "", overlay=False)
            shape.commit(overlay=False)

    def _apply_image_bg(self, pages: List[int]):
        """在指定頁面插入圖片背景（置於內容之下）。"""
        opacity = self._image_opacity.value() / 100.0

        for page_idx in pages:
            page = self._doc.fitz_doc[page_idx]
            target_rect = self._compute_image_rect(page)

            page.insert_image(
                target_rect,
                filename=self._image_path,
                overlay=False,
                alpha=int(opacity * 255) if opacity < 1.0 else -1,
            )
