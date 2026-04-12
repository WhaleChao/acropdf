# ~/Desktop/acropdf/ui/dialogs/optimize/optimize_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QMessageBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QCheckBox, QComboBox, QFileDialog
)


class OptimizeDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("優化 PDF")
        self.resize(400, 280)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        grp = QGroupBox("優化選項")
        form = QFormLayout(grp)

        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(["輕度（保留品質）", "標準", "強力（最小體積）"])
        self._cmb_preset.setCurrentIndex(1)
        form.addRow("壓縮等級：", self._cmb_preset)

        self._chk_img = QCheckBox("壓縮圖片")
        self._chk_img.setChecked(True)
        self._chk_font = QCheckBox("子集化字型")
        self._chk_font.setChecked(True)
        self._chk_meta = QCheckBox("移除隱藏資料（metadata / 縮圖）")
        self._chk_linearize = QCheckBox("線性化（Web 最佳化）")
        form.addRow(self._chk_img)
        form.addRow(self._chk_font)
        form.addRow(self._chk_meta)
        form.addRow(self._chk_linearize)
        layout.addWidget(grp)

        self._size_lbl = QLabel()
        if self._doc and self._doc.path:
            import os
            sz = os.path.getsize(self._doc.path)
            self._size_lbl.setText(f"目前大小：{sz/1024:.1f} KB")
        layout.addWidget(self._size_lbl)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._optimize)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _optimize(self):
        try:
            preset = self._cmb_preset.currentIndex()
            path, _ = QFileDialog.getSaveFileName(
                self, "另存優化後的 PDF", "", "PDF (*.pdf)"
            )
            if not path:
                return
            self._doc.optimize.optimize(
                path,
                compress_images=self._chk_img.isChecked(),
                subset_fonts=self._chk_font.isChecked(),
                remove_metadata=self._chk_meta.isChecked(),
                linearize=self._chk_linearize.isChecked(),
                preset=preset,
            )
            import os
            sz = os.path.getsize(path)
            QMessageBox.information(
                self, "完成",
                f"優化完成！\n輸出大小：{sz/1024:.1f} KB\n儲存至：{path}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "優化失敗", str(e))
