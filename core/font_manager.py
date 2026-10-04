# ~/Desktop/acropdf/core/font_manager.py
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

import fitz


@dataclass
class FontInfo:
    name: str
    type: str       # "Type1" | "TrueType" | "CIDFont"
    embedded: bool
    subset: bool
    pages: list[int] = field(default_factory=list)
    glyph_count: int = 0
    xref: int = 0


class FontManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def list_fonts(self) -> list[FontInfo]:
        """列出所有字型及其詳細資訊"""
        doc = self._fitz
        if doc is None:
            return []
        seen: dict[str, FontInfo] = {}
        for i in range(doc.page_count):
            page = doc[i]
            for f in page.get_fonts(full=True):
                xref = f[0]
                ftype = f[2] or "Type1"
                name = f[3] or f[4] or f"font_{xref}"
                try:
                    embedded = xref > 0 and bool(doc.extract_font(xref)[3])
                except Exception:
                    embedded = False
                subset = "+" in name
                if name not in seen:
                    seen[name] = FontInfo(
                        name=name,
                        type=ftype,
                        embedded=embedded,
                        subset=subset,
                        pages=[],
                        xref=xref,
                    )
                if i not in seen[name].pages:
                    seen[name].pages.append(i)
        return list(seen.values())

    def embed_font(self, font_name: str, font_path: str):
        """嵌入外部字型檔案到 PDF（替換非嵌入字型）"""
        import math
        import uuid
        doc = self._fitz
        if doc is None:
            raise ValueError("尚未載入文件。")
        font = fitz.Font(fontfile=font_path)
        normalize = lambda name: name.split("+")[-1].replace(" ", "").lower()
        edits = []
        for page in doc:
            matches = []
            all_spans = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    angle = round(math.degrees(math.atan2(-line["dir"][1], line["dir"][0]))) % 360
                    for span in line["spans"]:
                        all_spans.append(span)
                        if normalize(span["font"]) != normalize(font_name):
                            continue
                        if angle not in (0, 90, 180, 270):
                            raise ValueError("斜向文字需先在文字編輯工具調整；原文件保留。")
                        missing = [char for char in span["text"] if not char.isspace() and not font.has_glyph(ord(char))]
                        if missing:
                            raise ValueError("此字型缺少文件所需字元：" + "".join(dict.fromkeys(missing))[:30])
                        matches.append((span, angle))
            if matches:
                selected = {id(span) for span, _ in matches}
                for span, _ in matches:
                    if any(id(other) not in selected and fitz.Rect(other['bbox']).intersects(fitz.Rect(span['bbox'])) for other in all_spans):
                        raise ValueError('所選字型與其他文字重疊，請先調整版面，避免移除相鄰文字。')
                if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in page.annots() or ()):
                    raise ValueError("此頁有待套用的塗黑標記，請先處理再替換字型。")
                edits.append((page.number, matches))
        if not edits:
            raise ValueError("找不到使用此字型的文字。")
        alias = "acro_font_" + uuid.uuid4().hex[:8]
        with self._doc.edit_transaction("替換並嵌入字型"):
            for page_num, matches in edits:
                page = doc[page_num]
                for span, _ in matches:
                    page.add_redact_annot(fitz.Rect(span["bbox"]), fill=False)
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
                page.insert_font(fontname=alias, fontfile=font_path)
                for span, angle in matches:
                    rect = fitz.Rect(span["bbox"])
                    extent = rect.width if angle in (0, 180) else rect.height
                    length = font.text_length(span["text"], fontsize=span["size"])
                    size = min(span["size"], span["size"] * extent / length) if length else span["size"]
                    color = tuple(((span["color"] >> shift) & 255) / 255 for shift in (16, 8, 0))
                    page.insert_text(span["origin"], span["text"], fontsize=size, fontname=alias, color=color, rotate=angle)
                    # Preserve exact Unicode when multiple code points share a glyph,
                    # such as ordinary space and NBSP in an embedded font's cmap.
                    stream = page.get_contents()[-1]
                    payload = doc.xref_stream(stream)
                    actual = fitz.get_pdf_str(span['text']).encode('ascii')
                    doc.update_stream(stream, b'/Span << /ActualText ' + actual + b' >> BDC\n' + payload + b'\nEMC')
                page.clean_contents()

    def subset_font(self, font_name: str):
        """子集化嵌入字型（僅保留使用到的字符）"""
        if not any(font.name == font_name for font in self.list_fonts()):
            raise ValueError("找不到指定字型。")
        with self._doc.edit_transaction("文件字型子集化"):
            self._fitz.subset_fonts()

    def replace_font(self, old_name: str, new_path: str):
        """替換字型"""
        self.embed_font(old_name, new_path)

    def extract_font(self, font_name: str, output_path: str) -> bool:
        """提取嵌入字型到檔案"""
        doc = self._fitz
        if doc is None:
            return False
        for i in range(doc.page_count):
            page = doc[i]
            for f in page.get_fonts(full=True):
                xref = f[0]
                name = f[3] or f[4] or ""
                if font_name in name and xref > 0:
                    try:
                        data = doc.extract_font(xref)
                        if data and data[3]:  # data[3] = font buffer
                            ext = data[1] or "ttf"
                            out = output_path if output_path.endswith(f".{ext}") \
                                else f"{output_path}.{ext}"
                            with open(out, "wb") as fp:
                                fp.write(data[3])
                            return True
                    except Exception as e:
                        print(f"[FontManager] extract_font error: {e}")
        return False

    @staticmethod
    def find_system_fonts() -> list[str]:
        """探索系統字型"""
        paths = []
        sys = platform.system()
        if sys == "Darwin":
            dirs = [
                "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"),
                "/System/Library/Fonts",
                "/System/Library/AssetsV2/com_apple_MobileAsset_Font6",
            ]
        elif sys == "Windows":
            dirs = [
                os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
            ]
        else:
            dirs = ["/usr/share/fonts", "/usr/local/share/fonts",
                    os.path.expanduser("~/.fonts")]

        for d in dirs:
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith((".ttf", ".otf", ".ttc")):
                            paths.append(os.path.join(root, f))
        return paths
