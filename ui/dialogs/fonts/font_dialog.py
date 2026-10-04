# ~/Desktop/acropdf/ui/dialogs/fonts/font_dialog.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QFileDialog, QHeaderView,
)
from PyQt6.QtCore import Qt

from core.font_manager import FontManager


class FontDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._fm = FontManager(doc)
        self.setWindowTitle("字型管理")
        self.resize(700, 500)
        self._setup_ui()
        self._load_fonts()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["名稱", "類型", "嵌入", "子集", "使用頁碼"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        embed_btn = QPushButton("替換並嵌入字型...")
        embed_btn.setToolTip("套用指定字型並檢查缺字；較寬的文字會縮小至原區域。")
        embed_btn.clicked.connect(self._embed_font)
        btn_row.addWidget(embed_btn)

        extract_btn = QPushButton("提取字型...")
        extract_btn.clicked.connect(self._extract_font)
        btn_row.addWidget(extract_btn)

        subset_btn = QPushButton("子集化文件字型")
        subset_btn.clicked.connect(self._subset_fonts)
        btn_row.addWidget(subset_btn)


        btn_row.addStretch()
        refresh_btn = QPushButton("重新整理")
        refresh_btn.clicked.connect(self._load_fonts)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_fonts(self):
        fonts = self._fm.list_fonts()
        self._fonts = fonts
        self._table.setRowCount(len(fonts))
        for i, f in enumerate(fonts):
            self._table.setItem(i, 0, QTableWidgetItem(f.name))
            self._table.setItem(i, 1, QTableWidgetItem(f.type))
            embedded_txt = "是" if f.embedded else "否"
            item_emb = QTableWidgetItem(embedded_txt)
            if not f.embedded:
                item_emb.setForeground(Qt.GlobalColor.red)
            self._table.setItem(i, 2, item_emb)
            self._table.setItem(i, 3, QTableWidgetItem("是" if f.subset else "否"))
            pages_txt = ", ".join(str(p + 1) for p in f.pages[:10])
            if len(f.pages) > 10:
                pages_txt += "..."
            self._table.setItem(i, 4, QTableWidgetItem(pages_txt))

    def _selected_font(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._fonts):
            return None
        return self._fonts[row]

    def _embed_font(self):
        f = self._selected_font()
        if f is None:
            QMessageBox.warning(self, "提示", "請先選取字型")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇字型檔案", "", "字型 (*.ttf *.otf *.ttc)"
        )
        if not path:
            return
        try:
            self._fm.embed_font(f.name, path)
            self._load_fonts()
            QMessageBox.information(self, "完成", f"已嵌入字型：{f.name}")
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def _extract_font(self):
        f = self._selected_font()
        if f is None:
            QMessageBox.warning(self, "提示", "請先選取字型")
            return
        if not f.embedded:
            QMessageBox.warning(self, "提示", "此字型未嵌入，無法提取")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "儲存字型", f.name.replace("+", ""),
            "字型 (*.ttf *.otf)"
        )
        if not path:
            return
        ok = self._fm.extract_font(f.name, path)
        if ok:
            QMessageBox.information(self, "完成", f"字型已提取至：{path}")
        else:
            QMessageBox.warning(self, "失敗", "無法提取此字型")

    def _embed_all(self):
        QMessageBox.information(
            self, "提示",
            "全部嵌入功能需要對應的字型檔案。\n"
            "請逐一選取未嵌入字型並指定字型檔案路徑。"
        )

    def _subset_fonts(self):
        selected = self._selected_font()
        if selected is None:
            return
        try:
            self._fm.subset_font(selected.name)
            self._load_fonts()
        except Exception as exc:
            QMessageBox.critical(self, "子集化失敗", str(exc))
