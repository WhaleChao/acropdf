# ~/Desktop/acropdf/ui/panels/thumbnail_panel.py
import fitz
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThreadPool, QRunnable, QObject
from PyQt6.QtGui import QPixmap, QImage, QIcon
from app.constants import THUMBNAIL_SIZE, THUMBNAIL_DPI

class ThumbSignals(QObject):
    done = pyqtSignal(int, QPixmap)

class ThumbWorker(QRunnable):
    def __init__(self, path: str, page_num: int):
        super().__init__()
        self.setAutoDelete(True)
        self._path = path
        self._page_num = page_num
        self.signals = ThumbSignals()

    def run(self):
        try:
            doc = fitz.open(self._path)
            page = doc[self._page_num]
            zoom = THUMBNAIL_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples_ptr, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888).copy()
            pm = QPixmap.fromImage(img).scaled(
                THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            doc.close()
            self.signals.done.emit(self._page_num, pm)
        except Exception as e:
            pass

class ThumbnailPanel(QListWidget):
    page_selected = pyqtSignal(int)
    pages_reordered = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.setSpacing(4)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.currentRowChanged.connect(self.page_selected)

    def load_document(self, doc):
        self.clear()
        if not doc or not doc.fitz_doc:
            return
        for i in range(doc.page_count):
            item = QListWidgetItem(f" {i+1} ")
            item.setSizeHint(QSize(THUMBNAIL_SIZE[0] + 16, THUMBNAIL_SIZE[1] + 24))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.addItem(item)
            # 背景載入縮圖
            if doc.path:
                worker = ThumbWorker(doc.path, i)
                worker.signals.done.connect(self._set_thumb)
                QThreadPool.globalInstance().start(worker)

    def _set_thumb(self, page_num: int, pm: QPixmap):
        item = self.item(page_num)
        if item:
            item.setIcon(QIcon(pm))

    def dropEvent(self, event):
        super().dropEvent(event)
        new_order = [self.item(i).data(Qt.ItemDataRole.UserRole)
                     for i in range(self.count())]
        self.pages_reordered.emit(new_order)
