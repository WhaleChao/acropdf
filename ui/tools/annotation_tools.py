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
        }
        tool_cls = mapping.get(mode)
        return tool_cls(mode, view, doc) if tool_cls else None
