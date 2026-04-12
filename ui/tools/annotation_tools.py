# ~/Desktop/acropdf/ui/tools/annotation_tools.py
"""
所有繪圖 / 標注工具類別與 ToolFactory。
每個工具接收 mouse_press / mouse_move / mouse_release 事件，
可選擇實作 draw_overlay() 在 PageWidget.paintEvent 中畫即時預覽。
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import fitz
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPen, QFont, QPolygon
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QRadioButton, QSpinBox, QVBoxLayout,
    QTextEdit, QPushButton,
)

from app.constants import ToolMode


def _normalized_rect(start: QPoint, end: QPoint) -> QRect:
    return QRect(start, end).normalized()


# ═══════════════════════════════════════════════════════════════
# 基底類別
# ═══════════════════════════════════════════════════════════════

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
        return fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y),
                         max(p1.x, p2.x), max(p1.y, p2.y))


# ═══════════════════════════════════════════════════════════════
# 工具專用輔助對話框
# ═══════════════════════════════════════════════════════════════

class _StampChooserDialog(QDialog):
    STAMPS = [
        "Approved", "AsIs", "Confidential", "Departmental", "Draft",
        "Experimental", "Expired", "Final", "ForComment", "ForPublicRelease",
        "NotApproved", "NotForPublicRelease", "Sold", "TopSecret",
    ]
    _ZH = {
        "Approved": "已核准", "AsIs": "如現狀", "Confidential": "機密",
        "Departmental": "部門限閱", "Draft": "草稿", "Experimental": "實驗性",
        "Expired": "已過期", "Final": "定稿", "ForComment": "供審閱",
        "ForPublicRelease": "可公開發布", "NotApproved": "未核准",
        "NotForPublicRelease": "不可公開", "Sold": "已售出", "TopSecret": "最高機密",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("選擇圖章")
        self.resize(280, 120)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("圖章類型："))
        self._combo = QComboBox()
        for s in self.STAMPS:
            self._combo.addItem(f"{self._ZH.get(s, s)}  ({s})", s)
        self._combo.setCurrentIndex(4)  # Draft
        layout.addWidget(self._combo)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_stamp(self) -> str:
        return self._combo.currentData()


class _LinkDialog(QDialog):
    def __init__(self, max_page: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("插入連結")
        self.resize(360, 190)
        layout = QVBoxLayout(self)
        self._url_radio = QRadioButton("網頁連結（URL）")
        self._page_radio = QRadioButton("跳至頁面")
        self._url_radio.setChecked(True)
        layout.addWidget(self._url_radio)
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("  URL："))
        self._url_edit = QLineEdit("https://")
        url_row.addWidget(self._url_edit)
        layout.addLayout(url_row)
        layout.addWidget(self._page_radio)
        page_row = QHBoxLayout()
        page_row.addWidget(QLabel(f"  頁碼（1–{max_page}）："))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, max_page)
        self._page_spin.setEnabled(False)
        page_row.addWidget(self._page_spin)
        page_row.addStretch()
        layout.addLayout(page_row)
        self._url_radio.toggled.connect(self._url_edit.setEnabled)
        self._page_radio.toggled.connect(self._page_spin.setEnabled)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("插入")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_result(self) -> tuple[str, str]:
        if self._url_radio.isChecked():
            return "url", self._url_edit.text().strip()
        return "page", str(self._page_spin.value())


class _FormFieldDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增表單欄位")
        self.resize(320, 180)
        layout = QFormLayout(self)
        self._type_combo = QComboBox()
        self._type_combo.addItems([
            "文字欄位 (Text)", "核取方塊 (Checkbox)",
            "下拉選單 (Combo)", "清單 (List)",
        ])
        layout.addRow("欄位類型：", self._type_combo)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("欄位名稱（如：姓名）")
        layout.addRow("欄位名稱：", self._name_edit)
        self._default_edit = QLineEdit()
        self._default_edit.setPlaceholderText("預設值（選填）")
        layout.addRow("預設值：", self._default_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("新增")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_result(self) -> tuple[str, str, str]:
        idx = self._type_combo.currentIndex()
        types = ["text", "checkbox", "combo", "list"]
        return types[idx], self._name_edit.text().strip(), self._default_edit.text().strip()


# ═══════════════════════════════════════════════════════════════
# 共用：橡皮筋 overlay
# ═══════════════════════════════════════════════════════════════

def _draw_rubber_band(painter, overlay: QRect | None,
                      r: int = 0, g: int = 120, b: int = 215):
    if not overlay:
        return
    painter.save()
    pen = QPen(QColor(r, g, b), 2, Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(QColor(r, g, b, 25))
    painter.drawRect(overlay)
    painter.restore()


def _detect_font_size(doc, page_num: int, rect: fitz.Rect) -> float:
    """從頁面文字偵測周圍主要字體大小。"""
    try:
        page = doc.fitz_doc[page_num]
        search = rect + (-60, -60, 60, 60)
        blocks = page.get_text("dict", clip=search)["blocks"]
        sizes = []
        for b in blocks:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 2:
                        sizes.append(s)
        if sizes:
            return float(Counter(round(s) for s in sizes).most_common(1)[0][0])
    except Exception:
        pass
    return 12.0


# ═══════════════════════════════════════════════════════════════
# 便利貼
# ═══════════════════════════════════════════════════════════════

class StickyNoteTool(BaseTool):
    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        text, ok = QInputDialog.getText(widget, "新增便利貼", "內容：")
        if ok and text.strip():
            self.doc.annotations.add_text_annot(
                widget.page_num, self._pdf_point(widget, pos), text.strip())
        self._start = None


# ═══════════════════════════════════════════════════════════════
# 文字框（含橡皮筋 + 字體偵測）
# ═══════════════════════════════════════════════════════════════

class TextBoxTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() < 10 or rect_w.height() < 10:
            self._start = None
            return
        pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
        detected = _detect_font_size(self.doc, widget.page_num, pdf_rect)
        rect_info = (f"選取範圍：{pdf_rect.width:.0f} × {pdf_rect.height:.0f} pt"
                     f"  （第 {widget.page_num + 1} 頁）")
        from ui.dialogs.text_box.text_box_dialog import TextBoxDialog
        dlg = TextBoxDialog(font_size=detected, rect_info=rect_info, parent=widget)
        if dlg.exec():
            text, size = dlg.get_result()
            if text.strip():
                self.doc.annotations.add_freetext(
                    widget.page_num, pdf_rect, text.strip(), fontsize=float(size))
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 0, 170, 80)


# ═══════════════════════════════════════════════════════════════
# 標注框（Callout）
# ═══════════════════════════════════════════════════════════════

class CalloutTool(BaseTool):
    """拖曳定義文字框，自動在左上角加指向線。"""

    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() < 10 or rect_w.height() < 10:
            self._start = None
            return
        pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
        detected = _detect_font_size(self.doc, widget.page_num, pdf_rect)
        text, ok = QInputDialog.getMultiLineText(widget, "標注框", "內容：")
        if ok and text.strip():
            self.doc.annotations.add_callout(
                widget.page_num, pdf_rect, text.strip(), fontsize=detected)
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 200, 120, 0)


# ═══════════════════════════════════════════════════════════════
# 螢光筆
# ═══════════════════════════════════════════════════════════════

class HighlightTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() >= 5 and rect_w.height() >= 5:
            pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
            self.doc.annotations.add_area_highlight(widget.page_num, pdf_rect)
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 255, 200, 0)


# ═══════════════════════════════════════════════════════════════
# 底線
# ═══════════════════════════════════════════════════════════════

class UnderlineTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() >= 5 and rect_w.height() >= 3:
            pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
            self.doc.annotations.add_area_underline(widget.page_num, pdf_rect)
        self._start = None

    def draw_overlay(self, widget, painter):
        if not self._overlay:
            return
        painter.save()
        pen = QPen(QColor(0, 0, 220), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        # 畫底線（只在 overlay 底邊）
        r = self._overlay
        painter.drawRect(r)
        thick_pen = QPen(QColor(0, 0, 220), 3)
        painter.setPen(thick_pen)
        painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 刪除線
# ═══════════════════════════════════════════════════════════════

class StrikeoutTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() >= 5 and rect_w.height() >= 3:
            pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
            self.doc.annotations.add_area_strikeout(widget.page_num, pdf_rect)
        self._start = None

    def draw_overlay(self, widget, painter):
        if not self._overlay:
            return
        painter.save()
        pen = QPen(QColor(200, 0, 0), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(self._overlay)
        r = self._overlay
        mid_y = (r.top() + r.bottom()) // 2
        thick_pen = QPen(QColor(200, 0, 0), 3)
        painter.setPen(thick_pen)
        painter.drawLine(r.left(), mid_y, r.right(), mid_y)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 手繪（Freehand）
# ═══════════════════════════════════════════════════════════════

class FreehandTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._stroke: list[QPoint] = []
        self._drawing = False

    def mouse_press(self, widget, event, pos: QPoint):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._stroke = [pos]
            widget.update()

    def mouse_move(self, widget, event, pos: QPoint):
        if self._drawing:
            self._stroke.append(pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if not self._drawing or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drawing = False
        if len(self._stroke) < 2:
            self._stroke = []
            return
        pdf_pts = []
        for pt in self._stroke:
            p = self._pdf_point(widget, pt)
            pdf_pts.append((p.x, p.y))
        if len(pdf_pts) >= 2:
            self.doc.annotations.add_ink(
                widget.page_num, [pdf_pts], color=(0, 0, 0.8), width=2.0)
        self._stroke = []
        widget.update()

    def draw_overlay(self, widget, painter):
        if len(self._stroke) < 2:
            return
        painter.save()
        pen = QPen(QColor(0, 0, 200), 2, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for i in range(len(self._stroke) - 1):
            painter.drawLine(self._stroke[i], self._stroke[i + 1])
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 橡皮擦（Eraser）
# ═══════════════════════════════════════════════════════════════

class EraserTool(BaseTool):
    """點擊或拖曳，刪除與游標接觸的標注。"""

    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._erasing = False
        self._cursor_pos: QPoint | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        if event.button() == Qt.MouseButton.LeftButton:
            self._erasing = True
            self._erase_at(widget, pos)

    def mouse_move(self, widget, event, pos: QPoint):
        self._cursor_pos = pos
        widget.update()
        if self._erasing:
            self._erase_at(widget, pos)

    def mouse_release(self, widget, event, pos: QPoint):
        self._erasing = False

    def _erase_at(self, widget, pos: QPoint):
        pdf_pt = self._pdf_point(widget, pos)
        page = self.doc.fitz_doc[widget.page_num]
        to_delete = []
        for annot in page.annots():
            r = annot.rect
            # 擴大 4pt 偵測範圍，方便點選
            if r.contains(pdf_pt) or fitz.Rect(
                    r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4).contains(pdf_pt):
                to_delete.append(annot)
        for a in to_delete:
            self.doc.annotations.delete_annot(widget.page_num, a)
        if to_delete:
            widget.update()

    def draw_overlay(self, widget, painter):
        if not self._cursor_pos:
            return
        painter.save()
        pen = QPen(QColor(200, 0, 0), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(200, 0, 0, 20))
        painter.drawEllipse(self._cursor_pos, 12, 12)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 圖章（Stamp）— 含選擇器
# ═══════════════════════════════════════════════════════════════

class StampTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None
        self._chosen_stamp = "Draft"

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() < 10 or rect_w.height() < 10:
            self._start = None
            return
        dlg = _StampChooserDialog(widget)
        if dlg.exec():
            stamp = dlg.get_stamp()
            pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
            self.doc.annotations.add_stamp(widget.page_num, pdf_rect, stamp)
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 120, 80, 0)


# ═══════════════════════════════════════════════════════════════
# 塗黑（Redact）
# ═══════════════════════════════════════════════════════════════

class RedactTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() < 10 or rect_w.height() < 10:
            self._start = None
            return
        pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
        self.doc.annotations.add_redact(widget.page_num, pdf_rect, text="")
        QMessageBox.information(widget, "已標記塗黑",
                                "已加入塗黑區塊。儲存前請從選單執行「套用永久塗黑」。")
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 20, 20, 20)


# ═══════════════════════════════════════════════════════════════
# 矩形（Shape）
# ═══════════════════════════════════════════════════════════════

class RectTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() >= 5 and rect_w.height() >= 5:
            self.doc.annotations.add_rect(
                widget.page_num,
                self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight()),
                color=(1, 0, 0))
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 220, 30, 30)


# ═══════════════════════════════════════════════════════════════
# 圓形（Circle）
# ═══════════════════════════════════════════════════════════════

class CircleTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() >= 5 and rect_w.height() >= 5:
            self.doc.annotations.add_circle(
                widget.page_num,
                self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight()),
                color=(0, 0.5, 1))
        self._start = None

    def draw_overlay(self, widget, painter):
        if not self._overlay:
            return
        painter.save()
        pen = QPen(QColor(0, 120, 255), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 120, 255, 20))
        painter.drawEllipse(self._overlay)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 線條（Line）
# ═══════════════════════════════════════════════════════════════

class LineTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._end_pos: QPoint | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._end_pos = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._end_pos = pos
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        if self._start and pos:
            p1 = self._pdf_point(widget, self._start)
            p2 = self._pdf_point(widget, pos)
            dx, dy = p2.x - p1.x, p2.y - p1.y
            if math.hypot(dx, dy) >= 5:
                self.doc.annotations.add_line(
                    widget.page_num, p1, p2, color=(0, 0, 0))
        self._start = None
        self._end_pos = None
        widget.update()

    def draw_overlay(self, widget, painter):
        if not self._start or not self._end_pos:
            return
        painter.save()
        painter.setPen(QPen(QColor(0, 0, 0), 2, Qt.PenStyle.SolidLine))
        painter.drawLine(self._start, self._end_pos)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 箭頭（Arrow）
# ═══════════════════════════════════════════════════════════════

class ArrowTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._end_pos: QPoint | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._end_pos = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._end_pos = pos
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        if self._start and pos:
            p1 = self._pdf_point(widget, self._start)
            p2 = self._pdf_point(widget, pos)
            if math.hypot(p2.x - p1.x, p2.y - p1.y) >= 5:
                self.doc.annotations.add_line(
                    widget.page_num, p1, p2, color=(0.8, 0, 0),
                    end_symbol="OpenArrow")
        self._start = None
        self._end_pos = None
        widget.update()

    def draw_overlay(self, widget, painter):
        if not self._start or not self._end_pos:
            return
        painter.save()
        pen = QPen(QColor(200, 0, 0), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(self._start, self._end_pos)
        # 箭頭頭部
        dx = self._end_pos.x() - self._start.x()
        dy = self._end_pos.y() - self._start.y()
        length = math.hypot(dx, dy)
        if length > 0:
            ux, uy = dx / length, dy / length
            ah = 14  # 箭頭長
            aw = 7   # 箭頭寬
            ex, ey = self._end_pos.x(), self._end_pos.y()
            lx = int(ex - ah * ux + aw * uy)
            ly = int(ey - ah * uy - aw * ux)
            rx = int(ex - ah * ux - aw * uy)
            ry = int(ey - ah * uy + aw * ux)
            from PyQt6.QtGui import QPolygon
            painter.setBrush(QColor(200, 0, 0))
            painter.drawPolygon(QPolygon([
                self._end_pos,
                QPoint(lx, ly),
                QPoint(rx, ry),
            ]))
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 測量距離
# ═══════════════════════════════════════════════════════════════

class MeasureDistTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._p1: QPoint | None = None
        self._p2: QPoint | None = None
        self._label = ""

    def mouse_press(self, widget, event, pos: QPoint):
        if event.button() == Qt.MouseButton.LeftButton:
            self._p1 = pos
            self._p2 = None
            self._label = ""
            widget.update()

    def mouse_move(self, widget, event, pos: QPoint):
        if self._p1:
            self._p2 = pos
            pp1 = self._pdf_point(widget, self._p1)
            pp2 = self._pdf_point(widget, pos)
            dist_pt = math.hypot(pp2.x - pp1.x, pp2.y - pp1.y)
            dist_mm = dist_pt * 25.4 / 72
            self._label = f"{dist_mm:.2f} mm  ({dist_pt:.1f} pt)"
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        pass  # 保持顯示直到下次按下

    def draw_overlay(self, widget, painter):
        if not self._p1 or not self._p2:
            return
        painter.save()
        # 線條
        pen = QPen(QColor(255, 100, 0), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(self._p1, self._p2)
        # 端點
        painter.setBrush(QColor(255, 100, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self._p1, 5, 5)
        painter.drawEllipse(self._p2, 5, 5)
        # 距離文字（白色底）
        if self._label:
            mid = QPoint((self._p1.x() + self._p2.x()) // 2,
                         (self._p1.y() + self._p2.y()) // 2 - 12)
            bg_pen = QPen(QColor(255, 255, 255))
            painter.setPen(bg_pen)
            f = QFont()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            # 白色陰影
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(QPoint(mid.x() + dx, mid.y() + dy), self._label)
            painter.setPen(QColor(200, 60, 0))
            painter.drawText(mid, self._label)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 測量面積（多邊形，左鍵加點，接近首點自動閉合）
# ═══════════════════════════════════════════════════════════════

class MeasureAreaTool(BaseTool):
    _CLOSE_DIST = 16  # 像素距離，接近第一點即閉合

    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._points: list[QPoint] = []
        self._hover: QPoint | None = None
        self._label = ""

    def mouse_press(self, widget, event, pos: QPoint):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._points and self._near_first(pos):
                self._finish(widget)
            else:
                self._points.append(pos)
                self._update_label(widget)
                widget.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 3:
                self._finish(widget)
            else:
                self._points.clear()
                self._label = ""
                widget.update()

    def _near_first(self, pos: QPoint) -> bool:
        if not self._points:
            return False
        dx = pos.x() - self._points[0].x()
        dy = pos.y() - self._points[0].y()
        return math.hypot(dx, dy) <= self._CLOSE_DIST

    def mouse_move(self, widget, event, pos: QPoint):
        self._hover = pos
        widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        pass

    def _update_label(self, widget):
        if len(self._points) < 3:
            return
        # 用 Shoelace 公式計算 widget 像素面積，再換算成 PDF 單位
        pts_pdf = [self._pdf_point(widget, p) for p in self._points]
        n = len(pts_pdf)
        area_pt2 = abs(sum(
            pts_pdf[i].x * pts_pdf[(i + 1) % n].y -
            pts_pdf[(i + 1) % n].x * pts_pdf[i].y
            for i in range(n)
        )) / 2
        area_mm2 = area_pt2 * (25.4 / 72) ** 2
        self._label = f"面積：{area_mm2:.2f} mm²  ({area_pt2:.0f} pt²)"

    def _finish(self, widget):
        self._update_label(widget)
        if self._label:
            QMessageBox.information(widget, "測量結果", self._label)
        self._points.clear()
        self._hover = None
        self._label = ""
        widget.update()

    def draw_overlay(self, widget, painter):
        pts = self._points
        if not pts:
            return
        painter.save()
        pen = QPen(QColor(0, 180, 90), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        # 已確定的邊
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        # 游標到最後一點的橡皮筋
        if self._hover:
            pen2 = QPen(QColor(0, 180, 90), 2, Qt.PenStyle.DotLine)
            painter.setPen(pen2)
            painter.drawLine(pts[-1], self._hover)
            if len(pts) >= 2:
                painter.drawLine(pts[0], self._hover)
        # 頂點
        painter.setBrush(QColor(0, 180, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        for p in pts:
            painter.drawEllipse(p, 5, 5)
        # 第一個點更大，提示可閉合
        if pts:
            painter.setBrush(QColor(255, 220, 0))
            painter.drawEllipse(pts[0], 7, 7)
        # 面積文字
        if self._label and len(pts) >= 3:
            cx = sum(p.x() for p in pts) // len(pts)
            cy = sum(p.y() for p in pts) // len(pts)
            f = QFont()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.setPen(QColor(0, 100, 40))
            painter.drawText(QPoint(cx, cy), self._label)
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 裁切（Crop）
# ═══════════════════════════════════════════════════════════════

class CropTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

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
            f"裁切第 {widget.page_num + 1} 頁至選取範圍？\n（可透過「還原全頁」恢復）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.doc.pages.crop(widget.page_num, pdf_rect)
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 0, 120, 215)


# ═══════════════════════════════════════════════════════════════
# 連結（Link）
# ═══════════════════════════════════════════════════════════════

class LinkTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

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
        dlg = _LinkDialog(max_page=self.doc.page_count, parent=widget)
        if dlg.exec():
            link_type, target = dlg.get_result()
            if link_type == "url" and target:
                self.doc.annotations.add_link(widget.page_num, pdf_rect, uri=target)
            elif link_type == "page":
                self.doc.annotations.add_link(
                    widget.page_num, pdf_rect, page_target=int(target) - 1)
        self._start = None

    def draw_overlay(self, widget, painter):
        _draw_rubber_band(painter, self._overlay, 0, 100, 220)


# ═══════════════════════════════════════════════════════════════
# 表單欄位（Form Field）
# ═══════════════════════════════════════════════════════════════

class FormFieldTool(BaseTool):
    def __init__(self, mode, view, doc):
        super().__init__(mode, view, doc)
        self._overlay: QRect | None = None

    def mouse_press(self, widget, event, pos: QPoint):
        super().mouse_press(widget, event, pos)
        self._overlay = None

    def mouse_move(self, widget, event, pos: QPoint):
        if self._start:
            self._overlay = _normalized_rect(self._start, pos)
            widget.update()

    def mouse_release(self, widget, event, pos: QPoint):
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        rect_w = _normalized_rect(self._start, pos)
        self._overlay = None
        widget.update()
        if rect_w.width() < 10 or rect_w.height() < 8:
            self._start = None
            return
        pdf_rect = self._pdf_rect(widget, rect_w.topLeft(), rect_w.bottomRight())
        dlg = _FormFieldDialog(widget)
        if dlg.exec():
            ftype, fname, fdefault = dlg.get_result()
            if not fname:
                fname = f"field_{widget.page_num}_{int(pdf_rect.x0)}"
            self.doc.forms.add_field(
                widget.page_num, pdf_rect, ftype, fname, fdefault)
        self._start = None

    def draw_overlay(self, widget, painter):
        if not self._overlay:
            return
        painter.save()
        pen = QPen(QColor(0, 150, 80), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(QColor(200, 255, 220, 40))
        painter.drawRect(self._overlay)
        # 畫「欄位」提示
        f = QFont()
        f.setPointSize(9)
        painter.setFont(f)
        painter.setPen(QColor(0, 120, 60))
        painter.drawText(self._overlay, Qt.AlignmentFlag.AlignCenter, "表單欄位")
        painter.restore()


# ═══════════════════════════════════════════════════════════════
# 工廠
# ═══════════════════════════════════════════════════════════════

class ToolFactory:
    @staticmethod
    def create(mode: ToolMode, view, doc):
        mapping = {
            ToolMode.HIGHLIGHT:    HighlightTool,
            ToolMode.UNDERLINE:    UnderlineTool,
            ToolMode.STRIKEOUT:    StrikeoutTool,
            ToolMode.STICKY_NOTE:  StickyNoteTool,
            ToolMode.TEXT_BOX:     TextBoxTool,
            ToolMode.CALLOUT:      CalloutTool,
            ToolMode.FREEHAND:     FreehandTool,
            ToolMode.ERASER:       EraserTool,
            ToolMode.STAMP:        StampTool,
            ToolMode.REDACT:       RedactTool,
            ToolMode.SHAPE_RECT:   RectTool,
            ToolMode.SHAPE_CIRCLE: CircleTool,
            ToolMode.SHAPE_LINE:   LineTool,
            ToolMode.SHAPE_ARROW:  ArrowTool,
            ToolMode.MEASURE_DIST: MeasureDistTool,
            ToolMode.MEASURE_AREA: MeasureAreaTool,
            ToolMode.CROP:         CropTool,
            ToolMode.LINK:         LinkTool,
            ToolMode.FORM_FIELD:   FormFieldTool,
        }
        tool_cls = mapping.get(mode)
        return tool_cls(mode, view, doc) if tool_cls else None
