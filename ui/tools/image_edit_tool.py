# ~/Desktop/acropdf/ui/tools/image_edit_tool.py
"""
PDF 圖片編輯工具。

提供圖片的插入、替換、刪除與調整大小功能。
點擊既有圖片顯示右鍵選單；點擊空白區域開啟檔案對話框插入新圖片。
所有操作均支援 undo/redo。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QMenu, QMessageBox, QSpinBox,
)

from app.constants import ToolMode
from ui.tools.annotation_tools import BaseTool, _normalized_rect, _draw_rubber_band


# ═══════════════════════════════════════════════════════════════════
#  支援的圖片格式
# ═══════════════════════════════════════════════════════════════════

_IMAGE_FILTER = "圖片檔案 (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp);;所有檔案 (*)"


# ═══════════════════════════════════════════════════════════════════
#  輔助函式
# ═══════════════════════════════════════════════════════════════════

def _find_image_at(page: fitz.Page, point: fitz.Point) -> dict | None:
    """
    在 *page* 中尋找包含 *point* 的圖片。

    回傳 dict:
        xref (int)   : 圖片物件的 xref 編號
        rect (Rect)  : 圖片在頁面上的邊界矩形

    找不到時回傳 None。
    """
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            if rect.is_empty or rect.is_infinite:
                continue
            if rect.contains(point):
                return {"xref": xref, "rect": rect}
    return None


# ═══════════════════════════════════════════════════════════════════
#  調整大小對話框
# ═══════════════════════════════════════════════════════════════════

class _ResizeDialog(QDialog):
    """簡易圖片尺寸調整對話框（寬度 / 高度，單位：點）。"""

    def __init__(self, current_width: int, current_height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("調整圖片大小")
        self.resize(280, 140)

        layout = QFormLayout(self)

        self._w_spin = QSpinBox()
        self._w_spin.setRange(10, 10000)
        self._w_spin.setValue(current_width)
        self._w_spin.setSuffix(" pt")
        layout.addRow("寬度：", self._w_spin)

        self._h_spin = QSpinBox()
        self._h_spin.setRange(10, 10000)
        self._h_spin.setValue(current_height)
        self._h_spin.setSuffix(" pt")
        layout.addRow("高度：", self._h_spin)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_size(self) -> tuple[int, int]:
        """回傳使用者設定的 (寬, 高)。"""
        return self._w_spin.value(), self._h_spin.value()


# ═══════════════════════════════════════════════════════════════════
#  ImageEditTool
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ImageEditTool(BaseTool):
    """
    PDF 圖片編輯工具。

    - 點擊既有圖片：顯示操作選單（替換 / 刪除 / 調整大小）
    - 點擊空白區域：開啟檔案對話框插入新圖片
    """
    _hover_rect: QRect | None = field(default=None, repr=False)
    _selected_info: dict | None = field(default=None, repr=False)

    # ── 滑鼠事件 ──────────────────────────────────────────────────

    def mouse_press(self, widget, event, pos: QPoint) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        pdf_pt = self._pdf_point(widget, pos)
        if pdf_pt is None:
            return

        img = _find_image_at(page, pdf_pt)
        if img:
            # 點擊在既有圖片上 → 顯示操作選單
            self._selected_info = img
            self._show_context_menu(widget, event, pos)
        else:
            # 點擊空白區域 → 插入新圖片
            self._insert_new_image(widget, pdf_pt)

    def mouse_move(self, widget, event, pos: QPoint) -> None:
        """滑鼠移動時偵測游標下方的圖片，顯示選取框。"""
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

        img = _find_image_at(page, pdf_pt)
        if img:
            zoom = getattr(widget, "_zoom", 1.0)
            r = img["rect"]
            self._hover_rect = QRect(
                int(r.x0 * zoom), int(r.y0 * zoom),
                int(r.width * zoom), int(r.height * zoom),
            )
        else:
            self._hover_rect = None
        widget.update()

    def mouse_release(self, widget, event, pos: QPoint) -> None:
        pass

    # ── 覆蓋繪製 ──────────────────────────────────────────────────

    def draw_overlay(self, widget, painter) -> None:
        """在游標下方的圖片周圍繪製選取框與控制點。"""
        if self._hover_rect is None:
            return
        painter.save()
        # 虛線邊框
        pen = QPen(QColor(0, 120, 215), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 120, 215, 20))
        painter.drawRect(self._hover_rect)

        # 四角控制點（小方塊）
        handle_size = 6
        hs = handle_size // 2
        corners = [
            self._hover_rect.topLeft(),
            self._hover_rect.topRight(),
            self._hover_rect.bottomLeft(),
            self._hover_rect.bottomRight(),
        ]
        painter.setPen(QPen(QColor(0, 90, 180), 1))
        painter.setBrush(QColor(255, 255, 255))
        for c in corners:
            painter.drawRect(c.x() - hs, c.y() - hs, handle_size, handle_size)

        painter.restore()

    # ── 內部方法：操作選單 ────────────────────────────────────────

    def _show_context_menu(self, widget, event, pos: QPoint) -> None:
        """顯示圖片操作右鍵選單。"""
        menu = QMenu(widget)
        act_replace = menu.addAction("替換圖片")
        act_delete = menu.addAction("刪除圖片")
        act_resize = menu.addAction("調整大小")

        # 將 widget 本地座標轉為全域座標
        global_pos = widget.mapToGlobal(pos)
        chosen = menu.exec(global_pos)

        if chosen == act_replace:
            self._replace_image(widget)
        elif chosen == act_delete:
            self._delete_image(widget)
        elif chosen == act_resize:
            self._resize_image(widget)

    # ── 內部方法：插入圖片 ────────────────────────────────────────

    def _insert_new_image(self, widget, pdf_pt: fitz.Point) -> None:
        """開啟檔案對話框，在 *pdf_pt* 位置插入使用者選擇的圖片。"""
        path, _ = QFileDialog.getOpenFileName(
            widget, "選擇要插入的圖片", "", _IMAGE_FILTER,
        )
        if not path:
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        # 預設插入尺寸 200x200，原點為點擊位置
        insert_rect = fitz.Rect(
            pdf_pt.x, pdf_pt.y,
            pdf_pt.x + 200, pdf_pt.y + 200,
        )
        # 確保不超出頁面邊界
        page_rect = page.rect
        insert_rect = insert_rect & page_rect  # 交集
        if insert_rect.is_empty:
            insert_rect = fitz.Rect(
                pdf_pt.x, pdf_pt.y,
                min(pdf_pt.x + 200, page_rect.x1),
                min(pdf_pt.y + 200, page_rect.y1),
            )

        self.doc.begin_op("插入圖片")
        try:
            page.insert_image(insert_rect, filename=path)
        except Exception as exc:
            QMessageBox.warning(widget, "插入失敗", f"無法插入圖片：\n{exc}")
            print(f"[ImageEditTool] 插入圖片失敗: {exc}")
        finally:
            self.doc.end_op()
            self.doc._mark_modified()

        self._refresh(widget)

    # ── 內部方法：替換圖片 ────────────────────────────────────────

    def _replace_image(self, widget) -> None:
        """替換選取的圖片：刪除舊內容，在同一位置插入新圖片。"""
        if not self._selected_info:
            return

        path, _ = QFileDialog.getOpenFileName(
            widget, "選擇替換的圖片", "", _IMAGE_FILTER,
        )
        if not path:
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        rect = self._selected_info["rect"]

        self.doc.begin_op("替換圖片")
        try:
            # 先塗銷原圖區域
            page.add_redact_annot(rect)
            page.apply_redactions()
            # 在原位置插入新圖片
            page.insert_image(rect, filename=path)
        except Exception as exc:
            QMessageBox.warning(widget, "替換失敗", f"無法替換圖片：\n{exc}")
            print(f"[ImageEditTool] 替換圖片失敗: {exc}")
        finally:
            self.doc.end_op()
            self.doc._mark_modified()

        self._selected_info = None
        self._refresh(widget)

    # ── 內部方法：刪除圖片 ────────────────────────────────────────

    def _delete_image(self, widget) -> None:
        """刪除選取的圖片（以塗銷方式移除）。"""
        if not self._selected_info:
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        reply = QMessageBox.question(
            widget, "確認刪除",
            "確定要刪除此圖片嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        rect = self._selected_info["rect"]

        self.doc.begin_op("刪除圖片")
        try:
            page.add_redact_annot(rect)
            page.apply_redactions()
        except Exception as exc:
            QMessageBox.warning(widget, "刪除失敗", f"無法刪除圖片：\n{exc}")
            print(f"[ImageEditTool] 刪除圖片失敗: {exc}")
        finally:
            self.doc.end_op()
            self.doc._mark_modified()

        self._selected_info = None
        self._refresh(widget)

    # ── 內部方法：調整大小 ────────────────────────────────────────

    def _resize_image(self, widget) -> None:
        """以對話框讓使用者輸入新的寬高，重新插入圖片。"""
        if not self._selected_info:
            return

        page = self._page(widget.page_num)
        if page is None:
            return

        old_rect = self._selected_info["rect"]
        xref = self._selected_info["xref"]

        dlg = _ResizeDialog(
            int(old_rect.width), int(old_rect.height), widget,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_w, new_h = dlg.get_size()
        new_rect = fitz.Rect(
            old_rect.x0, old_rect.y0,
            old_rect.x0 + new_w, old_rect.y0 + new_h,
        )

        self.doc.begin_op("調整圖片大小")
        try:
            # 擷取原圖片資料
            fd = self.doc.fitz_doc
            img_data = fd.extract_image(xref)
            if not img_data:
                raise ValueError("無法擷取原始圖片資料")
            image_bytes = img_data["image"]
            ext = img_data.get("ext", "png")

            # 塗銷舊圖
            page.add_redact_annot(old_rect)
            page.apply_redactions()

            # 在新矩形插入原圖
            page.insert_image(new_rect, stream=image_bytes)
        except Exception as exc:
            QMessageBox.warning(widget, "調整失敗", f"無法調整圖片大小：\n{exc}")
            print(f"[ImageEditTool] 調整圖片大小失敗: {exc}")
        finally:
            self.doc.end_op()
            self.doc._mark_modified()

        self._selected_info = None
        self._refresh(widget)

    # ── 工具重新整理 ──────────────────────────────────────────────

    def _refresh(self, widget) -> None:
        """通知檢視器重新渲染目前頁面。"""
        if hasattr(self.view, "refresh_page"):
            self.view.refresh_page(widget.page_num)
        elif hasattr(widget, "update"):
            widget.update()
