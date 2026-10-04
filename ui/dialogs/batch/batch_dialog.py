# ~/Desktop/acropdf/ui/dialogs/batch/batch_dialog.py
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox,
    QGroupBox, QListWidget, QComboBox,
    QFormLayout, QDialogButtonBox, QProgressBar,
    QLineEdit, QSpinBox, QDoubleSpinBox, QStackedWidget, QWidget,
    QSlider,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class _BatchWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)

    def __init__(self, files, operation, params, parent=None):
        super().__init__(parent)
        self._files = files
        self._operation = operation
        self._params = params

    def run(self):
        from core.batch_engine import BatchEngine
        engine = BatchEngine()
        results = engine.batch_process(
            self._files, self._operation, self._params,
            progress_callback=self.progress.emit,
            is_cancelled=self.isInterruptionRequested,
        )
        self.finished.emit(results)


from ui.widgets.worker_dialog import WorkerDialog


class BatchDialog(WorkerDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批次處理")
        self.resize(620, 540)
        self._files = []
        self._setup_ui()

    _OP_MAP = {
        "OCR 辨識": "ocr",
        "最佳化壓縮": "optimize",
        "加密保護": "encrypt",
        "匯出為圖片 (PNG)": "png",
        "匯出為文字 (TXT)": "txt",
        "合併為單一 PDF": "merge",
        "加浮水印": "watermark",
        "加頁首頁尾": "header_footer",
        "Bates 編號": "bates",
        "匯出為 Word (.docx)": "docx",
        "匯出為 HTML": "html",
        "分割（每 N 頁）": "split",
        "塗黑並套用": "redact",
    }

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
        op_layout = QVBoxLayout(op_grp)
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("操作："))
        self._op_combo = QComboBox()
        self._op_combo.addItems(list(self._OP_MAP.keys()))
        self._op_combo.currentIndexChanged.connect(self._on_op_changed)
        op_row.addWidget(self._op_combo)
        op_layout.addLayout(op_row)

        # 動態設定面板
        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._build_empty_panel())     # ocr
        self._stacked.addWidget(self._build_empty_panel())     # optimize
        self._stacked.addWidget(self._build_encrypt_panel())   # encrypt
        self._stacked.addWidget(self._build_empty_panel())     # png
        self._stacked.addWidget(self._build_empty_panel())     # txt
        self._stacked.addWidget(self._build_empty_panel())     # merge
        self._stacked.addWidget(self._build_watermark_panel()) # watermark
        self._stacked.addWidget(self._build_hf_panel())        # header_footer
        self._stacked.addWidget(self._build_bates_panel())     # bates
        self._stacked.addWidget(self._build_empty_panel())     # docx
        self._stacked.addWidget(self._build_empty_panel())     # html
        self._stacked.addWidget(self._build_split_panel())     # split
        self._stacked.addWidget(self._build_empty_panel())     # redact
        op_layout.addWidget(self._stacked)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("輸出目錄："))
        self._out_dir = QLabel("（未選擇）")
        out_btn = QPushButton("選擇...")
        out_btn.clicked.connect(self._pick_outdir)
        out_row.addWidget(self._out_dir)
        out_row.addWidget(out_btn)
        op_layout.addLayout(out_row)
        layout.addWidget(op_grp)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        layout.addWidget(self._status_lbl)

        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="開始處理", cancel_text="取消")
        ok_btn.clicked.connect(self._run)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

        self._outdir_path = None

    # ── 動態面板 ──────────────────────────────────────────────────
    def _build_empty_panel(self) -> QWidget:
        w = QWidget()
        return w

    def _build_encrypt_panel(self):
        widget = QWidget()
        form = QFormLayout(widget)
        self._encrypt_owner = QLineEdit()
        self._encrypt_owner.setEchoMode(QLineEdit.EchoMode.Password)
        self._encrypt_user = QLineEdit()
        self._encrypt_user.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('擁有者密碼（必填）：', self._encrypt_owner)
        form.addRow('開啟密碼：', self._encrypt_user)
        return widget

    def _build_watermark_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._wm_text = QLineEdit("機密")
        form.addRow("浮水印文字：", self._wm_text)
        self._wm_opacity = QDoubleSpinBox()
        self._wm_opacity.setRange(0.05, 1.0)
        self._wm_opacity.setSingleStep(0.05)
        self._wm_opacity.setValue(0.3)
        form.addRow("透明度：", self._wm_opacity)
        self._wm_pos = QComboBox()
        self._wm_pos.addItems(["center", "top-left", "top-right", "bottom-left", "bottom-right"])
        form.addRow("位置：", self._wm_pos)
        return w

    def _build_hf_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._hf_header = QLineEdit()
        self._hf_header.setPlaceholderText("{page}/{total} {date}")
        form.addRow("頁首：", self._hf_header)
        self._hf_footer = QLineEdit()
        self._hf_footer.setPlaceholderText("第 {page} 頁，共 {total} 頁")
        form.addRow("頁尾：", self._hf_footer)
        return w

    def _build_bates_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._bates_prefix = QLineEdit("BATES-")
        form.addRow("前綴：", self._bates_prefix)
        self._bates_start = QSpinBox()
        self._bates_start.setRange(1, 999999)
        self._bates_start.setValue(1)
        form.addRow("起始編號：", self._bates_start)
        self._bates_digits = QSpinBox()
        self._bates_digits.setRange(1, 10)
        self._bates_digits.setValue(6)
        form.addRow("位數：", self._bates_digits)
        self._bates_pos = QComboBox()
        self._bates_pos.addItems(["bottom-right", "bottom-left", "top-right", "top-left"])
        form.addRow("位置：", self._bates_pos)
        return w

    def _build_split_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._split_n = QSpinBox()
        self._split_n.setRange(1, 9999)
        self._split_n.setValue(1)
        form.addRow("每個檔案頁數：", self._split_n)
        return w

    def _on_op_changed(self, idx: int):
        self._stacked.setCurrentIndex(idx)

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
        if self.running_workers():
            return
        if not self._files:
            QMessageBox.warning(self, "錯誤", "請先加入 PDF 檔案")
            return
        if not self._outdir_path:
            QMessageBox.warning(self, "錯誤", "請選擇輸出目錄")
            return

        op_label = self._op_combo.currentText()
        op_key = self._OP_MAP.get(op_label, "optimize")

        params = self._collect_params(op_key)
        params['output_dir'] = self._outdir_path
        if op_key == 'encrypt':
            params.update(owner_password=self._encrypt_owner.text(), user_password=self._encrypt_user.text())
            if not params['owner_password']:
                QMessageBox.warning(self, '密碼未設定', '請指定擁有者密碼，再執行批次加密。')
                return
        files_in_outdir = list(self._files)

        self._progress.setMaximum(len(files_in_outdir))
        self._worker = _BatchWorker(files_in_outdir, op_key, params, self)
        self._worker.progress.connect(lambda i, t, n: (
            self._progress.setValue(i),
            self._status_lbl.setText(f"處理中：{n}"),
        ))
        self._worker.finished.connect(self._on_batch_done)
        self._worker.start()

    def _collect_params(self, op_key: str) -> dict:
        if op_key == "watermark":
            return {
                "text": self._wm_text.text(),
                "opacity": self._wm_opacity.value(),
                "position": self._wm_pos.currentText(),
            }
        elif op_key == "header_footer":
            return {
                "header": self._hf_header.text(),
                "footer": self._hf_footer.text(),
            }
        elif op_key == "bates":
            return {
                "prefix": self._bates_prefix.text(),
                "start": self._bates_start.value(),
                "digits": self._bates_digits.value(),
                "position": self._bates_pos.currentText(),
            }
        elif op_key == "split":
            return {"pages_per_file": self._split_n.value()}
        return {}

    def _on_batch_done(self, results: list):
        errors = [r for r in results if not r.get("ok")]
        total = len(results)
        if errors:
            QMessageBox.warning(
                self, "部分失敗",
                f"完成 {total - len(errors)}/{total}，失敗：\n" +
                "\n".join(r.get("error", "") for r in errors[:5])
            )
        else:
            QMessageBox.information(self, "完成", f"批次處理完成（{total} 個檔案）")
        self.accept()
