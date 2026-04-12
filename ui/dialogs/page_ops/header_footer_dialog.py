# ~/Desktop/acropdf/ui/dialogs/page_ops/header_footer_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,
    QGroupBox, QFormLayout, QDialogButtonBox,
    QComboBox, QSpinBox, QCheckBox, QDoubleSpinBox
)


class HeaderFooterDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("新增頁首 / 頁尾")
        self.resize(480, 380)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        hdr_grp = QGroupBox("頁首")
        hdr_form = QFormLayout(hdr_grp)
        self._hdr_left   = QLineEdit(); self._hdr_left.setPlaceholderText("左側文字")
        self._hdr_center = QLineEdit(); self._hdr_center.setPlaceholderText("中央文字")
        self._hdr_right  = QLineEdit(); self._hdr_right.setPlaceholderText("右側文字（可用 <<n>> 作頁碼）")
        hdr_form.addRow("左：",   self._hdr_left)
        hdr_form.addRow("中：",   self._hdr_center)
        hdr_form.addRow("右：",   self._hdr_right)
        layout.addWidget(hdr_grp)

        ftr_grp = QGroupBox("頁尾")
        ftr_form = QFormLayout(ftr_grp)
        self._ftr_left   = QLineEdit(); self._ftr_left.setPlaceholderText("左側文字")
        self._ftr_center = QLineEdit(); self._ftr_center.setPlaceholderText("中央文字（可用 <<n>> 作頁碼）")
        self._ftr_right  = QLineEdit(); self._ftr_right.setPlaceholderText("右側文字")
        ftr_form.addRow("左：",   self._ftr_left)
        ftr_form.addRow("中：",   self._ftr_center)
        ftr_form.addRow("右：",   self._ftr_right)
        layout.addWidget(ftr_grp)

        fmt_grp = QGroupBox("格式")
        fmt_form = QFormLayout(fmt_grp)
        self._font_size = QSpinBox(); self._font_size.setRange(6, 36); self._font_size.setValue(10)
        self._margin = QDoubleSpinBox(); self._margin.setRange(0.0, 100.0); self._margin.setValue(20.0)
        self._margin.setSuffix(" pt")
        fmt_form.addRow("字體大小：", self._font_size)
        fmt_form.addRow("邊距：",     self._margin)
        layout.addWidget(fmt_grp)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply(self):
        try:
            parts = []
            for t in [self._hdr_left.text(), self._hdr_center.text(), self._hdr_right.text()]:
                if t:
                    parts.append(t)
            header = "  ".join(parts) if parts else ""

            fparts = []
            for t in [self._ftr_left.text(), self._ftr_center.text(), self._ftr_right.text()]:
                if t:
                    fparts.append(t)
            footer = "  ".join(fparts) if fparts else ""

            self._doc.pages.add_header_footer(
                header=header,
                footer=footer,
                fontsize=float(self._font_size.value()),
            )
            QMessageBox.information(self, "完成", "頁首/頁尾已套用")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))
