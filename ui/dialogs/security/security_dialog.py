# ~/Desktop/acropdf/ui/dialogs/security/security_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                              QCheckBox, QPushButton, QFileDialog, QMessageBox,
                              QGroupBox, QHBoxLayout)

class SecurityDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("安全性設定")
        self.resize(400, 350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 目前狀態
        info = self._doc.security.get_permissions()
        status = "已加密" if self._doc.security.is_encrypted() else "未加密"
        layout.addWidget(__import__('PyQt6.QtWidgets', fromlist=['QLabel']).QLabel(f"目前狀態：{status}"))

        # 密碼設定
        pw_group = QGroupBox("設定密碼")
        pw_layout = QFormLayout(pw_group)
        self._owner_pw = QLineEdit()
        self._owner_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._user_pw = QLineEdit()
        self._user_pw.setEchoMode(QLineEdit.EchoMode.Password)
        pw_layout.addRow("擁有者密碼（管理員）：", self._owner_pw)
        pw_layout.addRow("開啟密碼（使用者）：", self._user_pw)
        layout.addWidget(pw_group)

        # 權限
        perm_group = QGroupBox("使用者權限")
        perm_layout = QVBoxLayout(perm_group)
        self._perm_print = QCheckBox("允許列印")
        self._perm_copy = QCheckBox("允許複製文字")
        self._perm_edit = QCheckBox("允許編輯")
        self._perm_annotate = QCheckBox("允許標注")
        self._perm_print.setChecked(info.get("print", True))
        self._perm_copy.setChecked(info.get("copy", True))
        self._perm_edit.setChecked(info.get("modify", False))
        self._perm_annotate.setChecked(info.get("annotate", True))
        for cb in [self._perm_print, self._perm_copy, self._perm_edit, self._perm_annotate]:
            perm_layout.addWidget(cb)
        layout.addWidget(perm_group)

        # 按鈕
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("套用並另存新檔...")
        remove_btn = QPushButton("移除安全性...")
        cancel_btn = QPushButton("取消")
        apply_btn.clicked.connect(self._apply)
        remove_btn.clicked.connect(self._remove)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        out, _ = QFileDialog.getSaveFileName(self, "另存新檔", "", "PDF 檔案 (*.pdf)")
        if not out:
            return
        try:
            self._doc.security.encrypt(
                out,
                owner_pw=self._owner_pw.text(),
                user_pw=self._user_pw.text(),
                allow_print=self._perm_print.isChecked(),
                allow_copy=self._perm_copy.isChecked(),
                allow_edit=self._perm_edit.isChecked(),
                allow_annotate=self._perm_annotate.isChecked(),
            )
            QMessageBox.information(self, "完成", "安全性設定已套用")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _remove(self):
        out, _ = QFileDialog.getSaveFileName(self, "另存新檔", "", "PDF 檔案 (*.pdf)")
        if out:
            try:
                self._doc.security.remove_security(out)
                QMessageBox.information(self, "完成", "安全性已移除")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "錯誤", str(e))
