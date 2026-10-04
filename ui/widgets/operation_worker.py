"""Background exports using a private, authenticated current-document snapshot."""
from PyQt6.QtCore import QThread, pyqtSignal
import fitz


class OperationWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, document, operation, parent=None):
        super().__init__(parent)
        self._snapshot = document._snapshot()
        self._password = document._password
        self._source = document.source_path
        self._encrypted = document.is_encrypted
        self._operation = operation

    def run(self):
        from core.document import PDFDocument
        document = PDFDocument()
        try:
            document._fitz_doc = fitz.open('pdf', self._snapshot)
            document._password = self._password
            document._source_path = self._source
            # is_encrypted is derived from the original encrypted flag.
            document._was_encrypted = self._encrypted
            if document._fitz_doc.needs_pass and not document._fitz_doc.authenticate(self._password):
                raise ValueError('無法認證文件快照。')
            if not self.isInterruptionRequested():
                result = self._operation(document)
                self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            document.close()
            self._snapshot = b''; self._password = ''
