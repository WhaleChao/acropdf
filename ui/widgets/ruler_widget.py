# ~/Desktop/acropdf/ui/widgets/ruler_widget.py
"""
尺規與格線覆蓋元件。

提供水平尺規 (HorizontalRuler)、垂直尺規 (VerticalRuler) 以及
透明格線覆蓋層 (GridOverlay)，用於 PDF 檢視器的座標參考。
所有刻度均以 PDF 點 (point) 為單位，隨縮放比例自動調整。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


# ═══════════════════════════════════════════════════════════════════
#  常數
# ═══════════════════════════════════════════════════════════════════

_RULER_BG = None      # 用 palette 動態取色
_TICK_COLOR = None
_LABEL_COLOR = None
_MAJOR_TICK_INTERVAL = 72    # 每 72pt = 1 inch
_MINOR_TICK_INTERVAL = 36    # 每 36pt = 0.5 inch
_RULER_THICKNESS = 20        # 尺規寬/高（像素）
_MAJOR_TICK_LEN = 10         # 主要刻度長度（像素）
_MINOR_TICK_LEN = 5          # 次要刻度長度（像素）
_LABEL_FONT_SIZE = 8


# ═══════════════════════════════════════════════════════════════════
#  水平尺規
# ═══════════════════════════════════════════════════════════════════

class HorizontalRuler(QWidget):
    """
    橫向尺規元件，顯示於檢視區頂部。
    高度固定 20px；刻度依 PDF 點座標繪製，主刻度每 72pt（1 吋），
    次刻度每 36pt（0.5 吋），數字標籤標示點數值。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(_RULER_THICKNESS)
        self._zoom: float = 1.0
        self._scroll_offset: int = 0
        self._font = QFont("Helvetica", _LABEL_FONT_SIZE)

    # ── 公開 API ──────────────────────────────────────────────────

    def set_zoom(self, zoom: float) -> None:
        """設定目前縮放倍率，觸發重繪。"""
        if zoom != self._zoom:
            self._zoom = zoom
            self.update()

    def set_scroll_offset(self, offset: int) -> None:
        """設定水平捲動偏移量（像素），觸發重繪。"""
        if offset != self._scroll_offset:
            self._scroll_offset = offset
            self.update()

    # ── 繪製 ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self.palette()
        bg = pal.color(pal.ColorRole.Window)
        tick = pal.color(pal.ColorRole.Mid)
        label_c = pal.color(pal.ColorRole.Text)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(self.rect(), bg)

        painter.setPen(QPen(tick, 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        painter.setFont(self._font)
        pixel_per_pt = self._zoom

        start_pt = max(0, int(self._scroll_offset / pixel_per_pt))
        start_pt = (start_pt // _MINOR_TICK_INTERVAL) * _MINOR_TICK_INTERVAL
        end_pt = int((self._scroll_offset + self.width()) / pixel_per_pt) + _MAJOR_TICK_INTERVAL

        pt = start_pt
        while pt <= end_pt:
            x = int(pt * pixel_per_pt - self._scroll_offset)
            if 0 <= x <= self.width():
                is_major = (pt % _MAJOR_TICK_INTERVAL == 0)
                tick_len = _MAJOR_TICK_LEN if is_major else _MINOR_TICK_LEN

                painter.setPen(QPen(tick, 1))
                painter.drawLine(x, self.height() - 1, x, self.height() - 1 - tick_len)

                if is_major:
                    painter.setPen(label_c)
                    painter.drawText(x + 2, self.height() - _MAJOR_TICK_LEN - 2, str(pt))

            pt += _MINOR_TICK_INTERVAL

        painter.end()


# ═══════════════════════════════════════════════════════════════════
#  垂直尺規
# ═══════════════════════════════════════════════════════════════════

class VerticalRuler(QWidget):
    """
    縱向尺規元件，顯示於檢視區左側。
    寬度固定 20px；刻度系統與 HorizontalRuler 相同但方向垂直。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(_RULER_THICKNESS)
        self._zoom: float = 1.0
        self._scroll_offset: int = 0
        self._font = QFont("Helvetica", _LABEL_FONT_SIZE)

    # ── 公開 API ──────────────────────────────────────────────────

    def set_zoom(self, zoom: float) -> None:
        """設定目前縮放倍率，觸發重繪。"""
        if zoom != self._zoom:
            self._zoom = zoom
            self.update()

    def set_scroll_offset(self, offset: int) -> None:
        """設定垂直捲動偏移量（像素），觸發重繪。"""
        if offset != self._scroll_offset:
            self._scroll_offset = offset
            self.update()

    # ── 繪製 ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self.palette()
        bg = pal.color(pal.ColorRole.Window)
        tick = pal.color(pal.ColorRole.Mid)
        label_c = pal.color(pal.ColorRole.Text)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(self.rect(), bg)

        painter.setPen(QPen(tick, 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        painter.setFont(self._font)
        pixel_per_pt = self._zoom

        start_pt = max(0, int(self._scroll_offset / pixel_per_pt))
        start_pt = (start_pt // _MINOR_TICK_INTERVAL) * _MINOR_TICK_INTERVAL
        end_pt = int((self._scroll_offset + self.height()) / pixel_per_pt) + _MAJOR_TICK_INTERVAL

        pt = start_pt
        while pt <= end_pt:
            y = int(pt * pixel_per_pt - self._scroll_offset)
            if 0 <= y <= self.height():
                is_major = (pt % _MAJOR_TICK_INTERVAL == 0)
                tick_len = _MAJOR_TICK_LEN if is_major else _MINOR_TICK_LEN

                painter.setPen(QPen(tick, 1))
                painter.drawLine(
                    self.width() - 1, y,
                    self.width() - 1 - tick_len, y,
                )

                if is_major:
                    painter.save()
                    painter.setPen(label_c)
                    painter.translate(2, y + 2)
                    painter.rotate(90)
                    painter.drawText(0, 0, str(pt))
                    painter.restore()

            pt += _MINOR_TICK_INTERVAL

        painter.end()


# ═══════════════════════════════════════════════════════════════════
#  格線覆蓋層
# ═══════════════════════════════════════════════════════════════════

class GridOverlay(QWidget):
    """
    透明格線覆蓋元件，疊加在頁面上方顯示可配置間距的參考線。
    預設間距 20pt，線條為半透明淺藍色 (alpha 40)。
    設定 WA_TransparentForMouseEvents 確保不阻擋使用者互動。
    """

    _DEFAULT_SPACING = 20  # 預設格線間距（點）

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # 讓滑鼠事件穿透
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._zoom: float = 1.0
        self._page_rect: QRect | None = None
        self._spacing: int = self._DEFAULT_SPACING
        self._grid_color = QColor(100, 149, 237, 40)  # 淺藍、alpha 40

    # ── 公開 API ──────────────────────────────────────────────────

    def set_zoom(self, zoom: float) -> None:
        """設定目前縮放倍率。"""
        if zoom != self._zoom:
            self._zoom = zoom
            self.update()

    def set_page_rect(self, rect: QRect) -> None:
        """設定目前頁面在檢視器中的矩形區域（像素座標）。"""
        self._page_rect = rect
        self.update()

    def set_spacing(self, spacing: int) -> None:
        """設定格線間距（以 PDF 點為單位）。"""
        if spacing > 0 and spacing != self._spacing:
            self._spacing = spacing
            self.update()

    # ── 繪製 ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._page_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(self._grid_color, 1, Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        pr = self._page_rect
        pixel_spacing = self._spacing * self._zoom

        # 避免間距太小導致繪製過密
        if pixel_spacing < 3:
            painter.end()
            return

        # 垂直線
        x = float(pr.left())
        while x <= pr.right():
            xi = int(x)
            painter.drawLine(xi, pr.top(), xi, pr.bottom())
            x += pixel_spacing

        # 水平線
        y = float(pr.top())
        while y <= pr.bottom():
            yi = int(y)
            painter.drawLine(pr.left(), yi, pr.right(), yi)
            y += pixel_spacing

        painter.end()
