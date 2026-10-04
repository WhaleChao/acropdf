# ~/Desktop/acropdf/ui/tools/text_edit_tool.py
"""
PDF 文字直接編輯工具。

允許使用者點擊頁面上的既有文字，在原位以覆蓋式文字方塊進行內聯編輯。
編輯完成後以塗銷 (redact) + 重新插入的方式更新 PDF 內容。
支援中日韓 (CJK) 文字自動偵測與字型切換。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz
from PyQt6.QtCore import QPoint, QRect, Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QPen, QTextCharFormat
from PyQt6.QtWidgets import QTextEdit, QApplication, QMessageBox

from app.constants import ToolMode
from ui.tools.annotation_tools import BaseTool


# ═══════════════════════════════════════════════════════════════════
#  輔助函式
# ═══════════════════════════════════════════════════════════════════

def _is_cjk(text: str) -> bool:
    """檢查文字中是否包含 CJK 字元（中日韓統一表意文字）。"""
    return any(ord(c) > 0x4E00 for c in text)


def _pick_fontname(text: str) -> str:
    """依文字內容選擇適當的 PDF 內建字型名稱。"""
    return "china-t" if _is_cjk(text) else "helv"


def _find_text_at(page: fitz.Page, point: fitz.Point) -> dict | None:
    """
    在 *page* 中尋找包含 *point* 的文字 span。

    回傳 dict 包含:
        text     (str)  : span 的文字內容
        rect     (Rect) : span 的邊界矩形
        fontsize (float): 字型大小
        color    (tuple): (r, g, b) 浮點色值 0‥1
        origin   (Point): span 的基線起點

    找不到時回傳 None。
    """
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for blk in blocks:
        if blk.get("type") != 0:  # 只處理文字區塊
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                rect = fitz.Rect(span["bbox"])
                if rect.contains(point):
                    # 解析顏色：span["color"] 是 int (0xRRGGBB)
                    c = span.get("color", 0)
                    r = ((c >> 16) & 0xFF) / 255.0
                    g = ((c >> 8) & 0xFF) / 255.0
                    b = (c & 0xFF) / 255.0
                    return {
                        "text": span["text"],
                        "rect": rect,
                        "fontsize": span["size"],
                        "font": span["font"],
                        "flags": span["flags"],
                        "color": (r, g, b),
                        "origin": fitz.Point(span["origin"]),
                        "direction": tuple(line.get("dir", (1, 0))),
                    }
    return None


# ═══════════════════════════════════════════════════════════════════
#  內聯編輯覆蓋元件
# ═══════════════════════════════════════════════════════════════════

class _InlineEditor(QTextEdit):
    """
    半透明覆蓋文字編輯器，定位在頁面 widget 上方，
    讓使用者直接修改 PDF 上的文字。
    """

    def __init__(self, parent, text: str, font_size: float, zoom: float):
        super().__init__(parent)
        self.setFrameShape(QTextEdit.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet(
            "QTextEdit { background: palette(base); "
            "border: 2px solid #007AFF; color: palette(text); }"
        )
        # 設定字型大小（依縮放比例）
        display_size = max(8, int(font_size * zoom))
        font = QFont("Helvetica", display_size)
        self.setFont(font)
        # 載入原始文字
        self.setPlainText(text)
        self.selectAll()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def focusOutEvent(self, event):  # noqa: N802
        """失去焦點時發出 editingFinished 訊號。"""
        super().focusOutEvent(event)
        # 由父工具處理提交邏輯
        if hasattr(self, "on_finish") and callable(self.on_finish):
            self.on_finish()

    def keyPressEvent(self, event):  # noqa: N802
        """按 Enter（無 Shift）= 完成編輯；Escape = 取消。"""
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, "on_cancel") and callable(self.on_cancel):
                self.on_cancel()
            return
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if hasattr(self, "on_finish") and callable(self.on_finish):
                self.on_finish()
            return
        super().keyPressEvent(event)


# ═══════════════════════════════════════════════════════════════════
#  TextEditTool
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TextEditTool(BaseTool):
    """
    直接編輯 PDF 文字的工具。

    使用者點擊頁面上的文字後，會在該位置顯示內聯編輯器；
    編輯完成時以塗銷 + 重新插入的方式將修改寫回 PDF。
    """
    _editor: _InlineEditor | None = field(default=None, repr=False)
    _active_widget: object = field(default=None, repr=False)
    _span_info: dict | None = field(default=None, repr=False)
    _hover_rect: QRect | None = field(default=None, repr=False)
    _hover_page: int = field(default=-1, repr=False)
    _committing: bool = field(default=False, repr=False)

    # ── 滑鼠事件 ──────────────────────────────────────────────────

    def mouse_press(self, widget, event, pos: QPoint) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # 如果已有編輯器，先提交
        if self._editor is not None:
            self._commit_edit()
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        pdf_pt = self._pdf_point(widget, pos)
        if pdf_pt is None:
            return

        span = _find_text_at(page, pdf_pt)
        if span is None:
            return

        # 記錄 span 資訊
        self._span_info = span
        self._active_widget = widget

        # 計算覆蓋編輯器在 widget 座標系的位置
        zoom = getattr(widget, "_zoom", 1.0)
        rect = widget.pdf_rect_to_widget(span["rect"], page)
        x, y = rect.x(), rect.y()
        w = max(80, rect.width() + 20)
        h = max(28, rect.height() + 12)

        editor = _InlineEditor(widget, span["text"], span["fontsize"], zoom)
        editor.setGeometry(x, y, w, h)
        editor.on_finish = self._commit_edit
        editor.on_cancel = self._cancel_edit
        editor.show()
        editor.setFocus()
        self._editor = editor

    def mouse_move(self, widget, event, pos: QPoint) -> None:
        """滑鼠移動時，偵測游標下方的文字區塊並顯示高亮邊框。"""
        page = self._page(widget.page_num)
        if page is None:
            self._hover_rect = None
            widget.update()
            return

        pdf_pt = self._pdf_point(widget, pos)
        if pdf_pt is None:
            self._hover_rect = None
            widget.update()
            return

        span = _find_text_at(page, pdf_pt)
        if span:
            self._hover_rect = widget.pdf_rect_to_widget(span["rect"], page)
            self._hover_page = widget.page_num
        else:
            self._hover_rect = None
        widget.update()

    def mouse_release(self, widget, event, pos: QPoint) -> None:
        # 編輯操作在 press 或 editor callback 中處理，release 不做事
        pass

    # ── 覆蓋繪製 ──────────────────────────────────────────────────

    def draw_overlay(self, widget, painter) -> None:
        """在游標下方的文字區塊周圍繪製淺藍色邊框。"""
        if self._hover_rect is None or self._hover_page != widget.page_num:
            return
        painter.save()
        pen = QPen(QColor(74, 144, 217, 180), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(74, 144, 217, 25))
        painter.drawRect(self._hover_rect)
        painter.restore()

    # ── 內部方法 ──────────────────────────────────────────────────

    def _commit_edit(self) -> None:
        if self._committing:
            return
        self._committing = True
        try:
            self._apply_edit()
        finally:
            self._committing = False

    def _apply_edit(self) -> None:
        """將編輯器中的新文字寫回 PDF。"""
        if self._editor is None or self._span_info is None or self._active_widget is None:
            self._cleanup_editor()
            return

        new_text = self._editor.toPlainText().strip()
        old_text = self._span_info["text"]

        # 文字沒變就直接關閉
        if new_text == old_text:
            self._cleanup_editor()
            return

        page = self._page(self._active_widget.page_num)
        if page is None:
            self._cleanup_editor()
            return

        from core.content_editor import replace_text_span
        try:
            replace_text_span(self.doc, self._active_widget.page_num, self._span_info, new_text)
        except Exception as exc:
            QMessageBox.warning(self._editor, "無法完成編輯", str(exc))
            return
        self._cleanup_editor()

    def _cancel_edit(self) -> None:
        """取消編輯，不做任何 PDF 修改。"""
        self._cleanup_editor()

    def _cleanup_editor(self) -> None:
        """移除內聯編輯器並重設狀態。"""
        if self._editor is not None:
            self._editor.hide()
            self._editor.deleteLater()
            self._editor = None
        self._span_info = None
        self._active_widget = None
        self._hover_rect = None
