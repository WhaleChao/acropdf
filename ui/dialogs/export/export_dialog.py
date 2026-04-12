# ~/Desktop/acropdf/ui/dialogs/export/export_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QComboBox,
    QGroupBox, QFormLayout, QDialogButtonBox, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt


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

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._export)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._save_path = None

    def _browse(self):
        filt = self.FORMAT_FILTERS.get(self._fmt, "所有檔案 (*.*)")
        path, _ = QFileDialog.getSaveFileName(self, "儲存匯出檔案", "", filt)
        if path:
            self._save_path = path
            self._out_path.setText(path)

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
