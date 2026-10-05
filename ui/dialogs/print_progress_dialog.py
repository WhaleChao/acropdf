from PyQt6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout
from core.print_engine import PrintEngine
from ui.widgets.operation_worker import OperationWorker
from ui.widgets.worker_dialog import WorkerDialog


class PrintProgressDialog(WorkerDialog):
    def __init__(self, document, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('建立列印副本')
        self.setMinimumWidth(380)
        self.report = None
        self.error = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('保留向量內容，並攤平可見註解及表單。'))
        self._progress = QProgressBar()
        layout.addWidget(self._progress)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self._worker = OperationWorker(document, lambda doc: PrintEngine(doc).export_pdf(
            settings.output_pdf_path, settings.page_indices, settings.copies,
            settings.paper_size, landscape=settings.landscape, overwrite=settings.overwrite,
            interrupted=self._worker.isInterruptionRequested, progress=self._worker.progress.emit), self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.succeeded.connect(self._succeeded)
        self._worker.failed.connect(self._failed)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_started', False):
            self._started = True
            self._worker.start()

    def _succeeded(self, report):
        self.report = report
        self.accept()

    def _failed(self, message):
        self.error = message
        self.reject()
