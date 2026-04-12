# ~/Desktop/acropdf/ui/dialogs/signature/sign_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt


class SignDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("數位簽章")
        self.resize(480, 320)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        cert_group = QGroupBox("憑證設定")
        form = QFormLayout(cert_group)
        self._cert_path = QLineEdit()
        self._cert_path.setPlaceholderText("選擇 PFX/P12 憑證檔案...")
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._browse_cert)
        cert_row = QHBoxLayout()
        cert_row.addWidget(self._cert_path)
        cert_row.addWidget(browse_btn)
        form.addRow("憑證檔案：", cert_row)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("憑證密碼")
        form.addRow("密碼：", self._password)

        layout.addWidget(cert_group)

        sig_group = QGroupBox("簽章資訊")
        sig_form = QFormLayout(sig_group)
        self._reason = QLineEdit()
        self._reason.setPlaceholderText("例如：我已閱讀並同意本文件")
        sig_form.addRow("理由：", self._reason)
        self._location = QLineEdit()
        self._location.setPlaceholderText("例如：台北市")
        sig_form.addRow("地點：", self._location)
        layout.addWidget(sig_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._sign)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse_cert(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇憑證", "", "憑證檔案 (*.pfx *.p12)"
        )
        if path:
            self._cert_path.setText(path)

    def _sign(self):
        cert = self._cert_path.text().strip()
        pwd = self._password.text()
        if not cert:
            QMessageBox.warning(self, "錯誤", "請選擇憑證檔案")
            return
        if not self._doc.path:
            QMessageBox.warning(self, "錯誤", "請先將文件儲存成 PDF 後再簽章")
            return
        try:
            out_path, _ = QFileDialog.getSaveFileName(
                self, "儲存已簽章 PDF", "", "PDF (*.pdf)"
            )
            if not out_path:
                return
            ok = self._doc.signatures.sign_pdf(
                input_path=self._doc.path,
                output_path=out_path,
                cert_path=cert,
                cert_password=pwd.encode("utf-8"),
                reason=self._reason.text() or "數位簽章",
                location=self._location.text() or "",
            )
            if not ok:
                raise RuntimeError("簽章失敗，請確認憑證與 pyHanko 設定")
            QMessageBox.information(self, "完成", "簽章成功")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "簽章失敗", str(e))
