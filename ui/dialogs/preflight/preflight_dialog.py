# ~/Desktop/acropdf/ui/dialogs/preflight/preflight_dialog.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from core.preflight_engine import PreflightEngine, PreflightReport


class _PreflightWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, fitz_doc, profile, parent=None):
        super().__init__(parent)
        self._doc = fitz_doc
        self._profile = profile

    def run(self):
        engine = PreflightEngine()
        report = engine.full_preflight(self._doc, self._profile)
        self.finished.emit(report)


from ui.widgets.worker_dialog import WorkerDialog


class PreflightDialog(WorkerDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._report: PreflightReport | None = None
        self.setWindowTitle("預檢工具")
        self.resize(800, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("預設設定檔："))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems(list(PreflightEngine.PROFILES.keys()))
        self._profile_combo.addItem("自訂")
        top.addWidget(self._profile_combo)
        top.addStretch()
        run_btn = QPushButton("執行預檢")
        run_btn.clicked.connect(self._run)
        top.addWidget(run_btn)
        layout.addLayout(top)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        layout.addWidget(self._progress)

        # 結果樹狀
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["嚴重度", "類別", "頁面", "訊息", "可修正"])
        self._tree.setColumnWidth(0, 70)
        self._tree.setColumnWidth(1, 70)
        self._tree.setColumnWidth(2, 50)
        self._tree.setColumnWidth(3, 380)
        layout.addWidget(self._tree)

        # 摘要
        self._summary_lbl = QLabel("")
        layout.addWidget(self._summary_lbl)

        # 底部按鈕
        bottom = QHBoxLayout()
        self._fix_btn = QPushButton("自動修正所有可修正項目")
        self._fix_btn.setEnabled(False)
        self._fix_btn.clicked.connect(self._auto_fix)
        bottom.addWidget(self._fix_btn)
        export_btn = QPushButton("匯出報告 PDF...")
        export_btn.clicked.connect(self._export)
        bottom.addWidget(export_btn)
        bottom.addStretch()
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _run(self):
        if self.running_workers():
            return
        if self._doc.fitz_doc is None:
            QMessageBox.warning(self, "錯誤", "請先開啟 PDF 文件")
            return
        profile = self._profile_combo.currentText()
        if profile == "自訂":
            profile = "高品質列印"
        self._progress.show()
        self._tree.clear()
        from ui.widgets.operation_worker import OperationWorker
        self._worker = OperationWorker(self._doc, lambda doc: PreflightEngine().full_preflight(doc.fitz_doc, profile), self)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(lambda message: QMessageBox.critical(self, "預檢失敗", message))
        self._worker.finished.connect(self._progress.hide)
        self._worker.start()

    def _on_done(self, report: PreflightReport):
        self._progress.hide()
        self._report = report
        self._tree.clear()

        category_items: dict[str, QTreeWidgetItem] = {}
        for issue in report.issues:
            cat = issue.category
            if cat not in category_items:
                parent = QTreeWidgetItem(self._tree, [cat])
                parent.setExpanded(True)
                category_items[cat] = parent
            else:
                parent = category_items[cat]

            page_str = f"第 {issue.page + 1} 頁" if issue.page >= 0 else "全域"
            fixable_str = "是" if issue.auto_fixable else "否"
            item = QTreeWidgetItem(parent, [
                issue.severity, issue.category, page_str,
                issue.message, fixable_str
            ])
            if issue.severity == "error":
                item.setForeground(0, QColor("red"))
            elif issue.severity == "warning":
                item.setForeground(0, QColor("orange"))

        errors = report.error_count
        warnings = report.warning_count
        self._summary_lbl.setText(
            f"預檢完成：{errors} 個錯誤，{warnings} 個警告"
        )
        has_fixable = any(i.auto_fixable for i in report.issues)
        self._fix_btn.setEnabled(has_fixable)

    def _auto_fix(self):
        if self._doc.fitz_doc is None or self._report is None:
            return
        engine = PreflightEngine()
        with self._doc.edit_transaction("降低圖片解析度"):
            engine.fix_downsample_images(self._doc.fitz_doc)
        QMessageBox.information(self, "修正完成", "已自動修正圖片解析度問題。\n請重新執行預檢確認。")

    def _export(self):
        if self._report is None:
            QMessageBox.information(self, "提示", "請先執行預檢。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出預檢報告", "preflight_report.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            import fitz as _fitz
            doc = _fitz.open()
            page = doc.new_page()
            y = 50
            page.insert_text((50, 30), "AcroPDF 預檢報告", fontsize=16)
            page.insert_text(
                (50, 45),
                f"錯誤：{self._report.error_count}  警告：{self._report.warning_count}",
                fontsize=11,
            )
            for issue in self._report.issues:
                page_str = f"P{issue.page + 1}" if issue.page >= 0 else "全域"
                line = f"[{issue.severity.upper()}][{issue.category}][{page_str}] {issue.message}"
                if y > 750:
                    page = doc.new_page()
                    y = 50
                color = (1, 0, 0) if issue.severity == "error" else (0.8, 0.4, 0)
                page.insert_text((50, y), line, fontsize=9, color=color)
                y += 14
            doc.save(path, garbage=4, deflate=True)
            doc.close()
            QMessageBox.information(self, "完成", f"報告已儲存至：{path}")
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))
