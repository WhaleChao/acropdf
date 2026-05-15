# ~/Desktop/acropdf/ui/dialogs/forms/form_fill_dialog.py
"""
表單填寫對話框。
- 顯示文件內所有表單欄位
- 支援逐欄填寫、批次填寫（貼上 JSON）
- 匯出 / 匯入 FDF
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QMessageBox, QFileDialog, QDialogButtonBox,
    QAbstractItemView, QGroupBox, QSizePolicy,
)
from PyQt6.QtCore import Qt


class FormFillDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("表單填寫")
        self.resize(620, 480)
        self._setup_ui()
        self._load_fields()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── 說明 ─────────────────────────────────────────────────
        hint = QLabel("雙擊「值」欄可直接編輯；修改後按「套用」寫入 PDF。")
        hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        layout.addWidget(hint)

        # ── 欄位表格 ─────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["頁", "欄位名稱", "類型", "值"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # ── 動作按鈕列 ───────────────────────────────────────────
        action_row = QHBoxLayout()

        import_btn = QPushButton("匯入 FDF...")
        import_btn.clicked.connect(self._import_fdf)
        action_row.addWidget(import_btn)

        export_btn = QPushButton("匯出 FDF...")
        export_btn.clicked.connect(self._export_fdf)
        action_row.addWidget(export_btn)

        clear_btn = QPushButton("清除全部欄位值")
        clear_btn.clicked.connect(self._clear_all)
        action_row.addWidget(clear_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # ── 套用 / 套用並關閉 / 取消（左→右）───────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn = QPushButton("套用")
        apply_btn.clicked.connect(self._apply)
        ok_btn = QPushButton("套用並關閉")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._fields_meta: list[dict] = []  # 對應 table 每列的 metadata

    def _load_fields(self):
        fields = self._doc.forms.get_fields()
        self._fields_meta = fields
        self._table.setRowCount(len(fields))
        for row, f in enumerate(fields):
            pg_item = QTableWidgetItem(str(f["page"] + 1))
            pg_item.setFlags(pg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, pg_item)

            name_item = QTableWidgetItem(f["field_name"] or "")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, name_item)

            type_item = QTableWidgetItem(f["field_type"] or "")
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, type_item)

            val = f["field_value"]
            val_item = QTableWidgetItem(str(val) if val is not None else "")
            self._table.setItem(row, 3, val_item)

        if not fields:
            self._table.setRowCount(1)
            empty = QTableWidgetItem("（此文件無表單欄位）")
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(0, 1, empty)

    def _collect_edits(self) -> dict[str, str]:
        """收集表格中所有已編輯的值，回傳 {field_name: value}。"""
        data = {}
        for row in range(self._table.rowCount()):
            if row >= len(self._fields_meta):
                break
            name = self._fields_meta[row]["field_name"]
            val_item = self._table.item(row, 3)
            if val_item and name:
                data[name] = val_item.text()
        return data

    def _apply(self):
        data = self._collect_edits()
        if data:
            self._doc.forms.fill_all(data)
            QMessageBox.information(self, "已套用", f"已填寫 {len(data)} 個欄位。")

    def _ok(self):
        self._apply()
        self.accept()

    def _clear_all(self):
        for row in range(min(self._table.rowCount(), len(self._fields_meta))):
            item = self._table.item(row, 3)
            if item:
                item.setText("")

    def _export_fdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出 FDF", "", "FDF 檔案 (*.fdf)"
        )
        if path:
            try:
                self._doc.forms.export_fdf(path)
                QMessageBox.information(self, "完成", f"已匯出：{path}")
            except Exception as e:
                QMessageBox.critical(self, "失敗", str(e))

    def _import_fdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "匯入 FDF", "", "FDF 檔案 (*.fdf);;所有檔案 (*)"
        )
        if path:
            try:
                self._doc.forms.import_fdf(path)
                self._load_fields()   # 重新讀取
                QMessageBox.information(self, "完成", "已匯入 FDF 資料。")
            except Exception as e:
                QMessageBox.critical(self, "失敗", str(e))
