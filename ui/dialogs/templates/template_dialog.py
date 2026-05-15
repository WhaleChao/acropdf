# ~/Desktop/acropdf/ui/dialogs/templates/template_dialog.py
"""
文件範本管理對話框 — 瀏覽範本、從範本建立新文件、儲存目前文件為範本。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QInputDialog, QMessageBox, QFormLayout, QLineEdit,
    QGroupBox, QFileDialog
)
from PyQt6.QtCore import Qt


class TemplateDialog(QDialog):
    def __init__(self, doc=None, parent=None):
        super().__init__(parent)
        self._doc = doc          # 目前開啟的文件（可為 None）
        self.setWindowTitle("文件範本")
        self.resize(540, 460)
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 範本清單
        list_group = QGroupBox("可用範本")
        list_layout = QVBoxLayout(list_group)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._create_from_template)
        list_layout.addWidget(self._list)
        layout.addWidget(list_group)

        # 按鈕列
        btn_row = QHBoxLayout()
        self._create_btn = QPushButton("從範本建立文件…")
        self._create_btn.setEnabled(False)
        self._create_btn.clicked.connect(self._create_from_template)

        self._save_btn = QPushButton("儲存目前文件為範本…")
        self._save_btn.setEnabled(self._doc is not None)
        self._save_btn.clicked.connect(self._save_as_template)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self._create_btn)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        hint = QLabel("雙擊範本可從中建立新文件；亦可將目前文件存為範本供日後使用。")
        hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _refresh_list(self):
        from core.template_engine import TemplateEngine
        self._engine = TemplateEngine()
        self._templates = self._engine.list_templates()
        self._list.clear()
        if not self._templates:
            self._list.addItem(QListWidgetItem("（目前沒有任何範本）"))
            return
        for tmpl in self._templates:
            item = QListWidgetItem(f"[{tmpl['category']}] {tmpl['name']}")
            item.setData(Qt.ItemDataRole.UserRole, tmpl)
            self._list.addItem(item)

    def _on_selection_changed(self, row: int):
        has_tmpl = row >= 0 and self._templates
        self._create_btn.setEnabled(has_tmpl)

    def _create_from_template(self):
        item = self._list.currentItem()
        if not item:
            return
        tmpl = item.data(Qt.ItemDataRole.UserRole)
        if not tmpl:
            return

        variables = tmpl.get("variables", [])
        data = {}
        for var in variables:
            val, ok = QInputDialog.getText(self, "填入欄位", f"{var}：")
            if not ok:
                return
            data[var] = val

        save_path, _ = QFileDialog.getSaveFileName(
            self, "儲存新文件", tmpl["name"] + ".pdf", "PDF 檔案 (*.pdf)"
        )
        if not save_path:
            return

        try:
            new_doc = self._engine.create_from_template(tmpl["name"], data)
            new_doc.save(save_path, garbage=4, deflate=True)
            new_doc.close()
            QMessageBox.information(self, "完成",
                f"已從範本「{tmpl['name']}」建立文件：\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _save_as_template(self):
        if not self._doc or not self._doc.fitz_doc:
            QMessageBox.warning(self, "提示", "請先開啟文件")
            return

        name, ok = QInputDialog.getText(self, "範本名稱", "輸入範本名稱：")
        if not ok or not name.strip():
            return

        category, ok = QInputDialog.getText(
            self, "範本分類", "分類（例：合約、書狀、通知…）：", text="其他"
        )
        if not ok:
            return

        vars_str, ok = QInputDialog.getText(
            self, "變數欄位",
            "可替換的變數名稱（以逗號分隔，例：당事人,日期）：\n"
            "在範本 PDF 中以 {變數名} 標示佔位符。",
            text=""
        )
        variables = [v.strip() for v in vars_str.split(",") if v.strip()] if vars_str else []

        try:
            self._engine.save_as_template(
                self._doc.fitz_doc, name.strip(), category.strip(), variables
            )
            QMessageBox.information(self, "完成", f"已儲存為範本「{name.strip()}」")
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))
