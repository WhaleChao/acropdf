# ~/Desktop/acropdf/ui/dialogs/export/pdfx_dialog.py
"""PDF/X 匯出對話框 — 將文件匯出為 PDF/X 相容格式。"""

from pathlib import Path
from typing import Optional

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QMessageBox, QFileDialog, QComboBox,
    QDialogButtonBox, QLineEdit,
)
from PyQt6.QtCore import Qt


# ---------------------------------------------------------------------------
#  合規等級與 Output Intent 設定檔
# ---------------------------------------------------------------------------

COMPLIANCE_LEVELS = {"PDF/X-1a:2001": "1", "PDF/X-3:2002": "3", "PDF/X-4": "4"}

# ---------------------------------------------------------------------------
#  對話框
# ---------------------------------------------------------------------------

from ui.widgets.worker_dialog import WorkerDialog


class PDFXDialog(WorkerDialog):
    """PDF/X 匯出對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._worker = None
        self._image_results: list[dict] = []
        self.setWindowTitle("匯出 PDF/X")
        self.resize(580, 520)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # --- 合規等級 ---
        comply_group = QGroupBox("合規設定")
        comply_form = QFormLayout(comply_group)

        self._level_combo = QComboBox()
        for key in COMPLIANCE_LEVELS:
            self._level_combo.addItem(key)
        self._level_combo.setCurrentIndex(2)  # 預設 PDF/X-4
        comply_form.addRow("合規等級：", self._level_combo)

        self._icc_path = QLineEdit()
        self._icc_path.setPlaceholderText("選擇印刷廠提供的 CMYK ICC 檔案")
        icc_row = QHBoxLayout(); icc_row.addWidget(self._icc_path)
        browse = QPushButton("選擇 ICC…"); browse.clicked.connect(self._browse_icc); icc_row.addWidget(browse)
        comply_form.addRow("印刷描述檔：", icc_row)
        notice = QLabel("ICC 必須符合實際印刷條件。轉換後檢查描述檔、頁面邊界、字型與渲染；交印前仍應使用印刷廠的 PDF/X 檢查設定。")
        notice.setWordWrap(True); comply_form.addRow(notice)

        root.addWidget(comply_group)

        # --- 影像檢查 ---
        img_group = QGroupBox("影像解析度檢查")
        img_layout = QVBoxLayout(img_group)

        check_row = QHBoxLayout()
        self._check_btn = QPushButton("檢查影像")
        self._check_btn.clicked.connect(self._run_image_check)
        check_row.addWidget(self._check_btn)
        check_row.addStretch()
        img_layout.addLayout(check_row)

        self._img_progress = QProgressBar()
        self._img_progress.setRange(0, 100)
        self._img_progress.setValue(0)
        self._img_progress.hide()
        img_layout.addWidget(self._img_progress)

        self._img_report = QTextEdit()
        self._img_report.setReadOnly(True)
        self._img_report.setPlaceholderText("按「檢查影像」以掃描文件中的影像解析度⋯⋯")
        self._img_report.setMaximumHeight(150)
        img_layout.addWidget(self._img_report)

        root.addWidget(img_group)

        # --- 色彩空間資訊 ---
        color_group = QGroupBox("色彩空間資訊")
        color_layout = QVBoxLayout(color_group)
        self._color_label = QLabel()
        self._color_label.setWordWrap(True)
        self._refresh_color_info()
        color_layout.addWidget(self._color_label)
        root.addWidget(color_group)

        # --- 底部按鈕 ---
        btn_row = QHBoxLayout()

        self._export_btn = QPushButton("匯出")
        self._export_btn.clicked.connect(self._export)
        btn_row.addWidget(self._export_btn)

        btn_row.addStretch()

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # -- 色彩空間 --

    def _refresh_color_info(self):
        """掃描首頁色彩空間資訊（概略）。"""
        fitz_doc = self._doc.fitz_doc
        if self._doc.page_count == 0:
            self._color_label.setText("文件無頁面。")
            return

        color_spaces = set()
        try:
            for page_idx in range(min(self._doc.page_count, 5)):
                page = fitz_doc[page_idx]
                images = page.get_images(full=True)
                for img_info in images:
                    cs_name = img_info[5] if len(img_info) > 5 else ""
                    if cs_name:
                        color_spaces.add(cs_name)
        except Exception:
            pass

        if color_spaces:
            cs_list = "、".join(sorted(color_spaces))
            self._color_label.setText(f"偵測到的色彩空間（前 5 頁）：{cs_list}")
        else:
            self._color_label.setText("未偵測到嵌入影像或無法判別色彩空間。")

    # -- 影像解析度檢查 --

    def _run_image_check(self):
        if self.running_workers():
            return

        self._check_btn.setEnabled(False)
        self._img_progress.show()
        self._img_progress.setValue(0)
        self._img_report.clear()

        from core.image_inspection import inspect_images
        from ui.widgets.operation_worker import OperationWorker
        self._worker = OperationWorker(
            self._doc,
            lambda doc: inspect_images(doc.fitz_doc, self._worker.isInterruptionRequested),
            self,
        )
        self._img_progress.setRange(0, 0)
        self._worker.succeeded.connect(self._on_check_finished)
        self._worker.failed.connect(self._on_check_failed)
        self._worker.finished.connect(lambda: self._check_btn.setEnabled(True))
        self._worker.finished.connect(self._img_progress.hide)
        self._worker.start()

    def _on_check_failed(self, message):
        self._img_report.setPlainText(f"影像檢查未完成：{message}")

    def _on_check_finished(self, results: list):
        self._image_results = results
        self._check_btn.setEnabled(True)
        self._img_progress.hide()

        if not results:
            self._img_report.setPlainText("文件中未偵測到影像。")
            return

        low_dpi = [r for r in results if min(r["dpi_x"], r["dpi_y"]) < 300]
        lines = [
            f"共掃描 {len(results)} 處影像呈現位置。",
        ]

        if low_dpi:
            lines.append(f"警告：{len(low_dpi)} 張影像解析度低於 300 DPI：")
            lines.append("")
            for r in low_dpi:
                lines.append(
                    f"  第 {r['page'] + 1} 頁 — {r['width']}x{r['height']} px, "
                    f"約 {r['dpi_x']:.0f}×{r['dpi_y']:.0f} DPI"
                )
        else:
            lines.append("所有影像解析度均達 300 DPI 以上。")

        self._img_report.setPlainText("\n".join(lines))

    # -- 匯出 --

    def _browse_icc(self):
        path, _ = QFileDialog.getOpenFileName(self, "選擇 CMYK 描述檔", "", "ICC 描述檔 (*.icc *.icm)")
        if path: self._icc_path.setText(path)

    def _export(self):
        if self.running_workers(): return
        if not self._icc_path.text().strip():
            QMessageBox.warning(self, "需要印刷設定", "請先選擇印刷廠指定的 CMYK ICC 描述檔。")
            return
        allow = False
        if self._doc.is_encrypted:
            allow = QMessageBox.question(self, "輸出未加密副本", "PDF/X 不允許加密，是否輸出未加密副本？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
            if not allow: return
        path, _ = QFileDialog.getSaveFileName(self, "匯出 PDF/X", str(Path(self._doc.source_path or str(Path.home()/"Documents/document.pdf")).with_name("print-ready.pdf")), "PDF (*.pdf)")
        if not path: return
        from ui.widgets.operation_worker import OperationWorker
        from core.pdf_standards import PDFStandards
        # The worker owns an authenticated private snapshot; no cross-thread live document access.
        icc = self._icc_path.text(); level = COMPLIANCE_LEVELS[self._level_combo.currentText()]
        self._worker = OperationWorker(self._doc, lambda doc: PDFStandards(doc).export_pdfx(path, icc, level, allow), self)
        self._export_btn.setEnabled(False)
        self._worker.succeeded.connect(lambda report: QMessageBox.information(self, "轉換完成", f"已儲存 {report['level']}：\n{path}\nICC、字型、頁面邊界及渲染檢查通過。"))
        self._worker.failed.connect(lambda message: QMessageBox.critical(self, "轉換失敗", message))
        self._worker.finished.connect(lambda: self._export_btn.setEnabled(True))
        self._worker.start()
