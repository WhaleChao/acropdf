# ~/Desktop/acropdf/ui/dialogs/layer/layer_dialog.py
"""
PDF 圖層 (OCG) 管理對話框。

功能：
  - 以 QTreeWidget 顯示圖層階層
  - 勾選方塊切換圖層顯示狀態
  - 新增 / 刪除 / 重新命名圖層
  - 套用變更後存回文件
"""
from __future__ import annotations

from typing import Optional

import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QInputDialog, QMessageBox,
    QGroupBox, QHeaderView,
)
from PyQt6.QtCore import Qt


class LayerDialog(QDialog):
    """PDF 圖層 (OCG) 管理對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._fitz_doc: fitz.Document | None = doc.fitz_doc
        self._modified = False

        self.setWindowTitle("圖層管理")
        self.resize(520, 440)
        self._setup_ui()
        self._load_layers()

    # ── UI 建構 ───────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 說明
        self._info_label = QLabel("管理文件中的圖層（選用性內容群組）。")
        self._info_label.setStyleSheet("color: #8e8e93; font-size: 12px;")
        layout.addWidget(self._info_label)

        # 圖層樹
        grp = QGroupBox("圖層")
        grp_layout = QVBoxLayout(grp)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["圖層名稱", "xref"])
        self._tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tree.setColumnWidth(1, 60)
        self._tree.itemChanged.connect(self._on_item_changed)
        grp_layout.addWidget(self._tree, 1)

        # 操作按鈕
        btn_row = QHBoxLayout()

        self._btn_add = QPushButton("新增圖層")
        self._btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton("刪除圖層")
        self._btn_remove.clicked.connect(self._on_remove)
        btn_row.addWidget(self._btn_remove)

        self._btn_rename = QPushButton("重新命名")
        self._btn_rename.clicked.connect(self._on_rename)
        btn_row.addWidget(self._btn_rename)

        btn_row.addStretch()
        grp_layout.addLayout(btn_row)

        layout.addWidget(grp, 1)

        # 底部按鈕
        bottom = QHBoxLayout()

        self._btn_apply = QPushButton("套用")
        self._btn_apply.setToolTip("將圖層顯示狀態套用至文件")
        self._btn_apply.clicked.connect(self._on_apply)
        bottom.addWidget(self._btn_apply)

        bottom.addStretch()

        self._btn_close = QPushButton("關閉")
        self._btn_close.clicked.connect(self._on_close)
        bottom.addWidget(self._btn_close)

        layout.addLayout(bottom)

    # ── 載入圖層 ─────────────────────────────────────────────────
    def _load_layers(self):
        self._tree.blockSignals(True)
        self._tree.clear()

        if self._fitz_doc is None:
            self._show_empty()
            self._tree.blockSignals(False)
            return

        try:
            ocgs = self._fitz_doc.get_ocgs()
        except Exception:
            ocgs = {}

        if not ocgs:
            self._show_empty()
            self._tree.blockSignals(False)
            return

        self._info_label.setText(f"共 {len(ocgs)} 個圖層")
        self._btn_remove.setEnabled(True)
        self._btn_rename.setEnabled(True)

        # ocgs: {xref: {"name": str, "intent": ..., "on": bool, ...}}
        for xref, info in sorted(ocgs.items(), key=lambda kv: kv[1].get("name", "")):
            name = info.get("name", f"圖層 {xref}")
            is_on = info.get("on", True)

            item = QTreeWidgetItem()
            item.setText(0, name)
            item.setText(1, str(xref))
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            item.setCheckState(
                0,
                Qt.CheckState.Checked if is_on else Qt.CheckState.Unchecked,
            )
            item.setData(0, Qt.ItemDataRole.UserRole, xref)
            self._tree.addTopLevelItem(item)

        self._tree.blockSignals(False)

    def _show_empty(self):
        self._info_label.setText("此文件無圖層。")
        self._btn_remove.setEnabled(False)
        self._btn_rename.setEnabled(False)

    # ── 事件處理 ─────────────────────────────────────────────────
    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column == 0:
            self._modified = True

    def _on_add(self):
        if self._fitz_doc is None:
            QMessageBox.warning(self, "錯誤", "尚未開啟文件。")
            return

        name, ok = QInputDialog.getText(
            self, "新增圖層", "圖層名稱：",
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        try:
            self._doc.begin_op("新增圖層")
            xref = self._fitz_doc.add_ocg(name, on=True)
            self._doc.end_op()
            self._doc._mark_modified()
        except Exception as e:
            QMessageBox.warning(self, "新增失敗", str(e))
            return

        self._modified = True
        self._load_layers()

    def _on_remove(self):
        item = self._tree.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "請先選取要刪除的圖層。")
            return

        name = item.text(0)
        xref = item.data(0, Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self, "刪除圖層",
            f"確定要刪除圖層「{name}」嗎？\n此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._doc.begin_op("刪除圖層")
            # PyMuPDF: 移除 OCG 物件（將 xref 設為空 dict 使其失效）
            self._fitz_doc.xref_set_key(xref, "Type", "null")
            self._fitz_doc.xref_set_key(xref, "Name", "null")
            self._doc.end_op()
            self._doc._mark_modified()
        except Exception as e:
            QMessageBox.warning(self, "刪除失敗", str(e))
            return

        self._modified = True
        self._load_layers()

    def _on_rename(self):
        item = self._tree.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "請先選取要重新命名的圖層。")
            return

        old_name = item.text(0)
        xref = item.data(0, Qt.ItemDataRole.UserRole)

        new_name, ok = QInputDialog.getText(
            self, "重新命名圖層", "新名稱：", text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        try:
            self._doc.begin_op("重新命名圖層")
            self._fitz_doc.xref_set_key(xref, "Name", fitz.get_pdf_str(new_name))
            self._doc.end_op()
            self._doc._mark_modified()
        except Exception as e:
            QMessageBox.warning(self, "重新命名失敗", str(e))
            return

        self._modified = True
        self._load_layers()

    def _on_apply(self):
        """將勾選狀態套用至文件。"""
        if self._fitz_doc is None:
            return

        on_list: list[int] = []
        off_list: list[int] = []

        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            xref = item.data(0, Qt.ItemDataRole.UserRole)
            if xref is None:
                continue
            if item.checkState(0) == Qt.CheckState.Checked:
                on_list.append(xref)
            else:
                off_list.append(xref)

        if not on_list and not off_list:
            return

        try:
            self._doc.begin_op("切換圖層顯示")
            # PyMuPDF: set_layer(-1, on=, off=) 控制預設配置
            try:
                self._fitz_doc.set_layer(-1, on=on_list, off=off_list)
            except (AttributeError, TypeError):
                # 舊版 PyMuPDF 回退
                try:
                    self._fitz_doc.set_ocg_state(on=on_list, off=off_list)
                except (AttributeError, TypeError):
                    pass

            # 嘗試儲存 UI 設定
            try:
                self._fitz_doc.set_layer_ui_config()
            except (AttributeError, RuntimeError, TypeError):
                pass

            self._doc.end_op()
            self._doc._mark_modified()
        except Exception as e:
            QMessageBox.warning(self, "套用失敗", str(e))
            return

        self._modified = False
        QMessageBox.information(self, "完成", "圖層顯示狀態已套用。")

    def _on_close(self):
        if self._modified:
            reply = QMessageBox.question(
                self, "未套用的變更",
                "圖層顯示狀態已變更但尚未套用。\n確定要關閉嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.accept()
