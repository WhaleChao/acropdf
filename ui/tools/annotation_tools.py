from __future__ import annotations

from dataclasses import dataclass

import fitz
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QWidget

from app.constants import ToolMode


def _normalized_rect(start: QPoint, end: QPoint) -> QRect:
    return QRect(start, end).normalized()


@dataclass
class BaseTool:
    mode: ToolMode
    view: object
    doc: object
    _start: QPoint | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = pos

    def mouse_move(self, widget, event, pos: QPoint):
        return

    def mouse_release(self, widget, event, pos: QPoint):
        self._start = None

    def _page(self, page_num: int):
        return self.doc.fitz_doc[page_num]

    def _pdf_point(self, widget, pos: QPoint) -> fitz.Point:
        return widget.widget_to_pdf(pos, self._page(widget.page_num))

    def _pdf_rect(self, widget, start: QPoint, end: QPoint) -> fitz.Rect:
        p1 = self._pdf_point(widget, start)
        p2 = self._pdf_point(widget, end)
        return fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))


class StickyNoteTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        text, ok = QInputDialog.getText(widget, "新增便利貼", "內容：")
        if ok and text.strip():
            self.doc.annotations.add_text_annot(
                widget.page_num,
                self._pdf_point(widget, pos),
                text.strip(),
            )
        self._start = None


class TextBoxTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect = self._pdf_rect(widget, self._start, pos)
        if rect.width < 10 or rect.height < 10:
            self._start = None
            return
        text, ok = QInputDialog.getMultiLineText(widget, "新增文字框", "內容：")
        if ok and text.strip():
            self.doc.annotations.add_freetext(widget.page_num, rect, text.strip())
        self._start = None


class StampTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect = self._pdf_rect(widget, self._start, pos)
        if rect.width >= 10 and rect.height >= 10:
            self.doc.annotations.add_stamp(widget.page_num, rect, "Draft")
        self._start = None


class RedactTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect = self._pdf_rect(widget, self._start, pos)
        if rect.width < 10 or rect.height < 10:
            self._start = None
            return
        self.doc.annotations.add_redact(widget.page_num, rect, text="")
        QMessageBox.information(widget, "已標記塗黑", "已加入塗黑區塊。儲存前請用後續流程執行永久塗黑。")
        self._start = None


class HighlightTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect = self._pdf_rect(widget, self._start, pos)
        if rect.width >= 5 and rect.height >= 5:
            self.doc.annotations.add_area_highlight(widget.page_num, rect)
        self._start = None


class RectTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect = self._pdf_rect(widget, self._start, pos)
        if rect.width >= 5 and rect.height >= 5:
            self.doc.annotations.add_rect(widget.page_num, rect, color=(1, 0, 0))
        self._start = None


class CropTool(BaseTool):
    """拖曳選框裁切頁面。滑鼠按下拖曳畫矩形，放開後詢問確認，執行 set_cropbox。"""

    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()  # 觸發 paintEvent 重繪

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()

        if rect_w.width() < 5 or rect_w.height() < 5:
            self._start = None
            return

        pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())

        reply = QMessageBox.question(
            widget, "確認裁切",
            f"裁切第 {widget.page_num+1} 頁至選取範圍？\n（可透過「還原全頁」恢復）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.doc.pages.crop(widget.page_num, pdf_rect)
        self._start = None

    def draw_overlay(self, widget, painter):
        """由 PageWidget.paintEvent 呼叫，畫橡皮筋選框。"""
        if not self._overlay:
            return
        from PyQt6.QtGui import QColor, QPen
        painter.save()
        pen = QPen(QColor(0, 120, 215), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 120, 215, 30))
        painter.drawRect(self._overlay)
        painter.restore()


class ToolFactory:
    @staticmethod
    def create(mode: ToolMode, view, doc):
        mapping = {
            ToolMode.STICKY_NOTE: StickyNoteTool,
            ToolMode.TEXT_BOX: TextBoxTool,
            ToolMode.STAMP: StampTool,
            ToolMode.REDACT: RedactTool,
            ToolMode.HIGHLIGHT: HighlightTool,
            ToolMode.SHAPE_RECT: RectTool,
            ToolMode.CROP: CropTool,
        }
        tool_cls = mapping.get(mode)
        return tool_cls(mode, view, doc) if tool_cls else None
