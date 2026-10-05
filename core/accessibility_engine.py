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
    MAX_TABLE_CELLS = 10000

    @staticmethod
    def _structure_children(doc, parent_xref):
        import re
        kind, value = doc.xref_get_key(parent_xref, 'K')
        if kind not in ('array', 'xref'):
            raise ValueError('此結構沒有可重排的子標記。')
        children = [int(n) for n in re.findall(r'(\d+)\s+0\s+R', value)]
        residue = re.sub(r'\d+\s+0\s+R', '', value).strip('[] \t\r\n')
        if residue or any(doc.xref_get_key(n, 'S')[0] != 'name' or
                          doc.xref_get_key(n, 'Type')[1] not in ('null', '/StructElem')
                          for n in children):
            raise ValueError('此結構混合了內容標記，不能直接重排；原有內容保持不變。')
        return children

    def get_structure_tree(self, doc: fitz.Document) -> Optional[StructNode]:
        import re
        kind, value = doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")
        if kind != "xref": return None
        pages = {page.xref: page.number for page in doc}
        visited = set()
        def parse(xref, page=0):
            if xref in visited: return None
            visited.add(xref)
            if doc.xref_get_key(xref, 'Type')[1] != '/StructTreeRoot' and doc.xref_get_key(xref, 'S')[0] != 'name':
                return None
            tag = doc.xref_get_key(xref, "S")[1].lstrip("/")
            pg = doc.xref_get_key(xref, "Pg")
            if pg[0] == "xref": page = pages.get(int(pg[1].split()[0]), page)
            bbox = doc.xref_get_key(xref, "AcroBBox")
            rect = tuple(float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', bbox[1])) if bbox[0] == "array" else None
            alt = doc.xref_get_key(xref, "Alt")
            children = []
            kind, kids = doc.xref_get_key(xref, "K")
            if kind in ("xref", "array"):
                for number in re.findall(r'(\d+)\s+0\s+R', kids):
                    child = parse(int(number), page)
                    if child: children.append(child)
            return StructNode(tag if tag != "null" else "Document", children, page, rect, alt[1] if alt[0] == "string" else None, xref)
        return parse(int(value.split()[0]))

    def auto_tag(self, document, title, language="zh-TW", image_alts=None):
        from core.content_tags import tag_document
        with document.edit_transaction("建立內容與閱讀標記"):
            return tag_document(document.fitz_doc, title, language, image_alts, document._password)

    def set_alt_text(self, doc: fitz.Document, xref: int, alt: str):
        """設定圖片替代文字"""
        try:
            doc.xref_set_key(xref, "Alt", fitz.get_pdf_str(alt))
        except Exception as e:
            raise ValueError(f"無法修改替代文字：{e}") from e

    def set_heading_level(self, doc: fitz.Document, xref: int, level: int):
        """變更標題層級 (P → H1~H6)"""
        tag = f"H{level}" if 1 <= level <= 6 else "P"
        try:
            doc.xref_set_key(xref, "S", f"/{tag}")
        except Exception as e:
            raise ValueError(f"無法修改標題層級：{e}") from e

    def set_table_header(self, doc, xref, scope='Column'):
        if scope not in ('Column', 'Row', 'Both'): raise ValueError('表頭範圍無效。')
        if doc.xref_get_key(xref, 'S')[1] not in ('/TD', '/TH'): raise ValueError('請選擇表格儲存格。')
        doc.xref_set_key(xref, 'S', '/TH')
        doc.xref_set_key(xref, 'A', f'<< /O /Table /Scope /{scope} >>')

    def reorder_children(self, doc, parent_xref, new_order):
        children = self._structure_children(doc, parent_xref)
        if sorted(new_order) != list(range(len(children))): raise ValueError('請提供完整且不重複的標記順序。')
        doc.xref_set_key(parent_xref, 'K', '['+' '.join(f'{children[i]} 0 R' for i in new_order)+']')

    def add_table_structure(self, doc: fitz.Document, page_num: int,
                            table_rect: fitz.Rect, rows: int, cols: int, selected_xrefs=None):
        """建立 Table/TR/TD 結構標記"""
        if (not isinstance(rows, int) or not isinstance(cols, int)
                or not 0 <= page_num < len(doc) or rows < 1 or cols < 1
                or table_rect.is_empty or table_rect.is_infinite
                or not doc[page_num].rect.contains(table_rect)):
            raise ValueError("表格範圍、頁碼及列欄數必須有效。")
        if rows * cols > self.MAX_TABLE_CELLS:
            raise ValueError(f"表格最多可建立 {self.MAX_TABLE_CELLS:,} 個儲存格，請分段處理。")
        tree = self.get_structure_tree(doc)
        if tree is None: raise ValueError("請先建立內容標記。")
        nodes = []
        def visit(node):
            if node.type == "P" and node.page == page_num and node.rect and table_rect.contains(fitz.Rect(node.rect)):
                nodes.append(node)
            for child in node.children: visit(child)
        visit(tree)
        if selected_xrefs is not None:
            chosen = set(selected_xrefs)
            nodes = [node for node in nodes if node.xref in chosen]
            if {node.xref for node in nodes} != chosen:
                raise ValueError('選取項目須為表格範圍內的同頁段落標記。')
        if not nodes: raise ValueError("表格範圍內沒有已關聯的文字標記。")
        from core.content_tags import _new, _ref
        parents = {doc.xref_get_key(node.xref, "P")[1] for node in nodes}
        if len(parents) != 1: raise ValueError("表格內容跨不同結構區段，請先調整閱讀區段。")
        parent = int(parents.pop().split()[0]); page_xref = doc[page_num].xref
        old = self._structure_children(doc, parent)
        selected = {node.xref for node in nodes}
        positions = [i for i, xref in enumerate(old) if xref in selected]
        if len(positions) != len(nodes) or positions != list(range(positions[0], positions[-1]+1)):
            raise ValueError('表格段落在閱讀順序中必須相鄰，請先調整順序，避免移動其他內容。')
        cells = {(r,c): [] for r in range(rows) for c in range(cols)}
        for node in nodes:
            rect = fitz.Rect(node.rect)
            r = min(rows-1, int(((rect.y0+rect.y1)/2-table_rect.y0)/table_rect.height*rows))
            c = min(cols-1, int(((rect.x0+rect.x1)/2-table_rect.x0)/table_rect.width*cols))
            cells[r,c].append(node.xref)
        table = _new(doc, f"<< /Type /StructElem /S /Table /P {_ref(parent)} /Pg {_ref(page_xref)} >>")
        row_nodes = []
        for r in range(rows):
            tr = _new(doc, f"<< /Type /StructElem /S /TR /P {_ref(table)} >>"); row_nodes.append(tr)
            cell_nodes = []
            for c in range(cols):
                cell = _new(doc, f"<< /Type /StructElem /S /TD /P {_ref(tr)} /K [" + " ".join(_ref(n) for n in cells[r,c]) + "] >>")
                cell_nodes.append(cell)
                for n in cells[r,c]: doc.xref_set_key(n,"P",_ref(cell))
            doc.xref_set_key(tr,"K","["+" ".join(_ref(n) for n in cell_nodes)+"]")
        doc.xref_set_key(table,"K","["+" ".join(_ref(n) for n in row_nodes)+"]")
        result = []; inserted = False
        for xref in old:
            if xref in selected:
                if not inserted: result.append(table); inserted=True
            else: result.append(xref)
        doc.xref_set_key(parent,"K","["+" ".join(_ref(n) for n in result)+"]")
        return table

    def validate_pdfua(self, doc: fitz.Document) -> list[dict]:
        """Basic accessibility checks only; not a PDF/UA conformance validator."""
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
            lang = doc.xref_get_key(doc.pdf_catalog(), "Lang")
            if not lang or lang[1] in ("", "null"):
                issues.append({
                    "code": "UA-002",
                    "message": "文件未設定語言（Lang）",
                    "severity": "error",
                })
        except Exception:
            pass
        if self.get_structure_tree(doc) is None:
            issues.append({"code": "UA-004", "message": "文件缺少標記結構樹，不能視為 PDF/UA 合規。", "severity": "error"})
        issues.append({"code": "UA-INCOMPLETE", "message": "此為基礎檢查；完整 PDF/UA 驗證仍需外部驗證器與人工閱讀順序審查。", "severity": "warning"})
        tree = self.get_structure_tree(doc)
        def inspect(node):
            if node.type == "Figure" and not node.alt_text:
                issues.append({"code":"UA-003", "message":f"第 {node.page+1} 頁圖片標記缺少替代文字", "severity":"error", "page":node.page})
            for child in node.children: inspect(child)
        if tree: inspect(tree)
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
        tree = self.get_structure_tree(doc)
        if tree is None: raise ValueError("文件沒有結構樹。")
        container = tree.children[0] if len(tree.children) == 1 and tree.children[0].type == "Document" else tree
        children = self._structure_children(doc, container.xref)
        if sorted(new_order) != list(range(len(children))):
            raise ValueError("閱讀順序須完整包含所有區段，且不能重複。")
        doc.xref_set_key(container.xref, "K", "[" + " ".join(f"{children[i]} 0 R" for i in new_order) + "]")
