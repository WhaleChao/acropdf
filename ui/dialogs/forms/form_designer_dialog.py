# ~/Desktop/acropdf/ui/dialogs/forms/form_designer_dialog.py
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QFormLayout, QLineEdit, QDoubleSpinBox,
    QCheckBox, QComboBox, QSplitter, QWidget,
    QScrollArea, QMessageBox, QSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage


def _render_page(fitz_doc: fitz.Document, page_num: int, zoom: float = 1.2) -> QPixmap:
    if fitz_doc is None or page_num >= fitz_doc.page_count:
        return QPixmap()
    mat = fitz.Matrix(zoom, zoom)
    pix = fitz_doc[page_num].get_pixmap(matrix=mat, alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)


class FormDesignerDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._current_page = 0
        self._selected_type = "text"
        self.setWindowTitle("表單設計器")
        self.resize(1000, 700)
        self._setup_ui()
        self._refresh_fields()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        # ── 左側工具列 ────────────────────────────────────────────
        left = QGroupBox("欄位類型")
        left.setMaximumWidth(160)
        left_l = QVBoxLayout(left)
        self._type_btns: dict[str, QPushButton] = {}
        for key, label in [
            ("text", "文字欄位"),
            ("checkbox", "核取方塊"),
            ("radio", "選項按鈕"),
            ("combo", "下拉選單"),
            ("list", "清單方塊"),
            ("button", "按鈕"),
            ("signature", "簽名欄位"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._set_type(k))
            left_l.addWidget(btn)
            self._type_btns[key] = btn
        left_l.addStretch()
        layout.addWidget(left)

        # ── 中央頁面預覽 ──────────────────────────────────────────
        center = QWidget()
        center_l = QVBoxLayout(center)
        page_nav = QHBoxLayout()
        prev_btn = QPushButton("← 上一頁")
        prev_btn.clicked.connect(self._prev_page)
        self._page_lbl = QLabel("第 1 頁")
        next_btn = QPushButton("下一頁 →")
        next_btn.clicked.connect(self._next_page)
        page_nav.addWidget(prev_btn)
        page_nav.addWidget(self._page_lbl)
        page_nav.addWidget(next_btn)
        center_l.addLayout(page_nav)

        self._scroll = QScrollArea()
        self._page_lbl_img = QLabel()
        self._page_lbl_img.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._page_lbl_img)
        self._scroll.setWidgetResizable(True)
        center_l.addWidget(self._scroll)

        add_btn = QPushButton("在頁面中央新增選取類型的欄位")
        add_btn.clicked.connect(self._add_field_center)
        center_l.addWidget(add_btn)
        layout.addWidget(center, stretch=2)

        # ── 右側屬性面板 ──────────────────────────────────────────
        right = QGroupBox("欄位清單 / 屬性")
        right.setMinimumWidth(240)
        right_l = QVBoxLayout(right)

        self._field_list = QListWidget()
        self._field_list.currentRowChanged.connect(self._on_field_selected)
        right_l.addWidget(QLabel("欄位清單："))
        right_l.addWidget(self._field_list)

        prop_box = QGroupBox("屬性")
        prop_form = QFormLayout(prop_box)
        self._prop_name = QLineEdit()
        prop_form.addRow("名稱：", self._prop_name)
        self._prop_value = QLineEdit()
        prop_form.addRow("預設值：", self._prop_value)
        self._prop_fontsize = QDoubleSpinBox()
        self._prop_fontsize.setRange(4, 72)
        self._prop_fontsize.setValue(11)
        prop_form.addRow("字型大小：", self._prop_fontsize)
        self._prop_required = QCheckBox("必填")
        prop_form.addRow("", self._prop_required)
        right_l.addWidget(prop_box)

        apply_prop_btn = QPushButton("套用屬性")
        apply_prop_btn.clicked.connect(self._apply_properties)
        right_l.addWidget(apply_prop_btn)

        tab_lbl = QLabel("Tab 順序（欄位名稱，一行一個）：")
        right_l.addWidget(tab_lbl)
        from PyQt6.QtWidgets import QTextEdit
        self._tab_order_edit = QTextEdit()
        self._tab_order_edit.setMaximumHeight(100)
        right_l.addWidget(self._tab_order_edit)
        set_tab_btn = QPushButton("套用 Tab 順序")
        set_tab_btn.clicked.connect(self._apply_tab_order)
        right_l.addWidget(set_tab_btn)

        layout.addWidget(right)

        # 底部
        bottom = QHBoxLayout()
        layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        close_btn = QPushButton("完成")
        close_btn.clicked.connect(self.accept)

        outer = QVBoxLayout()
        outer.addLayout(layout)
        outer.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(outer)

        self._set_type("text")
        self._render()

    def _set_type(self, key: str):
        self._selected_type = key
        for k, btn in self._type_btns.items():
            btn.setChecked(k == key)

    def _render(self):
        if self._doc.fitz_doc is None:
            return
        pix = _render_page(self._doc.fitz_doc, self._current_page)
        self._page_lbl_img.setPixmap(pix)
        self._page_lbl_img.resize(pix.size())
        total = self._doc.page_count
        self._page_lbl.setText(f"第 {self._current_page + 1} 頁 / 共 {total} 頁")

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render()
            self._refresh_fields()

    def _next_page(self):
        if self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self._render()
            self._refresh_fields()

    def _add_field_center(self):
        if self._doc.fitz_doc is None:
            return
        page = self._doc.fitz_doc[self._current_page]
        cx = page.rect.width / 2
        cy = page.rect.height / 2
        rect = fitz.Rect(cx - 50, cy - 12, cx + 50, cy + 12)
        name = f"{self._selected_type}_{self._current_page}_{int(cx)}"
        fm = self._doc.forms
        if self._selected_type == "radio":
            fm.add_radio_button(self._current_page, rect, name, "yes")
        elif self._selected_type == "button":
            fm.add_push_button(self._current_page, rect, name, "按鈕")
        elif self._selected_type == "signature":
            fm.add_signature_field(self._current_page, rect, name)
        else:
            fm.add_field(self._current_page, rect, self._selected_type, name)
        self._render()
        self._refresh_fields()

    def _refresh_fields(self):
        self._field_list.clear()
        if self._doc.fitz_doc is None:
            return
        fields = self._doc.forms.get_all_fields(self._current_page)
        for f in fields:
            self._field_list.addItem(f"{f['name']} ({f['type']})")

    def _on_field_selected(self, row: int):
        if row < 0:
            return
        fields = self._doc.forms.get_all_fields(self._current_page)
        if row >= len(fields):
            return
        f = fields[row]
        self._prop_name.setText(f["name"])
        self._prop_value.setText(str(f.get("value") or ""))
        self._prop_fontsize.setValue(f.get("font_size") or 11)

    def _apply_properties(self):
        row = self._field_list.currentRow()
        if row < 0:
            return
        fields = self._doc.forms.get_all_fields(self._current_page)
        if row >= len(fields):
            return
        f = fields[row]
        self._doc.forms.set_field_properties(self._current_page, f["name"], {
            "font_size": self._prop_fontsize.value(),
            "field_value": self._prop_value.text(),
        })
        self._refresh_fields()

    def _apply_tab_order(self):
        names = [n.strip() for n in self._tab_order_edit.toPlainText().splitlines()
                 if n.strip()]
        if names:
            self._doc.forms.set_tab_order(self._current_page, names)
            QMessageBox.information(self, "完成", "Tab 順序已套用。")
