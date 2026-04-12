# ~/Desktop/acropdf/core/compare_engine.py
import fitz
import difflib
from dataclasses import dataclass, field

@dataclass
class PageDiff:
    page_num: int
    visual_rects: list[fitz.Rect] = field(default_factory=list)
    text_added: list[str] = field(default_factory=list)
    text_removed: list[str] = field(default_factory=list)

class CompareEngine:
    def compare(self, doc_a, doc_b, zoom: float = 1.0,
                text: bool = True, visual: bool = True) -> dict:
        left, close_left = self._open_if_needed(doc_a)
        right, close_right = self._open_if_needed(doc_b)
        try:
            results = []
            count = min(left.page_count, right.page_count)
            for i in range(count):
                diff = self._compare_page(left[i], right[i], zoom, text=text, visual=visual)
                diff.page_num = i
                results.append(diff)

            extra_a = max(left.page_count - right.page_count, 0)
            extra_b = max(right.page_count - left.page_count, 0)
            pages_with_diff = sum(
                1 for diff in results
                if diff.visual_rects or diff.text_added or diff.text_removed
            ) + extra_a + extra_b
            return {
                "page_diffs": results,
                "pages_compared": count,
                "pages_with_diff": pages_with_diff,
                "extra_pages_in_a": extra_a,
                "extra_pages_in_b": extra_b,
            }
        finally:
            if close_left:
                left.close()
            if close_right:
                right.close()

    def _compare_page(self, page_a: fitz.Page, page_b: fitz.Page,
                      zoom: float, text: bool = True, visual: bool = True) -> PageDiff:
        diff = PageDiff(page_num=0)

        # 視覺差異（像素 XOR）
        if visual:
            mat = fitz.Matrix(zoom, zoom)
            pix_a = page_a.get_pixmap(matrix=mat, alpha=False)
            pix_b = page_b.get_pixmap(matrix=mat, alpha=False)
            if pix_a.size == pix_b.size:
                data_a = pix_a.samples
                data_b = pix_b.samples
                threshold = 10
                stride = pix_a.stride
                w, h = pix_a.width, pix_a.height
                diff_pixels = []
                for y in range(h):
                    for x in range(w):
                        off = y * stride + x * 3
                        if (abs(data_a[off] - data_b[off]) > threshold or
                            abs(data_a[off+1] - data_b[off+1]) > threshold or
                            abs(data_a[off+2] - data_b[off+2]) > threshold):
                            diff_pixels.append((x / zoom, y / zoom))
                if diff_pixels:
                    xs = [p[0] for p in diff_pixels]
                    ys = [p[1] for p in diff_pixels]
                    diff.visual_rects.append(fitz.Rect(
                        min(xs) - 2, min(ys) - 2,
                        max(xs) + 2, max(ys) + 2
                    ))

        # 文字差異
        if text:
            text_a = page_a.get_text().splitlines()
            text_b = page_b.get_text().splitlines()
            for line in difflib.unified_diff(text_a, text_b, lineterm=""):
                if line.startswith("+") and not line.startswith("+++"):
                    diff.text_added.append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
                    diff.text_removed.append(line[1:])

        return diff

    @staticmethod
    def _open_if_needed(doc_or_path):
        if isinstance(doc_or_path, fitz.Document):
            return doc_or_path, False
        return fitz.open(doc_or_path), True
