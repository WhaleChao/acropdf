# ~/Desktop/acropdf/core/annotation_manager.py
import fitz
from PyQt6.QtGui import QColor

class AnnotationManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _page(self, page_num: int) -> fitz.Page:
        """取得頁面，含邊界與 None 防護。"""
        doc = self._fitz
        if doc is None:
            raise RuntimeError("尚未載入文件")
        if page_num < 0 or page_num >= doc.page_count:
            raise IndexError(f"頁碼 {page_num} 超出範圍 (共 {doc.page_count} 頁)")
        return doc[page_num]

    # ── 基礎 ─────────────────────────────────────────────────────
    def get_annots(self, page_num: int) -> list[fitz.Annot]:
        try:
            page = self._page(page_num)
            if page is None:
                return []
            return list(page.annots() or [])
        except (RuntimeError, IndexError, TypeError):
            return []

    def delete_annot(self, page_num: int, annot: fitz.Annot):
        page = self._page(page_num)
        if page is None:
            return
        self._doc.begin_op("刪除標注")
        page.delete_annot(annot)
        self._doc.end_op()
        self._doc._mark_modified()

    def flatten(self, page_indices: list[int] | None = None):
        """攤平：將標注永久燒入頁面"""
        if self._fitz is None:
            raise RuntimeError("尚未載入文件")
        self._doc.begin_op("攤平標注")
        indices = page_indices if page_indices else range(self._fitz.page_count)
        for i in indices:
            self._page(i).clean_contents()
        self._doc.end_op()
        self._doc._mark_modified()

    # ── 螢光筆 / 底線 / 刪除線 ───────────────────────────────────
    def add_highlight(self, page_num: int, quads: list[fitz.Quad],
                      color: tuple = (1, 1, 0), opacity: float = 0.5):
        self._doc.begin_op("加螢光筆")
        page = self._page(page_num)
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
        page = self._page(page_num)
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
        page = self._page(page_num)
        annot = page.add_underline_annot(quads)
        annot.set_colors(stroke=color)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_strikeout(self, page_num: int, quads: list[fitz.Quad],
                      color: tuple = (1, 0, 0)):
        self._doc.begin_op("加刪除線")
        page = self._page(page_num)
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
        page = self._page(page_num)
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
        page = self._page(page_num)
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
        page = self._page(page_num)
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
        page = self._page(page_num)
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
        page = self._page(page_num)
        annot = page.add_circle_annot(rect)
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=width)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # 線條端點符號映射（相容 PyMuPDF 1.24+）
    _LE_MAP = {
        "None": 0,   # PDF_ANNOT_LE_NONE
        "Square": 1, "Circle": 2, "Diamond": 3,
        "OpenArrow": 4, "ClosedArrow": 5,
        "Butt": 6, "ROpenArrow": 7, "RClosedArrow": 8, "Slash": 9,
    }

    def add_line(self, page_num: int, p1: fitz.Point, p2: fitz.Point,
                 color: tuple = (0, 0, 0), width: float = 1.5,
                 start_symbol: str = "None", end_symbol: str = "None"):
        self._doc.begin_op("加線條")
        page = self._page(page_num)
        annot = page.add_line_annot(p1, p2)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        le_start = self._LE_MAP.get(start_symbol, 0)
        le_end = self._LE_MAP.get(end_symbol, 0)
        try:
            annot.set_line_ends(le_start, le_end)
        except (TypeError, Exception):
            pass  # 舊版 PyMuPDF 或不支援：略過端點設定
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 區塊底線 / 刪除線 ─────────────────────────────────────────
    def add_area_underline(self, page_num: int, rect: fitz.Rect,
                           color: tuple = (0, 0, 1)):
        self._doc.begin_op("加底線")
        page = self._page(page_num)
        annot = page.add_underline_annot([rect])
        annot.set_colors(stroke=color)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def add_area_strikeout(self, page_num: int, rect: fitz.Rect,
                           color: tuple = (1, 0, 0)):
        self._doc.begin_op("加刪除線")
        page = self._page(page_num)
        annot = page.add_strikeout_annot([rect])
        annot.set_colors(stroke=color)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 標注框（Callout）────────────────────────────────────────────
    def add_callout(self, page_num: int, rect: fitz.Rect, text: str,
                    fontsize: float = 11):
        self._doc.begin_op("加標注框")
        page = self._page(page_num)
        # 指向點：矩形左上角外側
        tip = fitz.Point(rect.x0 - 30, rect.y0 - 30)
        knee = fitz.Point(rect.x0, rect.y0)
        try:
            annot = page.add_freetext_annot(
                rect, text, fontsize=fontsize, fontname="helv",
                text_color=(0, 0, 0), fill_color=(1, 1, 0.8),
                callout=[tip, knee, fitz.Point(rect.x0, rect.y0 + 4)],
            )
        except TypeError:
            # 舊版 PyMuPDF 不支援 callout 參數，退回普通文字框
            annot = page.add_freetext_annot(
                rect, text, fontsize=fontsize, fontname="helv",
                text_color=(0, 0, 0), fill_color=(1, 1, 0.8),
            )
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 連結（Link）──────────────────────────────────────────────────
    def add_link(self, page_num: int, rect: fitz.Rect,
                 uri: str = None, page_target: int = None):
        self._doc.begin_op("加連結")
        page = self._page(page_num)
        if uri:
            lnk = {"kind": fitz.LINK_URI, "from": rect, "uri": uri}
        elif page_target is not None:
            lnk = {
                "kind": fitz.LINK_GOTO, "from": rect,
                "page": page_target, "to": fitz.Point(0, 0), "zoom": 0,
            }
        else:
            self._doc.end_op()
            return None
        page.insert_link(lnk)
        self._doc.end_op()
        self._doc._mark_modified()

    # ── 圖章 ─────────────────────────────────────────────────────
    BUILTIN_STAMPS = [
        "Approved", "AsIs", "Confidential", "Departmental", "Draft",
        "Experimental", "Expired", "Final", "ForComment", "ForPublicRelease",
        "NotApproved", "NotForPublicRelease", "Sold", "TopSecret"
    ]

    def add_stamp(self, page_num: int, rect: fitz.Rect, stamp_name: str = "Draft"):
        self._doc.begin_op("加圖章")
        page = self._page(page_num)
        annot = page.add_stamp_annot(rect, stamp=self.BUILTIN_STAMPS.index(stamp_name)
                                     if stamp_name in self.BUILTIN_STAMPS else 7)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    # ── 塗黑（Redact）────────────────────────────────────────────
    def add_redact(self, page_num: int, rect: fitz.Rect, text: str = ""):
        self._doc.begin_op("標記塗黑")
        page = self._page(page_num)
        annot = page.add_redact_annot(rect, text=text)
        annot.update()
        self._doc.end_op()
        self._doc._mark_modified()
        return annot

    def apply_redactions(self, page_indices: list[int] | None = None):
        """永久執行塗黑"""
        if not self._fitz:
            return
        self._doc.begin_op("執行塗黑")
        indices = page_indices if page_indices else range(self._fitz.page_count)
        for i in indices:
            page = self._page(i)
            if page is None:
                continue
            page.apply_redactions()
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
