# ~/Desktop/acropdf/core/redaction_engine.py
import re
import fitz


class RedactionEngine:
    PATTERNS = {
        "身分證字號": r"[A-Z][12]\d{8}",
        "手機號碼": r"09\d{2}[- ]?\d{3}[- ]?\d{3}",
        "電子郵件": r"[\w.\-+]+@[\w.\-]+\.\w+",
        "信用卡號": r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}",
    }

    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _safe_fitz(self) -> fitz.Document:
        d = self._fitz
        if d is None:
            raise RuntimeError("尚未載入文件")
        return d

    def search_and_mark(self, text: str) -> list[dict]:
        """搜尋所有頁面中的文字並標記塗黑，回傳 [{page, rect, text}]"""
        doc = self._safe_fitz()
        if not text.strip():
            return []
        self._doc.begin_op("搜尋塗黑標記")
        results = []
        for i in range(doc.page_count):
            page = doc[i]
            hits = page.search_for(text)
            for rect in hits:
                page.add_redact_annot(rect)
                results.append({"page": i, "rect": rect, "text": text})
        if results:
            self._doc._mark_modified()
        return results

    def pattern_mark(self, pattern: str) -> list[dict]:
        """用正規表達式搜尋並標記塗黑"""
        doc = self._safe_fitz()
        results = []
        compiled = re.compile(pattern)
        self._doc.begin_op("樣式塗黑標記")
        seen = set()
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text()
            for m in compiled.finditer(text):
                matched = m.group()
                hits = page.search_for(matched)
                for rect in hits:
                    key = (i, tuple(rect))
                    if key in seen:
                        continue
                    seen.add(key)
                    page.add_redact_annot(rect)
                    results.append({"page": i, "rect": rect, "text": matched})
        if results:
            self._doc._mark_modified()
        return results

    def get_redact_count(self) -> int:
        """計算目前的塗黑標記數量"""
        doc = self._safe_fitz()
        count = 0
        for i in range(doc.page_count):
            page = doc[i]
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                    count += 1
        return count

    def apply_all(self, page_indices=None) -> int:
        """套用所有塗黑標記（不可逆），回傳套用數量"""
        doc = self._safe_fitz()
        total = 0
        indices = range(doc.page_count) if page_indices is None else sorted(set(page_indices))
        for i in indices:
            if not 0 <= i < doc.page_count:
                continue
            page = doc[i]
            count_before = sum(
                1 for a in page.annots() if a.type[0] == fitz.PDF_ANNOT_REDACT
            )
            if count_before:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                      graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
                total += count_before
        self._doc.end_op()
        if total:
            self._doc._undo_stack.clear()
            self._doc._redo_stack.clear()
            self._doc._sensitive_content_removed = True
            self._doc._mark_modified()
            self._doc.page_count_changed.emit(doc.page_count)
        return total
