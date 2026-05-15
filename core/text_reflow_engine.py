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
        # 若有 fontTools 可做精確計算，否則以字型大小 * 0.6 估算
        return font_size * 0.6

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
        char_w = self.calculate_char_width(font_name, font_size, "A")
        chars_per_line = max(1, int(width / char_w))

        # 按字元寬度換行
        words = new_text.split()
        lines = []
        current_line = ""
        for word in words:
            test = (current_line + " " + word).strip()
            if len(test) * char_w <= width:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
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
                origin=(x0, y0 + i * line_height),
            ))

        new_rect = (x0, y0, x1, y0 + len(lines) * line_height)
        return TextBlock(spans=new_spans, rect=new_rect, alignment=block.alignment,
                         line_spacing=block.line_spacing)

    def apply_edit(self, page: fitz.Page, old_block: TextBlock,
                   new_block: TextBlock):
        """套用編輯：刪除舊區塊 → 寫入新排版"""
        x0, y0, x1, y1 = old_block.rect
        old_rect = fitz.Rect(x0, y0, x1, y1)
        page.add_redact_annot(old_rect)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        for span in new_block.spans:
            if span.text.strip():
                page.insert_text(
                    span.origin,
                    span.text,
                    fontname=_safe_font(span.font),
                    fontsize=span.size,
                    color=span.color,
                )


def _int_to_rgb(color_int: int) -> tuple:
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def _safe_font(font_name: str) -> str:
    """回傳 fitz 可辨識的字型名稱，fallback 到 helv"""
    safe = {"helv", "Helvetica", "tiro", "TiRo", "cjk", "cour", "Courier",
            "times", "Times-Roman", "symb", "zadb"}
    if font_name in safe:
        return font_name
    return "helv"
