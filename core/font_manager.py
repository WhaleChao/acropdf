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
                embedded = xref > 0
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
        doc = self._fitz
        if doc is None:
            return
        self._doc.begin_op("嵌入字型")
        # 使用 pymupdf 字型機制插入
        try:
            with open(font_path, "rb") as fp:
                font_data = fp.read()
            doc.add_font(font_name, font_path)
        except Exception as e:
            print(f"[FontManager] embed_font error: {e}")
        self._doc.end_op()
        self._doc._mark_modified()

    def subset_font(self, font_name: str):
        """子集化嵌入字型（僅保留使用到的字符）"""
        try:
            import fontTools.subset as ft_subset
        except ImportError:
            raise RuntimeError("請先安裝 fonttools")
        # 實際子集化需要提取 → subset → 重新嵌入，這裡做佔位實作
        self._doc._mark_modified()

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
