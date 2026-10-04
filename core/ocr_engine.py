"""OCR runs on a private current-document snapshot and publishes atomically."""
import threading
import fitz
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, Qt
from core.file_io import atomic_output


class OCRSignals(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)


def _perform(doc, output, lang, dpi, pages, source=None, on_progress=None, cancelled=None):
    from acro_platform import get_ocr_backend
    if not 72 <= dpi <= 600: raise ValueError('OCR DPI 須介於 72 與 600。')
    pages = list(pages)
    if not pages or len(set(pages)) != len(pages) or any(p < 0 or p >= len(doc) for p in pages):
        raise ValueError('OCR 頁面範圍無效。')
    backend = get_ocr_backend()
    with atomic_output(output, source=source) as temporary:
        for index, page_num in enumerate(pages):
            if cancelled and cancelled(): raise RuntimeError('OCR 已取消；未產生不完整的輸出。')
            backend.ocr_page(doc[page_num], lang, dpi)
            if on_progress: on_progress(index + 1, len(pages))
        if cancelled and cancelled(): raise RuntimeError('OCR 已取消；未產生不完整的輸出。')
        doc.save(temporary, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    return str(output)


class OCRWorker(QRunnable):
    def __init__(self, snapshot, source, password, output, lang, dpi, pages, signals):
        super().__init__()
        self.snapshot, self.source, self.password = snapshot, source, password
        self.output, self.lang, self.dpi, self.pages = output, lang, dpi, pages
        self.signals = signals
        self._running = True
        self._cancelled = threading.Event()

    def isRunning(self): return self._running
    def requestInterruption(self): self._cancelled.set()

    def run(self):
        try:
            with fitz.open('pdf', self.snapshot) as doc:
                if doc.needs_pass and not doc.authenticate(self.password): raise ValueError('OCR 快照需要密碼。')
                path = _perform(doc, self.output, self.lang, self.dpi, self.pages, source=self.source,
                                on_progress=self.signals.progress.emit, cancelled=self._cancelled.is_set)
            self._running = False
            self.signals.finished.emit(path)
        except Exception as exc:
            self._running = False
            self.signals.error.emit(str(exc))
        finally:
            self.snapshot = None; self.password = ''


class OCREngine:
    @staticmethod
    def run_sync(input_path, output_path, lang='chi_tra+eng', dpi=300, page_range=None, on_progress=None, password=''):
        with fitz.open(input_path) as doc:
            if doc.needs_pass and not doc.authenticate(password): raise ValueError('OCR 來源需要正確密碼。')
            pages = page_range if page_range is not None else range(len(doc))
            return _perform(doc, output_path, lang, dpi, pages, input_path, on_progress)

    @staticmethod
    def get_backend_name():
        from acro_platform import get_ocr_backend
        return get_ocr_backend().name

    @staticmethod
    def get_supported_languages():
        from acro_platform import get_ocr_backend
        return get_ocr_backend().supported_languages()

    @staticmethod
    def run_async(doc, output_path, lang='chi_tra+eng', dpi=300, page_range=None,
                  on_progress=None, on_finished=None, on_error=None):
        if doc is None or doc.fitz_doc is None: raise ValueError('尚未載入文件。')
        signals = OCRSignals()
        for signal, callback in ((signals.progress, on_progress), (signals.finished, on_finished), (signals.error, on_error)):
            if callback: signal.connect(callback, Qt.ConnectionType.QueuedConnection)
        pages = list(page_range if page_range is not None else range(doc.page_count))
        worker = OCRWorker(doc._snapshot(), doc.source_path, doc._password, output_path, lang, dpi, pages, signals)
        QThreadPool.globalInstance().start(worker)
        return worker
