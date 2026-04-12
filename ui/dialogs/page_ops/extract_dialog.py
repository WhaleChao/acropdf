# ~/Desktop/acropdf/ui/dialogs/page_ops/extract_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QFileDialog,
                              QMessageBox, QCheckBox)
import os


class ExtractDialog(QDialog):
    def __init__(self, doc, preselected: list[int] = None, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._preselected = preselected or []
        self.setWindowTitle("擷取頁面")
        self.setFixedWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"文件共 {self._doc.page_count} 頁"))

        if self._preselected:
            pages_str = ", ".join(str(p + 1) for p in sorted(self._preselected))
            hint = QLabel(f"已選取頁面：{pages_str}")
            hint.setStyleSheet("color: #0078d4; font-size: 12px;")
            layout.addWidget(hint)

        layout.addWidget(QLabel("擷取頁碼（逗號或連字號，例：1,3,5-8）："))
        self._pages_edit = QLineEdit()
        if self._preselected:
            self._pages_edit.setText(
                ", ".join(str(p + 1) for p in sorted(self._preselected))
            )
        layout.addWidget(self._pages_edit)

        self._delete_check = QCheckBox("擷取後從原文件刪除這些頁面")
        layout.addWidget(self._delete_check)

        layout.addWidget(QLabel("輸出 PDF："))
        row = QHBoxLayout()
        self._out_edit = QLineEdit()
        browse = QPushButton("瀏覽...")
        browse.setFixedWidth(70)
        browse.clicked.connect(self._browse)
        row.addWidget(self._out_edit)
        row.addWidget(browse)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("擷取")
        ok.setDefault(True)
        ok.setFixedWidth(80)
        cancel = QPushButton("取消")
        cancel.setFixedWidth(80)
        ok.clicked.connect(self._do_extract)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "擷取為", "", "PDF 檔案 (*.pdf)")
        if path:
            self._out_edit.setText(path)

    def _parse_pages(self, text: str) -> list[int]:
        """解析「1,3,5-8」格式，回傳 0-based 索引。"""
        result = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                result.extend(range(int(a) - 1, int(b)))
            else:
                result.append(int(part) - 1)
        return sorted(set(p for p in result if 0 <= p < self._doc.page_count))

    def _do_extract(self):
        text = self._pages_edit.text().strip()
        out = self._out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "錯誤", "請指定輸出路徑")
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        try:
            indices = self._parse_pages(text)
            if not indices:
                QMessageBox.warning(self, "錯誤", "沒有有效的頁碼")
                return
            # 建立新文件
            import fitz
            new_doc = fitz.open()
            for i in indices:
                new_doc.insert_pdf(self._doc.fitz_doc, from_page=i, to_page=i)
            new_doc.save(out, garbage=4, deflate=True)
            new_doc.close()

            if self._delete_check.isChecked():
                self._doc.pages.delete(indices)

            QMessageBox.information(self, "完成",
                f"已擷取 {len(indices)} 頁至：\n{os.path.basename(out)}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))
