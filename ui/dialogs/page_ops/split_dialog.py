# ~/Desktop/acropdf/ui/dialogs/page_ops/split_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QFileDialog, QMessageBox)

class SplitDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("分割 PDF")
        self.resize(400, 200)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"總頁數：{self._doc.page_count}"))
        layout.addWidget(QLabel("輸入分割點（逗號分隔頁碼，例如：5,10,15）："))
        self._split_edit = QLineEdit()
        layout.addWidget(self._split_edit)

        layout.addWidget(QLabel("輸出資料夾："))
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        btn_row = QHBoxLayout()
        ok = QPushButton("分割")
        cancel = QPushButton("取消")
        ok.clicked.connect(self._do_split)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if d:
            self._dir_edit.setText(d)

    def _do_split(self):
        text = self._split_edit.text().strip()
        out_dir = self._dir_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "錯誤", "請選擇輸出資料夾")
            return
        try:
            points = [int(x.strip()) for x in text.split(",") if x.strip()]
            points = sorted(set(points))
            # 建立範圍
            boundaries = [0] + points + [self._doc.page_count]
            ranges = [(boundaries[i], boundaries[i+1] - 1)
                      for i in range(len(boundaries) - 1)]
            ranges = [(s, e) for s, e in ranges if s <= e]
            paths = self._doc.pages.split_by_range(ranges, out_dir)
            QMessageBox.information(self, "完成", f"已分割為 {len(paths)} 個檔案")
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "錯誤", "請輸入有效的頁碼數字")
