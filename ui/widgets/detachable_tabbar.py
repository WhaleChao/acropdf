# ~/Desktop/acropdf/ui/widgets/detachable_tabbar.py
"""
可拖離分頁列 — 把分頁拖出 tab bar 區域時，發出 detach 信號。
"""
from PyQt6.QtWidgets import QTabBar
from PyQt6.QtCore import pyqtSignal, QPoint, Qt
from PyQt6.QtGui import QMouseEvent, QCursor


class DetachableTabBar(QTabBar):
    """拖曳分頁超出 tab bar 範圍時發出 tab_detach_requested(index)。"""

    tab_detach_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start: QPoint | None = None
        self._drag_idx: int = -1
        self.setAcceptDrops(False)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._drag_idx = self.tabAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (self._drag_start is not None
                and self._drag_idx >= 0
                and self.count() > 1):
            # 計算拖曳距離：超出 tab bar 上下方 40px 即判定為拖離
            delta = event.pos() - self._drag_start
            if abs(delta.y()) > 40:
                idx = self._drag_idx
                self._drag_start = None
                self._drag_idx = -1
                self.tab_detach_requested.emit(idx)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start = None
        self._drag_idx = -1
        super().mouseReleaseEvent(event)
