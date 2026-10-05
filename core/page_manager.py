# ~/Desktop/acropdf/core/page_manager.py
import fitz
from core.file_io import publish_exclusive

class PageManager:
    def __init__(self, doc):
        self._doc = doc  # PDFDocument

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _ensure_doc(self) -> fitz.Document:
        if self._fitz is None:
            raise RuntimeError("尚未載入文件")
        return self._fitz

    def rotate(self, page_indices: list[int], angle: int):
        """angle: 90 / 180 / 270"""
        doc = self._ensure_doc()
        self._doc.begin_op("旋轉頁面")
        for i in page_indices:
            if 0 <= i < doc.page_count:
                page = doc[i]
                page.set_rotation((page.rotation + angle) % 360)
        self._doc.end_op()
        self._doc._mark_modified()

    def delete(self, page_indices: list[int]):
        doc = self._ensure_doc()
        # 不能刪除所有頁面（PyMuPDF 不允許 0 頁文件）
        valid = sorted({i for i in page_indices if 0 <= i < doc.page_count})
        if len(valid) >= doc.page_count:
            raise ValueError("無法刪除所有頁面，PDF 至少需保留一頁")
        if not valid:
            return
        self._doc.begin_op("刪除頁面")
        for i in sorted(valid, reverse=True):
            doc.delete_page(i)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def insert_blank(self, at: int, width: float = 595, height: float = 842):
        """在 at 位置插入空白頁（0 = 第一頁之前，A4 預設）"""
        doc = self._ensure_doc()
        self._doc.begin_op("插入空白頁")
        insert_at = max(0, min(at, doc.page_count))
        doc.new_page(pno=insert_at, width=width, height=height)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def move_page(self, from_index: int, to_index: int):
        doc = self._ensure_doc()
        pc = doc.page_count
        if from_index < 0 or from_index >= pc or to_index < 0 or to_index >= pc:
            return
        self._doc.begin_op("移動頁面")
        doc.move_page(from_index, to_index)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def reorder(self, new_order: list[int]):
        """new_order: 新順序中每個位置對應的原始頁面索引"""
        doc = self._ensure_doc()
        if sorted(new_order) != list(range(doc.page_count)):
            raise ValueError("頁面順序必須包含每一頁，且不能重複。")
        self._doc.begin_op("重排頁面")
        doc.select(new_order)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def crop(self, page_index: int, rect: fitz.Rect):
        doc = self._ensure_doc()
        if page_index < 0 or page_index >= doc.page_count:
            return
        self._doc.begin_op("裁切頁面")
        page = doc[page_index]
        page.set_cropbox(rect)
        self._doc.end_op()
        self._doc._mark_modified()

    def replace_pages(self, page_indices: list[int], source_path: str):
        """Replace entire page objects, preserving source vectors and annotations."""
        doc = self._ensure_doc()
        indices = sorted(set(page_indices))
        if not indices or any(i < 0 or i >= doc.page_count for i in indices):
            raise ValueError("請選擇有效的取代頁面。")
        with fitz.open(source_path) as source:
            if source.needs_pass:
                raise ValueError("來源 PDF 需要密碼，請先開啟並另存授權副本。")
            if source.page_count < len(indices):
                raise ValueError("來源頁數不足，沒有執行取代。")
            toc = doc.get_toc()
            self._doc.begin_op("取代頁面")
            for source_index, target in enumerate(indices):
                doc.insert_pdf(source, from_page=source_index, to_page=source_index, start_at=target)
                doc.delete_page(target + 1)
            if toc:
                doc.set_toc(toc)
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def merge_pdf(self, other_path: str, insert_at: int = -1):
        """將另一份 PDF 插入到指定位置（-1 = 附加到尾端）"""
        doc = self._ensure_doc()
        pos = insert_at if insert_at >= 0 else doc.page_count
        try:
            src = fitz.open(other_path)
        except Exception as e:
            raise RuntimeError(f"無法開啟來源檔案：{e}") from e
        self._doc.begin_op("合併 PDF")
        try:
            doc.insert_pdf(src, start_at=pos)
        finally:
            src.close()
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def insert_pdf(self, other_path: str, insert_at: int):
        """在指定位置插入 PDF（右鍵選單入口）"""
        self.merge_pdf(other_path, insert_at=insert_at)

    def insert_file(self, file_path: str, insert_at: int = -1):
        """插入任意支援的檔案（PDF/圖片/Word/Excel/PPTX），自動轉換後插入。"""
        import os
        doc = self._ensure_doc()
        pos = insert_at if insert_at >= 0 else doc.page_count

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            # PDF 直接用 merge_pdf（效率較好）
            self.merge_pdf(file_path, insert_at=pos)
            return

        # 非 PDF：透過 FileConverter 轉為 fitz.Document 後插入
        from core.file_converter import FileConverter, get_file_type
        file_type = get_file_type(file_path)
        if file_type is None:
            raise ValueError(f"不支援的格式：{os.path.basename(file_path)}")

        try:
            converted = FileConverter.convert(file_path)
        except Exception as e:
            raise RuntimeError(f"轉換檔案失敗：{e}") from e

        if converted.page_count == 0:
            converted.close()
            raise RuntimeError("轉換結果為空（0 頁）")

        self._doc.begin_op("插入檔案")
        try:
            doc.insert_pdf(converted, start_at=pos)
        finally:
            converted.close()
        self._doc.end_op()
        self._doc._mark_modified()
        self._doc.page_count_changed.emit(doc.page_count)

    def extract_pages(self, page_indices: list[int], output_path: str):
        """擷取指定頁面並存成新 PDF"""
        src_doc = self._ensure_doc()
        if not page_indices or any(not 0<=i<len(src_doc) for i in page_indices): raise ValueError("擷取頁碼無效。")
        from core.file_io import atomic_output
        with fitz.open('pdf',self._doc._snapshot()) as copied:
            if copied.needs_pass and not copied.authenticate(self._doc._password): raise ValueError("無法認證擷取快照。")
            copied.select(page_indices)
            with atomic_output(output_path,source=self._doc.source_path) as stage:
                copied.save(stage,garbage=4,deflate=True,encryption=fitz.PDF_ENCRYPT_KEEP)

    def split_by_range(self, ranges: list[tuple[int, int]], output_dir: str) -> list[str]:
        from pathlib import Path
        import tempfile
        import os
        src_doc=self._ensure_doc()
        if not ranges or any(not 0<=start<=end<len(src_doc) for start,end in ranges): raise ValueError("分割範圍無效。")
        destination=Path(output_dir);destination.mkdir(parents=True,exist_ok=True)
        base=Path(self._doc.source_path or "output.pdf").stem
        targets=[destination/f"{base}_part{i+1}.pdf" for i in range(len(ranges))]
        if any(path.exists() for path in targets): raise FileExistsError("分割目的檔已存在，原檔保留。")
        published=[]
        with tempfile.TemporaryDirectory(prefix='.acropdf_split_',dir=destination) as directory:
            staged=[]
            for i,(start,end) in enumerate(ranges):
                path=Path(directory)/targets[i].name
                self.extract_pages(list(range(start,end+1)),str(path));staged.append(path)
            try:
                for path,target in zip(staged,targets): publish_exclusive(path,target);published.append(str(target))
            except Exception:
                for path in published: Path(path).unlink(missing_ok=True)
                raise
        return published

    def add_watermark(self, text: str, page_indices: list[int] | None = None,
                      opacity: float = 0.3, fontsize: float = 60,
                      color: tuple = (0.7, 0.7, 0.7)):
        doc = self._ensure_doc()
        if not text:
            return
        fontsize = max(fontsize, 1)
        indices = page_indices if page_indices is not None else range(doc.page_count)
        self._doc.begin_op("加浮水印")
        for i in indices:
            if i < 0 or i >= doc.page_count:
                continue
            page = doc[i]
            r = page.rect
            # 使用 Shape 繪製旋轉浮水印（insert_text 不支援 45° 旋轉）
            shape = page.new_shape()
            # 中心點旋轉 45°
            import math
            cx, cy = r.width / 2, r.height / 2
            morph = (fitz.Point(cx, cy), fitz.Matrix(math.cos(math.radians(45)),
                     math.sin(math.radians(45)),
                     -math.sin(math.radians(45)),
                     math.cos(math.radians(45)), 0, 0))
            shape.insert_text(
                fitz.Point(cx - len(text) * fontsize * 0.25, cy),
                text,
                fontsize=fontsize,
                color=color,
                morph=morph,
                fontname="china-t" if any(ord(c) > 255 for c in text) else "helv",
                fill_opacity=max(0, min(opacity, 1)),
            )
            shape.commit(overlay=True)
        self._doc.end_op()
        self._doc._mark_modified()

    def add_header_footer(self, header: str = "", footer: str = "",
                          page_indices: list[int] | None = None, fontsize: float = 10,
                          header_left: str = "", header_right: str = "", footer_left: str = "",
                          footer_right: str = "", margin: float = 20):
        doc = self._ensure_doc()
        indices = list(page_indices) if page_indices is not None else list(range(doc.page_count))
        if not any((header, footer, header_left, header_right, footer_left, footer_right)):
            return
        if fontsize <= 0 or margin < fontsize:
            raise ValueError("邊距須至少等於字級，以避免文字超出頁面。")
        self._doc.begin_op("加頁首頁尾")
        for i in indices:
            if i < 0 or i >= doc.page_count:
                continue
            page = doc[i]
            r = page.cropbox
            for template, alignment, top in ((header_left, "left", True), (header, "center", True),
                                             (header_right, "right", True), (footer_left, "left", False),
                                             (footer, "center", False), (footer_right, "right", False)):
                if not template:
                    continue
                text = template.replace("<<n>>", str(i + 1)).replace("{page}", str(i + 1)).replace("{total}", str(doc.page_count))
                fontname = "china-t" if any(ord(c) > 255 for c in text) else "helv"
                length = fitz.Font(fontname=fontname).text_length(text, fontsize=fontsize)
                x = margin if alignment == "left" else r.width - margin - length if alignment == "right" else (r.width - length) / 2
                page.insert_text((max(x, margin), margin if top else r.height - margin), text,
                                 fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
        self._doc.end_op()
        self._doc._mark_modified()
