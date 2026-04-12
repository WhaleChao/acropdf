# ~/Desktop/acropdf/ui/dialogs/ocr/ocr_dialog.py
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QComboBox, QLabel,
                              QPushButton, QProgressBar, QFileDialog, QMessageBox)
from core.ocr_engine import OCREngine

class OCRDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("OCR 文字化")
        self.resize(350, 250)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("OCR 語言："))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems([
            "繁體中文 (chi_tra+eng)",
            "簡體中文 (chi_sim+eng)",
            "English (eng)",
            "日文 (jpn)",
        ])
        self._lang_map = {
            0: "chi_tra+eng", 1: "chi_sim+eng", 2: "eng", 3: "jpn"
        }
        layout.addWidget(self._lang_combo)

        layout.addWidget(QLabel("解析度（DPI）："))
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["150", "200", "300", "400"])
        self._dpi_combo.setCurrentIndex(2)
        layout.addWidget(self._dpi_combo)

        self._progress = QProgressBar()
        self._progress.hide()
        layout.addWidget(self._progress)

        self._run_btn = QPushButton("開始 OCR")
        self._run_btn.clicked.connect(self._run_ocr)
        layout.addWidget(self._run_btn)

    def _run_ocr(self):
        out_path, _ = QFileDialog.getSaveFileName(
            self, "儲存 OCR 結果", "", "PDF 檔案 (*.pdf)"
        )
        if not out_path:
            return
        lang = self._lang_map[self._lang_combo.currentIndex()]
        dpi = int(self._dpi_combo.currentText())
        self._progress.setMaximum(self._doc.page_count)
        self._progress.setValue(0)
        self._progress.show()
        self._run_btn.setEnabled(False)

        def on_progress(cur, total):
            self._progress.setValue(cur)

        def on_finished(path):
            self._progress.hide()
            self._run_btn.setEnabled(True)
            QMessageBox.information(self, "完成", f"OCR 完成！\n{path}")
            self.accept()

        def on_error(msg):
            self._progress.hide()
            self._run_btn.setEnabled(True)
            QMessageBox.critical(self, "錯誤", f"OCR 失敗：{msg}")

        OCREngine.run_async(
            self._doc, out_path, lang, dpi,
            on_progress=on_progress,
            on_finished=on_finished,
            on_error=on_error,
        )
