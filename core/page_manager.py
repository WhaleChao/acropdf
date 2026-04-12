# ~/Desktop/acropdf/core/page_manager.py
import fitz

class PageManager:
    def __init__(self, doc):
        self._doc = doc  # PDFDocument

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _ensure_doc(self) -> fitz.Document:
        if not self._fitz:
            raise RuntimeError("尚未載入文件")
        return self._fitz

    def rotate(self, page_indices: list[int], angle: int):
        """angle: 90 / 180 / 270"""
        doc = self._ensure_doc()
        self._doc.begin_op("旋轉頁面")
        for i in page_indices:
            page = doc[i]
            page.set_rotation((page.rotation + angle) % 360)
        self._doc.end_op()
        self._doc._mark_modified()

    def delete(self, page_indices: list[int]):
        doc = self._ensure_doc()
        self._doc.begin_op("刪除頁面")
        for i in sorted(page_indices, reverse=True):
            doc.delete_page(i)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def insert_blank(self, after_index: int, width: float = 595, height: float = 842):
        """在 after_index 之後插入空白頁（A4 預設）"""
        doc = self._ensure_doc()
        self._doc.begin_op("插入空白頁")
        insert_at = max(0, min(after_index + 1, doc.page_count))
        doc.new_page(pno=insert_at, width=width, height=height)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def move_page(self, from_index: int, to_index: int):
        doc = self._ensure_doc()
        self._doc.begin_op("移動頁面")
        doc.move_page(from_index, to_index)
        self._doc.end_op()
        self._doc._mark_modified()

    def reorder(self, new_order: list[int]):
        """new_order: 新順序中每個位置對應的原始頁面索引"""
        doc = self._ensure_doc()
        self._doc.begin_op("重排頁面")
        doc.select(new_order)
        self._doc.end_op()
        self._doc._mark_modified()

    def crop(self, page_index: int, rect: fitz.Rect):
        doc = self._ensure_doc()
        self._doc.begin_op("裁切頁面")
        page = doc[page_index]
        page.set_cropbox(rect)
        self._doc.end_op()
        self._doc._mark_modified()

    def merge_pdf(self, other_path: str, insert_at: int = -1):
        """將另一份 PDF 插入到指定位置（-1 = 附加到尾端）"""
        doc = self._ensure_doc()
        self._doc.begin_op("合併 PDF")
        pos = insert_at if insert_at >= 0 else doc.page_count
        src = fitz.open(other_path)
        try:
            doc.insert_pdf(src, start_at=pos)
        finally:
            src.close()
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def extract_pages(self, page_indices: list[int], output_path: str):
        """擷取指定頁面並存成新 PDF"""
        src_doc = self._ensure_doc()
        new_doc = fitz.open()
        new_doc.insert_pdf(src_doc, from_page=0, to_page=src_doc.page_count - 1, start_at=0)
        new_doc.select(page_indices)
        new_doc.save(output_path, garbage=4, deflate=True)
        new_doc.close()

    def split_by_range(self, ranges: list[tuple[int, int]], output_dir: str) -> list[str]:
        """
        ranges: [(0,4), (5,9), ...] 各區段的起始/結束頁（含）
        回傳產生的檔案路徑清單
        """
        import os
        src_doc = self._ensure_doc()
        base = os.path.splitext(os.path.basename(self._doc.path or "output"))[0]
        outputs = []
        for idx, (start, end) in enumerate(ranges):
            out_path = os.path.join(output_dir, f"{base}_part{idx+1}.pdf")
            new_doc = fitz.open()
            new_doc.insert_pdf(src_doc, from_page=start, to_page=end)
            new_doc.save(out_path, garbage=4, deflate=True)
            new_doc.close()
            outputs.append(out_path)
        return outputs

    def add_watermark(self, text: str, page_indices: list[int] | None = None,
                      opacity: float = 0.3, fontsize: float = 60,
                      color: tuple = (0.7, 0.7, 0.7)):
        doc = self._ensure_doc()
        indices = page_indices if page_indices is not None else range(doc.page_count)
        self._doc.begin_op("加浮水印")
        for i in indices:
            page = doc[i]
            r = page.rect
            page.insert_text(
                fitz.Point(r.width * 0.1, r.height * 0.5),
                text,
                fontsize=fontsize,
                rotate=45,
                color=color,
                overlay=True,
            )
        self._doc.end_op()
        self._doc._mark_modified()

    def add_header_footer(self, header: str = "", footer: str = "",
                          page_indices: list[int] | None = None,
                          fontsize: float = 10):
        doc = self._ensure_doc()
        indices = page_indices if page_indices is not None else range(doc.page_count)
        self._doc.begin_op("加頁首頁尾")
        for i in indices:
            page = doc[i]
            r = page.rect
            if header:
                page.insert_text(
                    fitz.Point(r.width / 2 - len(header) * fontsize * 0.3, 20),
                    header, fontsize=fontsize, color=(0, 0, 0)
                )
            if footer:
                page.insert_text(
                    fitz.Point(r.width / 2 - len(footer) * fontsize * 0.3, r.height - 15),
                    footer, fontsize=fontsize, color=(0, 0, 0)
                )
        self._doc.end_op()
        self._doc._mark_modified()
