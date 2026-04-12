# ~/Desktop/acropdf/core/ocr_engine.py
"""
跨平台 OCR 引擎。
自動選擇最佳 backend：
  macOS  → Apple Vision（繁中最佳）→ fallback Tesseract
  Windows → WinRT OCR（內建免安裝）→ fallback Tesseract
  Linux  → Tesseract
所有平台限定的 import 都在 platform/ 內完成，此檔案不含任何平台限定 import。
"""
import fitz
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, Qt

class OCRSignals(QObject):
    progress = pyqtSignal(int, int)   # current, total
    finished = pyqtSignal(str)        # output_path
    error = pyqtSignal(str)

class OCRWorker(QRunnable):
    def __init__(self, input_path: str, output_path: str, lang: str,
                 dpi: int, page_range: range, signals: OCRSignals):
        super().__init__()
        self.setAutoDelete(True)
        self._input = input_path
        self._output = output_path
        self._lang = lang
        self._dpi = dpi
        self._page_range = page_range
        self.signals = signals
        self._keep_signals = signals  # 防 GC

    def run(self):
        """完全例外隔離 — 任何錯誤只 emit signal，不 raise"""
        try:
            # 透過 platform 層自動選最佳 backend
            from acro_platform import get_ocr_backend
            backend = get_ocr_backend()
            print(f"[OCR] 使用引擎：{backend.name}")

            doc = fitz.open(self._input)
            try:
                total = len(self._page_range)
                for i, page_num in enumerate(self._page_range):
                    page = doc[page_num]
                    backend.ocr_page(page, self._lang, self._dpi)
                    self.signals.progress.emit(i + 1, total)
                doc.save(self._output, garbage=4, deflate=True)
            finally:
                doc.close()
            self.signals.finished.emit(self._output)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                self.signals.error.emit(str(e))
            except Exception:
                pass

class OCREngine:
    @staticmethod
    def get_backend_name() -> str:
        """回傳當前平台會使用的 OCR 引擎名稱"""
        try:
            from acro_platform import get_ocr_backend
            return get_ocr_backend().name
        except Exception:
            return "無"

    @staticmethod
    def get_supported_languages() -> list[str]:
        """回傳當前平台支援的 OCR 語言清單"""
        try:
            from acro_platform import get_ocr_backend
            return get_ocr_backend().supported_languages()
        except Exception:
            return ["eng"]

    @staticmethod
    def run_async(doc, output_path: str, lang: str = "chi_tra+eng",
                  dpi: int = 300, page_range: range = None,
                  on_progress=None, on_finished=None, on_error=None):
        if not doc or not doc.path:
            return
        pages = page_range or range(doc.page_count)
        signals = OCRSignals()
        if on_progress:
            signals.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)
        if on_finished:
            signals.finished.connect(on_finished, Qt.ConnectionType.QueuedConnection)
        if on_error:
            signals.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
        worker = OCRWorker(doc.path, output_path, lang, dpi, pages, signals)
        worker._keep_signals = signals
        QThreadPool.globalInstance().start(worker)
