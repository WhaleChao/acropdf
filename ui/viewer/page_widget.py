# ~/Desktop/acropdf/ui/viewer/page_widget.py
import fitz
from PyQt6.QtWidgets import QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor


class PageWidget(QWidget):
    clicked = pyqtSignal(int, QPoint)
    mouse_moved = pyqtSignal(int, QPoint)
    context_requested = pyqtSignal(int, QPoint)   # page_num, global_pos

    def __init__(self, page_num: int, parent=None):
        super().__init__(parent)
        self._page_num = page_num
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._tool = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.context_requested.emit(self._page_num, self.mapToGlobal(pos))
        )

    @property
    def page_num(self) -> int:
        return self._page_num

    def set_pixmap(self, pm: QPixmap, zoom: float):
        self._pixmap = pm
        self._zoom = zoom
        logical_w = int(pm.width() / pm.devicePixelRatio())
        logical_h = int(pm.height() / pm.devicePixelRatio())
        self.setFixedSize(logical_w, logical_h)
        self.update()

    def set_tool(self, tool):
        self._tool = tool

    def widget_to_pdf(self, pt: QPoint, page: fitz.Page) -> fitz.Point:
        dpr = self._pixmap.devicePixelRatio() if self._pixmap else 1.0
        scale = self._zoom * dpr
        return fitz.Point(pt.x() * dpr / scale, pt.y() * dpr / scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap:
            painter.drawPixmap(0, 0, self._pixmap)
        else:
            painter.fillRect(self.rect(), QColor(220, 220, 220))
        painter.end()

    def mousePressEvent(self, event):
        self.clicked.emit(self._page_num, event.pos())
        if event.button() == Qt.MouseButton.LeftButton and self._tool:
            self._tool.mouse_press(self, event, event.pos())

    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(self._page_num, event.pos())
        if self._tool:
            self._tool.mouse_move(self, event, event.pos())

    def mouseReleaseEvent(self, event):
        if self._tool:
            self._tool.mouse_release(self, event, event.pos())

