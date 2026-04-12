# ~/Desktop/acropdf/ui/dialogs/ocr/ocr_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QProgressBar, QFileDialog, QMessageBox,
    QRadioButton, QButtonGroup, QGroupBox, QSpinBox, QWidget,
)
from PyQt6.QtCore import Qt
from core.ocr_engine import OCREngine


class OCRDialog(QDialog):
    def __init__(self, doc, current_page: int = 0, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._current_page = current_page
        self.setWindowTitle("OCR 文字化")
        self.resize(400, 380)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 引擎資訊 ────────────────────────────────────────────────
        engine_name = OCREngine.get_backend_name()
        info_lbl = QLabel(f"OCR 引擎：<b>{engine_name}</b>")
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(info_lbl)

        # ── OCR 範圍 ─────────────────────────────────────────────────
        scope_box = QGroupBox("OCR 範圍")
        scope_layout = QVBoxLayout(scope_box)

        self._scope_all = QRadioButton(
            f"整本 PDF（全部 {self._doc.page_count} 頁）"
        )
        self._scope_all.setChecked(True)

        self._scope_current = QRadioButton(
            f"目前頁面（第 {self._current_page + 1} 頁）"
        )

        self._scope_custom = QRadioButton("自訂頁面範圍：")

        # 自訂範圍 row
        custom_row = QHBoxLayout()
        custom_row.setContentsMargins(20, 0, 0, 0)
        custom_row.addWidget(QLabel("從第"))
        self._from_spin = QSpinBox()
        self._from_spin.setRange(1, self._doc.page_count)
        self._from_spin.setValue(1)
        self._from_spin.setEnabled(False)
        custom_row.addWidget(self._from_spin)
        custom_row.addWidget(QLabel("頁到第"))
        self._to_spin = QSpinBox()
        self._to_spin.setRange(1, self._doc.page_count)
        self._to_spin.setValue(self._doc.page_count)
        self._to_spin.setEnabled(False)
        custom_row.addWidget(self._to_spin)
        custom_row.addWidget(QLabel("頁"))
        custom_row.addStretch()

        self._scope_group = QButtonGroup(self)
        self._scope_group.addButton(self._scope_all, 0)
        self._scope_group.addButton(self._scope_current, 1)
        self._scope_group.addButton(self._scope_custom, 2)
        self._scope_group.idToggled.connect(self._on_scope_changed)

        scope_layout.addWidget(self._scope_all)
        scope_layout.addWidget(self._scope_current)
        scope_layout.addWidget(self._scope_custom)
        scope_layout.addLayout(custom_row)
        layout.addWidget(scope_box)

        # ── OCR 語言 ─────────────────────────────────────────────────
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("語言："))
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
        lang_row.addWidget(self._lang_combo)
        layout.addLayout(lang_row)

        # ── 解析度 ───────────────────────────────────────────────────
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("解析度（DPI）："))
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["150", "200", "300", "400"])
        self._dpi_combo.setCurrentIndex(2)  # 300 dpi 預設
        dpi_row.addWidget(self._dpi_combo)
        dpi_row.addStretch()
        layout.addLayout(dpi_row)

        # ── 進度 ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m 頁")
        self._progress.hide()
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        # ── 按鈕 ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("開始 OCR")
        self._run_btn.setDefault(True)
        self._run_btn.clicked.connect(self._run_ocr)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._run_btn)
        layout.addLayout(btn_row)

    def _on_scope_changed(self, btn_id: int, checked: bool):
        is_custom = (btn_id == 2 and checked)
        self._from_spin.setEnabled(is_custom)
        self._to_spin.setEnabled(is_custom)

    def _get_page_range(self) -> range:
        scope_id = self._scope_group.checkedId()
        if scope_id == 0:
            return range(self._doc.page_count)
        elif scope_id == 1:
            return range(self._current_page, self._current_page + 1)
        else:
            frm = self._from_spin.value() - 1
            to = self._to_spin.value()
            return range(frm, min(to, self._doc.page_count))

    def _run_ocr(self):
        if not self._doc.path:
            QMessageBox.warning(self, "提示", "請先儲存文件後再執行 OCR")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "儲存 OCR 結果", "", "PDF 檔案 (*.pdf)"
        )
        if not out_path:
            return

        page_range = self._get_page_range()
        if len(page_range) == 0:
            QMessageBox.warning(self, "錯誤", "頁面範圍無效")
            return

        lang = self._lang_map[self._lang_combo.currentIndex()]
        dpi = int(self._dpi_combo.currentText())

        self._progress.setMaximum(len(page_range))
        self._progress.setValue(0)
        self._progress.show()
        self._status_lbl.setText("OCR 進行中…")
        self._status_lbl.show()
        self._run_btn.setEnabled(False)

        def on_progress(cur, total):
            self._progress.setValue(cur)
            self._status_lbl.setText(f"正在處理第 {cur}/{total} 頁…")

        def on_finished(path):
            self._progress.hide()
            self._status_lbl.hide()
            self._run_btn.setEnabled(True)
            QMessageBox.information(
                self, "OCR 完成",
                f"已完成 {len(page_range)} 頁 OCR。\n\n輸出：{path}"
            )
            self.accept()

        def on_error(msg):
            self._progress.hide()
            self._status_lbl.hide()
            self._run_btn.setEnabled(True)
            QMessageBox.critical(self, "OCR 失敗", f"錯誤：{msg}")

        OCREngine.run_async(
            self._doc, out_path, lang, dpi,
            page_range=page_range,
            on_progress=on_progress,
            on_finished=on_finished,
            on_error=on_error,
        )
