# ~/Desktop/acropdf/ui/viewer/presentation_view.py
"""全螢幕簡報模式 -- 一次顯示一頁 PDF，支援鍵盤與滑鼠換頁。"""
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPixmap, QColor, QFont, QKeyEvent, QMouseEvent, QPaintEvent,
    QResizeEvent,
)


class PresentationView(QWidget):
    """全螢幕簡報檢視器。

    Parameters
    ----------
    fitz_doc : fitz.Document
        已開啟的 PyMuPDF 文件。
    start_page : int
        起始頁碼（0-based）。
    parent : QWidget | None
        父 widget。
    """

    closed = pyqtSignal()           # 離開簡報模式時發出
    page_changed = pyqtSignal(int)  # 切換頁面時發出（0-based page_num）

    # ── 初始化 ──────────────────────────────────────────────────────

    def __init__(
        self,
        fitz_doc: fitz.Document,
        start_page: int = 0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._doc = fitz_doc
        self._page_count = fitz_doc.page_count
        self._current_page = max(0, min(start_page, self._page_count - 1))
        self._pixmap: QPixmap | None = None

        # 視窗屬性
        self.setWindowTitle("簡報模式")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("background-color: black;")
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 頁碼標籤字型（半透明白色）
        self._label_font = QFont("Microsoft JhengHei", 14)
        self._label_color = QColor(255, 255, 255, 160)

        # 進入全螢幕並渲染第一頁
        self.showFullScreen()
        self._render_page()

    # ── 渲染 ────────────────────────────────────────────────────────

    def _render_page(self) -> None:
        """將目前頁面以適合螢幕的縮放比例渲染為 QPixmap。"""
        if self._current_page < 0 or self._current_page >= self._page_count:
            self._pixmap = None
            self.update()
            return

        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        screen_w = self.width()
        screen_h = self.height()

        page = self._doc[self._current_page]
        page_w = page.rect.width
        page_h = page.rect.height

        if page_w <= 0 or page_h <= 0:
            self._pixmap = None
            self.update()
            return

        # 計算縮放以填滿螢幕（保持比例）
        zoom = min(screen_w / page_w, screen_h / page_h)
        scale = zoom * dpr
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

        from PyQt6.QtGui import QImage
        img = QImage(
            pix.samples_ptr, pix.width, pix.height, pix.stride,
            QImage.Format.Format_RGB888,
        )
        img = img.copy()  # 脫離 MuPDF buffer
        self._pixmap = QPixmap.fromImage(img)
        self._pixmap.setDevicePixelRatio(dpr)

        self.update()

    # ── 繪製 ────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        if self._pixmap:
            # 置中繪製
            logical_w = int(self._pixmap.width() / self._pixmap.devicePixelRatio())
            logical_h = int(self._pixmap.height() / self._pixmap.devicePixelRatio())
            x = (self.width() - logical_w) // 2
            y = (self.height() - logical_h) // 2
            painter.drawPixmap(x, y, self._pixmap)

        # 右下角頁碼標籤
        label = f"{self._current_page + 1} / {self._page_count}"
        painter.setFont(self._label_font)
        painter.setPen(self._label_color)
        margin = 20
        painter.drawText(
            self.width() - margin - painter.fontMetrics().horizontalAdvance(label),
            self.height() - margin,
            label,
        )
        painter.end()

    # ── 頁面導覽 ────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if self._current_page < self._page_count - 1:
            self._current_page += 1
            self._render_page()
            self.page_changed.emit(self._current_page)

    def _go_prev(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()
            self.page_changed.emit(self._current_page)

    def _go_first(self) -> None:
        if self._current_page != 0:
            self._current_page = 0
            self._render_page()
            self.page_changed.emit(self._current_page)

    def _go_last(self) -> None:
        last = self._page_count - 1
        if self._current_page != last:
            self._current_page = last
            self._render_page()
            self.page_changed.emit(self._current_page)

    # ── 事件處理 ────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            Qt.Key.Key_Right, Qt.Key.Key_Down,
            Qt.Key.Key_PageDown, Qt.Key.Key_Space,
        ):
            self._go_next()
        elif key in (
            Qt.Key.Key_Left, Qt.Key.Key_Up,
            Qt.Key.Key_PageUp, Qt.Key.Key_Backspace,
        ):
            self._go_prev()
        elif key == Qt.Key.Key_Home:
            self._go_first()
        elif key == Qt.Key.Key_End:
            self._go_last()
        elif key == Qt.Key.Key_Escape:
            self._exit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._go_next()
        elif event.button() == Qt.MouseButton.RightButton:
            self._go_prev()
        else:
            super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """視窗尺寸變更（例如切換螢幕）時重新渲染。"""
        super().resizeEvent(event)
        self._render_page()

    # ── 離開 ────────────────────────────────────────────────────────

    def _exit(self) -> None:
        self.closed.emit()
        self.close()

    def current_page(self) -> int:
        """回傳目前頁碼（0-based）。"""
        return self._current_page
