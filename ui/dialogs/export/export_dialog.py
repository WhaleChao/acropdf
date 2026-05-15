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


class ExportDialog(QDialog):
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
        ok_btn.clicked.connect(self._export)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

        self._save_path = None

    def _browse(self):
        filt = self.FORMAT_FILTERS.get(self._fmt, "所有檔案 (*.*)")
        default_path = default_export_path(self._doc, self._fmt)
        path, _ = QFileDialog.getSaveFileName(self, "儲存匯出檔案", default_path, filt)
        if path:
            self._save_path = ensure_export_suffix(path, self._fmt)
            self._out_path.setText(self._save_path)

    def _export(self):
        if not self._save_path:
            QMessageBox.warning(self, "錯誤", "請先選擇儲存路徑")
            return
        try:
            dpi = getattr(self, "_dpi", None)
            dpi_val = dpi.value() if dpi else 150
            self._doc.exports.export(self._save_path, self._fmt, dpi=dpi_val)
            QMessageBox.information(self, "完成", f"已匯出至\n{self._save_path}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗", str(e))
