# ~/Desktop/acropdf/ui/dialogs/filing/filing_dialog.py
"""
智慧歸檔對話框 — 掃描資料夾、自動分類 PDF，複製歸檔到對應子目錄。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QProgressBar, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor


class _FilingWorker(QThread):
    progress = pyqtSignal(int, int)       # done, total
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, input_dir: str, output_dir: str):
        super().__init__()
        self._input  = input_dir
        self._output = output_dir

    def run(self):
        try:
            from core.smart_filing_engine import SmartFilingEngine
            results = engine.analyze_and_file(self._input, self._output, rules=rules,
                                              progress_callback=self.progress.emit,
                                              is_cancelled=self.isInterruptionRequested)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


from ui.widgets.worker_dialog import WorkerDialog


class FilingDialog(WorkerDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("智慧歸檔")
        self.resize(720, 520)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 來源資料夾
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("來源資料夾："))
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("包含 PDF 的資料夾")
        btn_src = QPushButton("瀏覽…")
        btn_src.setFixedWidth(70)
        btn_src.clicked.connect(lambda: self._browse(self._src_edit))
        row1.addWidget(self._src_edit)
        row1.addWidget(btn_src)
        layout.addLayout(row1)

        # 目標資料夾
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("歸檔目標："))
        self._dst_edit = QLineEdit()
        self._dst_edit.setPlaceholderText("歸檔輸出的根目錄")
        btn_dst = QPushButton("瀏覽…")
        btn_dst.setFixedWidth(70)
        btn_dst.clicked.connect(lambda: self._browse(self._dst_edit))
        row2.addWidget(self._dst_edit)
        row2.addWidget(btn_dst)
        layout.addLayout(row2)

        hint = QLabel("系統會依內容自動分類：判決書 / 書狀 / 合約 / 財務 / 未分類，並移動到對應子目錄。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        layout.addWidget(hint)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # 結果表格
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["檔案名稱", "分類", "輸出路徑"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._run_btn = QPushButton("開始歸檔")
        self._run_btn.setDefault(True)
        self._run_btn.setFixedWidth(100)
        self._run_btn.clicked.connect(self._run)
        close_btn = QPushButton("關閉")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _browse(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "選擇資料夾", edit.text() or "")
        if path:
            edit.setText(path)

    def _run(self):
        if self.running_workers():
            return
        src = self._src_edit.text().strip()
        dst = self._dst_edit.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "提示", "請選擇來源與目標資料夾")
            return

        self._table.setRowCount(0)
        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)

        self._worker = _FilingWorker(src, dst)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, results: list):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._table.setRowCount(len(results))
        for i, r in enumerate(results):
            self._table.setItem(i, 0, QTableWidgetItem(r.get("file", "")))
            cat_item = QTableWidgetItem(r.get("category", "錯誤"))
            if r.get("error"):
                cat_item.setForeground(QColor("#ff453a"))
                cat_item.setText("錯誤：" + r["error"])
            self._table.setItem(i, 1, cat_item)
            self._table.setItem(i, 2, QTableWidgetItem(r.get("output", "")))
        self._table.resizeColumnsToContents()

    def _on_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "錯誤", msg)
