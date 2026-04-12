# ~/Desktop/acropdf/core/annotation_manager.py
import fitz
from PyQt6.QtGui import QColor

class AnnotationManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    # ── 基礎 ─────────────────────────────────────────────────────
    def get_annots(self, page_num: int) -> list[fitz.Annot]:
        return list(self._fitz[page_num].annots()) if self._fitz else []

    def delete_annot(self, page_num: int, annot: fitz.Annot):
        self._doc.begin_op("刪除標注")
        self._fitz[page_num].delete_annot(annot)
        self._doc.end_op()
        self._doc._mark_modified()

    def flatten(self, page_indices: list[int] | None = None):
        """攤平：將標注永久燒入頁面"""
        self._doc.begin_op("攤平標注")
        indices = page_indices if page_indices else range(self._fitz.page_count)
        for i in indices:
            self._fitz[i].clean_contents()
        self._doc.end_op()
        self._doc._mark_modified()

    # ── 螢光筆 / 底線 / 刪除線 ───────────────────────────────────
    def add_highlight(self, page_num: int, quads: list[fitz.Quad],
                      color: tuple = (1, 1, 0), opacity: float = 0.5):
        self._doc.begin_op("加螢光筆")
        page = self._fitz[page_num]
        annot = page.add_highlight_annot(quads)
        annot.set_colors(stroke=color)
        annot.set_opacity(opacity)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_area_highlight(self, page_num: int, rect: fitz.Rect,
                           color: tuple = (1, 1, 0), opacity: float = 0.35):
        """文字選取尚未實作前，先用半透明區塊提供高亮標記。"""
        self._doc.begin_op("區塊高亮")
        page = self._fitz[page_num]
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(opacity)
        annot.set_border(width=0.8)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_underline(self, page_num: int, quads: list[fitz.Quad],
                      color: tuple = (0, 0, 1)):
        self._doc.begin_op("加底線")
        page = self._fitz[page_num]
        annot = page.add_underline_annot(quads)
        annot.set_colors(stroke=color)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_strikeout(self, page_num: int, quads: list[fitz.Quad],
                      color: tuple = (1, 0, 0)):
        self._doc.begin_op("加刪除線")
        page = self._fitz[page_num]
        annot = page.add_strikeout_annot(quads)
        annot.set_colors(stroke=color)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 文字標注 / 便利貼 ────────────────────────────────────────
    def add_text_annot(self, page_num: int, point: fitz.Point,
                       content: str, author: str = "", icon: str = "Note"):
        self._doc.begin_op("加便利貼")
        page = self._fitz[page_num]
        annot = page.add_text_annot(point, content, icon=icon)
        info = annot.info
        info["title"] = author
        annot.set_info(info)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 文字框 ───────────────────────────────────────────────────
    def add_freetext(self, page_num: int, rect: fitz.Rect, text: str,
                     fontsize: float = 11, color: tuple = (0, 0, 0),
                     fill_color: tuple = (1, 1, 0.8)):
        self._doc.begin_op("加文字框")
        page = self._fitz[page_num]
        annot = page.add_freetext_annot(
            rect, text,
            fontsize=fontsize, fontname="helv",
            text_color=color, fill_color=fill_color,
            align=0
        )
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 手繪 Ink ─────────────────────────────────────────────────
    def add_ink(self, page_num: int, strokes: list[list[tuple[float,float]]],
                color: tuple = (0, 0, 1), width: float = 1.5):
        self._doc.begin_op("手繪")
        page = self._fitz[page_num]
        annot = page.add_ink_annot(strokes)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 圖形 ─────────────────────────────────────────────────────
    def add_rect(self, page_num: int, rect: fitz.Rect,
                 color: tuple = (1, 0, 0), fill: tuple | None = None, width: float = 1.5):
        self._doc.begin_op("加矩形")
        page = self._fitz[page_num]
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=width)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_circle(self, page_num: int, rect: fitz.Rect,
                   color: tuple = (1, 0, 0), fill: tuple | None = None, width: float = 1.5):
        self._doc.begin_op("加橢圓")
        page = self._fitz[page_num]
        annot = page.add_circle_annot(rect)
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=width)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_line(self, page_num: int, p1: fitz.Point, p2: fitz.Point,
                 color: tuple = (0, 0, 0), width: float = 1.5,
                 start_symbol: str = "None", end_symbol: str = "None"):
        self._doc.begin_op("加線條")
        page = self._fitz[page_num]
        annot = page.add_line_annot(p1, p2)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.set_line_ends(start_symbol, end_symbol)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 圖章 ─────────────────────────────────────────────────────
    BUILTIN_STAMPS = [
        "Approved", "AsIs", "Confidential", "Departmental", "Draft",
        "Experimental", "Expired", "Final", "ForComment", "ForPublicRelease",
        "NotApproved", "NotForPublicRelease", "Sold", "TopSecret"
    ]

    def add_stamp(self, page_num: int, rect: fitz.Rect, stamp_name: str = "Draft"):
        self._doc.begin_op("加圖章")
        page = self._fitz[page_num]
        annot = page.add_stamp_annot(rect, stamp=self.BUILTIN_STAMPS.index(stamp_name)
                                     if stamp_name in self.BUILTIN_STAMPS else 7)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 塗黑（Redact）────────────────────────────────────────────
    def add_redact(self, page_num: int, rect: fitz.Rect, text: str = ""):
        self._doc.begin_op("標記塗黑")
        page = self._fitz[page_num]
        annot = page.add_redact_annot(rect, text=text)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def apply_redactions(self, page_indices: list[int] | None = None):
        """永久執行塗黑"""
        self._doc.begin_op("執行塗黑")
        indices = page_indices if page_indices else range(self._fitz.page_count)
        for i in indices:
            self._fitz[i].apply_redactions()
        self._doc.end_op()
        self._doc._mark_modified()

    # ── 匯入/匯出 XFDF ───────────────────────────────────────────
    def export_xfdf(self, output_path: str):
        xfdf = self._fitz.get_xfdf() if hasattr(self._fitz, 'get_xfdf') else ""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xfdf)

    def import_xfdf(self, xfdf_path: str):
        with open(xfdf_path, encoding="utf-8") as f:
            content = f.read()
        # PyMuPDF 1.24+ 支援
        if hasattr(self._fitz, 'set_xfdf'):
            self._fitz.set_xfdf(content)
            self._doc._mark_modified()
