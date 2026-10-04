# ~/Desktop/acropdf/core/text_reflow_engine.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import fitz


@dataclass
class TextSpan:
    text: str
    font: str
    size: float
    color: tuple
    origin: tuple  # (x, y)


@dataclass
class TextBlock:
    spans: list[TextSpan]
    rect: tuple       # (x0, y0, x1, y1)
    alignment: str    # "left" | "center" | "right" | "justify"
    line_spacing: float = 1.2


class TextReflowEngine:

    def parse_blocks(self, page: fitz.Page) -> list[TextBlock]:
        """解析頁面文字區塊，保留完整樣式資訊"""
        raw = page.get_text("dict")
        blocks: list[TextBlock] = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:  # 0 = text block
                continue
            spans_all: list[TextSpan] = []
            rect = block.get("bbox", (0, 0, 0, 0))
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    ts = TextSpan(
                        text=span.get("text", ""),
                        font=span.get("font", "helv"),
                        size=span.get("size", 11),
                        color=_int_to_rgb(span.get("color", 0)),
                        origin=span.get("origin", (0, 0)),
                    )
                    spans_all.append(ts)
            if spans_all:
                blocks.append(TextBlock(
                    spans=spans_all,
                    rect=rect,
                    alignment="left",
                ))
        return blocks

    def detect_paragraph_at(self, page: fitz.Page,
                            point: tuple) -> Optional[TextBlock]:
        """偵測點擊位置所在的段落"""
        blocks = self.parse_blocks(page)
        px, py = point
        for blk in blocks:
            x0, y0, x1, y1 = blk.rect
            if x0 <= px <= x1 and y0 <= py <= y1:
                return blk
        return None

    def calculate_char_width(self, font_name: str, font_size: float,
                             char: str) -> float:
        """估算字元寬度（用字型大小比例估算）"""
        if font_size <= 0: raise ValueError("字級必須大於零。")
        font = fitz.Font(fontname="china-t" if any(ord(c)>255 for c in char) else _safe_font(font_name))
        return float(font.text_length(char,fontsize=font_size))

    def reflow(self, block: TextBlock, new_text: str) -> TextBlock:
        """重新排版段落文字"""
        if not block.spans:
            return block
        ref_span = block.spans[0]
        font_size = ref_span.size
        font_name = ref_span.font
        color = ref_span.color

        x0, y0, x1, y1 = block.rect
        width = x1 - x0
        if width <= 0: raise ValueError("段落寬度必須大於零。")
        lines = []
        for paragraph in new_text.replace("\r\n", "\n").split("\n"):
            current_line = ""
            for char in paragraph:
                candidate = current_line + char
                measured = sum(self.calculate_char_width(font_name,font_size,c) for c in candidate)
                if measured > width and current_line:
                    lines.append(current_line);current_line = char
                else: current_line = candidate
            lines.append(current_line)

        # 建立新的 spans
        new_spans = []
        line_height = font_size * block.line_spacing
        for i, line_text in enumerate(lines):
            new_spans.append(TextSpan(
                text=line_text,
                font=font_name,
                size=font_size,
                color=color,
                origin=(x0, ref_span.origin[1] + i * line_height),
            ))

        new_rect = (x0, y0, x1, max(y1, ref_span.origin[1] + max(0,len(lines)-1) * line_height + font_size*.3))
        return TextBlock(spans=new_spans, rect=new_rect, alignment=block.alignment,
                         line_spacing=block.line_spacing)

    def apply_edit(self, page: fitz.Page, old_block: TextBlock,
                   new_block: TextBlock):
        """套用編輯：刪除舊區塊 → 寫入新排版"""
        x0, y0, x1, y1 = old_block.rect
        old_rect = fitz.Rect(x0, y0, x1, y1)
        target = fitz.Rect(new_block.rect)
        if not (page.rect*page.derotation_matrix).contains(target): raise ValueError("重排段落超出頁面。")
        if any(a.type[0]==fitz.PDF_ANNOT_REDACT for a in page.annots() or ()): raise ValueError("請先處理待套用的塗黑標記。")
        for word in page.get_text("words"):
            rect = fitz.Rect(word[:4])
            if rect.intersects(target) and not old_rect.contains(rect): raise ValueError("重排會覆蓋相鄰文字，原文已保留。")
        for span in new_block.spans:
            font=fitz.Font(fontname="china-t" if any(ord(c)>255 for c in span.text) else _safe_font(span.font))
            if any(not c.isspace() and not font.has_glyph(ord(c)) for c in span.text): raise ValueError("字型缺少段落所需字元。")
        page.add_redact_annot(old_rect,fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for span in new_block.spans:
            if span.text.strip():
                page.insert_text(span.origin,span.text,fontname="china-t" if any(ord(c)>255 for c in span.text) else _safe_font(span.font),fontsize=span.size,color=span.color)


def _int_to_rgb(color_int: int) -> tuple:
    return tuple(((color_int>>shift)&255)/255 for shift in (16,8,0))


def _safe_font(font_name: str) -> str:
    names={"Helvetica":"helv", "Times-Roman":"tiro", "Courier":"cour"}
    return names.get(font_name,font_name if font_name in {"helv","tiro","cour","symb","zadb","cjk","china-t"} else "helv")
