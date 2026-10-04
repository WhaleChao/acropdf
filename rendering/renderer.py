# ~/Desktop/acropdf/rendering/renderer.py
import fitz
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, QMutex
from PyQt6.QtWidgets import QApplication

class RenderSignals(QObject):
    done = pyqtSignal(int, float, QImage)   # QPixmap must only be created on the GUI thread.
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
        screen = QApplication.primaryScreen() if QApplication.instance() else None
        self._dpr = min(screen.devicePixelRatio(), 1.5) if screen else 1.0

    def run(self):
        doc = None
        try:
            doc = fitz.open(self._path)
            if self._page_num >= doc.page_count:
                if self._signals:
                    self._signals.error.emit(self._page_num, "頁面已不存在")
                return
            pm = PageRenderer.render_page_image(
                doc[self._page_num], self._zoom, self._rotation, self._dpr
            )
            if self._signals:
                self._signals.done.emit(self._page_num, self._zoom, pm)
        except Exception as e:
            if self._signals:
                self._signals.error.emit(self._page_num, str(e))
        finally:
            if doc:
                doc.close()

class PageRenderer:
    @staticmethod
    def render_page_sync(
        page: fitz.Page,
        zoom: float,
        rotation: int = 0,
        device_pixel_ratio: float = 1.0,
    ) -> QPixmap:
        image = PageRenderer.render_page_image(page, zoom, rotation, device_pixel_ratio)
        return QPixmap.fromImage(image)

    @staticmethod
    def render_page_image(page, zoom, rotation=0, device_pixel_ratio=1.0) -> QImage:
        import math
        if not math.isfinite(zoom) or zoom <= 0 or not math.isfinite(device_pixel_ratio) or device_pixel_ratio <= 0:
            raise ValueError("渲染比例必須為有限正數。")
        rect = page.rect
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError("頁面尺寸不適用。")
        # Bound both allocations and dimensions, including oversize/hostile PDF pages.
        scale = min(zoom * device_pixel_ratio,
                    math.sqrt(24_000_000 / (rect.width * rect.height)),
                    16384 / max(rect.width, rect.height))
        mat = fitz.Matrix(scale, scale).prerotate(rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
        # zero-copy QImage via samples_ptr
        img = QImage(
            pix.samples_ptr, pix.width, pix.height, pix.stride,
            QImage.Format.Format_RGB888
        )
        img = img.copy()  # 解除對 MuPDF buffer 的依賴
        img.setDevicePixelRatio(scale / zoom)
        return img

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
