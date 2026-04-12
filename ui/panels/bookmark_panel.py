# ~/Desktop/acropdf/ui/panels/bookmark_panel.py
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal

class BookmarkPanel(QTreeWidget):
    bookmark_clicked = pyqtSignal(int)   # page_num (0-based)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.itemClicked.connect(self._on_item_clicked)

    def load_document(self, doc):
        self.clear()
        if not doc or not doc.fitz_doc:
            return
        toc = doc.bookmarks.get_toc()
        self._build_tree(toc)

    def _build_tree(self, toc: list):
        stack = [self.invisibleRootItem()]
        for entry in toc:
            level = entry[0]
            title = entry[1]
            page = entry[2] - 1  # fitz 回傳 1-based
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, page)
            while len(stack) > level:
                stack.pop()
            stack[-1].addChild(item)
            stack.append(item)
        self.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            self.bookmark_clicked.emit(page)
