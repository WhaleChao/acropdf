# ~/Desktop/acropdf/core/accessibility_engine.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import fitz


@dataclass
class StructNode:
    type: str           # "P" | "H1"-"H6" | "Figure" | "Table" | "TR" | "TD"
    children: list
    page: int
    rect: Optional[tuple]
    alt_text: Optional[str]
    xref: int


class AccessibilityEngine:

    def get_structure_tree(self, doc: fitz.Document) -> Optional[StructNode]:
        """解析結構樹（若文件有 Tagged PDF）"""
        try:
            # 嘗試讀取結構樹根節點
            catalog = doc.pdf_catalog()
            if "/StructTreeRoot" not in doc.xref_get_key(-1, "StructTreeRoot")[1]:
                return None
            return StructNode(
                type="Document",
                children=[],
                page=0,
                rect=None,
                alt_text=None,
                xref=0,
            )
        except Exception:
            return None

    def set_alt_text(self, doc: fitz.Document, xref: int, alt: str):
        """設定圖片替代文字"""
        try:
            doc.xref_set_key(xref, "Alt", fitz.get_pdf_str(alt))
        except Exception as e:
            print(f"[Accessibility] set_alt_text error: {e}")

    def set_heading_level(self, doc: fitz.Document, xref: int, level: int):
        """變更標題層級 (P → H1~H6)"""
        tag = f"H{level}" if 1 <= level <= 6 else "P"
        try:
            doc.xref_set_key(xref, "S", f"/{tag}")
        except Exception as e:
            print(f"[Accessibility] set_heading_level error: {e}")

    def add_table_structure(self, doc: fitz.Document, page_num: int,
                            table_rect: fitz.Rect, rows: int, cols: int):
        """建立 Table/TR/TD 結構標記"""
        # 使用 PDF 低階操作插入結構元素
        # 實際完整實作需要 pikepdf 操作結構樹
        pass

    def validate_pdfua(self, doc: fitz.Document) -> list[dict]:
        """PDF/UA 合規驗證"""
        issues = []
        # 1. 文件標題
        metadata = doc.metadata
        if not metadata.get("title"):
            issues.append({
                "code": "UA-001",
                "message": "文件缺少標題（文件標題）",
                "severity": "error",
            })
        # 2. 語言設定
        try:
            lang = doc.xref_get_key(-1, "Lang")
            if not lang or lang[1] in ("", "null"):
                issues.append({
                    "code": "UA-002",
                    "message": "文件未設定語言（Lang）",
                    "severity": "error",
                })
        except Exception:
            pass
        # 3. 圖片 alt text
        for i in range(doc.page_count):
            page = doc[i]
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    alt = doc.xref_get_key(xref, "Alt")
                    if not alt or alt[1] in ("", "null"):
                        issues.append({
                            "code": "UA-003",
                            "message": f"第 {i+1} 頁圖片 (xref={xref}) 缺少替代文字",
                            "severity": "warning",
                            "page": i,
                        })
                except Exception:
                    pass
        return issues

    def auto_detect_headings(self, doc: fitz.Document) -> list[dict]:
        """依字型大小推論標題層級"""
        headings = []
        for i in range(doc.page_count):
            page = doc[i]
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 11)
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        if size >= 24:
                            level = 1
                        elif size >= 20:
                            level = 2
                        elif size >= 16:
                            level = 3
                        elif size >= 14:
                            level = 4
                        else:
                            continue
                        headings.append({
                            "page": i,
                            "level": level,
                            "text": text,
                            "font_size": size,
                        })
        return headings

    def reorder_structure(self, doc: fitz.Document, new_order: list[int]):
        """重新排列閱讀順序（頁面層級）"""
        # 實際結構樹重排需要 pikepdf 操作 StructTreeRoot
        pass
