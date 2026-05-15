# ~/Desktop/acropdf/ui/panels/thumbnail_panel.py
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QAbstractItemView,
                              QMenu, QStyledItemDelegate, QStyle, QListView)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QRect
from PyQt6.QtGui import (QPixmap, QImage, QIcon, QAction, QKeySequence,
                          QPainter, QFontMetrics, QPen, QColor)
from app.constants import THUMBNAIL_SIZE, THUMBNAIL_DPI


class _ThumbDelegate(QStyledItemDelegate):
    """自訂繪製：圖示置中在上、頁碼置中在下。"""

    def __init__(self, icon_size: QSize, parent=None):
        super().__init__(parent)
        self._icon_w = icon_size.width()
        self._icon_h = icon_size.height()

    def paint(self, painter: QPainter, option, index):
        painter.save()
        # 選取背景
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        rect = option.rect
        # 圖示區域（上方置中）
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            pm = icon.pixmap(self._icon_w, self._icon_h)
            x = rect.x() + (rect.width() - pm.width()) // 2
            y = rect.y() + 4
            painter.drawPixmap(x, y, pm)

        # 頁碼文字（下方置中）
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fm = QFontMetrics(option.font)
        text_rect = QRect(rect.x(), rect.y() + self._icon_h + 6,
                          rect.width(), fm.height() + 4)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(option.palette.highlightedText().color()))
        else:
            painter.setPen(QPen(option.palette.text().color()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        fm = QFontMetrics(option.font)
        return QSize(self._icon_w + 24, self._icon_h + fm.height() + 14)


class ThumbnailPanel(QListWidget):
    page_selected = pyqtSignal(int)
    pages_reordered = pyqtSignal(list)
    context_action = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_doc = None
        self._current_doc_ref = None
        self._syncing_page = False
        self._drop_in_progress = False
        self._rendered_pages: set[int] = set()
        self._thumb_timer = None

        # IconMode + LeftToRight 流向：依面板寬度自動換行（1欄→2欄→N欄）
        # ResizeMode.Adjust 讓拖拉分隔軸時即時重新排列
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.setSpacing(4)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.currentRowChanged.connect(self._on_row_changed)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._schedule_visible_thumbnail_render())

        # 自訂 delegate：圖示在上、頁碼在下（保持 IconMode 視覺效果）
        self._delegate = _ThumbDelegate(QSize(*THUMBNAIL_SIZE), self)
        self.setItemDelegate(self._delegate)

    def _on_row_changed(self, row: int):
        if row >= 0 and not self._syncing_page:
            self.page_selected.emit(row)

    @staticmethod
    def _render_thumb(fitz_doc: fitz.Document, page_num: int) -> QPixmap | None:
        try:
            page = fitz_doc[page_num]
            zoom = THUMBNAIL_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples_ptr, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(img).scaled(
                THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            return None

    def load_document(self, doc, force_reload: bool = False):
        doc_id = id(doc) if doc else None
        if doc_id == self._current_doc and not force_reload:
            return

        self._current_doc = doc_id
        self._current_doc_ref = doc
        self._rendered_pages.clear()
        self.clear()
        if not doc or not doc.fitz_doc:
            return

        for i in range(doc.page_count):
            item = QListWidgetItem(str(i + 1))
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(item)
        self._schedule_visible_thumbnail_render()

    def invalidate_cache(self, doc=None):
        if doc is None or id(doc) == self._current_doc:
            self._rendered_pages.clear()
            for i in range(self.count()):
                item = self.item(i)
                if item:
                    item.setIcon(QIcon())
            self._schedule_visible_thumbnail_render()

    def update_page_thumbnail(self, page_num: int):
        """只重繪單一頁的縮圖，避免整份文件重新整理。"""
        if self._current_doc_ref is None:
            return
        doc = self._current_doc_ref
        if not doc or not doc.fitz_doc:
            return
        if 0 <= page_num < self.count():
            pm = self._render_thumb(doc.fitz_doc, page_num)
            if pm:
                item = self.item(page_num)
                if item:
                    item.setIcon(QIcon(pm))
                    self._rendered_pages.add(page_num)

    def _schedule_visible_thumbnail_render(self):
        from PyQt6.QtCore import QTimer
        if self._thumb_timer is None:
            self._thumb_timer = QTimer(self)
            self._thumb_timer.setSingleShot(True)
            self._thumb_timer.timeout.connect(self._render_visible_thumbnails)
        self._thumb_timer.start(40)

    def _render_visible_thumbnails(self):
        doc = self._current_doc_ref
        if not self.isVisible() or not doc or not doc.fitz_doc or self.count() == 0:
            return

        viewport_rect = self.viewport().rect().adjusted(0, -220, 0, 220)
        rendered = 0
        for i in range(self.count()):
            if i in self._rendered_pages:
                continue
            item = self.item(i)
            if not item:
                continue
            if not viewport_rect.intersects(self.visualItemRect(item)):
                continue
            pm = self._render_thumb(doc.fitz_doc, i)
            if pm:
                item.setIcon(QIcon(pm))
            self._rendered_pages.add(i)
            rendered += 1
            if rendered >= 12:
                self._schedule_visible_thumbnail_render()
                break

    def selected_page_indices(self) -> list[int]:
        indices = [item.data(Qt.ItemDataRole.UserRole)
                   for item in self.selectedItems()]
        return sorted(set(indices))

    def _show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        indices = self.selected_page_indices()
        if not indices and item:
            indices = [item.data(Qt.ItemDataRole.UserRole)]

        menu = QMenu(self)
        n = len(indices)
        label = f"（{n} 頁）" if n > 1 else ""

        ins_menu = menu.addMenu("插入頁面")
        ins_menu.addAction("從檔案插入...", lambda: self.context_action.emit("insert_from_file", indices))
        ins_menu.addAction("插入空白頁（在前）", lambda: self.context_action.emit("insert_blank_before", indices))
        ins_menu.addAction("插入空白頁（在後）", lambda: self.context_action.emit("insert_blank_after", indices))
        menu.addSeparator()

        act_del = menu.addAction(f"刪除頁面{label}")
        act_del.setShortcut(QKeySequence("Delete"))
        act_del.triggered.connect(lambda: self.context_action.emit("delete", indices))
        menu.addAction(f"擷取頁面{label}...",
                       lambda: self.context_action.emit("extract", indices))
        menu.addAction("取代頁面...",
                       lambda: self.context_action.emit("replace", indices))
        menu.addAction(f"分割文件{label}...",
                       lambda: self.context_action.emit("split", indices))
        menu.addSeparator()

        menu.addAction(f"向右旋轉 90°{label}",
                       lambda: self.context_action.emit("rotate_cw", indices))
        menu.addAction(f"向左旋轉 90°{label}",
                       lambda: self.context_action.emit("rotate_ccw", indices))
        menu.addSeparator()

        menu.addAction("加浮水印...",
                       lambda: self.context_action.emit("watermark", indices))
        menu.addAction("加頁首頁尾...",
                       lambda: self.context_action.emit("header_footer", indices))
        menu.addSeparator()

        menu.addAction("頁面屬性...",
                       lambda: self.context_action.emit("properties", indices))

        if item:
            menu.exec(self.mapToGlobal(pos))

    def resizeEvent(self, event):
        """面板寬度改變（例如拉動分隔軸）時，通知 Qt 重新計算換行排列。"""
        super().resizeEvent(event)
        self.scheduleDelayedItemsLayout()
        self._schedule_visible_thumbnail_render()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_visible_thumbnail_render()

    def dropEvent(self, event):
        self._drop_in_progress = True
        super().dropEvent(event)
        self._drop_in_progress = False
        new_order = []
        for i in range(self.count()):
            item = self.item(i)
            if item:
                new_order.append(item.data(Qt.ItemDataRole.UserRole))
        if new_order:
            self.pages_reordered.emit(new_order)

    def keyPressEvent(self, event):
        indices = self.selected_page_indices()
        key = event.key()
        mods = event.modifiers()
        has_cmd = bool(mods & Qt.KeyboardModifier.ControlModifier)

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and indices:
            self.context_action.emit("delete", indices)
        elif key == Qt.Key.Key_L and has_cmd and indices:
            self.context_action.emit("rotate_ccw", indices)
        elif key == Qt.Key.Key_R and has_cmd and indices:
            self.context_action.emit("rotate_cw", indices)
        elif key == Qt.Key.Key_BracketLeft and indices:
            self.context_action.emit("rotate_ccw", indices)
        elif key == Qt.Key.Key_BracketRight and indices:
            self.context_action.emit("rotate_cw", indices)
        else:
            super().keyPressEvent(event)
