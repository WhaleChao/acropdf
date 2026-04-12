# ~/Desktop/acropdf/rendering/renderer.py
import fitz
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, QMutex
from PyQt6.QtWidgets import QApplication

class RenderSignals(QObject):
    done = pyqtSignal(int, float, QPixmap)   # page_num, zoom, pixmap
    error = pyqtSignal(int, str)

class RenderWorker(QRunnable):
    def __init__(self, path: str, page_num: int, zoom: float,
                 rotation: int = 0, signals: RenderSignals = None):
        super().__init__()
        self.setAutoDelete(True)
        self._path = path
        self._page_num = page_num
        self._zoom = zoom
        self._rotation = rotation
        self._signals = signals
        self._dpr = QApplication.primaryScreen().devicePixelRatio() if QApplication.instance() else 1.0

    def run(self):
        try:
            doc = fitz.open(self._path)
            pm = PageRenderer.render_page_sync(
                doc[self._page_num], self._zoom, self._rotation, self._dpr
            )
            doc.close()
            if self._signals:
                self._signals.done.emit(self._page_num, self._zoom, pm)
        except Exception as e:
            if self._signals:
                self._signals.error.emit(self._page_num, str(e))

class PageRenderer:
    @staticmethod
    def render_page_sync(
        page: fitz.Page,
        zoom: float,
        rotation: int = 0,
        device_pixel_ratio: float = 1.0,
    ) -> QPixmap:
        scale = zoom * device_pixel_ratio
        mat = fitz.Matrix(scale, scale).prerotate(rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
        # zero-copy QImage via samples_ptr
        img = QImage(
            pix.samples_ptr, pix.width, pix.height, pix.stride,
            QImage.Format.Format_RGB888
        )
        img = img.copy()  # 解除對 MuPDF buffer 的依賴
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(device_pixel_ratio)
        return pm

    @staticmethod
    def make_signals() -> RenderSignals:
        return RenderSignals()

    @staticmethod
    def start_worker(path: str, page_num: int, zoom: float,
                     signals: RenderSignals, rotation: int = 0):
        worker = RenderWorker(path, page_num, zoom, rotation, signals)
        worker._keep_signals = signals  # prevent GC while in thread pool
        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def render_page_async(
        path: str, page_num: int, zoom: float,
        rotation: int = 0, callback=None
    ):
        signals = RenderSignals()
        if callback:
            signals.done.connect(callback)
        worker = RenderWorker(path, page_num, zoom, rotation, signals)
        worker._keep_signals = signals
        QThreadPool.globalInstance().start(worker)
