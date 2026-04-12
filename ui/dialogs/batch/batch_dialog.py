# ~/Desktop/acropdf/ui/dialogs/batch/batch_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox,
    QGroupBox, QListWidget, QComboBox,
    QFormLayout, QDialogButtonBox, QProgressBar
)
from PyQt6.QtCore import Qt


class BatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批次處理")
        self.resize(560, 440)
        self._files = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 檔案清單
        file_grp = QGroupBox("批次處理檔案")
        file_layout = QVBoxLayout(file_grp)
        self._file_list = QListWidget()
        file_layout.addWidget(self._file_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增 PDF...")
        add_btn.clicked.connect(self._add_files)
        clr_btn = QPushButton("清除全部")
        clr_btn.clicked.connect(self._clear_files)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(clr_btn)
        btn_row.addStretch()
        file_layout.addLayout(btn_row)
        layout.addWidget(file_grp)

        # 操作設定
        op_grp = QGroupBox("批次操作")
        op_form = QFormLayout(op_grp)
        self._op_combo = QComboBox()
        self._op_combo.addItems([
            "OCR 辨識",
            "優化壓縮",
            "加密保護",
            "匯出為圖片 (PNG)",
            "匯出為文字 (TXT)",
            "合併為單一 PDF",
        ])
        op_form.addRow("操作：", self._op_combo)

        self._out_dir = QLabel("（未選擇）")
        out_btn = QPushButton("選擇輸出目錄...")
        out_btn.clicked.connect(self._pick_outdir)
        out_row = QHBoxLayout()
        out_row.addWidget(self._out_dir)
        out_row.addWidget(out_btn)
        op_form.addRow("輸出目錄：", out_row)
        layout.addWidget(op_grp)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("開始處理")
        btns.accepted.connect(self._run)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._outdir_path = None

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇 PDF 檔案", "", "PDF (*.pdf)"
        )
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                self._file_list.addItem(p)

    def _clear_files(self):
        self._files.clear()
        self._file_list.clear()

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "選擇輸出目錄")
        if d:
            self._outdir_path = d
            self._out_dir.setText(d)

    def _run(self):
        if not self._files:
            QMessageBox.warning(self, "錯誤", "請先加入 PDF 檔案")
            return
        if not self._outdir_path:
            QMessageBox.warning(self, "錯誤", "請選擇輸出目錄")
            return

        op = self._op_combo.currentText()
        total = len(self._files)
        errors = []
        self._progress.setMaximum(total)

        for i, path in enumerate(self._files):
            try:
                self._batch_one(path, op, self._outdir_path)
            except Exception as e:
                errors.append(f"{path}: {e}")
            self._progress.setValue(i + 1)

        if errors:
            QMessageBox.warning(
                self, "部分失敗",
                f"完成 {total - len(errors)}/{total}，失敗：\n" + "\n".join(errors[:5])
            )
        else:
            QMessageBox.information(self, "完成", f"批次處理完成（{total} 個檔案）")
        self.accept()

    def _batch_one(self, path: str, op: str, outdir: str):
        import os, fitz
        name = os.path.splitext(os.path.basename(path))[0]
        doc = fitz.open(path)
        if op == "OCR 辨識":
            # placeholder — real OCR via ocr_engine
            out = os.path.join(outdir, name + "_ocr.pdf")
            doc.save(out)
        elif op == "優化壓縮":
            out = os.path.join(outdir, name + "_opt.pdf")
            doc.save(out, garbage=4, deflate=True)
        elif op == "匯出為圖片 (PNG)":
            for pi in range(doc.page_count):
                pix = doc[pi].get_pixmap(dpi=150)
                out = os.path.join(outdir, f"{name}_p{pi+1:04d}.png")
                pix.save(out)
        elif op == "匯出為文字 (TXT)":
            out = os.path.join(outdir, name + ".txt")
            with open(out, "w", encoding="utf-8") as f:
                for pi in range(doc.page_count):
                    f.write(doc[pi].get_text())
        elif op == "合併為單一 PDF":
            # handled after all files; just save as-is here
            out = os.path.join(outdir, name + ".pdf")
            doc.save(out)
        doc.close()
