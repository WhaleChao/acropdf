# ~/Desktop/acropdf/ui/dialogs/export/pdfx_dialog.py
"""PDF/X 匯出對話框 — 將文件匯出為 PDF/X 相容格式。"""

from pathlib import Path
from typing import Optional

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QMessageBox, QFileDialog, QComboBox,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


# ---------------------------------------------------------------------------
#  合規等級與 Output Intent 設定檔
# ---------------------------------------------------------------------------

COMPLIANCE_LEVELS = {
    "PDF/X-1a:2003": {
        "version": "PDF/X-1a:2003",
        "gts_key": "GTS_PDFXVersion",
        "gts_value": "(PDF/X-1a:2003)",
        "conformance": "PDF/X-1a:2003",
    },
    "PDF/X-3:2003": {
        "version": "PDF/X-3:2003",
        "gts_key": "GTS_PDFXVersion",
        "gts_value": "(PDF/X-3:2003)",
        "conformance": "PDF/X-3:2003",
    },
    "PDF/X-4": {
        "version": "PDF/X-4",
        "gts_key": "GTS_PDFXVersion",
        "gts_value": "(PDF/X-4)",
        "conformance": "PDF/X-4",
    },
}

OUTPUT_INTENTS = {
    "U.S. Web Coated (SWOP) v2": {
        "identifier": "CGATS TR 001",
        "condition": "SWOP (Publication) printing in USA (Alarm i ng 2.0)",
        "registry": "http://www.color.org",
        "info": "U.S. Web Coated (SWOP) v2",
    },
    "GRACoL 2006 (ISO 12647-2:2004)": {
        "identifier": "CGATS TR 006",
        "condition": "GRACoL2006_Coated1v2",
        "registry": "http://www.color.org",
        "info": "GRACoL 2006 (ISO 12647-2:2004)",
    },
    "ISO Coated v2 (ECI)": {
        "identifier": "ISO Coated v2",
        "condition": "ISOcoated_v2_eci",
        "registry": "http://www.color.org",
        "info": "ISO Coated v2 (ECI)",
    },
    "Japan Color 2001 Coated": {
        "identifier": "JC200103",
        "condition": "JapanColor2001Coated",
        "registry": "http://www.color.org",
        "info": "Japan Color 2001 Coated",
    },
    "ISO Coated v2 300% (ECI)": {
        "identifier": "ISO Coated v2 300",
        "condition": "ISOcoated_v2_300_eci",
        "registry": "http://www.color.org",
        "info": "ISO Coated v2 300% (ECI)",
    },
}


# ---------------------------------------------------------------------------
#  背景執行緒：影像解析度檢查
# ---------------------------------------------------------------------------

class _ImageCheckWorker(QThread):
    """掃描文件中的影像並檢查解析度。"""

    finished = pyqtSignal(list)   # list of dicts: page, xref, width, height, dpi_x, dpi_y
    progress = pyqtSignal(int)

    def __init__(self, fitz_doc, page_count: int, parent=None):
        super().__init__(parent)
        self._fitz_doc = fitz_doc
        self._page_count = page_count

    def run(self):  # noqa: D401
        results = []
        for page_idx in range(self._page_count):
            pct = int(100 * page_idx / max(self._page_count, 1))
            self.progress.emit(pct)

            page = self._fitz_doc[page_idx]
            image_list = page.get_images(full=True)

            for img_info in image_list:
                xref = img_info[0]
                try:
                    img_dict = self._fitz_doc.extract_image(xref)
                    if not img_dict:
                        continue

                    pix_w = img_dict.get("width", 0)
                    pix_h = img_dict.get("height", 0)

                    # 嘗試計算 DPI：pixel / (bbox size in inches)
                    # 取得此影像在頁面上的呈現大小
                    img_rects = page.get_image_rects(xref)
                    if img_rects:
                        rect = img_rects[0]
                        # PDF 單位為 72 pt/inch
                        display_w_in = rect.width / 72.0
                        display_h_in = rect.height / 72.0

                        dpi_x = int(pix_w / display_w_in) if display_w_in > 0 else 0
                        dpi_y = int(pix_h / display_h_in) if display_h_in > 0 else 0
                    else:
                        dpi_x = 0
                        dpi_y = 0

                    results.append({
                        "page": page_idx + 1,
                        "xref": xref,
                        "width": pix_w,
                        "height": pix_h,
                        "dpi_x": dpi_x,
                        "dpi_y": dpi_y,
                    })
                except Exception:
                    continue

        self.progress.emit(100)
        self.finished.emit(results)


# ---------------------------------------------------------------------------
#  對話框
# ---------------------------------------------------------------------------

class PDFXDialog(QDialog):
    """PDF/X 匯出對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._worker: Optional[_ImageCheckWorker] = None
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

        self._intent_combo = QComboBox()
        for key in OUTPUT_INTENTS:
            self._intent_combo.addItem(key)
        comply_form.addRow("輸出描述檔：", self._intent_combo)

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
                    cs_name = img_info[1] if len(img_info) > 1 else ""
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
        if self._worker and self._worker.isRunning():
            return

        self._check_btn.setEnabled(False)
        self._img_progress.show()
        self._img_progress.setValue(0)
        self._img_report.clear()

        self._worker = _ImageCheckWorker(
            self._doc.fitz_doc, self._doc.page_count, self
        )
        self._worker.progress.connect(self._img_progress.setValue)
        self._worker.finished.connect(self._on_check_finished)
        self._worker.start()

    def _on_check_finished(self, results: list):
        self._image_results = results
        self._check_btn.setEnabled(True)
        self._img_progress.hide()

        if not results:
            self._img_report.setPlainText("文件中未偵測到影像。")
            return

        low_dpi = [r for r in results if r["dpi_x"] > 0 and r["dpi_x"] < 300]
        lines = [
            f"共掃描 {len(results)} 張影像。",
        ]

        if low_dpi:
            lines.append(f"警告：{len(low_dpi)} 張影像解析度低於 300 DPI：")
            lines.append("")
            for r in low_dpi:
                lines.append(
                    f"  第 {r['page']} 頁 — {r['width']}x{r['height']} px, "
                    f"約 {r['dpi_x']}x{r['dpi_y']} DPI"
                )
        else:
            lines.append("所有影像解析度均達 300 DPI 以上。")

        self._img_report.setPlainText("\n".join(lines))

    # -- 匯出 --

    def _export(self):
        # 如果有低解析度影像，先警告
        if self._image_results:
            low = [r for r in self._image_results if 0 < r["dpi_x"] < 300]
            if low:
                reply = QMessageBox.question(
                    self, "低解析度警告",
                    f"文件中有 {len(low)} 張影像解析度低於 300 DPI。\n"
                    "仍要繼續匯出嗎？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        path, _ = QFileDialog.getSaveFileName(
            self, "匯出 PDF/X", "", "PDF 檔案 (*.pdf)"
        )
        if not path:
            return

        level_key = self._level_combo.currentText()
        intent_key = self._intent_combo.currentText()
        level_info = COMPLIANCE_LEVELS[level_key]
        intent_info = OUTPUT_INTENTS[intent_key]

        try:
            fitz_doc = self._doc.fitz_doc

            # --- 設定 GTS_PDFXVersion ---
            cat_xref = fitz_doc.pdf_catalog()

            fitz_doc.xref_set_key(
                cat_xref,
                level_info["gts_key"],
                level_info["gts_value"],
            )

            # --- 建立 OutputIntent 字典 ---
            oi_xref = fitz_doc.get_new_xref()
            oi_dict = (
                f"<< /Type /OutputIntent "
                f"/S /GTS_PDFX "
                f"/OutputConditionIdentifier ({intent_info['identifier']}) "
                f"/OutputCondition ({intent_info['condition']}) "
                f"/RegistryName ({intent_info['registry']}) "
                f"/Info ({intent_info['info']}) "
                f">>"
            )
            fitz_doc.update_object(oi_xref, oi_dict)

            # --- 將 OutputIntent 加入 Catalog 的 /OutputIntents 陣列 ---
            existing_intents = fitz_doc.xref_get_key(cat_xref, "OutputIntents")
            if existing_intents[0] == "null" or existing_intents[1] == "null":
                fitz_doc.xref_set_key(
                    cat_xref,
                    "OutputIntents",
                    f"[{oi_xref} 0 R]",
                )
            else:
                # 附加到現有陣列
                arr = existing_intents[1].strip()
                if arr.startswith("[") and arr.endswith("]"):
                    inner = arr[1:-1].strip()
                    fitz_doc.xref_set_key(
                        cat_xref,
                        "OutputIntents",
                        f"[{inner} {oi_xref} 0 R]",
                    )
                else:
                    fitz_doc.xref_set_key(
                        cat_xref,
                        "OutputIntents",
                        f"[{oi_xref} 0 R]",
                    )

            # --- 設定 PDF 中繼資料 ---
            meta = fitz_doc.metadata or {}
            meta["trapped"] = "False"
            fitz_doc.set_metadata(meta)

            # --- 儲存 ---
            fitz_doc.save(
                path,
                garbage=3,
                deflate=True,
                clean=True,
            )

            QMessageBox.information(
                self, "完成",
                f"已匯出 {level_key} 格式至\n{path}",
            )

        except Exception as exc:
            QMessageBox.critical(self, "匯出失敗", str(exc))
