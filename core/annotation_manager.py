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
        indices = set(page_indices if page_indices is not None else range(self._fitz.page_count))
        if not indices or any(not isinstance(i, int) or not 0 <= i < self._fitz.page_count for i in indices):
            raise ValueError("請選擇有效的標注攤平頁面。")
        with self._doc.edit_transaction("攤平標注"):
            hidden = {}
            for page in self._fitz:
                if page.number not in indices:
                    kind, value = self._fitz.xref_get_key(page.xref, 'Annots')
                    if kind != 'null':
                        hidden[page.xref] = value
                        self._fitz.xref_set_key(page.xref, 'Annots', 'null')
            # Bake in place to retain page identities, links, labels and destinations.
            self._fitz.bake(annots=True, widgets=False)
            for page_xref, value in hidden.items():
                self._fitz.xref_set_key(page_xref, 'Annots', value)
            # Loaded MuPDF pages may still render the old annotation over its
            # baked appearance. Reopen the serialized document to release all
            # page caches without replacing PDF page objects or destinations.
            refreshed = fitz.open('pdf', self._doc._snapshot())
            if refreshed.needs_pass and not refreshed.authenticate(self._doc._password):
                refreshed.close()
                raise ValueError('無法認證攤平後的文件。')
            self._fitz.close()
            self._doc._fitz_doc = refreshed

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

    def _selection_quads(self, page_num, rect):
        """Recover the selected glyph geometry, including rotated text."""
        if rect.is_empty or rect.is_infinite:
            raise ValueError("請選取有效的標注範圍。")
        page = self._page(page_num)
        quads = []
        for block in page.get_text('rawdict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    for char in span.get('chars', []):
                        box = fitz.Rect(char['bbox'])
                        if box.is_empty or char['c'].isspace(): continue
                        overlap = box & rect
                        if overlap.get_area() >= box.get_area() * .5:
                            quads.append(fitz.recover_char_quad(line['dir'], span, char))
        return quads

    def add_area_highlight(self, page_num: int, rect: fitz.Rect,
                           color: tuple = (1, 1, 0), opacity: float = 0.35):
        """Highlight actual text quads intersecting a selection; use an area for images."""
        quads = self._selection_quads(page_num, rect)
        if quads:
            return self.add_highlight(page_num, quads, color, opacity)
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
        return self._add_textbox(page_num, rect, text, fontsize, color, fill_color)

    def _add_textbox(self, page_num, rect, text, fontsize, color, fill_color, callout=None):
        import math
        page = self._page(page_num)
        if rect.is_empty or rect.is_infinite or not page.rect.contains(rect):
            raise ValueError("文字框須位於頁面內，且尺寸必須有效。")
        if not math.isfinite(fontsize) or fontsize <= 0 or not text.strip():
            raise ValueError("請輸入文字並設定有效的字級。")
        with self._doc.edit_transaction("加標注框" if callout else "加文字框"):
            annot = page.add_freetext_annot(rect, text, fontsize=fontsize, fontname="helv",
                text_color=color, fill_color=fill_color, align=0,
                **({'callout': callout, 'border_width': 1} if callout else {}))
            annot.update()
            # Check the actual appearance, since MuPDF silently truncates text
            # that does not fit. Line wrapping may change whitespace only.
            if ''.join(annot.get_text().split()) != ''.join(text.split()):
                raise ValueError("文字無法完整顯示，請放大文字框或減小字級；沒有建立截斷的標注。")
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
        quads = self._selection_quads(page_num, rect)
        if not quads:
            raise ValueError("選取範圍內沒有可加底線的文字；掃描頁請先執行 OCR。")
        return self.add_underline(page_num, quads, color)

    def add_area_strikeout(self, page_num: int, rect: fitz.Rect,
                           color: tuple = (1, 0, 0)):
        quads = self._selection_quads(page_num, rect)
        if not quads:
            raise ValueError("選取範圍內沒有可加刪除線的文字；掃描頁請先執行 OCR。")
        return self.add_strikeout(page_num, quads, color)

    # ── 標注框（Callout）────────────────────────────────────────────
    def add_callout(self, page_num: int, rect: fitz.Rect, text: str,
                    fontsize: float = 11):
        page = self._page(page_num)
        tip = fitz.Point(max(page.rect.x0, rect.x0 - 30), max(page.rect.y0, rect.y0 - 30))
        knee = fitz.Point(rect.x0, rect.y0)
        return self._add_textbox(page_num, rect, text, fontsize, (0, 0, 0), (1, 1, 0.8),
                                 [tip, knee, fitz.Point(rect.x0, rect.y0 + 4)])

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
        stamp = getattr(fitz, 'STAMP_' + stamp_name, None)
        if stamp is None: raise ValueError('未知的內建圖章。')
        page = self._page(page_num)
        self._doc.begin_op("加圖章")
        annot = page.add_stamp_annot(rect, stamp=stamp)
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
        return self._doc.redaction.apply_all(page_indices)

    # ── 匯入/匯出 XFDF ───────────────────────────────────────────
    def export_xfdf(self, output_path: str):
        from core.xfdf import export_annotations
        return export_annotations(self._doc, output_path)

    def import_xfdf(self, xfdf_path: str):
        from core.xfdf import import_annotations
        return import_annotations(self._doc, xfdf_path)
