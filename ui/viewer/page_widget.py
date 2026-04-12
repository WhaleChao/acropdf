# ~/Desktop/acropdf/ui/viewer/page_widget.py
import fitz
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QPoint, QRectF, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor, QCursor

class PageWidget(QWidget):
    clicked = pyqtSignal(int, QPoint)      # page_num, widget_pos
    mouse_moved = pyqtSignal(int, QPoint)

    def __init__(self, page_num: int, parent=None):
        super().__init__(parent)
        self._page_num = page_num
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._tool = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

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
        """螢幕座標 → PDF 座標"""
        dpr = self._pixmap.devicePixelRatio() if self._pixmap else 1.0
        scale = self._zoom * dpr
        return fitz.Point(pt.x() * dpr / scale * (1.0 / 1.0),
                          pt.y() * dpr / scale * (1.0 / 1.0))

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap:
            painter.drawPixmap(0, 0, self._pixmap)
        else:
            painter.fillRect(self.rect(), QColor(200, 200, 200))
        painter.end()

    def mousePressEvent(self, event):
        self.clicked.emit(self._page_num, event.pos())
        if self._tool:
            self._tool.mouse_press(self, event, event.pos())

    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(self._page_num, event.pos())
        if self._tool:
            self._tool.mouse_move(self, event, event.pos())

    def mouseReleaseEvent(self, event):
        if self._tool:
            self._tool.mouse_release(self, event, event.pos())
