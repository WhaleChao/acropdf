# ~/Desktop/acropdf/ui/dialogs/compare/compare_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QDialogButtonBox,
    QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt


class CompareDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件比較")
        self.resize(500, 300)
        self._path_a = None
        self._path_b = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        grp = QGroupBox("選擇比較文件")
        form = QFormLayout(grp)

        self._lbl_a = QLabel("（未選擇）")
        btn_a = QPushButton("選擇文件 A...")
        btn_a.clicked.connect(lambda: self._pick(True))
        row_a = QHBoxLayout()
        row_a.addWidget(self._lbl_a)
        row_a.addWidget(btn_a)
        form.addRow("原始文件：", row_a)

        self._lbl_b = QLabel("（未選擇）")
        btn_b = QPushButton("選擇文件 B...")
        btn_b.clicked.connect(lambda: self._pick(False))
        row_b = QHBoxLayout()
        row_b.addWidget(self._lbl_b)
        row_b.addWidget(btn_b)
        form.addRow("修訂文件：", row_b)

        layout.addWidget(grp)

        opt_grp = QGroupBox("比較選項")
        opt_layout = QVBoxLayout(opt_grp)
        self._chk_text = QCheckBox("文字差異")
        self._chk_text.setChecked(True)
        self._chk_visual = QCheckBox("視覺差異（像素比對）")
        self._chk_visual.setChecked(True)
        opt_layout.addWidget(self._chk_text)
        opt_layout.addWidget(self._chk_visual)
        layout.addWidget(opt_grp)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="開始比較", cancel_text="取消")
        ok_btn.clicked.connect(self._compare)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(row)

    def _pick(self, is_a: bool):
        path, _ = QFileDialog.getOpenFileName(self, "選擇 PDF", "", "PDF (*.pdf)")
        if path:
            if is_a:
                self._path_a = path
                self._lbl_a.setText(path)
            else:
                self._path_b = path
                self._lbl_b.setText(path)

    def _compare(self):
        if not self._path_a or not self._path_b:
            QMessageBox.warning(self, "錯誤", "請選擇兩份文件")
            return
        try:
            from core.compare_engine import CompareEngine
            engine = CompareEngine()
            result = engine.compare(
                self._path_a, self._path_b,
                text=self._chk_text.isChecked(),
                visual=self._chk_visual.isChecked(),
            )
            from ui.dialogs.compare.compare_result_dialog import CompareResultDialog
            self.accept()
            dlg = CompareResultDialog(self._path_a, self._path_b, result, self.parent())
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "比較失敗", str(e))
