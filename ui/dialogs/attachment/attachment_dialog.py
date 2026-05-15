# ~/Desktop/acropdf/ui/dialogs/attachment/attachment_dialog.py
"""
嵌入式附件管理對話框。

管理 PDF 文件中的嵌入式檔案附件：
  - 檢視目前已嵌入的檔案清單
  - 新增附件
  - 匯出（儲存）附件到磁碟
  - 刪除附件
  - 顯示檔案大小資訊
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QFileDialog,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt


def _format_size(size_bytes: int) -> str:
    """將位元組數轉換為人類可讀的格式。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class AttachmentDialog(QDialog):
    """嵌入式附件管理對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._modified = False
        self.setWindowTitle("嵌入式附件")
        self.resize(520, 400)

        if not self._check_embfile_support():
            self._setup_unsupported_ui()
        else:
            self._setup_ui()
            self._refresh_list()

    # --------------------------------------------------------- capability
    def _check_embfile_support(self) -> bool:
        """檢查 fitz 版本是否支援嵌入式附件方法。"""
        fitz_doc = self._doc.fitz_doc
        return (
            hasattr(fitz_doc, "embfile_names")
            and hasattr(fitz_doc, "embfile_add")
            and hasattr(fitz_doc, "embfile_get")
            and hasattr(fitz_doc, "embfile_del")
        )

    def _setup_unsupported_ui(self):
        """當 fitz 版本不支援嵌入式附件時顯示提示。"""
        layout = QVBoxLayout(self)
        msg = QLabel(
            "目前的 PyMuPDF (fitz) 版本不支援嵌入式附件功能。\n\n"
            "請升級至 PyMuPDF 1.18.0 或更新版本。"
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #8e8e93; font-size: 13px; padding: 40px;")
        layout.addWidget(msg)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 說明 ─────────────────────────────────────────────────────
        info_label = QLabel("管理 PDF 文件中的嵌入式檔案附件。")
        info_label.setStyleSheet("color: #8e8e93; font-size: 11px;")
        layout.addWidget(info_label)

        # ── 主要區域：清單 + 按鈕 ────────────────────────────────────
        content = QHBoxLayout()

        # 附件清單
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        content.addWidget(self._list, 1)

        # 右側按鈕欄
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        self._add_btn = QPushButton("新增")
        self._add_btn.clicked.connect(self._add_attachment)
        btn_col.addWidget(self._add_btn)

        self._export_btn = QPushButton("匯出")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_attachment)
        btn_col.addWidget(self._export_btn)

        self._delete_btn = QPushButton("刪除")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_attachment)
        btn_col.addWidget(self._delete_btn)

        btn_col.addStretch()

        # 檔案資訊
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #8e8e93; font-size: 11px;")
        self._info_label.setWordWrap(True)
        btn_col.addWidget(self._info_label)

        content.addLayout(btn_col)
        layout.addLayout(content)

        # ── 底部狀態 ─────────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setStyleSheet("color: #8e8e93; font-size: 11px;")
        layout.addWidget(self._status)

        # ── 按鈕 ─────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self._on_close)
        layout.addWidget(btns)

    # ----------------------------------------------------------- refresh
    def _refresh_list(self):
        """重新讀取嵌入式附件清單。"""
        self._list.clear()
        self._info_label.setText("")

        try:
            names = self._doc.fitz_doc.embfile_names()
        except Exception:
            names = []

        for name in names:
            item = QListWidgetItem(name)
            self._list.addItem(item)

        count = self._list.count()
        self._status.setText(f"共 {count} 個附件" if count else "無嵌入式附件")
        self._on_selection_changed(-1)

    def _on_selection_changed(self, row: int):
        has_sel = row >= 0
        self._export_btn.setEnabled(has_sel)
        self._delete_btn.setEnabled(has_sel)

        if has_sel:
            name = self._list.item(row).text()
            try:
                info = self._doc.fitz_doc.embfile_info(name)
                size = info.get("size", 0) if isinstance(info, dict) else 0
                self._info_label.setText(
                    f"檔案：{name}\n大小：{_format_size(size)}"
                )
            except Exception:
                # embfile_info 可能不存在或結構不同，改用 embfile_get 估算
                try:
                    data = self._doc.fitz_doc.embfile_get(name)
                    self._info_label.setText(
                        f"檔案：{name}\n大小：{_format_size(len(data))}"
                    )
                except Exception:
                    self._info_label.setText(f"檔案：{name}")
        else:
            self._info_label.setText("")

    # ----------------------------------------------------------- actions
    def _add_attachment(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇要嵌入的檔案", "",
            "所有檔案 (*)",
        )
        if not paths:
            return

        added = 0
        errors = []
        existing_names = set()
        try:
            existing_names = set(self._doc.fitz_doc.embfile_names())
        except Exception:
            pass

        self._doc.begin_op("新增附件")

        for path in paths:
            basename = os.path.basename(path)
            name = basename

            # 避免名稱重複
            counter = 1
            while name in existing_names:
                stem, ext = os.path.splitext(basename)
                name = f"{stem}_{counter}{ext}"
                counter += 1

            try:
                with open(path, "rb") as f:
                    data = f.read()
                self._doc.fitz_doc.embfile_add(name, data)
                existing_names.add(name)
                added += 1
            except Exception as e:
                errors.append(f"{basename}: {e}")

        self._doc.end_op()

        if added > 0:
            self._modified = True
            self._doc._mark_modified()

        self._refresh_list()

        if errors:
            QMessageBox.warning(
                self, "部分失敗",
                f"成功新增 {added} 個檔案，以下發生錯誤：\n\n"
                + "\n".join(errors)
            )
        elif added > 0:
            QMessageBox.information(
                self, "完成", f"已新增 {added} 個附件。"
            )

    def _export_attachment(self):
        item = self._list.currentItem()
        if not item:
            return

        name = item.text()
        save_path, _ = QFileDialog.getSaveFileName(
            self, "匯出附件", name, "所有檔案 (*)"
        )
        if not save_path:
            return

        try:
            data = self._doc.fitz_doc.embfile_get(name)
            with open(save_path, "wb") as f:
                f.write(data)
            QMessageBox.information(
                self, "完成",
                f"附件已匯出至：\n{save_path}\n\n"
                f"大小：{_format_size(len(data))}"
            )
        except Exception as e:
            QMessageBox.critical(self, "失敗", f"匯出附件時發生錯誤：\n{e}")

    def _delete_attachment(self):
        item = self._list.currentItem()
        if not item:
            return

        name = item.text()
        reply = QMessageBox.question(
            self, "確認刪除",
            f"確定要刪除附件「{name}」嗎？\n此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._doc.begin_op("刪除附件")
            self._doc.fitz_doc.embfile_del(name)
            self._doc.end_op()
            self._modified = True
            self._doc._mark_modified()
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "失敗", f"刪除附件時發生錯誤：\n{e}")

    # ------------------------------------------------------------- close
    def _on_close(self):
        self.accept() if self._modified else self.reject()
