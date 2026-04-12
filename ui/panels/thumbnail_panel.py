# ~/Desktop/acropdf/ui/panels/thumbnail_panel.py
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QAbstractItemView,
                              QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThreadPool, QRunnable, QObject, QPoint
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction, QKeySequence
from app.constants import THUMBNAIL_SIZE, THUMBNAIL_DPI


class ThumbSignals(QObject):
    done = pyqtSignal(int, QPixmap)


class ThumbWorker(QRunnable):
    def __init__(self, path: str, page_num: int):
        super().__init__()
        self.setAutoDelete(True)
        self._path = path
        self._page_num = page_num
        self.signals = ThumbSignals()
        self._keep = self.signals  # prevent GC

    def run(self):
        try:
            doc = fitz.open(self._path)
            page = doc[self._page_num]
            zoom = THUMBNAIL_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples_ptr, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888).copy()
            pm = QPixmap.fromImage(img).scaled(
                THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            doc.close()
            self.signals.done.emit(self._page_num, pm)
        except Exception:
            pass


class ThumbnailPanel(QListWidget):
    page_selected = pyqtSignal(int)
    pages_reordered = pyqtSignal(list)
    # 右鍵動作信號：(action_id, page_indices)
    context_action = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.setSpacing(6)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.currentRowChanged.connect(self._on_row_changed)

        # 選取提示文字
        self.setStyleSheet("""
            QListWidget::item {
                border-radius: 4px;
                padding: 2px;
                color: palette(text);
            }
            QListWidget::item:selected {
                background: #0078d4;
                border: 2px solid #005a9e;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background: rgba(0,120,212,0.15);
                border: 1px solid rgba(0,120,212,0.4);
            }
        """)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.page_selected.emit(row)

    def load_document(self, doc):
        self.clear()
        if not doc or not doc.fitz_doc:
            return
        for i in range(doc.page_count):
            item = QListWidgetItem(f"  {i+1}  ")
            item.setSizeHint(QSize(THUMBNAIL_SIZE[0] + 20, THUMBNAIL_SIZE[1] + 28))
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.addItem(item)
            if doc.path:
                worker = ThumbWorker(doc.path, i)
                worker.signals.done.connect(self._set_thumb)
                QThreadPool.globalInstance().start(worker)

    def _set_thumb(self, page_num: int, pm: QPixmap):
        item = self.item(page_num)
        if item:
            item.setIcon(QIcon(pm))

    def selected_page_indices(self) -> list[int]:
        """回傳目前選取的 0-based 頁碼，依序排列。"""
        indices = [item.data(Qt.ItemDataRole.UserRole)
                   for item in self.selectedItems()]
        return sorted(set(indices))

    def _show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        indices = self.selected_page_indices()
        if not indices and item:
            indices = [item.data(Qt.ItemDataRole.UserRole)]

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                border: 1px solid rgba(0,0,0,0.15);
                border-radius: 6px;
                padding: 4px;
                background: palette(window);
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected { background: #0078d4; color: white; }
            QMenu::separator { height: 1px; background: rgba(0,0,0,0.1); margin: 4px 8px; }
        """)

        n = len(indices)
        label = f"（{n} 頁）" if n > 1 else ""

        # ── 插入 ──────────────────────────────────────
        ins_menu = menu.addMenu("插入頁面")
        ins_menu.addAction("從 PDF 檔案插入...", lambda: self.context_action.emit("insert_from_file", indices))
        ins_menu.addAction("插入空白頁（在前）", lambda: self.context_action.emit("insert_blank_before", indices))
        ins_menu.addAction("插入空白頁（在後）", lambda: self.context_action.emit("insert_blank_after", indices))

        menu.addSeparator()

        # ── 刪除 / 擷取 / 取代 ──────────────────────
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

        # ── 旋轉 ────────────────────────────────────
        menu.addAction(f"向右旋轉 90°{label}",
                       lambda: self.context_action.emit("rotate_cw", indices))
        menu.addAction(f"向左旋轉 90°{label}",
                       lambda: self.context_action.emit("rotate_ccw", indices))

        menu.addSeparator()

        # ── 浮水印 / 頁首頁尾 ──────────────────────
        menu.addAction("加浮水印...",
                       lambda: self.context_action.emit("watermark", indices))
        menu.addAction("加頁首頁尾...",
                       lambda: self.context_action.emit("header_footer", indices))

        menu.addSeparator()

        # ── 屬性 ────────────────────────────────────
        menu.addAction("頁面屬性...",
                       lambda: self.context_action.emit("properties", indices))

        if item:
            menu.exec(self.mapToGlobal(pos))

    def dropEvent(self, event):
        super().dropEvent(event)
        new_order = [self.item(i).data(Qt.ItemDataRole.UserRole)
                     for i in range(self.count())]
        self.pages_reordered.emit(new_order)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            indices = self.selected_page_indices()
            if indices:
                self.context_action.emit("delete", indices)
        else:
            super().keyPressEvent(event)
