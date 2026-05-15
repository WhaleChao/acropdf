# ~/Desktop/acropdf/ui/panels/bookmark_panel.py
from PyQt6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QMenu,
                              QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction


class BookmarkPanel(QTreeWidget):
    bookmark_clicked  = pyqtSignal(int)   # page_num (0-based)
    add_requested     = pyqtSignal()      # 主視窗負責取得當前頁並呼叫
    delete_requested  = pyqtSignal(int)   # flat index in TOC
    rename_requested  = pyqtSignal(int, str)  # flat index, new_title

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_doc = None
        self._flat_toc: list = []          # 目前載入的 TOC（flat list）

        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.header().setStretchLastSection(True)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_double_clicked)

    def load_document(self, doc, force_reload: bool = False):
        doc_id = id(doc) if doc else None
        if doc_id == self._current_doc and not force_reload:
            return
        self._current_doc = doc_id
        self.clear()
        self._flat_toc = []
        if not doc or not doc.fitz_doc:
            return
        self._flat_toc = doc.bookmarks.get_toc()
        self._build_tree(self._flat_toc)

    def _build_tree(self, toc: list):
        self.clear()
        stack = [self.invisibleRootItem()]
        for entry in toc:
            try:
                level = max(1, entry[0])
                title = str(entry[1]) if len(entry) > 1 else ""
                page  = (entry[2] - 1) if len(entry) > 2 else 0
            except (IndexError, TypeError, ValueError):
                continue
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, max(0, page))
            while len(stack) > level and len(stack) > 1:
                stack.pop()
            stack[-1].addChild(item)
            stack.append(item)
        self.expandAll()
        self.resizeColumnToContents(0)

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None and isinstance(page, int) and page >= 0:
            self.bookmark_clicked.emit(page)

    def _on_double_clicked(self, item: QTreeWidgetItem, col: int):
        """雙擊重新命名書籤。"""
        idx = self._flat_index_of(item)
        if idx < 0:
            return
        old_title = item.text(0)
        new_title, ok = QInputDialog.getText(
            self, "重新命名書籤", "書籤名稱：", text=old_title
        )
        if ok and new_title.strip():
            self.rename_requested.emit(idx, new_title.strip())

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        idx  = self._flat_index_of(item) if item else -1

        menu = QMenu(self)
        act_add = QAction("新增書籤（目前頁面）", self)
        act_add.triggered.connect(self.add_requested.emit)
        menu.addAction(act_add)

        if item and idx >= 0:
            menu.addSeparator()
            act_rename = QAction("重新命名…", self)
            act_rename.triggered.connect(lambda: self._on_double_clicked(item, 0))
            menu.addAction(act_rename)

            act_del = QAction("刪除書籤", self)
            act_del.triggered.connect(lambda: self.delete_requested.emit(idx))
            menu.addAction(act_del)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _flat_index_of(self, item: QTreeWidgetItem | None) -> int:
        """把 tree widget item 對應回 flat TOC 的索引（用 title+page 比對）。"""
        if item is None or not self._flat_toc:
            return -1
        title = item.text(0)
        page  = item.data(0, Qt.ItemDataRole.UserRole)
        for i, entry in enumerate(self._flat_toc):
            try:
                if str(entry[1]) == title and (entry[2] - 1) == page:
                    return i
            except (IndexError, TypeError):
                continue
        return -1
