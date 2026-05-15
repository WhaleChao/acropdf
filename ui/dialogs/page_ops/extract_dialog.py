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
            hint.setStyleSheet("color: #007AFF; font-size: 12px;")
            layout.addWidget(hint)

        layout.addWidget(QLabel("擷取頁碼（逗號或連字號，例：1,3,5-8）："))
        self._pages_edit = QLineEdit()
        if self._preselected:
            self._pages_edit.setText(
                ", ".join(str(p + 1) for p in sorted(self._preselected))
            )
        self._pages_edit.textChanged.connect(self._update_default_path)
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

        # 初始化預設路徑
        self._update_default_path(self._pages_edit.text())

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

    def _default_dir(self) -> str:
        """來源檔案所在目錄，fallback 到桌面。"""
        src = self._doc.source_path or self._doc.path
        if src:
            return os.path.dirname(src)
        return os.path.expanduser("~/Desktop")

    def _page_suffix(self, pages_text: str) -> str:
        """把頁碼輸入轉成簡短後綴，例如 '2' → '_P2'、'1,3' → '_P1,3'、'5-8' → '_P5-8'。"""
        raw = pages_text.strip()
        if not raw:
            return "_擷取"
        # 清理多餘空白，保留逗號和連字號
        compact = raw.replace(" ", "").replace("，", ",")
        # 長度限制，避免檔名過長
        if len(compact) > 20:
            compact = compact[:20] + "…"
        return f"_P{compact}"

    def _build_default_path(self, pages_text: str) -> str:
        src = self._doc.source_path or self._doc.path
        if src:
            stem = os.path.splitext(os.path.basename(src))[0]
        else:
            stem = "擷取"
        suffix = self._page_suffix(pages_text)
        return os.path.join(self._default_dir(), f"{stem}{suffix}.pdf")

    def _update_default_path(self, pages_text: str):
        """頁碼輸入變化時自動更新輸出路徑（只在使用者尚未手動輸入時更新）。"""
        current = self._out_edit.text()
        # 若使用者已手動修改（不以預設 stem 開頭），不覆蓋
        src = self._doc.source_path or self._doc.path
        stem = os.path.splitext(os.path.basename(src))[0] if src else "擷取"
        if current and not os.path.basename(current).startswith(stem):
            return
        self._out_edit.setText(self._build_default_path(pages_text))

    def _browse(self):
        start = self._out_edit.text() or self._default_dir()
        path, _ = QFileDialog.getSaveFileName(
            self, "擷取為", start, "PDF 檔案 (*.pdf)"
        )
        if path:
            self._out_edit.setText(path)

    def _parse_pages(self, text: str) -> list[int]:
        """解析「1,3,5-8」格式，回傳 0-based 索引。"""
        result = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                if "-" in part:
                    a, b = part.split("-", 1)
                    a_int, b_int = int(a.strip()), int(b.strip())
                    if a_int > b_int:
                        a_int, b_int = b_int, a_int  # 自動修正反向範圍
                    result.extend(range(a_int - 1, b_int))
                else:
                    result.append(int(part) - 1)
            except ValueError:
                continue  # 忽略非數字部分
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
                if len(indices) >= self._doc.page_count:
                    QMessageBox.warning(self, "提示",
                        "無法刪除所有頁面，PDF 至少需保留一頁。\n擷取已完成但原文件保留不變。")
                else:
                    self._doc.pages.delete(indices)

            QMessageBox.information(self, "完成",
                f"已擷取 {len(indices)} 頁至：\n{os.path.basename(out)}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))
