# ~/Desktop/acropdf/ui/dialogs/export/export_dialog.py
import os
from pathlib import Path
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QComboBox,
    QGroupBox, QFormLayout, QDialogButtonBox, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt


_FORMAT_SUFFIXES = {
    "docx": ".docx",
    "xlsx": ".xlsx",
    "pptx": ".pptx",
    "txt": ".txt",
    "html": ".html",
    "png": ".png",
    "jpg": ".jpg",
    "jpeg": ".jpg",
    "tiff": ".tiff",
    "pdf/a": ".pdf",
    "pdfa": ".pdf",
    "pdf": ".pdf",
}


def default_export_path(doc, fmt: str) -> str:
    """回傳安全的預設匯出路徑，避免打包後落到根目錄。"""
    suffix = _FORMAT_SUFFIXES.get(fmt.lower(), "")
    raw_name = getattr(doc, "display_name", "") or "匯出檔案"
    stem = Path(raw_name).stem or "匯出檔案"
    name = _safe_filename(stem) + suffix
    return str(_default_export_dir(doc) / name)


def ensure_export_suffix(path: str, fmt: str) -> str:
    suffix = _FORMAT_SUFFIXES.get(fmt.lower(), "")
    if suffix and not path.lower().endswith(suffix):
        current_suffix = Path(path).suffix.lower()
        if current_suffix in set(_FORMAT_SUFFIXES.values()):
            return str(Path(path).with_suffix(suffix))
        return path + suffix
    return path


def _default_export_dir(doc) -> Path:
    doc_path = getattr(doc, "path", None)
    if doc_path:
        parent = Path(doc_path).expanduser().parent
        if _is_writable_dir(parent):
            return parent
    for candidate in (
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home(),
    ):
        if _is_writable_dir(candidate):
            return candidate
    return Path.cwd()


def _is_writable_dir(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip().strip(".")
    return cleaned or "匯出檔案"


from ui.widgets.worker_dialog import WorkerDialog


class ExportDialog(WorkerDialog):
    FORMAT_FILTERS = {
        "docx": "Word 文件 (*.docx)",
        "xlsx": "Excel 試算表 (*.xlsx)",
        "pptx": "PowerPoint 簡報 (*.pptx)",
        "txt":  "純文字 (*.txt)",
        "html": "HTML 網頁 (*.html)",
        "png":  "PNG 圖片 (*.png)",
        "jpg":  "JPEG 圖片 (*.jpg)",
        "tiff": "TIFF 圖片 (*.tiff)",
        "pdf/a":"PDF/A 長期保存 (*.pdf)",
        "pdfa": "PDF/A 長期保存 (*.pdf)",
    }

    def __init__(self, doc, fmt: str, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._fmt = fmt
        self.setWindowTitle(f"匯出為 {fmt.upper()}")
        self.resize(440, 260)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        out_group = QGroupBox("輸出設定")
        form = QFormLayout(out_group)

        self._out_path = QLabel("（尚未選擇）")
        browse_btn = QPushButton("選擇路徑...")
        browse_btn.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self._out_path)
        row.addWidget(browse_btn)
        form.addRow("儲存位置：", row)
        layout.addWidget(out_group)

        if self._fmt in ("png", "jpg", "tiff"):
            img_group = QGroupBox("圖片選項")
            img_form = QFormLayout(img_group)
            self._dpi = QSpinBox()
            self._dpi.setRange(72, 600)
            self._dpi.setValue(150)
            img_form.addRow("解析度 (DPI)：", self._dpi)
            layout.addWidget(img_group)

        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="匯出", cancel_text="取消")
        self._export_btn = ok_btn
        ok_btn.clicked.connect(self._export)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

        info = {
            "docx": "以文字與字級為主，複雜版面、表格與圖片可能無法完整保留。",
            "xlsx": "表格轉為儲存格；未偵測到表格的頁面會保留文字。",
            "pptx": "每頁轉為等比例圖片，投影片內文字無法直接編輯。",
            "png": "每頁一張圖片，以選擇的檔名加上 _p001、_p002… 儲存。",
            "jpg": "每頁一張图片，以選擇的檔名加上頁碼儲存。",
            "tiff": "每頁一張 TIFF，以選擇的檔名加上頁碼儲存。",
            "pdf/a": "转為 PDF/A-2b，通過 veraPDF 獨立驗證後儲存。需 Ghostscript 與 Java。",
            "pdfa": "轉為 PDF/A-2b，加入 ICC 與嵌入字型；通過 veraPDF 獨立驗證後才會儲存。需 Ghostscript 與 Java。",
        }.get(self._fmt, "")
        if info:
            notice = QLabel(info); notice.setWordWrap(True); notice.setProperty("role", "muted")
            layout.addWidget(notice)
        self._save_path = None

    def _browse(self):
        filt = self.FORMAT_FILTERS.get(self._fmt, "所有檔案 (*.*)")
        default_path = default_export_path(self._doc, self._fmt)
        path, _ = QFileDialog.getSaveFileName(self, "儲存匯出檔案", default_path, filt)
        if path:
            self._save_path = ensure_export_suffix(path, self._fmt)
            self._out_path.setText(self._save_path)

    def _export(self):
        if self.running_workers(): return
        if not self._save_path:
            QMessageBox.warning(self, "錯誤", "請先選擇儲存路徑")
            return
        allow = False
        if self._fmt in ("pdfa", "pdf/a") and self._doc.is_encrypted:
            allow = QMessageBox.question(self, "PDF/A 不支援加密", "轉換會輸出未加密的 PDF/A 副本。是否繼續？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
            if not allow: return
        from ui.widgets.operation_worker import OperationWorker
        from core.pdf_standards import PDFStandards
        path = self._save_path; fmt = self._fmt
        dpi = self._dpi.value() if hasattr(self, "_dpi") else 150
        def operation(doc):
            if fmt in ("pdfa", "pdf/a"):
                PDFStandards(doc).export_pdfa(path, allow_decryption=allow)
                return path
            return doc.exports.export(path, fmt, dpi=dpi)
        self._worker = OperationWorker(self._doc, operation, self)
        self._export_btn.setEnabled(False)
        self._worker.succeeded.connect(self._export_complete)
        self._worker.failed.connect(lambda message: QMessageBox.critical(self, "匯出失敗", message))
        self._worker.finished.connect(lambda: self._export_btn.setEnabled(True))
        self._worker.start()

    def _export_complete(self, result):
        details = "\n".join(result) if isinstance(result, list) else str(result)
        QMessageBox.information(self, "完成", f"已匯出至\n{details}")
        self.accept()
