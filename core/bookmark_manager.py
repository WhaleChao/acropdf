# ~/Desktop/acropdf/core/bookmark_manager.py
import fitz

class BookmarkManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def get_toc(self) -> list:
        """回傳 [[level, title, page_num, dest], ...]"""
        return self._fitz.get_toc(simple=False) if self._fitz else []

    def set_toc(self, toc: list):
        if not self._fitz:
            return
        self._doc.begin_op("更新書籤")
        self._fitz.set_toc(toc)
        self._doc.end_op()
        self._doc._mark_modified()

    def add(self, title: str, page_num: int, level: int = 1):
        toc = self.get_toc()
        toc.append([level, title, page_num + 1])
        self.set_toc(toc)

    def delete(self, index: int):
        toc = self.get_toc()
        if 0 <= index < len(toc):
            toc.pop(index)
            self.set_toc(toc)

    def rename(self, index: int, new_title: str):
        toc = self.get_toc()
        if 0 <= index < len(toc):
            toc[index][1] = new_title
            self.set_toc(toc)
