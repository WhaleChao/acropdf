from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QLabel,
    QLineEdit, QTextEdit, QDialogButtonBox, QMessageBox,
)


class DocumentPropertiesDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._fitz = doc.fitz_doc
        self.setWindowTitle("文件屬性")
        self.resize(560, 460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_summary_tab(), "摘要")
        tabs.addTab(self._build_metadata_tab(), "描述")
        tabs.addTab(self._build_security_tab(), "安全性")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_summary_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        source = self._doc.source_path or ""
        form.addRow("檔名：", QLabel(Path(source).name if source else "新文件"))
        form.addRow("位置：", QLabel(source or "尚未儲存"))
        form.addRow("頁數：", QLabel(str(self._doc.page_count)))
        if source and os.path.exists(source):
            form.addRow("檔案大小：", QLabel(self._format_size(os.path.getsize(source))))
        if self._fitz is not None:
            form.addRow("格式：", QLabel("PDF" if self._fitz.is_pdf else "轉換中的文件"))
            version_attr = getattr(self._fitz, "pdf_version", "?")
            version = version_attr() if callable(version_attr) else version_attr
            form.addRow("PDF 版本：", QLabel(str(version)))
            if self._fitz.page_count:
                rect = self._fitz[0].rect
                form.addRow("首頁尺寸：", QLabel(f"{rect.width:.1f} x {rect.height:.1f} pt"))
        return tab

    def _build_metadata_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        meta = dict(self._fitz.metadata or {}) if self._fitz is not None else {}
        self._title_edit = QLineEdit(meta.get("title", "") or "")
        self._author_edit = QLineEdit(meta.get("author", "") or "")
        self._subject_edit = QLineEdit(meta.get("subject", "") or "")
        self._keywords_edit = QLineEdit(meta.get("keywords", "") or "")
        self._creator_edit = QLineEdit(meta.get("creator", "") or "")
        self._producer_edit = QLineEdit(meta.get("producer", "") or "")
        self._producer_edit.setReadOnly(True)
        form.addRow("標題：", self._title_edit)
        form.addRow("作者：", self._author_edit)
        form.addRow("主旨：", self._subject_edit)
        form.addRow("關鍵字：", self._keywords_edit)
        form.addRow("建立程式：", self._creator_edit)
        form.addRow("PDF 產生器：", self._producer_edit)
        return tab

    def _build_security_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        if self._fitz is None:
            form.addRow("狀態：", QLabel("尚未開啟文件"))
            return tab
        form.addRow("是否加密：", QLabel("是" if self._fitz.needs_pass else "否"))
        form.addRow("可擷取文字：", QLabel("是" if self._fitz.permissions & 16 else "依文件權限限制"))
        form.addRow("可列印：", QLabel("是" if self._fitz.permissions & 4 else "依文件權限限制"))
        form.addRow("可修改：", QLabel("是" if self._fitz.permissions & 8 else "依文件權限限制"))
        notes = QTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(
            "這裡顯示目前 PDF 的本機安全狀態。若需要設定密碼、列印或複製權限，請使用「保護 PDF」。"
        )
        notes.setMaximumHeight(90)
        form.addRow("說明：", notes)
        return tab

    def _apply(self):
        if self._fitz is None:
            self.reject()
            return
        current = dict(self._fitz.metadata or {})
        updated = dict(current)
        updated.update({
            "title": self._title_edit.text().strip(),
            "author": self._author_edit.text().strip(),
            "subject": self._subject_edit.text().strip(),
            "keywords": self._keywords_edit.text().strip(),
            "creator": self._creator_edit.text().strip(),
        })
        if updated != current:
            try:
                self._doc.begin_op("修改文件屬性")
                self._fitz.set_metadata(updated)
                self._doc.end_op()
                self._doc._mark_modified()
            except Exception as e:
                QMessageBox.warning(self, "無法更新文件屬性", str(e))
                return
        self.accept()

    @staticmethod
    def _format_size(size: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
